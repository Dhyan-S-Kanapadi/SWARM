"""Groq JSON completion helper."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from groq import APIStatusError, Groq, RateLimitError

from backend.utils import parse_json_text

DEFAULT_GROQ_MODELS = (
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
)


class GroqJsonError(RuntimeError):
    """Raised when a Groq JSON completion cannot be completed."""


class MissingGroqApiKeyError(GroqJsonError):
    """Raised when a live Groq call is requested without an API key."""


class GroqRequestTooLargeError(GroqJsonError):
    """Raised when Groq rejects a request as too large."""


@dataclass(frozen=True)
class GroqJsonConfig:
    """Runtime configuration for Groq JSON completions."""

    api_key: str | None
    models: tuple[str, ...]
    temperature: float
    max_tokens: int
    timeout_seconds: float
    rate_limit_retries: int
    rate_limit_delay_seconds: float

    @classmethod
    def from_env(cls) -> "GroqJsonConfig":
        return cls(
            api_key=os.getenv("GROQ_API_KEY") or None,
            models=_models_from_env(),
            temperature=float(os.getenv("GROQ_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("GROQ_MAX_TOKENS", "2048")),
            timeout_seconds=float(os.getenv("GROQ_TIMEOUT_SECONDS", "30")),
            rate_limit_retries=int(os.getenv("GROQ_RATE_LIMIT_RETRIES", "2")),
            rate_limit_delay_seconds=float(os.getenv("GROQ_RATE_LIMIT_DELAY_SECONDS", "2")),
        )


def complete_json(
    prompt: str,
    *,
    system_prompt: str = "Return only valid JSON. Do not include Markdown fences or commentary.",
    config: GroqJsonConfig | None = None,
) -> dict[str, Any]:
    """Request a JSON object from Groq and parse it into a dictionary."""
    parsed = complete_json_value(prompt, system_prompt=system_prompt, config=config)
    if not isinstance(parsed, dict):
        raise GroqJsonError("Expected Groq response to parse to a JSON object.")
    return parsed


def complete_json_value(
    prompt: str,
    *,
    system_prompt: str = "Return only valid JSON. Do not include Markdown fences or commentary.",
    config: GroqJsonConfig | None = None,
) -> Any:
    """Request JSON from Groq and parse any valid JSON value."""
    resolved_config = config or GroqJsonConfig.from_env()
    if not resolved_config.api_key:
        raise MissingGroqApiKeyError("GROQ_API_KEY is required for Groq completions.")

    client = Groq(
        api_key=resolved_config.api_key,
        timeout=resolved_config.timeout_seconds,
        max_retries=0,
    )

    last_error: Exception | None = None
    for model in resolved_config.models:
        try:
            content = _chat_completion(client, model, system_prompt, prompt, resolved_config)
            return _parse_or_repair(client, model, system_prompt, content, resolved_config)
        except GroqRequestTooLargeError:
            raise
        except APIStatusError as exc:
            last_error = exc
            if exc.status_code in {401, 403}:
                raise GroqJsonError(f"Groq authentication failed with status {exc.status_code}.") from exc
            if exc.status_code == 413:
                raise GroqRequestTooLargeError("Groq rejected the request as too large.") from exc
        except (RateLimitError, GroqJsonError) as exc:
            last_error = exc

    raise GroqJsonError("Groq JSON completion failed for all configured models.") from last_error


def _chat_completion(
    client: Groq,
    model: str,
    system_prompt: str,
    prompt: str,
    config: GroqJsonConfig,
) -> str:
    for attempt in range(config.rate_limit_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=config.temperature,
                max_completion_tokens=config.max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                raise GroqJsonError("Groq returned an empty response.")
            return content
        except RateLimitError:
            if attempt >= config.rate_limit_retries:
                raise
            time.sleep(config.rate_limit_delay_seconds)
        except APIStatusError as exc:
            if exc.status_code == 413:
                raise GroqRequestTooLargeError("Groq rejected the request as too large.") from exc
            raise

    raise GroqJsonError("Groq completion failed after rate limit retries.")


def _parse_or_repair(
    client: Groq,
    model: str,
    system_prompt: str,
    content: str,
    config: GroqJsonConfig,
) -> Any:
    try:
        return parse_json_text(content)
    except ValueError as exc:
        repair_prompt = (
            "Repair this response into valid JSON only. Preserve the intended data and "
            "return no Markdown or commentary.\n\n"
            f"{content}"
        )
        repaired = _chat_completion(client, model, system_prompt, repair_prompt, config)
        try:
            return parse_json_text(repaired)
        except ValueError as repair_exc:
            raise GroqJsonError("Groq response could not be parsed as JSON.") from repair_exc
        except Exception as repair_exc:
            raise GroqJsonError("Groq JSON repair failed.") from repair_exc
    except Exception as exc:
        raise GroqJsonError("Groq response could not be parsed as JSON.") from exc


def _models_from_env() -> tuple[str, ...]:
    configured_models = os.getenv("GROQ_MODELS")
    if configured_models:
        models = tuple(model.strip() for model in configured_models.split(",") if model.strip())
        if models:
            return models

    single_model = os.getenv("GROQ_MODEL")
    if single_model:
        return (single_model, *tuple(model for model in DEFAULT_GROQ_MODELS if model != single_model))

    return DEFAULT_GROQ_MODELS
