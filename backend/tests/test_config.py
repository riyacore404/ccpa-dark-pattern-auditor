import pytest
from pydantic import ValidationError

from app.core.config import (
    DEFAULT_EVIDENCE_BUCKET,
    DEFAULT_TINYFISH_BASE_URL,
    Settings,
)


def make(**overrides):
    return Settings(_env_file=None, **overrides)


def test_defaults_match_the_env_template():
    settings = make()
    assert settings.audit_max_steps == 20
    assert settings.audit_timeout_seconds == 180
    assert settings.audit_max_dom_bytes == 250000
    assert settings.audit_allow_purchases is False
    assert settings.audit_require_target_validation is True
    assert settings.tinyfish_api_base_url == DEFAULT_TINYFISH_BASE_URL
    assert settings.supabase_storage_bucket == DEFAULT_EVIDENCE_BUCKET


def test_blank_template_values_are_treated_as_unset():
    settings = make(
        tinyfish_api_key="",
        tinyfish_api_base_url="",
        supabase_url="  ",
        supabase_service_role_key="",
        supabase_storage_bucket="",
    )
    assert settings.tinyfish_api_key is None
    assert settings.supabase_url is None
    assert settings.supabase_service_role_key is None
    assert settings.tinyfish_api_base_url == DEFAULT_TINYFISH_BASE_URL
    assert settings.supabase_storage_bucket == DEFAULT_EVIDENCE_BUCKET


def test_secrets_are_not_shown_in_repr():
    settings = make(
        tinyfish_api_key="tf-secret-value",
        supabase_service_role_key="sb-secret-value",
    )
    shown = repr(settings)
    assert "tf-secret-value" not in shown
    assert "sb-secret-value" not in shown


def test_purchases_cannot_be_enabled():
    with pytest.raises(ValidationError):
        make(audit_allow_purchases=True)


def test_target_validation_cannot_be_disabled():
    with pytest.raises(ValidationError):
        make(audit_require_target_validation=False)


def test_string_booleans_from_env_are_parsed(monkeypatch):
    monkeypatch.setenv("AUDIT_ALLOW_PURCHASES", "false")
    monkeypatch.setenv("AUDIT_REQUIRE_TARGET_VALIDATION", "true")
    settings = make()
    assert settings.audit_allow_purchases is False
    assert settings.audit_require_target_validation is True


def test_env_string_true_for_purchases_is_refused(monkeypatch):
    monkeypatch.setenv("AUDIT_ALLOW_PURCHASES", "true")
    with pytest.raises(ValidationError):
        make()


@pytest.mark.parametrize("value", [0, 101])
def test_step_limit_is_bounded(value):
    with pytest.raises(ValidationError):
        make(audit_max_steps=value)


@pytest.mark.parametrize("value", [10, 901])
def test_timeout_is_bounded(value):
    with pytest.raises(ValidationError):
        make(audit_timeout_seconds=value)
