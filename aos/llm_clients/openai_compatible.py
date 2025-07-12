# aos/llm_clients/openai_compatible.py
import os
import asyncio
import logging
from typing import Tuple, Any

try:
    from openai import AsyncOpenAI, RateLimitError, APIError
except ImportError:
    AsyncOpenAI, RateLimitError, APIError = None, None, None

from .base import BaseLLMClient
from ..config import LLMConfig

class OpenAICompatibleClient(BaseLLMClient):
    """
    A client for LLM providers that use an OpenAI-compatible API endpoint.
    This includes Deepseek, Moonshot (Kimi), Groq, etc.
    """
    def __init__(self, api_key: str, base_url: str):
        if AsyncOpenAI is None:
            raise ImportError("The 'openai' package is required to use OpenAI-compatible clients. Please run 'pip install openai'.")
        
        self.logger = logging.getLogger(f"AOS-LLM-Compatible")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.logger.info(f"Initialized OpenAI-compatible client for base URL: {base_url}")

    async def call_llm(self, prompt: str, config: LLMConfig) -> Tuple[str, int, int]:
        base_params = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant. Respond only in the requested JSON format."},
                {"role": "user", "content": prompt}
            ],
            "temperature": config.temperature,
            "timeout": config.timeout,
        }
        # Adapter les paramètres en fonction du modèle ou du fournisseur
        # C'est une heuristique, mais elle est efficace.
        # Les modèles plus récents (comme gpt-4o) utilisent 'max_completion_tokens'
        # On peut se baser sur le nom du modèle ou le fournisseur.
        if "gpt-4-turbo" in config.model:
            # Les anciens modèles turbo pourraient encore utiliser max_tokens
             base_params["max_tokens"] = config.max_tokens
             base_params["response_format"] = {"type": "json_object"}
        else:
            # Pour les modèles plus récents ou les API compatibles comme Groq
            base_params["max_tokens"] = config.max_tokens # on garde max_tokens au cas où
                                                          # mais on pourrait utiliser max_completion_tokens
            # `response_format` n'est pas toujours supporté par les API compatibles
            if config.provider == "openai":
                base_params["response_format"] = {"type": "json_object"}


        # Supprimons le paramètre qui pose problème si le modèle est connu pour ne pas le supporter
        # Pour cet exemple, on peut simplement faire un switch manuel
        # Une solution plus avancée serait d'avoir une config par modèle.
        # Ici, nous allons simplement renommer le paramètre.
        if 'max_tokens' in base_params:
            base_params['max_completion_tokens'] = base_params.pop('max_tokens')

        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**base_params),
                timeout=config.timeout + 10.0
            )
            response_text = response.choices[0].message.content
            usage = response.usage

            if usage:
                return response_text, usage.prompt_tokens, usage.completion_tokens
            return response_text, 0, 0
            
        except RateLimitError as e:
            self.logger.error(f"Rate limit hit for {config.model}. Error: {e}")
            error_msg = f"API rate limit exceeded for model {config.model}."
            return f'{{"reasoning": "{error_msg}", "action": "FAIL"}}', 0, 0
        except APIError as e:
            self.logger.error(f"API error for {config.model}. Error: {e}")
            error_msg = f"An API error occurred with model {config.model}: {str(e)}".replace('"', "'")
            return f'{{"reasoning": "{error_msg}", "action": "FAIL"}}', 0, 0
        except Exception as e:
            self.logger.error(f"An unexpected error occurred with {config.model}: {e}", exc_info=True)
            error_msg = f"An unexpected error occurred: {str(e)}".replace('"', "'")
            return f'{{"reasoning": "{error_msg}", "action": "FAIL"}}', 0, 0