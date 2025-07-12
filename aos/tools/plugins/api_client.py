import httpx
import logging
import json
import socket
import ipaddress
from typing import Dict, Any, Optional

from aos.tools.base_tool import BaseTool, ToolError

class ApiClientTool(BaseTool):
    """A tool for making HTTP requests to external APIs."""

    def __init__(self):
        super().__init__(
            name="api_client",
            description="Makes HTTP requests (GET, POST) to external APIs to fetch or send data."
        )
        self.logger = logging.getLogger(f"AOS-Tool-{self.name}")

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "The HTTP method to use.",
                    "enum": ["GET", "POST"]
                },
                "url": {
                    "type": "string",
                    "description": "The URL of the API endpoint."
                },
                "params": {
                    "type": "object",
                    "description": "Optional dictionary of URL query parameters for GET requests."
                },
                "headers": {
                    "type": "object",
                    "description": "Optional dictionary of HTTP headers."
                },
                "json_body": {
                    "type": "object",
                    "description": "Optional JSON payload for POST requests."
                }
            },
            "required": ["method", "url"]
        }

    def _validate_url(self, url: str):
        """Security check to prevent requests to local or private networks."""
        try:
            hostname = url.split('/')[2].split(':')[0]
            ip_info = socket.getaddrinfo(hostname, None)[0]
            ip_address = ipaddress.ip_address(ip_info[4][0])
            
            if ip_address.is_private or ip_address.is_loopback:
                raise PermissionError(f"Access to private or loopback address {ip_address} is forbidden.")
        except (socket.gaierror, IndexError):
            raise ValueError("Invalid or unresolvable URL.")
        except Exception as e:
            # Re-raise security errors, otherwise treat as validation failure
            if isinstance(e, PermissionError):
                raise e
            raise ValueError(f"URL validation failed: {e}")

    async def execute(self, parameters: Dict[str, Any], agent_id: str, orchestrator: Optional[Any] = None) -> Dict[str, Any]:
        method = parameters.get("method", "").upper()
        url = parameters.get("url")
        
        if not url or method not in ["GET", "POST"]:
            return {"error": "Invalid parameters. 'method' (GET/POST) and 'url' are required."}

        try:
            self._validate_url(url)
        except (PermissionError, ValueError) as e:
            self.logger.error(f"Agent {agent_id} URL validation failed: {e}")
            return {"error": str(e), "code": "SECURITY_VALIDATION_FAILED"}

        headers = parameters.get("headers", {})
        params = parameters.get("params", {})
        json_body = parameters.get("json_body", {})

        try:
            async with httpx.AsyncClient() as client:
                self.logger.info(f"Agent {agent_id} executing {method} request to {url}")
                
                if method == "GET":
                    response = await client.get(url, headers=headers, params=params, follow_redirects=True)
                elif method == "POST":
                    response = await client.post(url, headers=headers, params=params, json=json_body, follow_redirects=True)
                
                response.raise_for_status()  # Lève une exception pour les codes 4xx/5xx

                try:
                    # Tente de parser la réponse comme JSON
                    response_data = response.json()
                except json.JSONDecodeError:
                    # Si ce n'est pas du JSON, retourne le texte brut
                    response_data = response.text

                return {
                    "status": "success",
                    "status_code": response.status_code,
                    "content_type": response.headers.get('content-type'),
                    "body": response_data
                }
        except httpx.RequestError as e:
            return {"error": f"HTTP request failed: {e.__class__.__name__}", "details": str(e)}
        except Exception as e:
            return {"error": "An unexpected error occurred during the API call.", "details": str(e)}