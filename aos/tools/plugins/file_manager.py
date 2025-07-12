# aos/tools/file_manager.py
import os
import logging
from typing import Dict, Any, List, Optional
from aos.tools.base_tool import BaseTool, ToolError

# Constants for operations
OP_WRITE = "write"
OP_READ = "read"
OP_LIST = "list"
OP_COPY_TO_DELIVERY = "copy_to_delivery"
SUPPORTED_OPERATIONS = [OP_WRITE, OP_READ, OP_LIST, OP_COPY_TO_DELIVERY]

class FileManagerTool(BaseTool):
    """A tool for managing files in a sandboxed workspace."""

    def __init__(self, workspace_dir: str, delivery_folder: Optional[str] = None):
        super().__init__(
            name="file_manager",
            description=(
                "Manages files in a sandboxed workspace. "
                f"Operations: {', '.join(SUPPORTED_OPERATIONS)}."
            )
        )
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.delivery_folder = delivery_folder
        self.logger = logging.getLogger(f"AOS-Tool-{self.name}")

    def get_schema(self) -> Dict[str, Any]:
        """Provides the JSON schema for the tool's parameters."""
        schema = {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "The file operation to perform.",
                    "enum": SUPPORTED_OPERATIONS
                },
                "path": {
                    "type": "string",
                    "description": f"Relative path for the file or directory within the workspace. Required for '{OP_WRITE}', '{OP_READ}', and '{OP_COPY_TO_DELIVERY}'."
                },
                "content": {
                    "type": "string",
                    "description": f"The content to write to the file. Required for '{OP_WRITE}'."
                },
                "delivery_name": {
                    "type": "string",
                    "description": f"Optional name for the file in the delivery folder. Used with '{OP_COPY_TO_DELIVERY}'."
                }
            },
            "required": ["operation"]
        }
        
        # Make path required for specific operations
        if "path" not in schema["required"]:
            schema["required"].append("path")
            
        return schema
    
    def _get_safe_path(self, path: str) -> str:
        """Ensures the path is within the workspace directory."""
        full_path = os.path.abspath(os.path.join(self.workspace_dir, path))
        if not full_path.startswith(self.workspace_dir):
            raise PermissionError("Access denied: Attempt to access files outside of the workspace.")
        return full_path

    async def execute(self, parameters: Dict[str, Any], agent_id: str, orchestrator: Optional[Any] = None) -> Dict[str, Any]:
        operation = parameters.get("operation")
        if not operation:
            return {"error": "'operation' parameter is required.", "code": "INVALID_PARAMETERS"}

        if operation not in SUPPORTED_OPERATIONS:
            return {"error": f"Unsupported operation: {operation}. Supported operations: {', '.join(SUPPORTED_OPERATIONS)}", "code": "INVALID_PARAMETERS"}

        try:
            if operation == OP_WRITE:
                return await self._write_file(parameters, agent_id)
            elif operation == OP_READ:
                return await self._read_file(parameters, agent_id)
            elif operation == OP_LIST:
                return await self._list_directory(parameters, agent_id)
            elif operation == OP_COPY_TO_DELIVERY:
                return await self._copy_to_delivery(parameters, agent_id)

        except PermissionError as e:
            self.logger.error(f"Agent {agent_id} permission error: {e}")
            return {"error": str(e), "code": "PERMISSION_DENIED"}
        except FileNotFoundError as e:
            self.logger.error(f"Agent {agent_id} file not found: {e}")
            return {"error": str(e), "code": "FILE_NOT_FOUND"}
        except IsADirectoryError as e:
            self.logger.error(f"Agent {agent_id} expected file but found directory: {e}")
            return {"error": str(e), "code": "IS_A_DIRECTORY"}
        except Exception as e:
            self.logger.error(f"FileManagerTool error: {e}", exc_info=True)
            return {"error": f"An unexpected file error occurred: {e}", "code": "UNKNOWN_ERROR"}

    async def _write_file(self, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        path = parameters.get("path")
        content = parameters.get("content")
        if not path or content is None:
            return {"error": "'path' and 'content' are required for 'write'.", "code": "INVALID_PARAMETERS"}
        
        safe_path = self._get_safe_path(path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        msg = f"File '{path}' written successfully."
        self.logger.info(f"Agent {agent_id}: {msg}")
        return {"status": "success", "message": msg}

    async def _read_file(self, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        path = parameters.get("path")
        if not path:
            return {"error": "'path' is required for 'read'.", "code": "INVALID_PARAMETERS"}
        
        safe_path = self._get_safe_path(path)
        if not os.path.exists(safe_path):
            return {"error": f"File not found: {path}", "code": "FILE_NOT_FOUND"}
        if os.path.isdir(safe_path):
             return {"error": f"Path is a directory, not a file: {path}", "code": "IS_A_DIRECTORY"}
        
        with open(safe_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return {"status": "success", "path": path, "content": content}

    async def _list_directory(self, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        path = parameters.get("path", ".") # Default to workspace root
        safe_path = self._get_safe_path(path)
        if not os.path.isdir(safe_path):
            return {"error": f"Directory not found: {path}", "code": "DIRECTORY_NOT_FOUND"}
        
        items = os.listdir(safe_path)
        return {"status": "success", "path": path, "items": items}

    async def _copy_to_delivery(self, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Copy a file from the agent's workspace to the delivery folder."""
        if not self.delivery_folder:
            return {"error": "Delivery folder not configured", "code": "DELIVERY_NOT_CONFIGURED"}
            
        path = parameters.get("path")
        delivery_name = parameters.get("delivery_name", os.path.basename(path))
        
        if not path:
            return {"error": "'path' is required for 'copy_to_delivery'.", "code": "INVALID_PARAMETERS"}
        
        source_path = self._get_safe_path(path)
        if not os.path.exists(source_path):
            return {"error": f"File not found: {path}", "code": "FILE_NOT_FOUND"}
        
        delivery_path = os.path.join(self.delivery_folder, delivery_name)
        os.makedirs(os.path.dirname(delivery_path), exist_ok=True)
        
        import shutil
        shutil.copy2(source_path, delivery_path)
        
        msg = f"File '{path}' copied to delivery as '{delivery_name}'."
        self.logger.info(f"Agent {agent_id}: {msg}")
        return {"status": "success", "message": msg, "delivery_path": delivery_path}