import os
import re
import time
from typing import Any

from dotenv import load_dotenv
from groq import Groq

from backend.utils import parse_json_response

load_dotenv()

DEFAULT_MODEL = "llama-3.1-8b-instant"
DEFAULT_FALLBACK_MODELS = "llama-3.1-8b-instant"
DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_RATE_LIMIT_RETRY_SECONDS = 20
DEFAULT_REQUEST_TOKEN_BUDGET = 5600
PLACEHOLDER_API_KEYS = {
    "",
    "your_groq_api_key_here",
    "your-groq-api-key-here",
    "replace_me",
    "changeme",
}
AGENT_MIN_TOKENS = {
    "analyst": 2200,
    "architect": 2400,
    "builder": 4200,
    "pitcher": 900,
}


class LLMUnavailableError(RuntimeError):
    pass


def groq_api_key() -> str:
    raw_key = os.getenv("GROQ_API_KEY", "").strip().strip('"').strip("'")
    if raw_key.lower() in PLACEHOLDER_API_KEYS:
        return ""
    return raw_key


def groq_configured() -> bool:
    return bool(groq_api_key())


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


def call_groq_json(
    *,
    agent_name: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    api_key = groq_api_key()
    if not api_key:
        raise LLMUnavailableError("GROQ_API_KEY is not set")

    model = os.getenv("GROQ_MODEL", DEFAULT_MODEL)
    token_cap = _agent_token_cap(agent_name, max_tokens)
    client = Groq(api_key=api_key, timeout=float(os.getenv("GROQ_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)))

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    content = _create_completion_with_model_fallback(
        client=client,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=token_cap,
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
                    f"Parser error from previous attempt: {parse_exc}"
                ),
            },
        ]
        repaired = _create_completion_with_model_fallback(
            client=client,
            model=model,
            messages=repair_messages,
            temperature=0.1,
            max_tokens=repair_token_cap,
        )
        return parse_json_response(repaired)


def _agent_token_cap(agent_name: str, fallback: int) -> int:
    key = f"GROQ_{agent_name.upper()}_MAX_TOKENS"
    minimum = AGENT_MIN_TOKENS.get(agent_name.lower(), 256)
    try:
        return max(minimum, int(os.getenv(key, fallback)))
    except ValueError:
        return max(minimum, fallback)


def _repair_token_cap(agent_name: str, token_cap: int) -> int:
    repair_key = f"GROQ_{agent_name.upper()}_REPAIR_MAX_TOKENS"
    default_cap = min(6000, max(token_cap + 1200, round(token_cap * 1.4)))
    try:
        return max(token_cap, int(os.getenv(repair_key, default_cap)))
    except ValueError:
        return default_cap


def _create_completion_with_model_fallback(
    *,
    client: Groq,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> str:
    last_error: Exception | None = None
    for candidate_model in _model_candidates(model):
        try:
            return _create_completion_with_short_retry(
                client=client,
                model=candidate_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            last_error = exc
            if not _should_try_next_model(str(exc)):
                raise
    if last_error:
        raise last_error
    raise LLMUnavailableError("No Groq models configured")


def _model_candidates(primary_model: str) -> list[str]:
    configured = os.getenv("GROQ_FALLBACK_MODELS", DEFAULT_FALLBACK_MODELS)
    candidates = [primary_model]
    candidates.extend(model.strip() for model in configured.split(",") if model.strip())
    deduped = []
    for model in candidates:
        if model not in deduped:
            deduped.append(model)
    return deduped


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
        )
    )


def _create_completion_with_short_retry(
    *,
    client: Groq,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> str:
    fitted_max_tokens = _fit_max_tokens(messages, max_tokens)
    try:
        return _create_completion(
            client=client,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=fitted_max_tokens,
        )
    except Exception as exc:
        reduced_max_tokens = _reduced_max_tokens_after_413(str(exc), fitted_max_tokens)
        if reduced_max_tokens:
            return _create_completion(
                client=client,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=reduced_max_tokens,
            )
        wait_seconds = _retry_after_seconds(str(exc))
        retry_limit = int(os.getenv("GROQ_RATE_LIMIT_RETRY_SECONDS", DEFAULT_RATE_LIMIT_RETRY_SECONDS))
        if wait_seconds is None or wait_seconds > retry_limit:
            raise
        time.sleep(max(1, wait_seconds))
        return _create_completion(
            client=client,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=fitted_max_tokens,
        )


def _create_completion(
    *,
    client: Groq,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or "{}"


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
    try:
        return max(1500, int(os.getenv("GROQ_REQUEST_TOKEN_BUDGET", DEFAULT_REQUEST_TOKEN_BUDGET)))
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
    return reduced if reduced >= 512 and reduced < current_max_tokens else None
