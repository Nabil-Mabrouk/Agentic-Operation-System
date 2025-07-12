# aos/tools/messaging.py
from typing import Dict, Any, Optional
from aos.tools.base_tool import BaseTool, ToolError

class MessagingTool(BaseTool):
    """A tool for sending messages to other agents."""

    def __init__(self):
        super().__init__(
            name="messaging",
            description="Sends a message to another agent in the system."
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "recipient_id": {
                    "type": "string",
                    "description": "The ID of the agent to send the message to."
                },
                "content": {
                    "type": "object",
                    "description": "A JSON object containing the message content."
                }
            },
            "required": ["recipient_id", "content"]
        }

    # aos/tools/messaging.py
    async def execute(self, parameters: Dict[str, Any], agent_id: str, orchestrator: Optional[Any] = None) -> Dict[str, Any]:
        if not orchestrator:
            return {"error": "Messaging is not available."}
        
        recipient_id = parameters.get("recipient_id")
        content = parameters.get("content")
        # ... (validation des paramètres)

        success = await orchestrator.send_message(agent_id, recipient_id, content)
        if success:
            return {"status": "success", "message": f"Message sent to {recipient_id}."}
        else:
            return {"error": f"Failed to send message to {recipient_id}."}