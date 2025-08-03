from typing import List
from langchain_core.messages.base import BaseMessage

class BaseLLMClient:

    def __init__(self, url: str, api_key: str, model: str) -> None:
        self.url = url
        self.api_key = api_key
        self.model = model

    def complete(self, messages: List[BaseMessage]) -> BaseMessage:
        raise NotImplementedError

    @property
    def context_window_size(self) -> int:
        return 128_000
