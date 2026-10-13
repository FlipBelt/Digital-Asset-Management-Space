"""Map existing group directory names without moving directory people or departments."""

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import AppSetting, AuditLog, Department, DingTalkPersonProfile, LegalEntity, Person
from app.services.dingtalk import resolve_dingtalk_organization
from app.services.dingtalk_company import stored_company_affiliation
from app.services.service_catalog import digest


@dataclass
class CompanySource:
    id: UUID
    name: str
    detail: str


def directory_structure(db):
    binding = resolve_dingtalk_organization(db)
    if binding.status != "bound" or binding.entity is None:
        return {}, []
    root = binding.entity
    setting = db.scalar(select(AppSetting).where(AppSetting.key == "dingtalk_directory_snapshot"))
    snapshot = setting.value if setting and isinstance(setting.value, dict) else {}
    valid_snapshot = snapshot.get("legal_entity_id") == str(root.id)
    codes = set(snapshot.get("department_codes") or []) if valid_snapshot else set()
    current_ids = set(snapshot.get("current_person_ids") or []) if valid_snapshot else set()
    departments = list(db.scalars(select(Department).where(
        Department.legal_entity_id == root.id, Department.archived_at.is_(None), Department.status == "active",
    )))
    departments = [row for row in departments if not codes or not row.code.startswith("DT-") or row.code in codes]
    names = {root.name: "钉钉组织绑定主体"}
    for profile, person in db.execute(select(DingTalkPersonProfile, Person)
            .join(Person, Person.id == DingTalkPersonProfile.person_id)
            .where(Person.legal_entity_id == root.id, Person.archived_at.is_(None), Person.employment_status == "active")):
        if current_ids and str(person.id) not in current_ids:
            continue
        if not current_ids and (profile.profile_data or {}).get("directory_status") == "historical":
            continue
        affiliation = stored_company_affiliation(profile.profile_data)
        if affiliation["status"] == "available":
            names[affiliation["name"]] = "钉钉主体（社保公司）字段"
    for row in departments:
        if row.name.endswith(("公司", "合伙企业", "个体工商户")):
            names.setdefault(row.name, "当前通讯录公司节点")
    registered = set(db.scalars(select(LegalEntity.name).where(LegalEntity.archived_at.is_(None))))
    departments = [row for row in departments if row.name not in names and row.name not in registered]
    return names, departments


def group_company_targets(db):
    entities = list(db.scalars(select(LegalEntity).where(
        LegalEntity.archived_at.is_(None), LegalEntity.status == "active",
    )))
    names, _ = directory_structure(db)
    result = [CompanySource(row.id, row.name, "已登记公司主体") for row in entities]
    registered = {row.name for row in entities}
    result.extend(CompanySource(uuid5(NAMESPACE_URL, "digital-center/company/" + name), name,
        source + " · 尚未映射，保存时登记主体") for name, source in names.items() if name not in registered)
    return result


def department_compatible(db, department, company_id):
    if company_id is None or department.legal_entity_id == company_id:
        return True
    names, departments = directory_structure(db)
    company = db.get(LegalEntity, company_id)
    return bool(company and not company.archived_at and company.status == "active" and
        company.name in names and department.id in {row.id for row in departments})


def department_path(department, departments):
    by_id = {row.id: row for row in departments}
    path, seen, current = [], set(), department
    while current and current.id not in seen:
        seen.add(current.id)
        path.append(current.name)
        current = by_id.get(current.parent_id)
    return " / ".join(reversed(path))


def register_source_company(db, access, target):
    if not access.is_global_manager:
        raise HTTPException(403, "集团公司映射需要资产管理员权限")
    lock_company_mapping(db)
    existing = db.get(LegalEntity, target.id)
    if existing:
        return existing
    names, _ = directory_structure(db)
    if target.name not in names:
        raise HTTPException(422, "公司来源已经变化，请重新读取集团架构")
    matches = list(db.scalars(select(LegalEntity).where(LegalEntity.name == target.name)))
    if len(matches) > 1 or (matches and (matches[0].archived_at or matches[0].status != "active")):
        raise HTTPException(409, "同名公司主体有历史或重复档案，请先核实映射")
    if matches:
        return matches[0]
    item = LegalEntity(id=target.id, code="ORG-" + str(target.id).replace("-", "")[:20], name=target.name)
    db.add(item)
    db.flush()
    db.add(AuditLog(actor_user_id=access.user.id, action="organization.company.map", object_type="legal_entity",
        object_id=item.id, after_data={"name": item.name, "source": names[item.name], "statutory_verified": False}))
    return item


def lock_company_mapping(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(select(func.pg_advisory_xact_lock(
            int(digest("digital-center/company-mapping")[:15], 16))))


def mapping_snapshot(db):
    targets = group_company_targets(db)
    return {"fingerprint": digest(sorted((str(row.id), row.name, row.detail) for row in targets)),
        "companies": [{"id": str(row.id), "name": row.name, "source": row.detail,
            "mapped": db.get(LegalEntity, row.id) is not None} for row in targets]}
