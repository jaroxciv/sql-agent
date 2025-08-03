
from typing import List
from langchain_mistralai.chat_models import ChatMistralAI
from langchain_core.messages.base import BaseMessage
from .base import BaseLLMClient


class MistralLLMClient(BaseLLMClient):

    def __init__(self, url: str, api_key: str, model: str) -> None:
        super().__init__(url, api_key, model)
        self.mistral_client = ChatMistralAI(api_key=api_key, model_name=model)

    def complete(self, messages: List[BaseMessage]) -> BaseMessage:
        return self.mistral_client.invoke(messages)

    @property
    def context_window_size(self) -> int:
        MODEL_CONTEXT_WINDOWS = {
            "mistral-large-2411": 128_000,
            "mistral-large-latest": 128_000,
            "open-mistral-nemo": 128_000,
            "codestral-latest": 256_000,
        }

        if self.model in MODEL_CONTEXT_WINDOWS:
            return MODEL_CONTEXT_WINDOWS[self.model]

        return 128_000





