from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

class ToolError(Exception):
    """Base exception for tool-related errors."""
    pass

class BaseTool(ABC):
    """Base class for all tools in the AOS toolbox"""
    
    def __init__(self, name: str, description: str, category: str = "General", version: str = "1.0.0"):
        self.name = name
        self.description = description
        self.category = category
        self.version = version
        
    @abstractmethod
    async def execute(self, parameters: Dict[str, Any], agent_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the tool with given parameters.
        
        Args:
            parameters: Tool-specific parameters
            agent_id: ID of the agent executing the tool
            context: Optional context information (e.g., agent balance, role)
            
        Returns:
            Dict containing the result or error information
        """
        pass
        
    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for tool parameters"""
        pass
        
    async def initialize(self) -> None:
        """Optional initialization for the tool. Called when registered."""
        pass
        
    async def cleanup(self) -> None:
        """Optional cleanup for the tool. Called when unregistered."""
        pass
        
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """
        Basic parameter validation against the schema.
        This is a simplified example. For production, use a proper JSON Schema validator.
        """
        schema = self.get_schema()
        required_params = schema.get("required", [])
        for param in required_params:
            if param not in parameters:
                return False
        return True