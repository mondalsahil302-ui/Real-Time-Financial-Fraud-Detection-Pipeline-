"""Gemini-only LLM provider configuration for fraud investigation tasks."""
from __future__ import annotations

import json
import logging
import math
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Protocol

LOGGER = logging.getLogger(__name__)
MAX_LLM_TIMEOUT_SECONDS = 60
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
LEGACY_GEMINI_MODELS = {
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
}


class LLMProvider(Protocol):
    provider: str
    model: str

    def generate(self, prompt: str, system_prompt: str | None = None) -> str: ...


class LLMProviderError(RuntimeError):
    def __init__(self, message: str, category: str = "provider_error"):
        super().__init__(message)
        self.category = category


class GeminiProvider:
    """Gemini Developer API provider used by the fraud investigation assistant."""

    def __init__(self, *, model=None, timeout=None, temperature=None, max_tokens=None, client=None,
                 sleep=time.sleep):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise LLMProviderError("GEMINI_API_KEY is not configured", "configuration_error")

        self.provider = "gemini"
        raw_model = (model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)).strip()
        if raw_model in LEGACY_GEMINI_MODELS:
            LOGGER.warning(
                "Using the supported Gemini default model instead of the retired model %s; "
                "Gemini 2.x Flash models are unavailable to new users.",
                raw_model,
            )
            raw_model = DEFAULT_GEMINI_MODEL
        self.model = raw_model or DEFAULT_GEMINI_MODEL
        try:
            configured_timeout = float(
                timeout if timeout is not None else os.getenv("LLM_TIMEOUT", "30")
            )
            self.temperature = float(
                temperature if temperature is not None else os.getenv("LLM_TEMPERATURE", "0.1")
            )
            self.max_tokens = int(
                max_tokens if max_tokens is not None else os.getenv("LLM_MAX_TOKENS", "2048")
            )
        except ValueError:
            raise LLMProviderError(
                "LLM timeout, temperature, and token limit must be numeric",
                "configuration_error",
            ) from None

        if (
            not self.model
            or not math.isfinite(configured_timeout)
            or configured_timeout <= 0
            or self.max_tokens <= 0
        ):
            raise LLMProviderError(
                "Gemini model must be set and timeout/token limit must be positive",
                "configuration_error",
            )
        self.timeout = min(configured_timeout, MAX_LLM_TIMEOUT_SECONDS)
        self._sleep = sleep

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise LLMProviderError(
                "The google-genai package is required for Gemini",
                "configuration_error",
            ) from None

        self._types = types
        try:
            self.client = client or genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=int(self.timeout * 1000),
                ),
            )
        except Exception as exc:
            raise LLMProviderError(
                "Could not initialize the Gemini client",
                "configuration_error",
            ) from exc

    @staticmethod
    def _status_code(error: Exception) -> int | None:
        raw_status = getattr(error, "status_code", None) or getattr(error, "code", None)
        try:
            return int(raw_status)
        except (TypeError, ValueError):
            return None

    def _category(self, error: Exception) -> tuple[str, bool]:
        status = self._status_code(error)
        class_name = type(error).__name__.lower()
        if "timeout" in class_name or isinstance(error, (TimeoutError, socket.timeout)):
            return "llm_timeout", True
        if status == 429 or (status is not None and status >= 500):
            return "endpoint_unavailable", True
        if status in (401, 403, 404):
            return "configuration_error", False
        if status is not None:
            return "provider_error", False
        if isinstance(error, (ConnectionError, OSError, urllib.error.URLError)):
            return "endpoint_unavailable", True
        return "provider_error", False

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        config = self._types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
            response_mime_type="application/json",
        )
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                content = getattr(response, "text", None)
                if not isinstance(content, str) or not content.strip():
                    raise LLMProviderError(
                        "Gemini returned an empty response",
                        "malformed_provider_response",
                    )
                return content
            except LLMProviderError:
                raise
            except Exception as exc:
                category, retryable = self._category(exc)
                if retryable and attempt < 2:
                    self._sleep(0.5 * (2 ** attempt))
                    continue
                if category == "configuration_error":
                    message = "The configured Gemini model or API key is not accessible"
                elif category == "llm_timeout":
                    message = "Gemini request timed out"
                elif category == "endpoint_unavailable":
                    message = "Gemini endpoint is unavailable"
                else:
                    message = "Gemini could not generate a response"
                raise LLMProviderError(message, category) from exc

        raise LLMProviderError("Gemini could not generate a response", "provider_error")

    def check_connection(self) -> dict:
        try:
            self.client.models.get(model=self.model)
        except Exception as exc:
            category, _ = self._category(exc)
            if category == "configuration_error":
                message = "The configured Gemini model or API key is not accessible"
            elif category == "llm_timeout":
                message = "Gemini model verification timed out"
            else:
                message = "Gemini model verification failed"
            raise LLMProviderError(message, category) from exc
        return {"provider": self.provider, "model": self.model, "status": "reachable"}

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            close()


def create_llm_provider(provider_name: str):
    name = (provider_name or "gemini").strip().lower()
    if name == "gemini":
        return GeminiProvider()
    raise LLMProviderError(
        "Gemini is the only supported LLM provider for this application.",
        "configuration_error",
    )


def verify_configured_chat_provider() -> dict:
    provider_name = (os.getenv("LLM_PROVIDER", "gemini") or "gemini").strip().lower()
    if provider_name != "gemini":
        return {
            "provider": "gemini",
            "model": os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            "status": "configuration error",
            "available": False,
            "detail": "Gemini is the only supported LLM provider; remove unsupported provider settings.",
            "rag_enabled": True,
            "fallback": "none",
        }

    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    if model in LEGACY_GEMINI_MODELS:
        model = DEFAULT_GEMINI_MODEL
    try:
        provider = GeminiProvider()
    except LLMProviderError as exc:
        return {
            "provider": "gemini",
            "model": model,
            "status": "configuration error",
            "available": False,
            "detail": str(exc),
            "rag_enabled": True,
            "fallback": "none",
        }
    try:
        provider.check_connection()
    except LLMProviderError as exc:
        return {
            "provider": provider.provider,
            "model": provider.model,
            "status": "configuration error" if exc.category == "configuration_error" else "unavailable",
            "available": False,
            "detail": str(exc),
            "rag_enabled": True,
            "fallback": "none",
        }
    finally:
        provider.close()
    return {
        "provider": provider.provider,
        "model": provider.model,
        "status": "ready",
        "available": True,
        "rag_enabled": True,
        "fallback": "none",
    }
