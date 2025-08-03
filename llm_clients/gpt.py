from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.messages.base import BaseMessage
from .base import BaseLLMClient  # use relative import for package structure

class OpenAILLMClient(BaseLLMClient):

    def __init__(self, url: str, api_key: str, model: str) -> None:
        super().__init__(url, api_key, model)
        # url parameter is ignored here, as OpenAI uses a fixed endpoint unless using Azure
        self.openai_client = ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            base_url=url,
        )

    def complete(self, messages: List[BaseMessage]) -> BaseMessage:
        return self.openai_client.invoke(messages)

    @property
    def context_window_size(self) -> int:
        MODEL_CONTEXT_WINDOWS = {
            "gpt-4o": 128_000,
            "gpt-4-turbo": 128_000,
            "gpt-4": 32_000,
            "gpt-3.5-turbo": 16_385,
        }

        if self.model in MODEL_CONTEXT_WINDOWS:
            return MODEL_CONTEXT_WINDOWS[self.model]

        # Default for unknown/future models
        return 128_000
