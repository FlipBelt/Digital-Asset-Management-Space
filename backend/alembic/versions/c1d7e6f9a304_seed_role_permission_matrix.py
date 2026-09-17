"""seed the initial role-to-permission matrix

Revision ID: c1d7e6f9a304
Revises: a8e5f4c2d110
Create Date: 2026-08-10
"""

from collections.abc import Sequence

from alembic import op


revision: str = "c1d7e6f9a304"
down_revision: str | Sequence[str] | None = "a8e5f4c2d110"
branch_labels = None
depends_on = None


ROLE_PERMISSION_ROWS = (
    ("system_admin", "asset.read"),
    ("system_admin", "asset.write"),
    ("system_admin", "asset.export"),
    ("system_admin", "organization.read"),
    ("system_admin", "organization.write"),
    ("system_admin", "governance.read"),
    ("system_admin", "governance.write"),
    ("system_admin", "admin.manage"),
    ("asset_manager", "asset.read"),
    ("asset_manager", "asset.write"),
    ("asset_manager", "asset.export"),
    ("asset_manager", "organization.read"),
    ("asset_manager", "governance.read"),
    ("asset_manager", "governance.write"),
    ("department_manager", "asset.read"),
    ("department_manager", "asset.write"),
    ("department_manager", "organization.read"),
    ("department_manager", "governance.read"),
    ("department_manager", "governance.write"),
    ("executive", "asset.read"),
    ("executive", "asset.export"),
    ("executive", "organization.read"),
    ("executive", "governance.read"),
    ("auditor", "asset.read"),
    ("auditor", "organization.read"),
    ("auditor", "governance.read"),
    ("employee", "asset.read"),
    ("employee", "governance.read"),
)


def upgrade() -> None:
    for role_code, permission_code in ROLE_PERMISSION_ROWS:
        op.execute(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT roles.id, permissions.id
            FROM roles, permissions
            WHERE roles.code = :role_code AND permissions.code = :permission_code
            ON CONFLICT DO NOTHING
            """.replace(":role_code", f"'{role_code}'").replace(
                ":permission_code", f"'{permission_code}'"
            )
        )


def downgrade() -> None:
    # Permission rows are configuration data. Keep them on downgrade so rolling
    # back application code never reduces a currently assigned user's access.
    pass
