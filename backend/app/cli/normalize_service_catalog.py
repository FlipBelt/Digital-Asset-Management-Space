"""Preview first. Applying binds to the current plan digest and a real administrator."""

import argparse
import json
from uuid import UUID

from sqlalchemy import select, text

from app.core.access import get_access_context
from app.db.session import SessionLocal
from app.models import User
from app.services.catalog_cleanup import cleanup_catalog
from app.services.service_catalog import digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--actor-id", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--review-known", action="store_true")
    parser.add_argument("--expected-digest")
    args = parser.parse_args()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == args.actor_id))
        if (
            user is None
            or not user.is_active
            or user.archived_at is not None
            or not get_access_context(user, db).is_global_manager
        ):
            raise RuntimeError("必须使用已验证的真实资产管理员身份")
        # Block concurrent catalog and reference writes during preview/apply, so
        # the confirmed digest binds to one transactionally consistent state.
        db.execute(
            text(
                "LOCK TABLE providers, platforms, service_products, service_instances, "
                "platform_tenants, asset_platform_links, import_proposed_objects "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
        )
        report = cleanup_catalog(db, actor_id=user.id, review=args.review_known)
        # Timestamps are runtime evidence, not stable approval-plan identities.
        stable = json.loads(json.dumps(report))
        for change in stable["changes"]:
            for state in ("before", "after"):
                if state in change and "archived_at" in change[state]:
                    change[state]["archived_at"] = bool(change[state]["archived_at"])
        fingerprint = digest(stable)
        if args.apply:
            if fingerprint != args.expected_digest:
                raise RuntimeError("预览摘要未确认或目录已改变，请重新预览")
            db.commit()
        else:
            db.rollback()
        print(
            json.dumps(
                {"applied": args.apply, "digest": fingerprint, **report},
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
