import os
from collections.abc import Generator

os.environ["DATABASE_URL"] = "sqlite:///./test-placeholder.db"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
import app.main as main_module


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(test_engine)

    def override_get_db():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    original_engine = main_module.engine
    main_module.engine = test_engine
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    main_module.engine = original_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()
