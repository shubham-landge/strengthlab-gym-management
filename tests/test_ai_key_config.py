"""Configuring a cloud AI key must actually enable AI generation."""

import app as gym_app


def test_a_single_api_key_is_enough_to_enable_ai(monkeypatch):
    """The documented setup is one env var. It must work on its own.

    AI_PROVIDER_ORDER defaults to "openai,gemini"; that default used to be
    returned unsplit, matching no provider and leaving AI silently disabled.
    """
    monkeypatch.delenv("AI_PROVIDER_ORDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    assert gym_app.ai_generation_enabled() is True
    assert [p["name"] for p in gym_app.configured_ai_providers()] == ["openai"]


def test_gemini_key_alone_also_works(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER_ORDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEYS", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test-key")
    assert [p["name"] for p in gym_app.configured_ai_providers()] == ["gemini"]


def test_defaults_are_split_on_commas(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER_ORDER", raising=False)
    assert gym_app.split_env_values("AI_PROVIDER_ORDER", default="openai,gemini") == ["openai", "gemini"]


def test_multiple_keys_are_all_collected(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER_ORDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEYS", "key-one, key-two ; key-three")
    provider = gym_app.configured_ai_providers()[0]
    assert provider["keys"] == ["key-one", "key-two", "key-three"]


def test_no_key_means_local_fallback(monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENAI_API_KEYS", "GEMINI_API_KEY",
                 "GEMINI_API_KEYS", "GOOGLE_API_KEY", "AI_PROVIDER_ORDER"):
        monkeypatch.delenv(name, raising=False)
    assert gym_app.ai_generation_enabled() is False
    assert gym_app.ai_generation_label() == "local fallback"
