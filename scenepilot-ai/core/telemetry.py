"""
Prometheus metrics + OpenTelemetry tracer setup.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram, start_http_server  # type: ignore

# ── Prometheus counters / histograms ──────────────────────────────────────────

STORIES_GENERATED = Counter(
    "scenepilot_stories_generated_total",
    "Total approved stories generated",
)

VALIDATION_DURATION = Histogram(
    "scenepilot_validation_duration_seconds",
    "Time spent in sandbox validation",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

LOOP_DETECTIONS = Counter(
    "scenepilot_loop_detections_total",
    "Number of cycle/loop detections in story graphs",
)

STYLE_VIOLATIONS = Counter(
    "scenepilot_style_violations_total",
    "FAISS tone/format violations detected",
)

SANDBOX_REJECTIONS = Counter(
    "scenepilot_sandbox_rejections_total",
    "Stories rejected by the sandbox validator",
)

AGENT_TOKEN_SPEND = Counter(
    "scenepilot_agent_token_spend_total",
    "Total LLM tokens spent across all agents",
)

BUDGET_HALTS = Counter(
    "scenepilot_budget_halts_total",
    "Times the token budget ceiling was hit",
)

GUARDIAN_BLOCKS = Counter(
    "scenepilot_guardian_blocks_total",
    "Stories blocked by IBM Granite Guardian content safety check",
)

PROVIDER_QUOTA_HITS = Counter(
    "scenepilot_provider_quota_hits_total",
    "Times a provider returned 429/quota-exceeded — triggers fallback chain",
    ["provider"],   # label: groq-primary | groq-fallback | gemini
)

# ── OpenTelemetry tracer (no-op if OTEL_EXPORTER_OTLP_ENDPOINT not set) ───────

def get_tracer(name: str = "scenepilot"):
    try:
        from opentelemetry import trace  # type: ignore
        return trace.get_tracer(name)
    except ImportError:
        return None


def setup_otel() -> None:
    try:
        import os
        from opentelemetry import trace  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.trace.export.otlp.proto.grpc.trace_exporter import (  # type: ignore
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore

        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not endpoint:
            return
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
    except Exception:
        pass  # OTel is optional
