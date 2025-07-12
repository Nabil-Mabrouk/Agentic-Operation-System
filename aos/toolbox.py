# aos/toolbox.py
import os
import logging
from typing import Dict, Any, List, Optional
import asyncio
import importlib # <--- NOUVEL IMPORT
import inspect   # <--- NOUVEL IMPORT

from .tools.base_tool import BaseTool, ToolError

class Toolbox:
    """A collection of tools sandboxed to a specific agent's workspace."""
    
    def __init__(self, workspace_dir: str, delivery_folder: Optional[str] = None, orchestrator: Optional[Any] = None):
        self.logger = logging.getLogger("AOS-Toolbox")
        self.tools: Dict[str, BaseTool] = {}
        self.workspace_dir = workspace_dir
        self.delivery_folder = delivery_folder
        self._lock = asyncio.Lock()  # Ensure thread safety for tool registration
        self.orchestrator = orchestrator # Stocker l'orchestrateur
        
    # --- MÉTHODE D'INITIALISATION ENTIÈREMENT REVUE ---
    async def initialize(self) -> None:
        """Dynamically discover and load tools from the plugins directory."""
        self.logger.info(f"Initializing toolbox for workspace: {self.workspace_dir}")
        self.tools = {} # Réinitialiser les outils
        
        plugins_path = os.path.join(os.path.dirname(__file__), 'tools', 'plugins')
        plugin_files = [f for f in os.listdir(plugins_path) if f.endswith('.py') and not f.startswith('__')]

        for file_name in plugin_files:
            module_name = f"aos.tools.plugins.{file_name[:-3]}"
            try:
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module):
                    # On cherche les classes qui héritent de BaseTool mais qui ne sont pas BaseTool elles-mêmes
                    if inspect.isclass(obj) and issubclass(obj, BaseTool) and obj is not BaseTool:
                        self.logger.debug(f"Found tool class: {obj.__name__} in {module_name}")

                        # Instancier l'outil. Gérer le cas de FileManagerTool qui a des arguments.
                        if obj.__name__ == "FileManagerTool":
                            tool_instance = obj(workspace_dir=self.workspace_dir, delivery_folder=self.delivery_folder)
                        else:
                            tool_instance = obj()
                            
                        # Le PytestRunnerTool est un outil système et ne peut pas être désactivé
                        is_protected_tool = tool_instance.name == "pytest_runner"

                        if tool_instance.name in self.orchestrator.config.disabled_tools:
                            self.logger.warning(f"Tool '{tool_instance.name}' is disabled by configuration. Skipping.")
                            continue # On ne charge pas cet outil    

                        # Dans la boucle de chargement dynamique
                        if obj.__name__ == "MessagingTool" and not self.orchestrator.config.capabilities.allow_messaging:
                            continue # On saute le chargement de cet outil

                        await self.register_tool(tool_instance)
                                            # --- VÉRIFICATION DE DÉSACTIVATION ---

            except ImportError as e:
                self.logger.error(f"Failed to import plugin module {module_name}: {e}")

        self.logger.info(f"Toolbox initialized with {len(self.tools)} tools: {list(self.tools.keys())}")
        
        # La création du delivery folder reste
        if self.delivery_folder:
            os.makedirs(self.delivery_folder, exist_ok=True)
            
    async def register_tool(self, tool: BaseTool) -> None:
        async with self._lock:
            if tool.name in self.tools:
                self.logger.warning(f"Tool '{tool.name}' is already registered. Overwriting.")
            self.tools[tool.name] = tool
            self.logger.debug(f"Registered tool: {tool.name}")

    async def refresh(self):
        """
        Re-scans the plugins directory and loads any new tools,
        preserving the existing ones.
        """
        self.logger.info("Refreshing toolbox by reloading all tools...")
        # La manière la plus simple et la plus sûre est de ré-appeler initialize.
        # Cela garantit que tous les nouveaux outils sont chargés.
        await self.initialize()          
    
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
            result = await tool.execute(parameters, agent_id, self.orchestrator)
            self.logger.debug(f"Tool {name} executed successfully for agent {agent_id}. Result: {result}")
            return result
        except Exception as e:
            error_msg = f"Tool '{name}' execution failed: {str(e)}"
            self.logger.error(f"Agent {agent_id}: {error_msg}", exc_info=True)
            return {"error": error_msg, "code": "EXECUTION_FAILED", "details": str(e)}