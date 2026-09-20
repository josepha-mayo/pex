"""OpenAI Chat Completions adapter with a fresh guarded transport per turn."""

from __future__ import annotations

from contextlib import asynccontextmanager

import openai
from strands.models.openai import OpenAIModel


class OpenAIChatModel(OpenAIModel):
    """Prevent a multi-turn agent from reusing an HTTP client closed after turn one."""

    def __init__(self, *, http_client_factory=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._http_client_factory = http_client_factory

    @classmethod
    def _format_regular_messages(cls, messages, **kwargs):
        """Drop provider reasoning blocks before the generic adapter warns about them."""

        cleaned = [
            {
                **message,
                "content": [
                    block for block in message["content"] if "reasoningContent" not in block
                ],
            }
            for message in messages
        ]
        return super()._format_regular_messages(cleaned, **kwargs)

    @asynccontextmanager
    async def _get_client(self):
        if self._custom_client is not None or self._http_client_factory is None:
            async with super()._get_client() as client:
                yield client
            return
        client_args = self._resolve_client_args()
        client_args["http_client"] = self._http_client_factory()
        async with openai.AsyncOpenAI(**client_args) as client:
            yield client
