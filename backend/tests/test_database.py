import pytest

from app.core.config import ConfigurationError
from app.core.database import get_database_url


def test_missing_database_url_has_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EDUMIND_DATABASE_URL", raising=False)

    with pytest.raises(ConfigurationError, match="EDUMIND_DATABASE_URL"):
        get_database_url()


def test_database_url_requires_asyncpg_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDUMIND_DATABASE_URL", "postgresql://localhost/edumind")

    with pytest.raises(ConfigurationError, match="postgresql\\+asyncpg"):
        get_database_url()
