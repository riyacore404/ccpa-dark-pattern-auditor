"""Baseline: the schema created by database/migrations/001 and 002.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-14

The first two migrations were plain SQL files applied by hand. This revision
changes nothing; it marks that state. On a database that already has both
applied, record it once with:

    .venv/bin/alembic stamp head

New schema changes are added as new revisions after this one.
"""

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
