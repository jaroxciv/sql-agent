from .base import BaseLLMClient
from .mistral import MistralLLMClient
from .gpt import OpenAILLMClient

def build_client(url: str, api_key: str, model: str) -> BaseLLMClient:
    """
    Factory method for LLM clients.
    Prioritizes model name, but falls back to URL as a backup.
    """
    model_lower = model.lower() if model else ""
    url_lower = url.lower() if url else ""

    if "mistral" in model_lower or "mistral" in url_lower:
        return MistralLLMClient(url, api_key, model)
    elif "gpt" in model_lower or "gpt" in url_lower:
        return OpenAILLMClient(url, api_key, model)
    else:
        raise ValueError(f"No valid client found for [{model}] : [{url}]")

__all__ = [
    "BaseLLMClient",
    "MistralLLMClient",
    "OpenAILLMClient",
    "build_client"
]
