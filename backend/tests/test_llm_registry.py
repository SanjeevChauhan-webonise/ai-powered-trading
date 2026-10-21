import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.llm import registry
from app.llm.registry import ModelError, available_models, build_model, resolve_model
from app.main import app

NO_KEYS = Settings(default_model="openai:gpt-4o-mini")
ALL_KEYS = Settings(
    openai_api_key="k", anthropic_api_key="k", gemini_api_key="k", groq_api_key="k", openrouter_api_key="k",
    ollama_base_url="http://ollama.test:11434",
)  # fmt: skip


@pytest.fixture(autouse=True)
def _clear_ollama_cache() -> None:
    registry._ollama_cache.clear()


def _fake_ollama(monkeypatch: pytest.MonkeyPatch, names: list[str] | None) -> None:
    def get(url: str, timeout: float) -> httpx.Response:
        if names is None:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"models": [{"name": n} for n in names]}, request=httpx.Request("GET", url))

    monkeypatch.setattr(registry.httpx, "get", get)


def test_no_keys_no_models() -> None:
    assert available_models(NO_KEYS) == []


def test_only_configured_providers_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = {m.id for m in available_models(Settings(anthropic_api_key="k", groq_api_key="k"))}
    assert "anthropic:claude-sonnet-5-5" in ids and "groq:llama-3.3-70b-versatile" in ids
    assert not any(i.startswith(("openai:", "google:", "openrouter:", "ollama:")) for i in ids)


def test_all_providers_and_ollama_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_ollama(monkeypatch, ["qwen3:8b", "llama3.2:3b"])
    models = available_models(ALL_KEYS)
    assert {m.provider for m in models} == {"anthropic", "openai", "google", "groq", "openrouter", "ollama"}
    assert [m.id for m in models if m.provider == "ollama"] == ["ollama:llama3.2:3b", "ollama:qwen3:8b"]
    assert len({m.id for m in models}) == len(models)


def test_ollama_unreachable_is_empty_not_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_ollama(monkeypatch, None)
    assert [m for m in available_models(Settings(ollama_base_url="http://x:1")) if m.provider == "ollama"] == []


def test_extra_models() -> None:
    s = Settings(openai_api_key="k", extra_models="openai:gpt-9, groq:foo, nonsense, openai:gpt-4o")
    ids = [m.id for m in available_models(s)]
    assert "openai:gpt-9" in ids
    assert "groq:foo" not in ids  # provider not configured
    assert ids.count("openai:gpt-4o") == 1  # no duplicates


def test_resolve_priority() -> None:
    s = Settings(
        openai_api_key="k",
        anthropic_api_key="k",
        default_model="openai:gpt-4o",
        risk_model="anthropic:claude-haiku-5-5",
    )
    assert resolve_model(s) == "openai:gpt-4o"
    assert resolve_model(s, agent="risk") == "anthropic:claude-haiku-5-5"
    assert resolve_model(s, agent="research") == "openai:gpt-4o"  # no override for this agent
    assert resolve_model(s, "anthropic:claude-opus-5-5", agent="risk") == "anthropic:claude-opus-5-5"  # request wins
    assert resolve_model(s, "openai:brand-new-model") == "openai:brand-new-model"  # names are not gatekept


def test_resolve_errors() -> None:
    with pytest.raises(ModelError, match="not configured"):
        resolve_model(NO_KEYS)
    with pytest.raises(ModelError, match="Invalid model id"):
        resolve_model(ALL_KEYS, "gpt-4o")
    with pytest.raises(ModelError, match="Invalid model id"):
        resolve_model(ALL_KEYS, "mistral:x")
    with pytest.raises(ModelError, match="Invalid model id"):
        resolve_model(ALL_KEYS, "openai:")


@pytest.mark.parametrize(
    "model_id, cls",
    [
        ("openai:gpt-4o", "OpenAIChatModel"),
        ("anthropic:claude-sonnet-5-5", "AnthropicModel"),
        ("google:gemini-2.5-flash", "GoogleModel"),
        ("groq:llama-3.3-70b-versatile", "GroqModel"),
        ("openrouter:openai/gpt-4o", "OpenAIChatModel"),
        ("ollama:llama3", "OpenAIChatModel"),
    ],
)
def test_build_model_uses_settings_credentials(model_id: str, cls: str) -> None:
    m = build_model(ALL_KEYS, model_id)
    assert type(m).__name__ == cls
    assert m.model_name == model_id.split(":", 1)[1]


def test_build_model_unconfigured() -> None:
    with pytest.raises(ModelError):
        build_model(NO_KEYS, "openai:gpt-4o")


def test_models_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = client.get("/models").json()
    assert empty["models"] == [] and empty["default_available"] is False and empty["default"]
    app.dependency_overrides[get_settings] = lambda: Settings(openai_api_key="k", default_model="openai:gpt-4o")
    body = client.get("/models").json()
    assert body["default_available"] is True
    assert {"id": "openai:gpt-4o", "provider": "openai", "label": "OpenAI · gpt-4o"} in body["models"]


def test_azure_openai_needs_key_and_endpoint_and_lists_deployments():
    from app.llm.registry import available_models, build_model

    assert not [m for m in available_models(Settings(azure_openai_api_key="k")) if m.provider == "azure"]
    s = Settings(
        azure_openai_api_key="k",
        azure_openai_endpoint="https://x.openai.azure.com",
        azure_openai_deployments="gpt4o, mini",
    )
    assert [m.id for m in available_models(s) if m.provider == "azure"] == ["azure:gpt4o", "azure:mini"]
    assert build_model(s, "azure:gpt4o").model_name == "gpt4o"
