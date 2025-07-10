import logging
from dataclasses import dataclass
from typing import Literal

# Define valid log levels
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

@dataclass
class SystemConfig:
    """System-wide configuration settings for the AOS simulation."""
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
    delivery_folder: str = "./delivery"

    def __post_init__(self):
        """Validate configuration parameters after initialization."""
        if self.initial_budget <= 0:
            raise ValueError("initial_budget must be positive")
        if self.max_agents <= 0:
            raise ValueError("max_agents must be a positive integer")
        if self.price_per_1m_input_tokens < 0 or self.price_per_1m_output_tokens < 0:
            raise ValueError("Token prices cannot be negative")
        if self.spawn_cost < 0 or self.tool_use_cost < 0:
            raise ValueError("Costs cannot be negative")