import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import litellm

from job_kick.core.config import Credentials, JobqConfig, LLMConfig, get_api_key

litellm.telemetry = False
logger = logging.getLogger(__name__)

Message = dict[str, Any]


class LLMClient:
    def __init__(self, cfg: LLMConfig, api_key: str) -> None:
        self._model = f"{cfg.provider}/{cfg.model}"
        self._api_key = api_key

    @classmethod
    def from_config(cls, cfg: JobqConfig, creds: Credentials) -> "LLMClient":
        if cfg.llm is None:
            raise RuntimeError("LLM not configured.")
        resolved = get_api_key(cfg.llm.provider, creds)
        if resolved is None:
            raise RuntimeError(f"No API key for {cfg.llm.provider}.")
        api_key, _ = resolved
        return cls(cfg.llm, api_key)

    async def complete(self, messages: list[Message], **kwargs: Any) -> str:
        logger.debug("complete model=%s messages=%d", self._model, len(messages))
        started = time.monotonic()
        resp = await litellm.acompletion(
            model=self._model,
            messages=messages,
            api_key=self._api_key,
            **kwargs,
        )
        content = resp.choices[0].message.content or ""
        logger.debug(
            "complete done model=%s elapsed=%.2fs response_chars=%d",
            self._model,
            time.monotonic() - started,
            len(content),
        )
        return content

    async def stream(
        self, messages: list[Message], **kwargs: Any
    ) -> AsyncIterator[str]:
        logger.debug("stream model=%s messages=%d", self._model, len(messages))
        resp = await litellm.acompletion(
            model=self._model,
            messages=messages,
            api_key=self._api_key,
            stream=True,
            **kwargs,
        )
        async for chunk in resp:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
