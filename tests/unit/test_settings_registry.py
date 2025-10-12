from config.registry import MONITOR_KEY, bind_model, get_model
from config.settings import Settings


def test_settings_defaults():
    settings = Settings(_env_file=None)
    assert settings.DB_PATH.endswith(".db")
    assert settings.HINTS_PER_STAGE == 2


def test_registry_bind_and_retrieve():
    marker = object()
    bind_model(MONITOR_KEY, lambda **_: marker)
    model = get_model(MONITOR_KEY)
    assert model() is marker
