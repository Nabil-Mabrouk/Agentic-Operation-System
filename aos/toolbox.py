import asyncio
import logging
from typing import Dict, Any, Callable, Optional, List
from abc import ABC, abstractmethod
import importlib.util
import sys
from .tools.base_tool import BaseTool

class Toolbox:
    """The Shared Library - dynamic registry of tools available to agents"""
    
    def __init__(self):
        self.logger = logging.getLogger("AOS-Toolbox")
        self.tools: Dict[str, BaseTool] = {}
        self._lock = asyncio.Lock()
        
    async def initialize(self) -> None:
        """Initialize the toolbox with basic tools"""
        self.logger.info("Initializing toolbox...")
        
        # Load built-in tools
        await self._load_builtin_tools()
        
    async def _load_builtin_tools(self) -> None:
        """Load built-in tools"""
        from .tools.web_search import WebSearchTool
        from .tools.code_executor import CodeExecutorTool
        from .tools.file_manager import FileManagerTool
        
        builtin_tools = [
            WebSearchTool(),
            CodeExecutorTool(),
            FileManagerTool()
        ]
        
        for tool in builtin_tools:
            await self.register_tool(tool)
            
    async def register_tool(self, tool: BaseTool) -> None:
        """Register a new tool in the toolbox"""
        async with self._lock:
            if tool.name in self.tools:
                self.logger.warning(f"Tool {tool.name} already exists, overwriting")
            self.tools[tool.name] = tool
            self.logger.info(f"Tool {tool.name} registered")
            
    async def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name"""
        return self.tools.get(name)
        
    async def list_tools(self) -> List[str]:
        """List all available tools"""
        return list(self.tools.keys())
        
    async def execute_tool(self, name: str, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Execute a tool with given parameters"""
        tool = await self.get_tool(name)
        if not tool:
            return {"error": f"Tool {name} not found"}
            
        try:
            result = await tool.execute(parameters, agent_id)
            self.logger.debug(f"Tool {name} executed by {agent_id}")
            return result
        except Exception as e:
            self.logger.error(f"Error executing tool {name}: {str(e)}")
            return {"error": str(e)}
            
    async def load_dynamic_tool(self, tool_code: str, tool_name: str) -> bool:
        """Dynamically load a tool from code"""
        try:
            # Create a temporary module
            spec = importlib.util.spec_from_loader(tool_name, loader=None)
            module = importlib.util.module_from_spec(spec)
            
            # Execute the tool code
            exec(tool_code, module.__dict__)
            
            # Find the tool class (should inherit from BaseTool)
            tool_class = None
            for item_name in dir(module):
                item = getattr(module, item_name)
                if (isinstance(item, type) and 
                    issubclass(item, BaseTool) and 
                    item != BaseTool):
                    tool_class = item
                    break
                    
            if not tool_class:
                self.logger.error(f"No valid tool class found in dynamic tool {tool_name}")
                return False
                
            # Instantiate and register the tool
            tool_instance = tool_class()
            await self.register_tool(tool_instance)
            
            self.logger.info(f"Dynamically loaded tool: {tool_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load dynamic tool {tool_name}: {str(e)}")
            return False