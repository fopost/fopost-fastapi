from __future__ import annotations

import pytest
from fopost import DEFAULT_BASE_URL

from fopost_fastapi import FoPostSettings


def test_settings_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOPOST_API_KEY", "fp_from_env")
    monkeypatch.setenv("FOPOST_BASE_URL", "https://api.staging.fopost.com/v1")
    monkeypatch.setenv("FOPOST_TIMEOUT", "12.5")
    monkeypatch.setenv("FOPOST_MAX_RETRIES", "5")
    monkeypatch.setenv("FOPOST_DEFAULT_WORKSPACE_ID", "ws_env")
    monkeypatch.setenv("FOPOST_WEBHOOK_SECRET", "whsec_env")

    settings = FoPostSettings(_env_file=None)

    assert settings.api_key == "fp_from_env"
    assert settings.base_url == "https://api.staging.fopost.com/v1"
    assert settings.timeout == 12.5
    assert settings.max_retries == 5
    assert settings.default_workspace_id == "ws_env"
    assert settings.webhook_secret == "whsec_env"


def test_defaults_match_the_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "FOPOST_API_KEY",
        "FOPOST_BASE_URL",
        "FOPOST_TIMEOUT",
        "FOPOST_MAX_RETRIES",
        "FOPOST_DEFAULT_WORKSPACE_ID",
        "FOPOST_WEBHOOK_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = FoPostSettings(_env_file=None)

    assert settings.api_key is None
    assert settings.base_url == DEFAULT_BASE_URL
    assert settings.timeout == 30.0
    assert settings.max_retries == 3
    assert settings.default_workspace_id is None
    assert settings.webhook_secret is None


def test_explicit_values_beat_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOPOST_API_KEY", "fp_from_env")
    assert FoPostSettings(api_key="fp_explicit", _env_file=None).api_key == "fp_explicit"


def test_a_missing_api_key_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    from fopost_fastapi import create_client

    monkeypatch.delenv("FOPOST_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FOPOST_API_KEY"):
        create_client(FoPostSettings(_env_file=None))
