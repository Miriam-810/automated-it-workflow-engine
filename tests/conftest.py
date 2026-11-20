import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import models  # noqa: E402
from database import get_db  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    # Not used as a context manager, so the lifespan (which touches the real DB) doesn't run.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def make_request(client):
    def _make(**overrides):
        body = {
            "employee_id": "E100",
            "resource_type": "laptop",
            "justification": "Replacing a broken work laptop",
            "estimated_cost": 1200.0,
        } | overrides
        resp = client.post("/api/v1/requests", json=body)
        assert resp.status_code == 201, resp.text
        return resp.json()
    return _make
