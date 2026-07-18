"""
core/llm_client.py — Unified LLM fallback chain for ScenePilot AI.

Provider order
──────────────
  1. Groq  llama-3.3-70b-versatile   (primary — best quality)
  2. Groq  llama-3.1-8b-instant      (secondary — separate quota, same key)
  3. Gemini gemini-2.5-flash          (tertiary — different provider entirely)

On any 429 / quota error the chain moves to the next provider automatically,
logs a Prometheus warning counter, and records which provider was used in the
returned metadata so the span can surface it in the UI.

All callers (story_generator.py) go through a single function:

    raw, tokens, provider = llm_call(system, user, max_tokens)

This replaces the previous scattered _call_groq / _call_gemini pattern and
ensures every future provider addition is made in exactly one place.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Provider constants ────────────────────────────────────────────────────────

GROQ_PRIMARY_MODEL   = "llama-3.3-70b-versatile"
GROQ_FALLBACK_MODEL  = os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
GEMINI_MODEL         = "gemini-2.5-flash"

# Strings that identify a quota / rate-limit error across both SDKs
_QUOTA_MARKERS = ("rate_limit_exceeded", "429", "quota", "RESOURCE_EXHAUSTED")


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(m.lower() in msg for m in _QUOTA_MARKERS)


# ── Individual provider callers ───────────────────────────────────────────────

def _call_groq_model(
    model: str, system: str, user: str, max_tokens: int
) -> tuple[str, int]:
    from groq import Groq  # type: ignore
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.7,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content or ""
    tokens  = response.usage.total_tokens if response.usage else 0
    return content, tokens


def _call_gemini_model(
    system: str, user: str, max_tokens: int
) -> tuple[str, int]:
    import google.generativeai as genai  # type: ignore
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model    = genai.GenerativeModel(GEMINI_MODEL)
    prompt   = system + "\n\n" + user
    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.7, "max_output_tokens": max_tokens},
    )
    content = response.text or ""
    tokens  = (
        getattr(getattr(response, "usage_metadata", None), "total_token_count", 0)
        or 0
    )
    return content, tokens


# ── Public entry point ────────────────────────────────────────────────────────

def llm_call(
    system: str,
    user: str,
    max_tokens: int = 8_192,
) -> tuple[str, int, str]:
    """Call LLMs in fallback order. Returns (content, tokens, provider_used).

    provider_used is one of:
        'groq-primary'   groq llama-3.3-70b-versatile
        'groq-fallback'  groq llama-3.1-8b-instant  (separate daily quota)
        'gemini'         gemini-2.5-flash

    Raises ProviderQuotaExhausted if all three providers are rate-limited.
    Raises the last non-quota exception if all providers fail for other reasons.
    """
    # Lazy import here so the module can be imported without telemetry being
    # initialised (e.g. in unit tests).
    try:
        from core.telemetry import PROVIDER_QUOTA_HITS  # type: ignore
    except Exception:
        PROVIDER_QUOTA_HITS = None  # telemetry optional

    errors: list[str] = []

    # ── 1. Groq primary ───────────────────────────────────────────────────────
    try:
        content, tokens = _call_groq_model(
            GROQ_PRIMARY_MODEL, system, user, max_tokens
        )
        return content, tokens, "groq-primary"
    except Exception as exc:
        if _is_quota_error(exc):
            logger.warning("Groq primary quota hit — falling back to groq-fallback. %s", exc)
            if PROVIDER_QUOTA_HITS:
                PROVIDER_QUOTA_HITS.labels(provider="groq-primary").inc()
            errors.append(f"groq-primary(429): {exc}")
        else:
            raise  # non-quota error — surface immediately

    # ── 2. Groq fallback (separate model = separate TPD quota) ───────────────
    try:
        content, tokens = _call_groq_model(
            GROQ_FALLBACK_MODEL, system, user, max_tokens
        )
        return content, tokens, "groq-fallback"
    except Exception as exc:
        if _is_quota_error(exc):
            logger.warning("Groq fallback quota hit — falling back to Gemini. %s", exc)
            if PROVIDER_QUOTA_HITS:
                PROVIDER_QUOTA_HITS.labels(provider="groq-fallback").inc()
            errors.append(f"groq-fallback(429): {exc}")
        else:
            raise

    # ── 3. Gemini ─────────────────────────────────────────────────────────────
    try:
        content, tokens = _call_gemini_model(system, user, max_tokens)
        return content, tokens, "gemini"
    except Exception as exc:
        if _is_quota_error(exc):
            logger.warning("Gemini quota hit — all providers exhausted. %s", exc)
            if PROVIDER_QUOTA_HITS:
                PROVIDER_QUOTA_HITS.labels(provider="gemini").inc()
            errors.append(f"gemini(429): {exc}")
            raise ProviderQuotaExhausted(
                "All LLM providers are rate-limited. "
                + " | ".join(errors)
            ) from exc
        else:
            raise


class ProviderQuotaExhausted(RuntimeError):
    """Raised when every provider in the chain returned a 429/quota error."""
