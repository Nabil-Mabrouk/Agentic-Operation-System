from typing import Dict, Any
import asyncio
from .base_tool import BaseTool
from duckduckgo_search import DDGS

# Constants
DEFAULT_MAX_RESULTS = 5
SEARCH_TIMEOUT = 10.0  # seconds

class WebSearchTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="web_search",
            description="Performs a web search using DuckDuckGo to find information."
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query."
                },
                "num_results": {
                    "type": "integer",
                    "description": f"Maximum number of results to return (default: {DEFAULT_MAX_RESULTS}).",
                    "minimum": 1,
                    "maximum": 10
                }
            },
            "required": ["query"]
        }

    async def execute(self, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        query = parameters.get("query")
        if not query:
            return {"error": "'query' parameter is required.", "code": "INVALID_PARAMETERS"}
        
        num_results = parameters.get("num_results", DEFAULT_MAX_RESULTS)
        
        try:
            # Wrap the synchronous DDGS call in asyncio.to_thread to avoid blocking
            results = await asyncio.wait_for(
                asyncio.to_thread(self._perform_search, query, num_results),
                timeout=SEARCH_TIMEOUT
            )
            
            if not results:
                return {"status": "success", "message": "No results found.", "results": []}
            
            return {"status": "success", "results": results}

        except asyncio.TimeoutError:
            return {"error": f"Web search timed out after {SEARCH_TIMEOUT} seconds.", "code": "TIMEOUT"}
        except Exception as e:
            return {"error": f"Web search failed: {e}", "code": "SEARCH_FAILED"}

    def _perform_search(self, query: str, num_results: int) -> list[Dict[str, Any]]:
        """Perform the actual search using DDGS."""
        try:
            with DDGS() as ddgs:
                return [r for r in ddgs.text(query, max_results=num_results)]
        except Exception as e:
            # Re-raise the exception to be caught in execute
            raise e