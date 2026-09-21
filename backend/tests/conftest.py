"""Pytest fixtures: in-memory SQLite + TestClient, independent of Postgres."""

import os

os.environ["SEED_ON_EMPTY"] = "false"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest
from fastapi.testclient import TestClient

# Import the database module first and swap its engine BEFORE app.main binds
# the name at import time.
from app import database as dbmod
from app.models import models  # noqa: F401  (register mappers on Base.metadata)

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
dbmod.engine = test_engine
dbmod.SessionLocal.configure(bind=test_engine)

from app.main import app  # noqa: E402

TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture
def db():
    import app.database as database

    dbmod.Base.metadata.drop_all(bind=test_engine)
    dbmod.Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    # No `with`: lifespan (create_all/seed) is skipped; tables already fresh.
    return TestClient(app)
