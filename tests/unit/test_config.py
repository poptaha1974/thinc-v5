from thinc_v5.config import Settings


def test_settings_rejects_missing_database_url() -> None:
    try:
        Settings(database_url="", environment="test")
    except ValueError as exc:
        assert "database_url" in str(exc)
    else:
        raise AssertionError("empty database_url must be rejected")


def test_settings_defaults_environment_for_valid_database_url() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://thinc:change-me@localhost:5432/thinc"
    )

    assert settings.database_url == (
        "postgresql+psycopg://thinc:change-me@localhost:5432/thinc"
    )
    assert settings.environment == "development"
