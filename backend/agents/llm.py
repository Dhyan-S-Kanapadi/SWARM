"""LiteLLM-backed routing for SWARM's LLM-dependent agents."""

from __future__ import annotations

import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from litellm import completion

from backend.utils import parse_json_response


load_dotenv()

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_RATE_LIMIT_RETRY_SECONDS = 20
DEFAULT_REQUEST_TOKEN_BUDGET = 5600
PLACEHOLDER_API_KEYS = {
    "",
    "your_groq_api_key_here",
    "your-groq-api-key-here",
    "your_api_key_here",
    "replace_me",
    "changeme",
}
AGENT_MIN_TOKENS = {
    "analyst": 2200,
    "architect": 2400,
    "builder": 4200,
    "pitcher": 900,
}
_PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "azure": "AZURE_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "xai": "XAI_API_KEY",
}


class LLMUnavailableError(RuntimeError):
    pass


def groq_api_key() -> str:
    """Return the legacy Groq key when it is configured with a real value."""

    return _clean_api_key(os.getenv("GROQ_API_KEY", ""))


def groq_configured() -> bool:
    return bool(groq_api_key())


def llm_model_for_agent(agent_name: str) -> str:
    """Resolve a LiteLLM provider/model string for one SWARM agent.

    Set ``LLM_<AGENT>_MODEL`` for an explicit route, for example
    ``anthropic/claude-sonnet-4-5-20250929``. Existing ``GROQ_MODEL``
    configuration remains a backward-compatible Groq default.
    """

    agent_key = _agent_env_key(agent_name)
    configured = os.getenv(f"LLM_{agent_key}_MODEL") or os.getenv("LLM_DEFAULT_MODEL")
    if configured and configured.strip():
        return configured.strip()

    legacy_model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
    return legacy_model if legacy_model.startswith("groq/") else f"groq/{legacy_model}"


def llm_provider_for_agent(agent_name: str) -> str:
    model = llm_model_for_agent(agent_name)
    return model.split("/", maxsplit=1)[0] if "/" in model else "unknown"


def llm_configuration_status() -> dict[str, dict[str, Any]]:
    """Return safe per-agent routing metadata for health reporting."""

    return {
        agent: {
            "model": llm_model_for_agent(agent),
            "provider": llm_provider_for_agent(agent),
            "configured": _agent_has_credentials(agent),
        }
        for agent in ("analyst", "architect", "pitcher")
    }


def allow_llm_fallback() -> bool:
    return os.getenv("SWARM_ALLOW_LLM_FALLBACK", "false").strip().lower() in {"1", "true", "yes", "on"}


def allow_bakery_website_fallback(idea: str) -> bool:
    enabled = os.getenv("SWARM_ALLOW_BAKERY_WEBSITE_FALLBACK", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return False
    lowered = idea.lower()
    return any(keyword in lowered for keyword in ("bakery", "cake", "cakes", "baker", "pastry", "bread"))


def allow_saloon_website_fallback(idea: str) -> bool:
    enabled = os.getenv("SWARM_ALLOW_SALOON_WEBSITE_FALLBACK", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return False
    lowered = idea.lower()
    return any(keyword in lowered for keyword in ("salon", "saloon", "beauty", "spa", "hair", "makeup", "barber"))


def allow_fallback_for_idea(idea: str) -> bool:
    return allow_llm_fallback() or allow_bakery_website_fallback(idea) or allow_saloon_website_fallback(idea)


def call_llm_json(
    *,
    agent_name: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    """Call the configured LiteLLM route and return a parsed JSON object."""

    if not _agent_has_credentials(agent_name):
        raise LLMUnavailableError(
            f"No API key is configured for {agent_name}. Set LLM_{_agent_env_key(agent_name)}_API_KEY "
            f"or the provider's standard API key environment variable."
        )

    token_cap = _agent_token_cap(agent_name, max_tokens)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    content = _create_completion_with_model_fallback(
        agent_name=agent_name,
        messages=messages,
        temperature=temperature,
        max_tokens=token_cap,
        **_json_generation_options(agent_name),
    )

    try:
        return parse_json_response(content)
    except Exception as parse_exc:
        repair_token_cap = _repair_token_cap(agent_name, token_cap)
        repair_messages = [
            {
                "role": "system",
                "content": (
                    f"{system_prompt}\n\n"
                    "Your previous response was invalid or truncated. Return a complete JSON object only. "
                    "Use compact JSON with no markdown. Keep array items concise, but include every required top-level key."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{user_content}\n\n"
                    "Return the full corrected JSON now. Do not continue the old text. "
                    f"Parser error from previous attempt: {parse_exc}\n\n"
                    "Previous invalid response follows. Correct it into one complete JSON object:\n"
                    f"{_repairable_response_excerpt(content)}"
                ),
            },
        ]
        repaired = _create_completion_with_model_fallback(
            agent_name=agent_name,
            messages=repair_messages,
            temperature=0.1,
            max_tokens=repair_token_cap,
            **_json_generation_options(agent_name),
        )
        return parse_json_response(repaired)


# Compatibility for callers outside this repository that still import the old name.
call_groq_json = call_llm_json


def _create_completion_with_model_fallback(
    *,
    agent_name: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    response_format: dict[str, str] | None = None,
    extra_body: dict[str, Any] | None = None,
) -> str:
    last_error: Exception | None = None
    for candidate_model in _model_candidates(agent_name):
        try:
            return _create_completion(
                model=candidate_model,
                api_key=_api_key_for_agent(agent_name, candidate_model),
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                extra_body=extra_body,
            )
        except Exception as exc:
            last_error = exc
            if not _should_try_next_model(str(exc)):
                raise
    if last_error:
        raise last_error
    raise LLMUnavailableError(f"No models are configured for {agent_name}")


def _model_candidates(agent_name: str) -> list[str]:
    agent_key = _agent_env_key(agent_name)
    primary = llm_model_for_agent(agent_name)
    configured = os.getenv(f"LLM_{agent_key}_FALLBACK_MODELS") or os.getenv("LLM_FALLBACK_MODELS")
    if not configured:
        legacy = os.getenv("GROQ_FALLBACK_MODELS", "")
        configured = ",".join(
            model if model.startswith("groq/") else f"groq/{model}"
            for model in legacy.split(",")
            if model.strip()
        )
    candidates = [primary, *(model.strip() for model in configured.split(",") if model.strip())]
    return list(dict.fromkeys(candidates))


def _create_completion(
    *,
    model: str,
    api_key: str | None,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    response_format: dict[str, str] | None = None,
    extra_body: dict[str, Any] | None = None,
) -> str:
    fitted_max_tokens = _fit_max_tokens(messages, max_tokens)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": fitted_max_tokens,
        "timeout": float(os.getenv("LLM_TIMEOUT_SECONDS", os.getenv("GROQ_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))),
        "num_retries": 1,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if response_format:
        kwargs["response_format"] = response_format
    if extra_body:
        kwargs["extra_body"] = extra_body
    try:
        response = completion(**kwargs)
    except Exception as exc:
        reduced_max_tokens = _reduced_max_tokens_after_413(str(exc), fitted_max_tokens)
        if reduced_max_tokens:
            kwargs["max_tokens"] = reduced_max_tokens
            response = completion(**kwargs)
            content = response.choices[0].message.content
            return content if isinstance(content, str) else "{}"
        wait_seconds = _retry_after_seconds(str(exc))
        retry_limit = int(os.getenv("LLM_RATE_LIMIT_RETRY_SECONDS", os.getenv("GROQ_RATE_LIMIT_RETRY_SECONDS", DEFAULT_RATE_LIMIT_RETRY_SECONDS)))
        if wait_seconds is None or wait_seconds > retry_limit:
            raise
        time.sleep(max(1, wait_seconds))
        response = completion(**kwargs)
    content = response.choices[0].message.content
    return content if isinstance(content, str) else "{}"


def _json_generation_options(agent_name: str) -> dict[str, Any]:
    """Return provider-specific controls needed for valid structured output.

    NVIDIA Nemotron models can emit reasoning text before their answer. JSON mode and
    disabling that reasoning ensure Architect receives one parseable object instead.
    Other providers retain their existing request format.
    """

    if llm_model_for_agent(agent_name).startswith("nvidia_nim/"):
        return {
            "response_format": {"type": "json_object"},
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }
    return {}


def _repairable_response_excerpt(content: str, limit: int = 24000) -> str:
    """Keep parser repair context bounded while preserving the malformed object."""

    if len(content) <= limit:
        return content
    return f"{content[:limit]}\n[response truncated for repair context]"


def _api_key_for_agent(agent_name: str, model: str) -> str | None:
    agent_key = _agent_env_key(agent_name)
    provider = model.split("/", maxsplit=1)[0]
    if provider == llm_provider_for_agent(agent_name):
        configured = _clean_api_key(os.getenv(f"LLM_{agent_key}_API_KEY", ""))
        if configured:
            return configured
    configured = _clean_api_key(os.getenv("LLM_API_KEY", ""))
    if configured:
        return configured
    key_env = _PROVIDER_KEY_ENV.get(provider)
    return _clean_api_key(os.getenv(key_env, "")) if key_env else None


def _agent_has_credentials(agent_name: str) -> bool:
    return any(_api_key_for_agent(agent_name, model) for model in _model_candidates(agent_name))


def _clean_api_key(value: str) -> str:
    cleaned = value.strip().strip('"').strip("'")
    return "" if cleaned.lower() in PLACEHOLDER_API_KEYS else cleaned


def _agent_env_key(agent_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", agent_name).upper()


def _agent_token_cap(agent_name: str, fallback: int) -> int:
    key = _agent_env_key(agent_name)
    minimum = AGENT_MIN_TOKENS.get(agent_name.lower(), 256)
    configured = os.getenv(f"LLM_{key}_MAX_TOKENS") or os.getenv(f"GROQ_{key}_MAX_TOKENS")
    try:
        return max(minimum, int(configured if configured is not None else fallback))
    except ValueError:
        return max(minimum, fallback)


def _repair_token_cap(agent_name: str, token_cap: int) -> int:
    key = _agent_env_key(agent_name)
    default_cap = min(6000, max(token_cap + 1200, round(token_cap * 1.4)))
    configured = os.getenv(f"LLM_{key}_REPAIR_MAX_TOKENS") or os.getenv(f"GROQ_{key}_REPAIR_MAX_TOKENS")
    try:
        return max(token_cap, int(configured if configured is not None else default_cap))
    except ValueError:
        return default_cap


def _should_try_next_model(message: str) -> bool:
    lowered = message.lower()
    if "invalid api key" in lowered or "authentication" in lowered:
        return False
    return any(
        signal in lowered
        for signal in (
            "rate_limit",
            "rate limit",
            "tokens per day",
            "request too large",
            "model",
            "timeout",
            "temporarily unavailable",
            "connection",
        )
    )


def _retry_after_seconds(message: str) -> int | None:
    match = re.search(r"try again in (?:(\d+)m)?\s*([0-9.]+)s", message, re.IGNORECASE)
    if not match:
        return None
    minutes = int(match.group(1) or 0)
    seconds = float(match.group(2))
    return round(minutes * 60 + seconds)


def _fit_max_tokens(messages: list[dict[str, str]], requested_max_tokens: int) -> int:
    budget = _request_token_budget()
    input_estimate = _estimate_message_tokens(messages)
    available = budget - input_estimate
    if available <= 0:
        return max(512, min(requested_max_tokens, 900))
    return max(512, min(requested_max_tokens, available))


def _request_token_budget() -> int:
    configured = os.getenv("LLM_REQUEST_TOKEN_BUDGET") or os.getenv("GROQ_REQUEST_TOKEN_BUDGET", DEFAULT_REQUEST_TOKEN_BUDGET)
    try:
        return max(1500, int(configured))
    except ValueError:
        return DEFAULT_REQUEST_TOKEN_BUDGET


def _estimate_message_tokens(messages: list[dict[str, str]]) -> int:
    chars = sum(len(message.get("content", "")) for message in messages)
    overhead = 12 * len(messages)
    return round(chars / 4) + overhead


def _reduced_max_tokens_after_413(message: str, current_max_tokens: int) -> int | None:
    lowered = message.lower()
    if "request too large" not in lowered and "requested" not in lowered:
        return None
    limit_match = re.search(r"limit\s+(\d+)", message, re.IGNORECASE)
    requested_match = re.search(r"requested\s+(\d+)", message, re.IGNORECASE)
    if not limit_match or not requested_match:
        return max(512, current_max_tokens - 800) if current_max_tokens > 1200 else None
    limit = int(limit_match.group(1))
    requested = int(requested_match.group(1))
    overage = max(0, requested - limit)
    reduced = current_max_tokens - overage - 250
    return reduced if 512 <= reduced < current_max_tokens else None
