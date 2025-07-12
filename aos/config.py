#aos/config.py
import logging
from dataclasses import dataclass, field
from typing import Literal, Optional, Dict, Any, List
import os
# Define valid log levels
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

@dataclass
class LLMConfig:
    """Configuration for the Language Model client."""
    provider: str = "openai"  # Pourrait être 'anthropic', 'google', 'ollama' etc. à l'avenir
    model: str = os.getenv("AOS_MODEL_NAME", "o4-mini-2025-04-16")
    temperature: float = 1
    max_tokens: int = 4000
    timeout: float = 90.0
    # On peut ajouter d'autres paramètres spécifiques ici
    # ex: api_params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentCapabilities:
    """Defines the advanced capabilities available to the agents."""
    allow_messaging: bool = True
    allow_advanced_planning: bool = True # Pour la boucle de validation par l'Architecte
    allow_tool_creation: bool = False   # Désactivé par défaut car très puissant/coûteux

@dataclass
class SystemConfig:
    """System-wide configuration settings for the AOS simulation."""
    # --- NOUVEAUX CHAMPS DE CHEMIN ---
    # Le répertoire parent pour toutes les sorties
    output_base_dir: str = "output"
    # Les sous-répertoires, relatifs au répertoire de base
    workspace_dir_name: str = "workspace"
    delivery_dir_name: str = "delivery"

    # --- ANCIENS CHAMPS (maintenant dérivés) ---
    # Ces champs seront calculés après l'initialisation
    workspace_path: str = field(init=False)
    delivery_path: str = field(init=False)

    initial_budget: float = 100.0
    objective: str = "Achieve a complex, multi-step goal."
    max_agents: int = 10
    log_level: LogLevel = "INFO"
    
    # Token-based pricing model (in USD per million tokens)
    price_per_1m_input_tokens: float = 5.0
    price_per_1m_output_tokens: float = 15.0

    # Other fixed costs (in USD)
    spawn_cost: float = 0.01
    tool_use_cost: float = 0.005
    
    # Delivery/output folder where final results are assembled
    #delivery_folder: str = "./delivery"
    simulation_timeout: float = 600.0 # <--- NOUVELLE LIGNE
    shutdown_timeout: float = 10.0 # <--- NOUVELLE LIGNE
    disabled_tools: List[str] = field(default_factory=list)
    llm: LLMConfig = field(default_factory=LLMConfig)
    capabilities: AgentCapabilities = field(default_factory=AgentCapabilities)

    def __post_init__(self):
        """Validate configuration parameters after initialization."""
                # Créer le répertoire de base s'il n'existe pas
        os.makedirs(self.output_base_dir, exist_ok=True)
        
        # Construire les chemins complets
        self.workspace_path = os.path.join(self.output_base_dir, self.workspace_dir_name)
        self.delivery_path = os.path.join(self.output_base_dir, self.delivery_dir_name)

        if self.initial_budget <= 0:
            raise ValueError("initial_budget must be positive")
        if self.max_agents <= 0:
            raise ValueError("max_agents must be a positive integer")
        if self.price_per_1m_input_tokens < 0 or self.price_per_1m_output_tokens < 0:
            raise ValueError("Token prices cannot be negative")
        if self.spawn_cost < 0 or self.tool_use_cost < 0:
            raise ValueError("Costs cannot be negative")