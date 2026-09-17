import argparse
import getpass

from sqlalchemy import select

from app.core.auth import hash_password
from app.db.session import SessionLocal
from app.models import Role, User, UserRoleScope


def create_admin(username: str, password: str) -> None:
    normalized_username = username.strip().lower()
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == normalized_username)) is not None:
            raise ValueError("username already exists")
        admin_role = db.scalar(select(Role).where(Role.code == "system_admin"))
        if admin_role is None:
            raise ValueError("roles are not seeded; run app.cli.seed after migrations")
        user = User(username=normalized_username, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        db.add(UserRoleScope(user_id=user.id, role_id=admin_role.id, scope_type="company"))
        db.commit()
    print(f"Administrator '{normalized_username}' created.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the initial system administrator")
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("password confirmation does not match")
    create_admin(args.username, password)


if __name__ == "__main__":
    main()
