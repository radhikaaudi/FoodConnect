"""Strands SDK integration layer — detection and model providers.

This module isolates everything that depends on the Strands Agents SDK so the rest of the
codebase (and the offline demo) never breaks when the SDK or AWS credentials are absent.

Three ways to run the *real* agent brain:
  * ``bedrock`` (default) — Amazon Bedrock, the production path for AgentCore.
  * ``ollama``            — a free local model (e.g. llama3.2) so you can run a genuinely
                            LLM-driven agent at $0 with no cloud account.
  * ``litellm``           — any LiteLLM-supported provider.

If none are available, the caller falls back to the deterministic ``SimulatedBrain`` and the
product still runs end to end.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

try:  # pragma: no cover - depends on environment
    from strands import Agent, tool  # noqa: F401

    STRANDS_AVAILABLE = True
except Exception:
    STRANDS_AVAILABLE = False

    def tool(func: Callable) -> Callable:  # no-op decorator for the offline path
        return func


DEFAULT_BEDROCK_MODEL = "us.anthropic.claude-sonnet-4-20250514-v1:0"
DEFAULT_OLLAMA_MODEL = "llama3.2"


def _bedrock_credentials_present() -> bool:
    """True only when boto3 can actually resolve AWS credentials (fast, no network)."""
    try:
        import boto3

        return boto3.Session().get_credentials() is not None
    except Exception:
        return False


def _ollama_reachable(host: str) -> bool:
    """True only when a local Ollama server answers (sub-second probe)."""
    try:
        import urllib.request

        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=1.5):
            return True
    except Exception:
        return False


def make_model(provider: Optional[str] = None, model_id: Optional[str] = None) -> Any:
    """Construct a Strands model for the chosen provider, or return None if unavailable.

    Provider resolves from the argument, then the ``FOODBRIDGE_MODEL_PROVIDER`` env var,
    then defaults to Bedrock. Returns None when the provider cannot actually serve calls
    (no AWS credentials / no running Ollama), so callers can fall back honestly instead of
    advertising an LLM that would silently fail.
    """
    if not STRANDS_AVAILABLE:
        return None
    provider = (provider or os.getenv("FOODBRIDGE_MODEL_PROVIDER") or "bedrock").lower()

    try:
        if provider == "ollama":
            host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            if not _ollama_reachable(host):
                return None
            from strands.models.ollama import OllamaModel

            return OllamaModel(
                host=host,
                model_id=model_id or os.getenv("FOODBRIDGE_MODEL_ID", DEFAULT_OLLAMA_MODEL),
            )
        if provider == "litellm":
            from strands.models.litellm import LiteLLMModel

            return LiteLLMModel(
                model_id=model_id or os.getenv("FOODBRIDGE_MODEL_ID", "gpt-4o-mini")
            )
        # default: bedrock
        if not _bedrock_credentials_present():
            return None
        from strands.models import BedrockModel

        return BedrockModel(
            model_id=model_id or os.getenv("FOODBRIDGE_MODEL_ID", DEFAULT_BEDROCK_MODEL)
        )
    except Exception:
        return None
