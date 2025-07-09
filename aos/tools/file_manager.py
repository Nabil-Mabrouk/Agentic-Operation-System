import os
import shutil
from typing import Dict, Any
from .base_tool import BaseTool

class FileManagerTool(BaseTool):
    """Tool for managing files and directories"""
    
    def __init__(self):
        super().__init__(
            name="file_manager",
            description="Manage files and directories"
        )
        
    async def execute(self, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Execute file operation"""
        operation = parameters.get("operation", "")
        path = parameters.get("path", "")
        content = parameters.get("content", "")
        
        if not operation or not path:
            return {"error": "Operation and path are required"}
            
        try:
            if operation == "read":
                if not os.path.exists(path):
                    return {"error": f"File {path} does not exist"}
                with open(path, 'r') as f:
                    content = f.read()
                return {"success": True, "content": content}
                
            elif operation == "write":
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w') as f:
                    f.write(content)
                return {"success": True, "message": f"File {path} written"}
                
            elif operation == "delete":
                if os.path.isfile(path):
                    os.remove(path)
                    return {"success": True, "message": f"File {path} deleted"}
                elif os.path.isdir(path):
                    shutil.rmtree(path)
                    return {"success": True, "message": f"Directory {path} deleted"}
                else:
                    return {"error": f"Path {path} does not exist"}
                    
            elif operation == "mkdir":
                os.makedirs(path, exist_ok=True)
                return {"success": True, "message": f"Directory {path} created"}
                
            elif operation == "list":
                if not os.path.exists(path):
                    return {"error": f"Path {path} does not exist"}
                items = os.listdir(path)
                return {"success": True, "items": items}
                
            else:
                return {"error": f"Unknown operation: {operation}"}
                
        except Exception as e:
            return {"error": f"File operation failed: {str(e)}"}
            
    def get_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for parameters"""
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "File operation to perform",
                    "enum": ["read", "write", "delete", "mkdir", "list"]
                },
                "path": {
                    "type": "string",
                    "description": "File or directory path"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for write operation)"
                }
            },
            "required": ["operation", "path"]
        }