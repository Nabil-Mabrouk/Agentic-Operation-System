from dataclasses import dataclass
from typing import Optional

@dataclass
class SystemConfig:
    """Configuration for the AOS system"""
    initial_budget: float = 1000.0
    objective: str = "Build a web application"
    max_agents: int = 10
    api_cost_per_call: float = 0.01
    spawn_cost: float = 10.0
    log_level: str = "INFO"