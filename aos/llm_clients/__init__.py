# aos/llm_clients/__init__.py
from .base import BaseLLMClient
from .openai import OpenAIClient
from .openai_compatible import OpenAICompatibleClient
# À l'avenir, vous ajouterez ici d'autres clients :
# from .anthropic import AnthropicClient
import os
from dotenv import load_dotenv
load_dotenv()

# --- RÉCUPÉRATION DES SECRETS DEPUIS L'ENVIRONNEMENT ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
KIMI_API_KEY = os.getenv("KIMI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY") # <--- AJOUTER

def get_llm_client(provider: str) -> BaseLLMClient:
    """
    Factory function to get an instance of a LLM client based on the provider name.
    """
    provider_lower = provider.lower()
    
    if provider_lower == "openai":
        return OpenAIClient()
        
    elif provider_lower == "deepseek":
        if not DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY environment variable not set.")
        return OpenAICompatibleClient(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1"
        )
        
    elif provider_lower == "kimi":
        if not KIMI_API_KEY:
            raise ValueError("KIMI_API_KEY environment variable not set.")
        return OpenAICompatibleClient(
            api_key=KIMI_API_KEY,
            base_url="https://api.moonshot.cn/v1"
        )
    # --- NOUVELLE SECTION POUR GROQ ---
    elif provider_lower == "groq":
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY environment variable not set.")
        return OpenAICompatibleClient(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1" # URL de base spécifique à Groq
        ) 
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")