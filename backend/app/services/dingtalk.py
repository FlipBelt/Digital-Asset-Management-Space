from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    Department,
    DepartmentMembership,
    DingTalkDepartmentLink,
    DingTalkPersonProfile,
    LegalEntity,
    Person,
)

_OAPI_BASE = "https://oapi.dingtalk.com"


@dataclass
class SyncResult:
    departments_created: int = 0
    departments_updated: int = 0
    people_created: int = 0
    people_updated: int = 0
    memberships_synced: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "departments_created": self.departments_created,
            "departments_updated": self.departments_updated,
            "people_created": self.people_created,
            "people_updated": self.people_updated,
            "memberships_synced": self.memberships_synced,
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
        response = self.client.request(method, f"{_OAPI_BASE}{path}", params=params, **kwargs)
        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="invalid DingTalk response") from exc
        if response.is_error or data.get("errcode", 0) != 0:
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
            result = data.get("result", [])
            rows = result if isinstance(result, list) else result.get("list", [])
            for row in rows:
                if not isinstance(row, dict):
                    continue
                department_id = str(row.get("dept_id") or "")
                if not department_id or department_id == "-7" or department_id in visited:
                    continue
                visited.add(department_id)
                departments.append(row)
                pending.append(department_id)
        return departments

    def users(self, access_token: str, department_id: str) -> Iterable[dict]:
        cursor = 0
        while True:
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
            result = data.get("result", {})
            rows = result.get("list", [])
            yield from (row for row in rows if isinstance(row, dict))
            if not result.get("has_more"):
                return
            cursor = int(result.get("next_cursor", 0))

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

    def run(self, legal_entity_id: str) -> SyncResult:
        entity = self.db.get(LegalEntity, legal_entity_id)
        if entity is None or entity.archived_at is not None:
            raise HTTPException(status_code=404, detail="legal entity not found")
        token = self.client.access_token()
        result = SyncResult()
        links = self._upsert_departments(entity, self.client.departments(token), result)
        for dingtalk_id, department in links.items():
            for user_data in self.client.users(token, dingtalk_id):
                user_id = str(user_data.get("userid") or user_data.get("user_id") or "")
                if user_id in self._seen_user_ids:
                    continue
                detail = self.client.user_detail(token, user_id) if user_id else {}
                self._upsert_person(entity, department, {**user_data, **detail}, links, result)
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
            "department_ids": data.get("dept_id_list", []),
            "hired_date": data.get("hired_date"),
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
                if not isinstance(leadership, dict) or not leadership.get("leader"):
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
        for membership in existing.values():
            membership.is_active = False

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
