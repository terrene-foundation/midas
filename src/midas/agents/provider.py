"""Frontier LLM provider with automatic fallback.

Uses httpx.AsyncClient for OpenAI-compatible API calls.
Reads API key and model names from environment variables.
"""

import os

import httpx
import structlog

logger = structlog.get_logger("midas.agents.provider")

API_BASE_URL = "https://api.openai.com/v1/chat/completions"
MODELS_URL = "https://api.openai.com/v1/models"


class FrontierProvider:
    """Frontier LLM provider with automatic fallback.

    Calls the OpenAI-compatible chat completions endpoint. If the primary
    model fails (network error, rate limit, etc.), falls back to the
    fallback model automatically.
    """

    def __init__(
        self,
        primary_model: str | None = None,
        fallback_model: str | None = None,
    ):
        self.primary_model = primary_model or os.environ.get("OPENAI_PROD_MODEL", "gpt-4")
        self.fallback_model = fallback_model or os.environ.get("FALLBACK_LLM_MODEL", "gpt-4")
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the httpx async client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        """Build authorization headers from environment."""
        api_key = os.environ.get("OPENAI_API_KEY", "")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def complete(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict:
        """Complete with fallback.

        Returns dict with 'content', 'model', and 'provider' keys.
        """
        client = self._get_client()

        for model in [self.primary_model, self.fallback_model]:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            try:
                response = await client.post(
                    API_BASE_URL,
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info(
                    "provider.complete",
                    model=model,
                    tokens=data.get("usage", {}).get("total_tokens", 0),
                )
                return {
                    "content": content,
                    "model": model,
                    "provider": "openai",
                }
            except Exception as exc:
                logger.warning(
                    "provider.complete.fallback",
                    model=model,
                    error=str(exc),
                )
                if model == self.fallback_model:
                    raise
                continue

        # Unreachable, but satisfies type checkers
        raise RuntimeError("No model available")

    async def health_check(self) -> dict:
        """Check provider availability.

        Returns dict with 'available' (bool) and 'model' (str) keys.
        """
        client = self._get_client()
        try:
            response = await client.get(
                MODELS_URL,
                headers=self._headers(),
            )
            response.raise_for_status()
            return {
                "available": True,
                "model": self.primary_model,
            }
        except Exception as exc:
            logger.warning("provider.health_check.failed", error=str(exc))
            return {
                "available": False,
                "model": self.primary_model,
                "error": str(exc),
            }

    async def close(self):
        """Close the underlying httpx client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
