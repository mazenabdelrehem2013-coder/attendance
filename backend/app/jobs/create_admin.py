r"""One-time start-up of a new installation: the company and its first ADMIN account.

    ORG_NAME=Raya ADMIN_EMAIL=admin@company.com INITIAL_ADMIN_PASSWORD=... \
        python -m app.jobs.create_admin

The password comes from Secret Manager (never from the command line or logs) and must be
changed at the first login. Running it again changes nothing.
"""

import os
import sys

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import make_session_factory
from app.models import Organization, User
from app.models.enums import Role
from app.services.audit import write_audit


def main() -> int:
    from app.core.logging import configure_logging

    configure_logging(get_settings().log_level)
    org_name = os.environ.get("ORG_NAME", "").strip()
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
    timezone = os.environ.get("ORG_TIMEZONE", "Africa/Lagos")
    if not org_name or "@" not in email or len(password) < 12:
        print("ORG_NAME, ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD (12+ characters) are required.")
        return 2

    with make_session_factory().begin() as db:
        if db.scalar(select(User.id).where(func.lower(User.email) == email)):
            print(f"{email} already exists - nothing to do.")
            return 0
        org = db.scalar(select(Organization).where(Organization.name == org_name))
        if org is None:
            org = Organization(name=org_name, default_timezone=timezone,
                               settings={"report_company_name": org_name, "email_from_name": org_name})
            db.add(org)
            db.flush()
            write_audit(db, action="ORGANIZATION_CREATED", organization_id=org.id, actor_user_id=None,
                        actor_role="SYSTEM", object_type="organization", object_id=org.id,
                        new_value={"name": org_name, "timezone": timezone})
        admin = User(organization_id=org.id, email=email, password_hash=hash_password(password), role=Role.ADMIN,
                     must_change_password=True)
        db.add(admin)
        db.flush()
        write_audit(db, action="ADMIN_CREATED", organization_id=org.id, actor_user_id=None, actor_role="SYSTEM",
                    object_type="user", object_id=admin.id, new_value={"email": email, "role": "ADMIN"})
    print(f"Company '{org_name}' and admin {email} created. The password must be changed at first login.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
