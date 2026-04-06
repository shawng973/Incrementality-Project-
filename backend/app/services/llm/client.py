"""
OpenRouter LLM client.

Wraps OpenRouter's OpenAI-compatible chat completions endpoint.
The model is sourced from settings so any OpenRouter-supported model
can be hot-swapped by changing LLM_MODEL in the environment — no code
changes required.

Ref: https://openrouter.ai/docs
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class OpenRouterClient:
    """Async HTTP client for OpenRouter chat completions."""

    def __init__(
        self,
        api_key: str,
        model: str,
        site_url: str = "",
        site_name: str = "",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": site_url,
            "X-Title": site_name,
        }
        self._timeout = timeout

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """
        Send a chat completion request and return the assistant's message.

        Args:
            messages:    List of {"role": "...", "content": "..."} dicts.
            temperature: Sampling temperature (lower = more deterministic).
            max_tokens:  Maximum tokens in the completion.

        Returns:
            LLMResponse with content and token usage.

        Raises:
            httpx.HTTPStatusError: If OpenRouter returns a non-2xx response.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            response = await http.post(
                OPENROUTER_URL,
                headers=self._headers,
                json=payload,
            )
            response.raise_for_status()

        body = response.json()
        choice = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})

        return LLMResponse(
            content=choice,
            model=body.get("model", self.model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )


def client_from_settings() -> OpenRouterClient:
    """Build a client from app settings. Import lazily to avoid circular deps."""
    from app.core.config import settings

    return OpenRouterClient(
        api_key=settings.openrouter_api_key,
        model=settings.llm_model,
        site_url=settings.llm_site_url,
        site_name=settings.llm_site_name,
    )
