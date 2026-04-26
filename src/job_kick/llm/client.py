from collections.abc import AsyncIterator
from typing import Any

import litellm

from job_kick.core.config import Credentials, JobqConfig, LLMConfig, get_api_key

litellm.telemetry = False

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
        resp = await litellm.acompletion(
            model=self._model,
            messages=messages,
            api_key=self._api_key,
            **kwargs,
        )
        return resp.choices[0].message.content or ""

    async def stream(
        self, messages: list[Message], **kwargs: Any
    ) -> AsyncIterator[str]:
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
