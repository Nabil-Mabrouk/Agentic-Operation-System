import subprocess
import tempfile
import os
from typing import Dict, Any
from .base_tool import BaseTool

class CodeExecutorTool(BaseTool):
    """Tool for executing code snippets"""
    
    def __init__(self):
        super().__init__(
            name="code_executor",
            description="Execute Python code snippets safely"
        )
        
    async def execute(self, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Execute code with given parameters"""
        code = parameters.get("code", "")
        language = parameters.get("language", "python")
        
        if not code:
            return {"error": "No code provided"}
            
        if language != "python":
            return {"error": f"Language {language} not supported"}
            
        try:
            # Create a temporary file to execute the code
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
                
            try:
                # Execute the code with timeout
                result = subprocess.run(
                    ["python", temp_file],
                    capture_output=True,
                    text=True,
                    timeout=10  # 10 second timeout
                )
                
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.returncode
                }
            finally:
                # Clean up the temporary file
                os.unlink(temp_file)
                
        except subprocess.TimeoutExpired:
            return {"error": "Code execution timed out"}
        except Exception as e:
            return {"error": f"Code execution failed: {str(e)}"}
            
    def get_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for parameters"""
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The code to execute"
                },
                "language": {
                    "type": "string",
                    "description": "Programming language",
                    "enum": ["python"],
                    "default": "python"
                }
            },
            "required": ["code"]
        }