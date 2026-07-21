"""
core/llm_client.py — Unified LLM fallback chain for ScenePilot AI.

Provider order
──────────────
  1. Groq  llama-3.3-70b-versatile   (primary — best quality)
  2. Groq  llama-3.1-8b-instant      (secondary — separate quota, same key)
  3. Gemini gemini-2.5-flash          (tertiary — different provider entirely)

On any 429 / quota error the chain first retries the same provider once
(with exponential backoff) before moving to the next provider.  Groq rate
limits are often transient (token-per-minute window resets in 1–5 s), so a
single cheap retry avoids burning the fallback quota unnecessarily.

Retry policy (per provider):
  attempt 1 → immediate
  attempt 2 → sleep RETRY_BASE_DELAY × 2^0  (default 2 s)
  (no further retries — escalate to next provider)

All callers (story_generator.py) go through a single function:

    raw, tokens, provider = llm_call(system, user, max_tokens)
"""
from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

# ── Provider constants ────────────────────────────────────────────────────────

GROQ_PRIMARY_MODEL   = "llama-3.3-70b-versatile"
GROQ_FALLBACK_MODEL  = os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
GEMINI_MODEL         = "gemini-2.5-flash"

# Strings that identify a quota / rate-limit error across both SDKs
_QUOTA_MARKERS = ("rate_limit_exceeded", "429", "quota", "RESOURCE_EXHAUSTED")

# Retry config — one retry per provider before escalating to the next
_RETRY_BASE_DELAY: float = float(os.environ.get("LLM_RETRY_DELAY", "2.0"))  # seconds
_MAX_RETRIES_PER_PROVIDER: int = 1   # 1 retry = 2 total attempts per provider


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

    def _with_retry(label: str, call, fallback_msg: str):
        """Attempt `call()` up to 1+_MAX_RETRIES_PER_PROVIDER times.

        On a quota error, sleep _RETRY_BASE_DELAY seconds and try once more
        before giving up and appending to `errors`.  Non-quota errors are
        re-raised immediately (they won't be fixed by waiting).

        Returns (content, tokens) on success, or None on quota exhaustion.
        """
        for attempt in range(1 + _MAX_RETRIES_PER_PROVIDER):
            try:
                return call()
            except Exception as exc:
                if not _is_quota_error(exc):
                    raise  # non-quota — surface immediately
                if attempt < _MAX_RETRIES_PER_PROVIDER:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "%s quota hit (attempt %d/%d) — retrying in %.1fs. %s",
                        label, attempt + 1, 1 + _MAX_RETRIES_PER_PROVIDER, delay, exc,
                    )
                    time.sleep(delay)
                else:
                    logger.warning("%s quota exhausted after retry — %s. %s", label, fallback_msg, exc)
                    if PROVIDER_QUOTA_HITS:
                        PROVIDER_QUOTA_HITS.labels(provider=label).inc()
                    errors.append(f"{label}(429): {exc}")
        return None  # all attempts failed with quota errors

    # ── 1. Groq primary ───────────────────────────────────────────────────────
    result = _with_retry(
        "groq-primary",
        lambda: _call_groq_model(GROQ_PRIMARY_MODEL, system, user, max_tokens),
        "falling back to groq-fallback",
    )
    if result is not None:
        return result[0], result[1], "groq-primary"

    # ── 2. Groq fallback (separate model = separate TPD quota) ───────────────
    result = _with_retry(
        "groq-fallback",
        lambda: _call_groq_model(GROQ_FALLBACK_MODEL, system, user, max_tokens),
        "falling back to Gemini",
    )
    if result is not None:
        return result[0], result[1], "groq-fallback"

    # ── 3. Gemini ─────────────────────────────────────────────────────────────
    result = _with_retry(
        "gemini",
        lambda: _call_gemini_model(system, user, max_tokens),
        "all providers exhausted",
    )
    if result is not None:
        return result[0], result[1], "gemini"

    raise ProviderQuotaExhausted(
        "All LLM providers are rate-limited after retries. "
        + " | ".join(errors)
    )


class ProviderQuotaExhausted(RuntimeError):
    """Raised when every provider in the chain returned a 429/quota error."""
