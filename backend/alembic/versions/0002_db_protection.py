"""Database-level protection: append-only tables, audit hash chain, app-role permissions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "attendance_app"

# Rows in these tables are evidence: once written they may never be changed.
# DELETE is allowed only for the data-retention job, which must first run
#   SET LOCAL app.allow_purge = 'on';
# and connect as the owner role (the app role has no DELETE right on these tables at all).
APPEND_ONLY_TABLES = [
    "attendance_events",
    "attendance_verification",
    "verification_signals",
    "attendance_event_reviews",
    "attendance_adjustments",
    "security_events",
    "audit_logs",
]


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION prevent_modification() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND current_setting('app.allow_purge', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'Table % is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        """
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION prevent_modification();
            """
        )
        # TRUNCATE bypasses row triggers, so block it separately.
        op.execute(
            f"""
            CREATE TRIGGER {table}_no_truncate
            BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION prevent_modification();
            """
        )

    # Hash chain: each audit row stores the hash of the previous row. Editing or deleting any
    # row (even directly in the database by an admin) breaks the chain and becomes detectable.
    op.execute(
        """
        CREATE FUNCTION audit_logs_chain() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            last_seq  bigint;
            last_hash text;
        BEGIN
            -- Serialize writers so the chain is linear.
            PERFORM pg_advisory_xact_lock(hashtext('audit_logs_chain'));
            SELECT seq, row_hash INTO last_seq, last_hash
              FROM audit_logs ORDER BY seq DESC LIMIT 1;

            NEW.seq        := COALESCE(last_seq, 0) + 1;
            NEW.prev_hash  := last_hash;
            NEW.created_at := COALESCE(NEW.created_at, now());
            NEW.row_hash   := audit_log_hash(
                NEW.prev_hash, NEW.seq, NEW.id, NEW.organization_id, NEW.actor_user_id,
                NEW.action, NEW.object_type, NEW.object_id, NEW.old_value, NEW.new_value,
                NEW.created_at);
            RETURN NEW;
        END;
        $$;
        """
    )
    # Separate function so a verification query can recompute hashes the same way.
    op.execute(
        """
        CREATE FUNCTION audit_log_hash(
            prev_hash text, seq bigint, id uuid, organization_id uuid, actor_user_id uuid,
            action text, object_type text, object_id text, old_value jsonb, new_value jsonb,
            created_at timestamptz
        ) RETURNS text
        LANGUAGE sql IMMUTABLE AS $$
            SELECT encode(sha256(convert_to(concat_ws('|',
                COALESCE(prev_hash, ''), seq::text, id::text,
                COALESCE(organization_id::text, ''), COALESCE(actor_user_id::text, ''),
                action, COALESCE(object_type, ''), COALESCE(object_id, ''),
                COALESCE(old_value::text, ''), COALESCE(new_value::text, ''),
                extract(epoch FROM created_at)::text
            ), 'UTF8')), 'hex');
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_chain
        BEFORE INSERT ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_chain();
        """
    )

    # Permissions for the API's database role (skipped if the role doesn't exist).
    tables = ", ".join(APPEND_ONLY_TABLES)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                GRANT USAGE ON SCHEMA public TO {APP_ROLE};
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE};
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE};
                REVOKE UPDATE, DELETE, TRUNCATE ON {tables} FROM {APP_ROLE};
                REVOKE ALL ON alembic_version FROM {APP_ROLE};
                GRANT SELECT ON alembic_version TO {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE};
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE};
                REVOKE USAGE ON SCHEMA public FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS audit_logs_chain ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_chain()")
    op.execute(
        "DROP FUNCTION IF EXISTS audit_log_hash(text, bigint, uuid, uuid, uuid, text, text, "
        "text, jsonb, jsonb, timestamptz)"
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
    op.execute("DROP FUNCTION IF EXISTS prevent_modification()")
