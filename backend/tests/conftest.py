import pytest
from app.database import init_db
import app.models  # registers all models on SQLModel.metadata


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    # init_db() creates tables AND applies the dev-SQLite forward-migration,
    # so newly added columns exist even on a pre-existing heard.db.
    init_db()
    yield
