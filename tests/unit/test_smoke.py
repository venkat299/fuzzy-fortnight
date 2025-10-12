"""Basic smoke tests for the agent scaffolding."""

def test_imports():
    import agents  # noqa: F401
    from config.settings import settings

    assert settings.DB_PATH.endswith(".db")
