# aos/llm_clients/base.py
from abc import ABC, abstractmethod
from typing import Tuple, Any

class BaseLLMClient(ABC):
    @abstractmethod
    # La signature de retour doit être (texte, tokens_input, tokens_output)
    async def call_llm(self, prompt: str, config: Any) -> Tuple[str, int, int]:
        """
        Calls the language model and returns the response text, input tokens, and output tokens.
        'config' is an instance of a configuration object (like LLMConfig).
        """
        pass