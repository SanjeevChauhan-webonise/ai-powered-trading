"""Optional Langfuse tracing via OpenTelemetry. Does nothing unless both Langfuse keys are configured."""

import base64
import logging
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from pydantic_ai import Agent
from pydantic_ai.models.instrumented import InstrumentationSettings

from app.core.config import Settings

log = logging.getLogger(__name__)
_provider: TracerProvider | None = None


def tracing_enabled(settings: Settings) -> bool:
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def setup_tracing(settings: Settings, processor: SpanProcessor | None = None) -> bool:
    """Configure OTel + Pydantic AI instrumentation. `processor` is a test seam replacing the Langfuse exporter."""
    global _provider
    if processor is None and not tracing_enabled(settings):
        log.info("Langfuse keys not set; tracing disabled")
        return False
    provider = TracerProvider(resource=Resource.create({"service.name": settings.app_name}))
    if processor is None:
        token = base64.b64encode(f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()).decode()
        exporter: SpanExporter = OTLPSpanExporter(
            endpoint=f"{settings.langfuse_host.rstrip('/')}/api/public/otel/v1/traces",
            headers={"Authorization": f"Basic {token}"},
        )
        processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    _provider = provider
    Agent.instrument_all(InstrumentationSettings(tracer_provider=provider))
    log.info("Langfuse tracing enabled (%s)", settings.langfuse_host)
    return True


def reset_tracing() -> None:
    global _provider
    if _provider is not None:
        _provider.shutdown()
    _provider = None
    Agent.instrument_all(False)


@contextmanager
def run_span(run_id: str, name: str = "pipeline_run") -> Iterator[None]:
    """One parent span per pipeline run so all agent/tool spans form a single Langfuse trace tagged with run_id."""
    tracer = _provider.get_tracer("app.pipeline") if _provider else trace.get_tracer("app.pipeline")
    attrs = {
        "run_id": run_id,
        "langfuse.session.id": run_id,
        "langfuse.trace.name": name,
        "langfuse.trace.tags": ["options-backtester"],
        "langfuse.trace.metadata.run_id": run_id,
    }
    with tracer.start_as_current_span(name, attributes=attrs):
        yield
