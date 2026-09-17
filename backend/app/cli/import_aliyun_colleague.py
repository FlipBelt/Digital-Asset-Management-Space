"""Operational entry point for the confirmed Aliyun colleague import batch."""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import User
from app.services.aliyun_colleague_import import (
    commit_aliyun_colleague_import,
    rollback_aliyun_colleague_import,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("commit", "rollback"))
    parser.add_argument("--operator", required=True, help="已登录中台用户的用户名")
    parser.add_argument("--batch-id", help="rollback 时必填")
    arguments = parser.parse_args()
    with SessionLocal() as db:
        operator = db.scalar(
            select(User).where(User.username == arguments.operator, User.archived_at.is_(None))
        )
        if operator is None:
            raise ValueError("操作用户不存在")
        if arguments.action == "commit":
            result = commit_aliyun_colleague_import(db, actor_user_id=operator.id)
        else:
            if not arguments.batch_id:
                raise ValueError("rollback 必须提供 --batch-id")
            result = rollback_aliyun_colleague_import(
                db, batch_id=arguments.batch_id, actor_user_id=operator.id
            )
    print(result)


if __name__ == "__main__":
    main()
