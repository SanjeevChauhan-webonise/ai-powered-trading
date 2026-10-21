"""Model registry: which LLMs can be used, based on which provider credentials are configured.

Model ids are "<provider>:<model>" strings (e.g. "anthropic:claude-sonnet-5-5"). The curated lists below are
the one place to edit; use EXTRA_MODELS in env to add ids without code changes. Ollama models are discovered live.
"""

import logging
import time
from dataclasses import dataclass

import httpx
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.groq import GroqProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from app.core.config import Settings
from app.schemas.llm import ModelInfo

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    settings_field: str  # Settings attribute holding the API key / base URL
    models: tuple[str, ...]


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        "anthropic",
        "Anthropic",
        "anthropic_api_key",
        ("claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"),
    ),  # fmt: skip
    Provider("openai", "OpenAI", "openai_api_key", ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini")),
    Provider("google", "Google Gemini", "gemini_api_key", ("gemini-2.5-pro", "gemini-2.5-flash")),
    Provider("groq", "Groq", "groq_api_key", ("llama-3.3-70b-versatile", "llama-3.1-8b-instant")),
    Provider(
        "openrouter",
        "OpenRouter",
        "openrouter_api_key",
        ("openai/gpt-4o", "anthropic/claude-sonnet-4.5", "meta-llama/llama-3.3-70b-instruct"),
    ),  # fmt: skip
    Provider("ollama", "Ollama (local)", "ollama_base_url", ()),  # models discovered from the server
    Provider("mock", "Mock (offline demo)", "enable_mock_llm", ("demo",)),
)
_BY_KEY = {p.key: p for p in PROVIDERS}

_OLLAMA_TTL = 30.0
_ollama_cache: dict[str, tuple[float, list[str]]] = {}


class ModelError(ValueError):
    """Requested model is unknown or its provider is not configured."""


def _split(model_id: str) -> tuple[str, str]:
    provider, sep, name = model_id.partition(":")
    if not sep or not name or provider not in _BY_KEY:
        raise ModelError(f"Invalid model id '{model_id}'. Expected '<provider>:<model>', provider in {sorted(_BY_KEY)}")
    return provider, name


def _configured(settings: Settings, provider: Provider) -> bool:
    return bool(getattr(settings, provider.settings_field))


def ollama_models(base_url: str) -> list[str]:
    """Installed Ollama models; empty if the server is unreachable. Cached briefly."""
    now = time.monotonic()
    cached = _ollama_cache.get(base_url)
    if cached and now - cached[0] < _OLLAMA_TTL:
        return cached[1]
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=1.5)
        r.raise_for_status()
        names = sorted(m["name"] for m in r.json().get("models", []))
    except Exception:
        log.warning("ollama not reachable at %s", base_url)
        names = []
    _ollama_cache[base_url] = (now, names)
    return names


def available_models(settings: Settings) -> list[ModelInfo]:
    out: list[ModelInfo] = []
    seen: set[str] = set()

    def add(provider: Provider, name: str) -> None:
        mid = f"{provider.key}:{name}"
        if mid not in seen:
            seen.add(mid)
            out.append(ModelInfo(id=mid, provider=provider.key, label=f"{provider.label} · {name}"))

    for p in PROVIDERS:
        if not _configured(settings, p):
            continue
        names = ollama_models(settings.ollama_base_url) if p.key == "ollama" else list(p.models)
        for n in names:
            add(p, n)
    for extra in settings.extra_model_list:
        try:
            provider, name = _split(extra)
        except ModelError:
            log.warning("ignoring invalid EXTRA_MODELS entry '%s'", extra)
            continue
        if _configured(settings, _BY_KEY[provider]):
            add(_BY_KEY[provider], name)
    return out


def resolve_model(settings: Settings, requested: str | None = None, agent: str | None = None) -> str:
    """Pick the model id: explicit request > per-agent override > DEFAULT_MODEL. Provider must be configured.

    The model name itself is not checked against the curated list (new models work immediately); only the
    provider and its credentials are.
    """
    override = getattr(settings, f"{agent}_model", "") if agent else ""
    model_id = requested or override or settings.default_model
    provider, _ = _split(model_id)
    if not _configured(settings, _BY_KEY[provider]):
        raise ModelError(
            f"Provider '{provider}' is not configured (set its API key / URL in env) for model '{model_id}'"
        )
    return model_id


def build_model(settings: Settings, model_id: str) -> Model:
    """Construct a Pydantic AI model using credentials from Settings (not process env)."""
    provider, name = _split(model_id)
    if not _configured(settings, _BY_KEY[provider]):
        raise ModelError(f"Provider '{provider}' is not configured")
    match provider:
        case "openai":
            return OpenAIChatModel(name, provider=OpenAIProvider(api_key=settings.openai_api_key))
        case "anthropic":
            return AnthropicModel(name, provider=AnthropicProvider(api_key=settings.anthropic_api_key))
        case "google":
            return GoogleModel(name, provider=GoogleProvider(api_key=settings.gemini_api_key))
        case "groq":
            return GroqModel(name, provider=GroqProvider(api_key=settings.groq_api_key))
        case "openrouter":
            return OpenAIChatModel(name, provider=OpenRouterProvider(api_key=settings.openrouter_api_key))
        case "mock":
            from app.agents.mock import build_mock_model

            return build_mock_model()
        case _:  # ollama
            return OpenAIChatModel(name, provider=OllamaProvider(base_url=f"{settings.ollama_base_url.rstrip('/')}/v1"))
