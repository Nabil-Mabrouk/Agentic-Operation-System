# aos/tools/plugins/pytest_runner.py
import subprocess
import sys
import os
from typing import Dict, Any, Optional

from aos.tools.base_tool import BaseTool

class PytestRunnerTool(BaseTool):
    """
    A specialized tool to run pytest on a specific test file within the agent's workspace.
    This tool is essential for the system's self-improvement capabilities.
    """

    def __init__(self):
        super().__init__(
            name="pytest_runner",
            description="Runs pytest on a specified test file and returns the output."
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "test_file_path": {
                    "type": "string",
                    "description": "The relative path to the test file to be executed."
                }
            },
            "required": ["test_file_path"]
        }

    async def execute(self, parameters: Dict[str, Any], agent_id: str, orchestrator: Optional[Any] = None) -> Dict[str, Any]:
        test_file_path = parameters.get("test_file_path")
        if not test_file_path:
            return {"error": "'test_file_path' parameter is required."}

        # Sécurité : Assurer que le chemin est relatif et ne sort pas du workspace
        # On utilise le FileManagerTool pour sa logique de chemin sécurisé
        workspace_dir = os.path.join(orchestrator.config.workspace_path, agent_id)
        # Ceci est une simplification. Idéalement, on ne recrée pas un FileManagerTool ici.
        # Mais pour l'instant, c'est une solution rapide pour la sécurité.
        from .file_manager import FileManagerTool
        try:
            safe_path = FileManagerTool(workspace_dir=workspace_dir)._get_safe_path(test_file_path)
            if not os.path.exists(safe_path):
                 return {"error": f"Test file not found at '{test_file_path}'."}
        except PermissionError as e:
            return {"error": str(e)}

        # Exécuter pytest dans un sous-processus pour l'isoler
        # On utilise sys.executable pour s'assurer d'utiliser le même interpréteur Python
        cmd = [sys.executable, "-m", "pytest", safe_path]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=workspace_dir, # Exécuter la commande depuis le workspace de l'agent
                timeout=60 # Mettre un timeout pour éviter les blocages
            )
            
            return {
                "status": "success" if result.returncode == 0 else "failed",
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except subprocess.TimeoutExpired:
            return {"error": "Pytest execution timed out after 60 seconds."}
        except Exception as e:
            return {"error": f"An unexpected error occurred while running pytest: {e}"}