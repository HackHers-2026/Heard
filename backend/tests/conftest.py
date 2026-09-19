import pytest
from sqlmodel import SQLModel
from app.database import engine
import app.models  # registers all models on SQLModel.metadata


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    SQLModel.metadata.create_all(engine)
    yield
