# aos/toolbox.py
import os
import logging
from typing import Dict, Any, List, Optional
import asyncio

from .tools.base_tool import BaseTool, ToolError

class Toolbox:
    """A collection of tools sandboxed to a specific agent's workspace."""
    
    def __init__(self, workspace_dir: str, delivery_folder: Optional[str] = None):
        self.logger = logging.getLogger("AOS-Toolbox")
        self.tools: Dict[str, BaseTool] = {}
        self.workspace_dir = workspace_dir
        self.delivery_folder = delivery_folder
        self._lock = asyncio.Lock()  # Ensure thread safety for tool registration
        
    async def initialize(self) -> None:
        """Initialize the toolbox with tools configured for its workspace."""
        self.logger.info(f"Initializing toolbox for workspace: {self.workspace_dir}")
        from aos.tools import WebSearchTool, CodeExecutorTool, FileManagerTool
        
        builtin_tools = [
            WebSearchTool(),
            CodeExecutorTool(),
            FileManagerTool(workspace_dir=self.workspace_dir, delivery_folder=self.delivery_folder)
        ]
        
        for tool in builtin_tools:
            await self.register_tool(tool)
        self.logger.info(f"Toolbox initialized with {len(self.tools)} tools.")
        
        # Create delivery folder if specified
        if self.delivery_folder:
            os.makedirs(self.delivery_folder, exist_ok=True)
            self.logger.info(f"Delivery folder created at: {self.delivery_folder}")
            
    async def register_tool(self, tool: BaseTool) -> None:
        async with self._lock:
            if tool.name in self.tools:
                self.logger.warning(f"Tool '{tool.name}' is already registered. Overwriting.")
            self.tools[tool.name] = tool
            self.logger.debug(f"Registered tool: {tool.name}")
            
    async def get_tool(self, name: str) -> Optional[BaseTool]:
        return self.tools.get(name)
        
    async def list_tools_for_prompt(self) -> List[Dict[str, Any]]:
        """Returns a detailed list of tools with schemas for the LLM prompt."""
        return [{
            "name": tool.name,
            "description": tool.description,
            "parameters_schema": tool.get_schema()
        } for name, tool in self.tools.items()]
        
    async def execute_tool(self, name: str, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        tool = await self.get_tool(name)
        if not tool:
            error_msg = f"Tool '{name}' not found."
            self.logger.error(f"Agent {agent_id}: {error_msg}")
            return {"error": error_msg, "code": "TOOL_NOT_FOUND"}
        
        self.logger.info(f"Agent {agent_id} executing tool: {name} with params: {parameters}")
        try:
            result = await tool.execute(parameters, agent_id)
            self.logger.debug(f"Tool {name} executed successfully for agent {agent_id}. Result: {result}")
            return result
        except Exception as e:
            error_msg = f"Tool '{name}' execution failed: {str(e)}"
            self.logger.error(f"Agent {agent_id}: {error_msg}", exc_info=True)
            return {"error": error_msg, "code": "EXECUTION_FAILED", "details": str(e)}