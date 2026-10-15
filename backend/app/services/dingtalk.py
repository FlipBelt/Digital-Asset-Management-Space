from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    AppSetting,
    AuditLog,
    Department,
    DepartmentMembership,
    DingTalkDepartmentLink,
    DingTalkPersonProfile,
    LegalEntity,
    Person,
)
from app.services.dingtalk_company import (
    company_affiliation_from_detail,
    unavailable_company_affiliation,
)

_OAPI_BASE = "https://oapi.dingtalk.com"


@dataclass
class DingTalkOrganizationBinding:
    status: Literal["bound", "unbound", "invalid", "ambiguous"]
    entity: LegalEntity | None = None
    message: str | None = None


def resolve_dingtalk_organization(db: Session) -> DingTalkOrganizationBinding:
    """Use the configured organization, corroborated by existing directory links."""
    setting = db.scalar(select(AppSetting).where(AppSetting.key == "organization_bootstrap"))
    config = setting.value if setting and isinstance(setting.value, dict) else {}
    code = config.get("legal_entity_code")
    name = config.get("legal_entity_name")
    code = code.strip() if isinstance(code, str) else ""
    name = name.strip() if isinstance(name, str) else ""
    linked_ids = set(
        db.scalars(
            select(Department.legal_entity_id)
            .join(DingTalkDepartmentLink, DingTalkDepartmentLink.department_id == Department.id)
            .where(Department.archived_at.is_(None))
            .distinct()
        )
    )
    entity = None
    if code:
        entity = db.scalar(select(LegalEntity).where(LegalEntity.code == code))
    elif name:
        matches = list(db.scalars(select(LegalEntity).where(LegalEntity.name == name)))
        if len(matches) > 1:
            return DingTalkOrganizationBinding(
                "ambiguous", message="组织名称对应多个主体，请核实组织代码。"
            )
        entity = matches[0] if matches else None
    elif len(linked_ids) == 1:
        entity = db.get(LegalEntity, next(iter(linked_ids)))
    elif linked_ids:
        return DingTalkOrganizationBinding(
            "ambiguous", message="钉钉部门关联多个主体，请先核实组织绑定。"
        )
    else:
        return DingTalkOrganizationBinding(
            "unbound", message="尚未绑定钉钉组织，请先配置组织主体。"
        )

    if entity is None or entity.archived_at is not None or entity.status != "active":
        return DingTalkOrganizationBinding(
            "invalid", message="绑定的组织主体不存在或已停用，请先核实配置。"
        )
    if linked_ids - {entity.id}:
        return DingTalkOrganizationBinding(
            "ambiguous", message="钉钉部门与配置的组织主体不一致，请先核实绑定。"
        )
    return DingTalkOrganizationBinding("bound", entity=entity)


@dataclass
class SyncResult:
    departments_created: int = 0
    departments_updated: int = 0
    people_created: int = 0
    people_updated: int = 0
    memberships_synced: int = 0
    people_current: int = 0
    people_historical: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "departments_created": self.departments_created,
            "departments_updated": self.departments_updated,
            "people_created": self.people_created,
            "people_updated": self.people_updated,
            "memberships_synced": self.memberships_synced,
            "people_current": self.people_current,
            "people_historical": self.people_historical,
        }


class DingTalkClient:
    """Minimal server-side client for approved internal-app directory APIs."""

    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=20.0)

    def validate_configuration(self, *, require_corp_id: bool = False) -> None:
        if not self.settings.dingtalk_enabled:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="DingTalk connector is disabled"
            )
        if missing := self.settings.dingtalk_missing_settings(require_corp_id=require_corp_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "DingTalk connector is not configured", "missing": missing},
            )

    def _request(
        self, method: str, path: str, *, access_token: str | None = None, **kwargs: Any
    ) -> dict:
        params = dict(kwargs.pop("params", {}))
        if access_token:
            params["access_token"] = access_token
        try:
            response = self.client.request(method, f"{_OAPI_BASE}{path}", params=params, **kwargs)
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(status_code=502, detail="DingTalk request failed") from None
        if not isinstance(data, dict):
            raise HTTPException(status_code=502, detail="invalid DingTalk response")
        if response.is_error or data.get("errcode", 0) not in (0, "0"):
            raise HTTPException(
                status_code=502,
                detail={"message": "DingTalk API request failed", "code": data.get("errcode")},
            )
        return data

    def access_token(self) -> str:
        self.validate_configuration()
        data = self._request(
            "GET",
            "/gettoken",
            params={
                "appkey": self.settings.dingtalk_client_id,
                "appsecret": self.settings.dingtalk_client_secret,
            },
        )
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise HTTPException(status_code=502, detail="DingTalk did not return an access token")
        return token

    def departments(self, access_token: str) -> list[dict]:
        # ``listsub`` returns one hierarchy level.  Walk the complete tree so
        # the master data is not limited to the company's top-level units.
        pending = ["1"]
        visited = {"1"}
        departments: list[dict] = []
        while pending:
            parent_id = pending.pop(0)
            data = self._request(
                "POST",
                "/topapi/v2/department/listsub",
                access_token=access_token,
                json={"dept_id": int(parent_id), "language": "zh_CN"},
            )
            # DingTalk's legacy endpoint has returned both shapes in the wild:
            # {"result": [...]} and {"result": {"list": [...]}}.
            result = data.get("result")
            rows = (
                result
                if isinstance(result, list)
                else result.get("list")
                if isinstance(result, dict)
                else None
            )
            if not isinstance(rows, list):
                raise HTTPException(status_code=502, detail="invalid DingTalk department page")
            for row in rows:
                if not isinstance(row, dict) or not row.get("dept_id") or not row.get("name"):
                    raise HTTPException(status_code=502, detail="invalid DingTalk department row")
                department_id = str(row["dept_id"])
                if not department_id or department_id == "-7" or department_id in visited:
                    continue
                visited.add(department_id)
                departments.append(row)
                pending.append(department_id)
        return departments

    def users(self, access_token: str, department_id: str) -> Iterable[dict]:
        cursor = 0
        visited: set[int] = set()
        while True:
            if cursor in visited or len(visited) >= 10000:
                raise HTTPException(
                    status_code=502, detail="DingTalk directory cursor did not progress"
                )
            visited.add(cursor)
            data = self._request(
                "POST",
                "/topapi/v2/user/list",
                access_token=access_token,
                json={
                    "dept_id": int(department_id),
                    "cursor": cursor,
                    "size": 100,
                    "language": "zh_CN",
                },
            )
            result = data.get("result")
            rows = result.get("list") if isinstance(result, dict) else None
            if not isinstance(rows, list) or any(
                not isinstance(row, dict) or not row.get("userid") for row in rows
            ):
                raise HTTPException(status_code=502, detail="invalid DingTalk directory page")
            more = result.get("has_more")
            if more not in (True, False, 0, 1, "true", "false", "True", "False"):
                raise HTTPException(status_code=502, detail="invalid DingTalk directory pagination")
            yield from rows
            if more in (False, 0, "false", "False"):
                return
            try:
                next_cursor = int(result["next_cursor"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(
                    status_code=502, detail="invalid DingTalk directory cursor"
                ) from None
            if next_cursor <= cursor:
                raise HTTPException(
                    status_code=502, detail="DingTalk directory cursor did not progress"
                )
            cursor = next_cursor

    def user_detail(self, access_token: str, user_id: str) -> dict:
        data = self._request(
            "POST",
            "/topapi/v2/user/get",
            access_token=access_token,
            json={"userid": user_id, "language": "zh_CN"},
        )
        result = data.get("result", {})
        if not isinstance(result, dict):
            raise HTTPException(status_code=502, detail="invalid DingTalk user detail response")
        return result

    def user_from_auth_code(self, auth_code: str) -> dict:
        token = self.access_token()
        data = self._request(
            "POST",
            "/topapi/v2/user/getuserinfo",
            access_token=token,
            json={"code": auth_code},
        )
        user_id = data.get("result", {}).get("userid")
        if not isinstance(user_id, str) or not user_id:
            raise HTTPException(status_code=401, detail="DingTalk identity was not returned")
        detail = self._request(
            "POST",
            "/topapi/v2/user/get",
            access_token=token,
            json={"userid": user_id, "language": "zh_CN"},
        )
        return detail.get("result", {})

    def _web_request(self, method: str, path: str, **kwargs: Any) -> dict:
        try:
            response = self.client.request(method, f"https://api.dingtalk.com{path}", **kwargs)
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(status_code=502, detail="DingTalk web request failed") from None
        if response.is_error or not isinstance(data, dict):
            raise HTTPException(status_code=502, detail="DingTalk web request failed")
        return data

    def user_from_web_auth_code(self, auth_code: str) -> dict:
        """Resolve web OAuth into a verified employee of the configured organization."""
        self.validate_configuration(require_corp_id=True)
        user_token_data = self._web_request(
            "POST",
            "/v1.0/oauth2/userAccessToken",
            json={
                "clientId": self.settings.dingtalk_client_id,
                "clientSecret": self.settings.dingtalk_client_secret,
                "code": auth_code,
                "grantType": "authorization_code",
            },
        )
        if user_token_data.get("corpId") != self.settings.dingtalk_corp_id:
            raise HTTPException(status_code=403, detail="DingTalk organization does not match")
        user_token = user_token_data.get("accessToken")
        if not isinstance(user_token, str) or not user_token:
            raise HTTPException(status_code=401, detail="DingTalk identity was not returned")
        personal = self._web_request(
            "GET",
            "/v1.0/contact/users/me",
            headers={"x-acs-dingtalk-access-token": user_token},
        )
        union_id = personal.get("unionId")
        if not isinstance(union_id, str) or not union_id or len(union_id) > 200:
            raise HTTPException(status_code=401, detail="DingTalk identity was not returned")
        organization_token = self.access_token()
        try:
            mapping = self._request(
                "POST",
                "/topapi/user/getbyunionid",
                access_token=organization_token,
                json={"unionid": union_id},
            )
        except HTTPException as exc:
            if isinstance(exc.detail, dict) and exc.detail.get("code") in (60121, "60121"):
                raise HTTPException(
                    status_code=403, detail="DingTalk employee was not found"
                ) from None
            raise
        mapped = mapping.get("result")
        user_id = mapped.get("userid") if isinstance(mapped, dict) else None
        if not isinstance(user_id, str) or not user_id:
            raise HTTPException(status_code=403, detail="DingTalk employee was not found")
        detail = self.user_detail(organization_token, user_id)
        if detail.get("userid") != user_id or detail.get("unionid") != union_id:
            raise HTTPException(status_code=403, detail="DingTalk employee identity does not match")
        # Use the corporate profile, never the personal nickname, for account mapping and roles.
        return detail

    def send_work_notification(self, user_ids: list[str], content: str) -> None:
        """Send a plain-text internal-app work notification to DingTalk users."""
        self.validate_configuration()
        if not self.settings.dingtalk_agent_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "DingTalk notification is not configured",
                    "missing": ["DINGTALK_AGENT_ID"],
                },
            )
        recipients = [item for item in user_ids if item]
        if not recipients:
            raise HTTPException(status_code=422, detail="没有可接收钉钉通知的人员")
        self._request(
            "POST",
            "/topapi/message/corpconversation/asyncsend_v2",
            access_token=self.access_token(),
            json={
                "agent_id": int(self.settings.dingtalk_agent_id),
                "userid_list": ",".join(recipients),
                "msg": {"msgtype": "text", "text": {"content": content[:20000]}},
            },
        )


class DingTalkDirectorySync:
    def __init__(self, db: Session, client: DingTalkClient) -> None:
        self.db = db
        self.client = client
        self._seen_user_ids: set[str] = set()

    def _require_entity(self, legal_entity_id: str) -> LegalEntity:
        entity = self.db.get(LegalEntity, legal_entity_id)
        if entity is None or entity.archived_at is not None:
            raise HTTPException(status_code=404, detail="legal entity not found")
        binding = resolve_dingtalk_organization(self.db)
        if binding.entity is None:
            raise HTTPException(status_code=409, detail=binding.message)
        if entity.id != binding.entity.id:
            raise HTTPException(status_code=409, detail="同步目标与绑定的钉钉组织主体不一致")
        return entity

    def refresh_company_affiliations(self, legal_entity_id: str) -> dict[str, int]:
        entity = self._require_entity(legal_entity_id)
        profiles = list(
            self.db.scalars(
                select(DingTalkPersonProfile)
                .join(Person, Person.id == DingTalkPersonProfile.person_id)
                .where(Person.legal_entity_id == entity.id, Person.archived_at.is_(None))
            )
        )
        token = self.client.access_token()
        directory = self.client.departments(token)
        directory_ids = [str(row["dept_id"]) for row in directory if row.get("dept_id") is not None]
        if not directory_ids:
            raise HTTPException(status_code=502, detail="钉钉组织目录为空，请核实通讯录可见范围")
        counts = dict.fromkeys(
            ("checked", "available", "missing", "invalid", "conflict", "unavailable"), 0
        )
        pending = []
        # Finish all reads before staging writes. Transient failures leave the old snapshot intact.
        for profile in profiles:
            try:
                detail = self.client.user_detail(token, profile.dingtalk_user_id)
            except HTTPException as exc:
                code = exc.detail.get("code") if isinstance(exc.detail, dict) else None
                if code not in (60121, "60121"):
                    raise
                affiliation = unavailable_company_affiliation()
            else:
                if detail.get("userid") != profile.dingtalk_user_id:
                    raise HTTPException(status_code=502, detail="钉钉成员详情与查询身份不一致")
                affiliation = company_affiliation_from_detail(detail)
            pending.append((profile, affiliation))
            counts["checked"] += 1
            counts[affiliation["status"]] += 1
        for profile, affiliation in pending:
            profile.profile_data = {
                **(profile.profile_data or {}),
                "company_affiliation": affiliation,
            }
        snapshot = self.db.scalar(
            select(AppSetting).where(AppSetting.key == "dingtalk_directory_snapshot")
        )
        if snapshot is None:
            snapshot = AppSetting(key="dingtalk_directory_snapshot", value={})
            self.db.add(snapshot)
        snapshot.value = {
            **(snapshot.value or {}),
            "legal_entity_id": str(entity.id),
            "department_codes": [f"DT-{value}" for value in directory_ids],
            "checked_at": pending[0][1]["checked_at"] if pending else None,
        }
        counts["directory_nodes_checked"] = len(directory_ids)
        self.db.add(
            AuditLog(
                actor_user_id=self.db.info.get("audit_actor_user_id"),
                action="organization.company_affiliations_refresh",
                object_type="legal_entity",
                object_id=entity.id,
                after_data=counts,
            )
        )
        self.db.commit()
        return counts

    def run(self, legal_entity_id: str) -> SyncResult:
        entity = self._require_entity(legal_entity_id)
        token = self.client.access_token()
        directory = self.client.departments(token)
        if not directory:
            raise HTTPException(status_code=502, detail="钉钉组织目录为空，请核实通讯录可见范围")
        directory_ids = {str(row["dept_id"]) for row in directory}
        pending: dict[str, tuple[str, dict]] = {}
        # Complete and validate every upstream read before staging master-data writes.
        for row in directory:
            department_id = str(row["dept_id"])
            for user_data in self.client.users(token, department_id):
                user_id = str(user_data.get("userid") or "")
                if not user_id:
                    raise HTTPException(status_code=502, detail="钉钉目录成员缺少稳定身份")
                if user_id in pending:
                    continue
                detail = self.client.user_detail(token, user_id)
                if detail.get("userid") != user_id:
                    raise HTTPException(status_code=502, detail="钉钉成员详情与查询身份不一致")
                placements = detail.get("dept_id_list")
                if not isinstance(placements, list) or not any(
                    str(item) in directory_ids for item in placements
                ):
                    raise HTTPException(status_code=502, detail="钉钉成员部门不在本次目录范围中")
                pending[user_id] = (department_id, {**user_data, **detail})
        if not pending:
            raise HTTPException(status_code=502, detail="钉钉成员目录为空，保留已有数据")
        unresolved = {str(row["dept_id"]): str(row.get("parent_id", "1")) for row in directory}
        if len(unresolved) != len(directory):
            raise HTTPException(
                status_code=502, detail="DingTalk directory contains duplicate departments"
            )
        resolved = {"", "0", "1"}
        while unresolved:
            ready = {key for key, parent in unresolved.items() if parent in resolved}
            if not ready:
                raise HTTPException(
                    status_code=502, detail="DingTalk department hierarchy is invalid"
                )
            resolved.update(ready)
            unresolved = {key: parent for key, parent in unresolved.items() if key not in ready}
        for department in self.db.scalars(
            select(Department)
            .join(DingTalkDepartmentLink, DingTalkDepartmentLink.department_id == Department.id)
            .where(DingTalkDepartmentLink.dingtalk_department_id.in_(directory_ids))
        ):
            if department.legal_entity_id != entity.id:
                raise HTTPException(status_code=409, detail="钉钉部门已经绑定其他组织，停止同步")
        for user_id in pending:
            profile = self.db.scalar(
                select(DingTalkPersonProfile).where(
                    DingTalkPersonProfile.dingtalk_user_id == user_id
                )
            )
            person = self.db.get(Person, profile.person_id) if profile else None
            if person and person.legal_entity_id != entity.id:
                raise HTTPException(status_code=409, detail="钉钉成员已经绑定其他组织，停止同步")
        result = SyncResult()
        self._seen_user_ids.clear()
        links = self._upsert_departments(entity, directory, result)
        for department_id, data in pending.values():
            self._upsert_person(entity, links[department_id], data, links, result)
        self.db.flush()
        checked_at = datetime.now(UTC).isoformat()
        current_person_ids = []
        historical_person_ids = []
        profiles = list(
            self.db.scalars(
                select(DingTalkPersonProfile)
                .join(Person, Person.id == DingTalkPersonProfile.person_id)
                .where(Person.legal_entity_id == entity.id, Person.archived_at.is_(None))
            )
        )
        for profile in profiles:
            current = profile.dingtalk_user_id in pending
            profile.profile_data = {
                **(profile.profile_data or {}),
                "directory_status": "current" if current else "not_in_current_directory",
                "directory_checked_at": checked_at,
            }
            if current:
                current_person_ids.append(str(profile.person_id))
                result.people_current += 1
            else:
                result.people_historical += 1
                historical_person_ids.append(str(profile.person_id))
                # Absence is evidence for the display snapshot only. Keep the
                # person's placements, accounts and stored grants unchanged.
        snapshot = self.db.scalar(
            select(AppSetting).where(AppSetting.key == "dingtalk_directory_snapshot")
        )
        if snapshot is None:
            snapshot = AppSetting(key="dingtalk_directory_snapshot", value={})
            self.db.add(snapshot)
        snapshot.value = {
            "legal_entity_id": str(entity.id),
            "department_codes": [f"DT-{item}" for item in sorted(directory_ids)],
            "checked_at": checked_at,
            "people_checked_at": checked_at,
            "current_person_ids": sorted(current_person_ids),
            "historical_person_ids": sorted(historical_person_ids),
        }
        self.db.add(
            AuditLog(
                actor_user_id=self.db.info.get("audit_actor_user_id"),
                action="organization.directory_sync",
                object_type="legal_entity",
                object_id=entity.id,
                after_data=result.as_dict(),
            )
        )
        self.db.commit()
        return result

    def _upsert_departments(
        self, entity: LegalEntity, rows: list[dict], result: SyncResult
    ) -> dict[str, Department]:
        existing_links = {
            link.dingtalk_department_id: link
            for link in self.db.scalars(select(DingTalkDepartmentLink))
        }
        departments: dict[str, Department] = {}
        pending = {str(row["dept_id"]): row for row in rows if row.get("dept_id") is not None}
        while pending:
            progressed = False
            for dingtalk_id, row in list(pending.items()):
                parent_external_id = str(row.get("parent_id", "1"))
                parent = departments.get(parent_external_id)
                if parent_external_id not in {"", "0", "1"} and parent is None:
                    continue
                link = existing_links.get(dingtalk_id)
                department = self.db.get(Department, link.department_id) if link else None
                if department is None:
                    department = Department(
                        legal_entity_id=entity.id,
                        code=f"DT-{dingtalk_id}",
                        name=str(row.get("name") or dingtalk_id),
                        parent_id=parent.id if parent else None,
                    )
                    self.db.add(department)
                    self.db.flush()
                    self.db.add(
                        DingTalkDepartmentLink(
                            department_id=department.id, dingtalk_department_id=dingtalk_id
                        )
                    )
                    result.departments_created += 1
                else:
                    department.name = str(row.get("name") or department.name)
                    department.parent_id = parent.id if parent else None
                    department.status = "active"
                    result.departments_updated += 1
                departments[dingtalk_id] = department
                del pending[dingtalk_id]
                progressed = True
            if not progressed:
                raise HTTPException(
                    status_code=502, detail="DingTalk department hierarchy is invalid"
                )
        return departments

    def _upsert_person(
        self,
        entity: LegalEntity,
        department: Department,
        data: dict,
        departments_by_dingtalk_id: dict[str, Department],
        result: SyncResult,
    ) -> None:
        user_id = str(data.get("userid") or data.get("user_id") or "")
        if not user_id:
            return
        # A member may appear in several department lists.  The person/profile
        # master is unique per DingTalk user, so process that member once per
        # synchronization run (the first returned department is retained).
        if user_id in self._seen_user_ids:
            return
        self._seen_user_ids.add(user_id)
        profile = self.db.scalar(
            select(DingTalkPersonProfile).where(DingTalkPersonProfile.dingtalk_user_id == user_id)
        )
        person = self.db.get(Person, profile.person_id) if profile else None
        employee_no = str(data.get("job_number") or f"DT-{user_id}")
        if person is None:
            person = self.db.scalar(
                select(Person).where(
                    Person.legal_entity_id == entity.id, Person.employee_no == employee_no
                )
            )
        if person is None:
            person = Person(
                legal_entity_id=entity.id,
                department_id=department.id,
                employee_no=employee_no[:50],
                display_name=str(data.get("name") or user_id)[:100],
                email=data.get("email"),
                employment_status="active" if data.get("active", True) else "inactive",
            )
            self.db.add(person)
            self.db.flush()
            result.people_created += 1
        else:
            person.department_id = department.id
            person.display_name = str(data.get("name") or person.display_name)[:100]
            person.email = data.get("email") or person.email
            person.employment_status = "active" if data.get("active", True) else "inactive"
            result.people_updated += 1
        if profile is None:
            profile = DingTalkPersonProfile(person_id=person.id, dingtalk_user_id=user_id)
            self.db.add(profile)
        profile.union_id = data.get("unionid") or data.get("union_id")
        profile.job_title = data.get("title") or data.get("position")
        profile.profile_data = {
            **(profile.profile_data or {}),
            "department_ids": data.get("dept_id_list", []),
            "hired_date": data.get("hired_date"),
            "company_affiliation": company_affiliation_from_detail(data),
        }
        self._sync_department_memberships(
            person, department, data, departments_by_dingtalk_id, result
        )

    def _sync_department_memberships(
        self,
        person: Person,
        default_department: Department,
        data: dict,
        departments_by_dingtalk_id: dict[str, Department],
        result: SyncResult,
    ) -> None:
        """Persist every DingTalk department placement and leadership marker."""
        raw_department_ids = data.get("dept_id_list", [])
        department_ids = (
            [str(item) for item in raw_department_ids]
            if isinstance(raw_department_ids, list)
            else []
        )
        placements = [
            departments_by_dingtalk_id[item]
            for item in department_ids
            if item in departments_by_dingtalk_id
        ]
        if not placements:
            placements = [default_department]

        manager_department_ids: set[str] = set()
        leadership_rows = data.get("leader_in_dept", [])
        if isinstance(leadership_rows, list):
            for leadership in leadership_rows:
                if not isinstance(leadership, dict) or leadership.get("leader") not in (
                    True,
                    1,
                    "true",
                    "True",
                ):
                    continue
                department_id = leadership.get("dept_id")
                if department_id is not None:
                    manager_department_ids.add(str(department_id))

        existing = {
            membership.department_id: membership
            for membership in self.db.scalars(
                select(DepartmentMembership).where(DepartmentMembership.person_id == person.id)
            )
        }
        source_ids = {department.id for department in departments_by_dingtalk_id.values()}
        for membership in existing.values():
            if membership.department_id in source_ids:
                membership.is_active = False
                membership.is_primary = False

        primary_department = placements[0]
        person.department_id = primary_department.id
        for placement in placements:
            membership = existing.get(placement.id)
            if membership is None:
                membership = DepartmentMembership(
                    person_id=person.id,
                    department_id=placement.id,
                )
                self.db.add(membership)
            linked_dingtalk_id = next(
                (
                    dingtalk_id
                    for dingtalk_id, linked_department in departments_by_dingtalk_id.items()
                    if linked_department.id == placement.id
                ),
                "",
            )
            membership.is_manager = linked_dingtalk_id in manager_department_ids
            membership.is_primary = placement.id == primary_department.id
            membership.is_active = True
            result.memberships_synced += 1
