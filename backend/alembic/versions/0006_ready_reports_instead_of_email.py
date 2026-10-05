"""ready reports instead of email

Emails are not used: scheduled reports are saved as files to download instead.
Drops the (unused) email tables from 0005 and adds report_files + report_runs.owner_user_id.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-04 17:47:06.535646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "attendance_app"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('email_attachments')  # first: it points to email_outbox
    op.drop_table('email_outbox')

    op.create_table('report_files',
    sa.Column('report_run_id', sa.UUID(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('media_type', sa.String(length=150), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['report_run_id'], ['report_runs.id'], name=op.f('fk_report_files_report_run_id_report_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_report_files'))
    )
    op.create_index(op.f('ix_report_files_report_run_id'), 'report_files', ['report_run_id'], unique=False)
    op.add_column('report_runs', sa.Column('owner_user_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_report_runs_owner_user_id'), 'report_runs', ['owner_user_id'], unique=False)
    op.create_foreign_key(op.f('fk_report_runs_owner_user_id_users'), 'report_runs', 'users', ['owner_user_id'], ['id'])

    # The API's database role may read/add/delete report files (skipped if the role doesn't exist).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                GRANT SELECT, INSERT, DELETE ON report_files TO {APP_ROLE};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema. Report files are lost; the email tables come back empty."""
    op.drop_constraint(op.f('fk_report_runs_owner_user_id_users'), 'report_runs', type_='foreignkey')
    op.drop_index(op.f('ix_report_runs_owner_user_id'), table_name='report_runs')
    op.drop_column('report_runs', 'owner_user_id')
    op.drop_index(op.f('ix_report_files_report_run_id'), table_name='report_files')
    op.drop_table('report_files')

    op.create_table('email_outbox',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('category', sa.Enum('NOTIFICATION', 'REPORT', 'TEST', name='category', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('to_address', sa.String(length=320), nullable=False),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('body_text', sa.Text(), nullable=False),
    sa.Column('body_html', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('QUEUED', 'SENT', 'FAILED', name='status', native_enum=False, create_constraint=True, length=32), server_default='QUEUED', nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('dedupe_key', sa.String(length=200), nullable=True),
    sa.Column('report_setting_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_email_outbox_organization_id_organizations')),
    sa.ForeignKeyConstraint(['report_setting_id'], ['report_settings.id'], name=op.f('fk_email_outbox_report_setting_id_report_settings'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_email_outbox_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_outbox'))
    )
    op.create_index('ix_email_outbox_due', 'email_outbox', ['status', 'next_attempt_at'], unique=False)
    op.create_index('ix_email_outbox_org_created', 'email_outbox', ['organization_id', 'created_at'], unique=False)
    op.create_index('uq_email_outbox_dedupe', 'email_outbox', ['to_address', 'dedupe_key'], unique=True, postgresql_where=sa.text('dedupe_key IS NOT NULL'))
    op.create_table('email_attachments',
    sa.Column('email_id', sa.UUID(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('media_type', sa.String(length=150), nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.ForeignKeyConstraint(['email_id'], ['email_outbox.id'], name=op.f('fk_email_attachments_email_id_email_outbox'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_attachments'))
    )
    op.create_index(op.f('ix_email_attachments_email_id'), 'email_attachments', ['email_id'], unique=False)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON email_outbox, email_attachments TO {APP_ROLE};
            END IF;
        END $$;
        """
    )
