from typing import Dict, Any
import asyncio
import subprocess
import sys
from .base_tool import BaseTool

# Constants
CODE_EXECUTION_TIMEOUT = 30.0  # seconds
MAX_OUTPUT_LENGTH = 100 * 1024  # 100 KB limit for stdout/stderr

class CodeExecutorTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="code_executor",
            description="Executes a block of Python code and returns the output."
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The Python code to execute."
                }
            },
            "required": ["code"]
        }

    async def execute(self, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        code = parameters.get("code")
        if not code:
            return {"error": "'code' parameter is required.", "code": "INVALID_PARAMETERS"}
            
        try:
            # Execute code in a separate process for isolation
            process = await asyncio.create_subprocess_exec(
                sys.executable, '-c', code,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=CODE_EXECUTION_TIMEOUT
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {"status": "error", "error": f"Code execution timed out after {CODE_EXECUTION_TIMEOUT} seconds", "code": "TIMEOUT"}

            # Limit output length
            if len(stdout) > MAX_OUTPUT_LENGTH:
                stdout = stdout[:MAX_OUTPUT_LENGTH] + b"... [Output truncated]"
            if len(stderr) > MAX_OUTPUT_LENGTH:
                stderr = stderr[:MAX_OUTPUT_LENGTH] + b"... [Error output truncated]"

            if process.returncode != 0:
                return {"status": "error", "error": stderr.decode('utf-8'), "code": "EXECUTION_FAILED", "return_code": process.returncode}
            
            return {"status": "success", "output": stdout.decode('utf-8')}

        except FileNotFoundError:
            return {"error": "Python executable not found.", "code": "EXECUTABLE_NOT_FOUND"}
        except Exception as e:
            return {"error": f"Code execution failed: {e}", "code": "UNKNOWN_ERROR"}