# aos/llm_clients/openai.py
import os
import asyncio
from typing import Tuple
from dotenv import load_dotenv
from .base import BaseLLMClient
from ..config import LLMConfig
import logging # <--- AJOUTER L'IMPORT

load_dotenv()

try:
    import openai
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = os.getenv("OPENAI_API_KEY") is not None
    if OPENAI_AVAILABLE:
        async_openai_client = AsyncOpenAI()
except ImportError:
    openai, OPENAI_AVAILABLE, async_openai_client = None, False, None

from .base import BaseLLMClient
from ..config import LLMConfig

class OpenAIClient(BaseLLMClient):
    # --- AJOUTER LE CONSTRUCTEUR ---
    def __init__(self):
        self.logger = logging.getLogger("AOS-LLM-OpenAI")

    def _adapt_parameters(self, config: LLMConfig) -> dict[str, any]:
        """
        Adapts the generic LLMConfig to the specific requirements of an OpenAI model.
        """
        params = {
            "model": config.model,
            "temperature": config.temperature,
            "timeout": config.timeout,
        }

        # Logique d'adaptation pour max_tokens
        # Les modèles 'o' (comme gpt-4o) et certains modèles récents utilisent 'max_completion_tokens'
        if 'o' in config.model or 'mini' in config.model:
             params["max_completion_tokens"] = config.max_tokens
        else:
             params["max_tokens"] = config.max_tokens



        # Logique d'adaptation pour response_format (si nécessaire pour d'autres fournisseurs)
        if config.provider == "openai":
            params["response_format"] = {"type": "json_object"}
            
        return params


    
    async def call_llm(self, prompt: str, config: LLMConfig) -> Tuple[str, int, int]:
        if not OPENAI_AVAILABLE:
            # Gérer le cas où OpenAI n'est pas disponible
            return '{"reasoning": "Fallback due to LLM unavailability.", "action": "FAIL"}', 0, 0

        # --- NOUVELLE LOGIQUE ---
        # 1. Construire les messages
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Respond only in the requested JSON format."},
            {"role": "user", "content": prompt}
        ]

        # 2. Adapter les paramètres
        api_params = self._adapt_parameters(config)
        api_params["messages"] = messages
        
        self.logger.debug(f"Calling LLM with adapted parameters: {api_params}")

        try:
            response = await asyncio.wait_for(
                async_openai_client.chat.completions.create(**api_params),
                timeout=config.timeout + 10.0
            )
            response_text = response.choices[0].message.content
            # Note: le calcul du coût devrait aussi être dans la config
            # Pour l'instant, on le laisse ici pour la simplicité.
            cost = 0.0 # Mettre à jour avec le vrai calcul si nécessaire
            if response.usage:
                # Retourne les tokens, pas le coût
                return response_text, response.usage.prompt_tokens, response.usage.completion_tokens
            return response_text, 0, 0
        # --- NOUVELLE GESTION D'ERREUR ---
        except openai.RateLimitError as e:
            self.logger.error(f"OpenAI rate limit hit. The API is temporarily unavailable. Error: {e}")
            error_msg = "OpenAI API rate limit exceeded. Please wait and try again later."
            return f'{{"reasoning": "{error_msg}", "action": "FAIL"}}', 0, 0
        except openai.APIError as e:
            self.logger.error(f"OpenAI API error occurred: {e}")
            error_msg = f"A an error occurred with the OpenAI API: {str(e)}".replace('"', "'")
            return f'{{"reasoning": "{error_msg}", "action": "FAIL"}}', 0, 0
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during LLM call: {e}", exc_info=True)
            error_msg = f"An unexpected error occurred: {str(e)}".replace('"', "'")
            return f'{{"reasoning": "{error_msg}", "action": "FAIL"}}', 0, 0