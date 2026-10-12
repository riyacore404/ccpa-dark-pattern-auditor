import os

import pytest

_SETTINGS_ENV_PREFIXES = ("TINYFISH_", "SUPABASE_", "GEMINI_", "AUDIT_")


@pytest.fixture(autouse=True)
def _hermetic_settings_environment(monkeypatch):
    """Keep tests independent of keys exported in the developer's shell."""
    for name in list(os.environ):
        if name.upper().startswith(_SETTINGS_ENV_PREFIXES):
            monkeypatch.delenv(name, raising=False)
