import pytest
from pydantic import ValidationError

import app.config as config


def test_settings_requires_database_url_without_environment_file(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as error:
        config.Settings(_env_file=None)
    assert any(item.get("loc") == ("database_url",) for item in error.value.errors())


def test_missing_database_url_fails_with_clear_configuration_message(monkeypatch):
    def settings_without_database_url():
        raise ValidationError.from_exception_data(
            "Settings",
            [{"type": "missing", "loc": ("database_url",), "input": {}}],
        )

    monkeypatch.setattr(config, "Settings", settings_without_database_url)
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
            config.get_settings()
    finally:
        config.get_settings.cache_clear()
