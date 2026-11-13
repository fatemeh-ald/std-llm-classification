"""Thin wrappers around the three API styles used in the study.

Supported providers
-------------------
chat        OpenAI-compatible Chat Completions API (used for DeepSeek-V3.1)
responses   OpenAI-compatible Responses API        (used for GPT-4.1)
anthropic   Anthropic Messages API                 (used for Claude Sonnet 5)
"""

from __future__ import annotations

from typing import Any, Optional

PROVIDERS = ("chat", "responses", "anthropic")

# AvalAI gateway endpoints. The Anthropic SDK appends /v1/messages itself,
# so its base URL must NOT end with /v1.
DEFAULT_BASE_URLS = {
    "chat": "https://api.avalai.ir/v1",
    "responses": "https://api.avalai.ir/v1",
    "anthropic": "https://api.avalai.ir",
}


def build_client(
    provider: str, api_key: str, base_url: Optional[str] = None, timeout: float = 120.0
) -> Any:
    """Create an SDK client. Retries are handled by the caller, not the SDK."""
    base_url = base_url or DEFAULT_BASE_URLS[provider]

    if provider == "anthropic":
        from anthropic import Anthropic

        return Anthropic(
            api_key=api_key, base_url=base_url, max_retries=0, timeout=timeout
        )

    from openai import OpenAI

    return OpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=timeout)


def complete(
    client: Any,
    provider: str,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Send one request and return the model's text output (stripped).

    ``temperature`` and ``max_tokens`` are only sent when explicitly given, so
    omitting them reproduces the provider's default behaviour.
    """
    if provider == "chat":
        kwargs: dict[str, Any] = dict(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        response = client.chat.completions.create(**kwargs)
        return (response.choices[0].message.content or "").strip()

    if provider == "responses":
        kwargs = dict(model=model, instructions=system_prompt, input=user_message)
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        response = client.responses.create(**kwargs)
        return (response.output_text or "").strip()

    if provider == "anthropic":
        kwargs = dict(
            model=model,
            max_tokens=max_tokens or 4000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        # Some Claude models reject sampling parameters; only send if requested.
        if temperature is not None:
            kwargs["temperature"] = temperature
        response = client.messages.create(**kwargs)
        return "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ).strip()

    raise ValueError(f"Unknown provider: {provider!r}")
