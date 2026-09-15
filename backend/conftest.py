"""
Pytest configuration shared by every test module.

IMPORTANT: `models.py` reads DATABASE_URL at *import* time to build its
engine, so the test database must be pointed at a throwaway sqlite file
before `models` (or anything that imports it, i.e. `app`) is imported
anywhere in the process. That's why these env vars are set at module load
time, before the `import pytest` fixtures below ever touch `app`/`models`.

Schema creation for this throwaway DB is done directly via
Base.metadata.create_all() below rather than by running the real Alembic
migrations — these tests exercise model/route logic, not migration
correctness, and create_all() is faster and needs no extra tooling.
"""
import os
import tempfile

_fd, _TEST_DB_PATH = tempfile.mkstemp(suffix='.db')
os.close(_fd)
os.environ['DATABASE_URL'] = f'sqlite:///{_TEST_DB_PATH}'
os.environ.setdefault('ADMIN_KEY', '')
os.environ.setdefault('SUPABASE_JWT_SECRET', '')
os.environ.setdefault('REDIS_URL', '')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('ANTHROPIC_API_KEY', '')

import pytest


@pytest.fixture(scope='session')
def app_module():
    """Import the Flask app module once per test session (it's expensive:
    creates the Limiter, the scheduler object, etc). Importing it here
    rather than at collection time keeps the DATABASE_URL override above
    guaranteed to run first."""
    import app as app_module
    from models import Base, engine
    Base.metadata.create_all(engine)
    return app_module


@pytest.fixture()
def client(app_module):
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture()
def db_session():
    from models import Session
    session = Session()
    try:
        yield session
    finally:
        session.close()


def pytest_sessionfinish(session, exitstatus):
    try:
        os.remove(_TEST_DB_PATH)
    except OSError:
        pass
