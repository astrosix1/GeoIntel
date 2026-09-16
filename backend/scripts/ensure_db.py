#!/usr/bin/env python3
"""
Run before the app starts, in every deploy environment (Procfile,
nixpacks.toml, Dockerfile all call this instead of `alembic upgrade head`
directly):

  - Fresh database (no tables yet): run the Alembic migrations normally —
    this creates the schema.
  - Pre-existing database that already has the app's tables but predates
    Alembic (created via the old Base.metadata.create_all() path that
    models.py used before migrations were introduced, so it has no
    alembic_version bookkeeping table): `alembic upgrade head` would try
    to CREATE TABLE on tables that already exist and fail outright,
    crash-looping the deploy. Stamp the database at the baseline revision
    instead — it records "already at head" without re-running the
    creates, which is exactly correct since the baseline migration's
    schema *is* what create_all() already built.

Safe to run on every deploy: a database already stamped/migrated to head
is a no-op either way.
"""
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect
from models import engine


def run_alembic(*args):
    return subprocess.run(['alembic', *args], cwd=BACKEND_DIR).returncode


def main():
    tables = set(inspect(engine).get_table_names())
    has_app_tables = 'crises' in tables
    has_alembic_version = 'alembic_version' in tables

    if has_app_tables and not has_alembic_version:
        print('Existing pre-Alembic database detected (tables present, no '
              'alembic_version) — stamping baseline revision instead of '
              'replaying CREATE TABLE against tables that already exist.')
        code = run_alembic('stamp', 'head')
    else:
        code = run_alembic('upgrade', 'head')

    sys.exit(code)


if __name__ == '__main__':
    main()
