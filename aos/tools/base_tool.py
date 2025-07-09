from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTool(ABC):
    """Base class for all tools in the AOS toolbox"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        
    @abstractmethod
    async def execute(self, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Execute the tool with given parameters"""
        pass
        
    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for tool parameters"""
        pass