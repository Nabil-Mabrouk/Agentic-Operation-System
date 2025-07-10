import asyncio
import logging
import json
import os
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv

load_dotenv()

try:
    import openai
    from openai import AsyncOpenAI
    openai.api_key = os.getenv("OPENAI_API_KEY")
    OPENAI_AVAILABLE = openai.api_key is not None
    if OPENAI_AVAILABLE:
        async_openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except ImportError:
    openai, async_openai_client, OPENAI_AVAILABLE = None, None, False

from .ledger import TransactionType
# Fix the import - use direct import instead of module import
from .prompts import FOUNDER_PLANNING_PROMPT, FOUNDER_DELEGATION_PROMPT, FOUNDER_WAITING_PROMPT, WORKER_AGENT_PROMPT

# Constants
MAX_CONSECUTIVE_ERRORS = 3
LLM_TIMEOUT = 90.0  # seconds
FALLBACK_RESPONSE = json.dumps({"reasoning": "Fallback due to LLM unavailability.", "action": "COMPLETE"})

class AgentState(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"

@dataclass
class AgentConfig:
    role: str
    task: str
    budget: float
    parent_id: Optional[str] = None
    max_subagents: int = 5
    price_per_1m_input_tokens: float = 5.0
    price_per_1m_output_tokens: float = 15.0
    spawn_cost: float = 0.01
    tool_use_cost: float = 0.005

class Agent:
    def __init__(self, agent_id: str, config: AgentConfig, ledger, toolbox, orchestrator):
        self.id = agent_id
        self.config = config
        self.ledger = ledger
        self.toolbox = toolbox
        self.orchestrator = orchestrator
        self.logger = logging.getLogger(f"AOS-Agent-{agent_id}")
        self.state = AgentState.ACTIVE
        self.subagents: List[str] = []
        self.thoughts: List[str] = []
        self.results: List[Dict[str, Any]] = []
        self.consecutive_errors = 0
        self.plan: List[Dict[str, Any]] = []
        self.plan_created = False

    async def initialize(self) -> bool:
        await self.ledger.create_account(self.id, self.config.budget)
        self.logger.info(f"Agent initialized. Role: {self.config.role}")
        return True

    async def think(self, context: str = "") -> str:
        self.logger.debug("Thinking...")
        current_balance = await self.ledger.get_balance(self.id)
        if current_balance <= 0:
            self.state = AgentState.DEAD
            return "Out of funds"
        
        prompt = await self._build_prompt(context)
        response_text, cost = await self._call_llm(prompt)
        
        if cost > 0 and not await self.ledger.charge(self.id, cost, TransactionType.API_CALL, "LLM API usage"):
            self.state = AgentState.DEAD
            return "Out of funds after final API call"
        
        if self.state != AgentState.FAILED:
            self.thoughts.append(response_text)
        return response_text

    async def act(self, thought: str) -> Dict[str, Any]:
        self.logger.debug("Acting...")
        action = self._parse_action(thought)
        self.logger.info(f"Decided action: {action.get('type', 'N/A').upper()}")
        
        action_type = action.get("type")
        if action_type == "error": return action
        elif action_type == "delegate": return await self._delegate_task(action)
        elif action_type == "use_tool": return await self._use_tool(action)
        elif action_type == "complete": return await self._complete_task(action)
        elif action_type == "fail": return {"error": thought}
        else: return {"error": f"Unknown action type: {action_type}"}

    async def run(self) -> Dict[str, Any]:
        self.logger.info(f"Starting main execution loop.")
        
        if self.config.parent_id is None and not self.plan_created:
            await self._create_plan()

        while self.state == AgentState.ACTIVE:
            if self.config.parent_id is None:
                action_to_take = await self._get_next_action_from_plan()
                if action_to_take:
                    thought = json.dumps(action_to_take)
                else:
                    self.logger.debug("Founder is waiting for sub-agents to complete their tasks.")
                    if await self._is_task_complete():
                        self.state = AgentState.COMPLETED
                    await asyncio.sleep(2)
                    continue
            else:
                context = f"History of your previous actions and their results: {self.results[-3:]}" if self.results else "This is your first action."
                thought = await self.think(context)

            if self.state != AgentState.ACTIVE: break
            
            result = await self.act(thought)
            self.results.append(result)

            if "error" in result:
                self.logger.error(f"Action error: {result['error']}")
                self.consecutive_errors += 1
                if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS: self.state = AgentState.FAILED
            else:
                self.consecutive_errors = 0
            
            # NEW: Auto-deliver files when task is complete
            if await self._is_task_complete():
                await self._deliver_files()
                self.state = AgentState.COMPLETED
            
            await asyncio.sleep(0.1)
        
        self.logger.info(f"Finished execution with state: {self.state.value}")
        return {"agent_id": self.id, "state": self.state.value}

    async def _create_plan(self):
        self.logger.info("Founder is creating a project plan...")
        # Use the directly imported constant
        planning_prompt = FOUNDER_PLANNING_PROMPT.format(task=self.config.task)
        response_text, cost = await self._call_llm(planning_prompt)
        if cost > 0:
            await self.ledger.charge(self.id, cost, TransactionType.API_CALL, "Project Planning")
        try:
            plan_data = json.loads(response_text)
            self.plan = plan_data.get("plan", [])
            self.plan_created = True
            self.logger.info(f"Project plan created with {len(self.plan)} steps.")
        except json.JSONDecodeError:
            self.logger.error("Failed to parse project plan. Agent will fail.")
            self.state = AgentState.FAILED

    async def _get_next_action_from_plan(self) -> Optional[Dict[str, Any]]:
        if not self.plan_created or not self.plan: return None
        completed_subagents = sum(1 for sid in self.subagents if self.orchestrator.agents.get(sid).state != AgentState.ACTIVE)
        if completed_subagents == len(self.subagents) and len(self.plan) > len(self.subagents):
            next_step_index = len(self.subagents)
            self.logger.info(f"Executing step {next_step_index + 1} of the plan.")
            return self.plan[next_step_index]
        return None

    async def _build_prompt(self, context: str) -> str:
        # This method now acts as a router to the correct prompt template
        balance = await self.ledger.get_balance(self.id)
        if self.config.role.lower() == 'founder':
            has_delegated = any(res.get("action") == "delegate" for res in self.results)
            if has_delegated:
                # Use directly imported constant
                return FOUNDER_WAITING_PROMPT.format(task=self.config.task, balance=balance, context=context)
            else:
                # Use directly imported constant
                return FOUNDER_DELEGATION_PROMPT.format(task=self.config.task, balance=balance, context=context)
        else:
            tools_list = await self.toolbox.list_tools_for_prompt()
            tools_formatted = json.dumps(tools_list, indent=2)
            # Use directly imported constant
            return WORKER_AGENT_PROMPT.format(
                role=self.config.role, task=self.config.task, balance=balance, 
                context=context, tools_formatted=tools_formatted
            )

    async def _call_llm(self, prompt: str) -> Tuple[str, float]:
        border = "=" * 50
        self.logger.debug(f"\n{border}\n>>> PROMPT (Agent: {self.id}) >>>\n{border}\n{prompt}\n{border}")
        if not OPENAI_AVAILABLE:
            self.logger.warning("OpenAI not available, using fallback response.")
            return FALLBACK_RESPONSE, 0.0

        model = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
        api_params = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant. Respond only in the requested JSON format."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
            "timeout": LLM_TIMEOUT,
            "response_format": {"type": "json_object"}
        }

        try:
            response = await asyncio.wait_for(
                async_openai_client.chat.completions.create(**api_params),
                timeout=LLM_TIMEOUT + 10.0 # Add a bit more time for network overhead
            )
            response_text = response.choices[0].message.content
            self.logger.debug(f"\n{border}\n<<< RAW RESPONSE (Agent: {self.id}) <<<\n{border}\n{response_text}\n{border}")
            usage = response.usage
            if usage:
                cost = ((usage.prompt_tokens / 1_000_000) * self.config.price_per_1m_input_tokens) + \
                       ((usage.completion_tokens / 1_000_000) * self.config.price_per_1m_output_tokens)
                return response_text, cost
            return response_text, 0.0
        except asyncio.TimeoutError:
            self.logger.error(f"LLM call timed out for agent {self.id}")
            self.state = AgentState.FAILED
            return f"LLM call timed out after {LLM_TIMEOUT} seconds", 0.0
        except openai.RateLimitError as e:
            self.logger.error(f"OpenAI rate limit hit for agent {self.id}: {e}")
            # Potentially implement retry logic here
            self.state = AgentState.FAILED
            return f"OpenAI rate limit error: {e}", 0.0
        except openai.APIError as e:
             self.logger.error(f"OpenAI API error for agent {self.id}: {e}")
             self.state = AgentState.FAILED
             return f"OpenAI API error: {e}", 0.0
        except Exception as e:
            self.state = AgentState.FAILED
            self.logger.error(f"LLM call failed for agent {self.id}: {e}", exc_info=True)
            return f"LLM call failed: {e}", 0.0

    async def _get_fallback_response(self) -> str:
        return json.dumps({"reasoning": "Fallback.", "action": "COMPLETE"})

    def _parse_action(self, thought: str) -> Dict[str, Any]:
        try:
            json_start, json_end = thought.find('{'), thought.rfind('}') + 1
            if json_start == -1: raise json.JSONDecodeError("No JSON object found.", thought, 0)
            data = json.loads(thought[json_start:json_end])
            action_type = data.get("action", "error").lower()
            tool_field, details, parameters = data.get("tool"), data.get("details", {}), data.get("parameters")
            tool_name = tool_field.get("name") if isinstance(tool_field, dict) else tool_field
            if not parameters and "parameters" in details: parameters = details.get("parameters")
            return {"type": action_type, "tool": tool_name, "details": details, "parameters": parameters or {}}
        except (json.JSONDecodeError, ValueError) as e:
            return {"type": "error", "error": f"JSON parse failed: {e}. Raw: '{thought}'"}

    async def _delegate_task(self, action: Dict[str, Any]) -> Dict[str, Any]:
        parent_balance = await self.ledger.get_balance(self.id)
        if parent_balance < self.config.spawn_cost:
            return {"error": "Insufficient funds for spawn cost."}
        spendable_balance = parent_balance - self.config.spawn_cost
        budget_to_allocate = spendable_balance * 0.75
        
        if not await self.ledger.charge(self.id, self.config.spawn_cost, TransactionType.SPAWN_AGENT, "Spawning sub-agent") or \
           not await self.ledger.charge(self.id, budget_to_allocate, TransactionType.BUDGET_ALLOCATION, "Allocating budget"):
            await self.ledger.credit(self.id, self.config.spawn_cost, TransactionType.REFUND, "Refund for failed delegation.")
            return {"error": "Failed to complete delegation transaction."}
            
        details = action.get("details", {})
        subagent_id = await self.orchestrator.spawn_agent(
            role=details.get("role", "Specialist"), 
            task=details.get("task", "Complete assigned sub-task."), 
            budget=budget_to_allocate, 
            parent_id=self.id
        )
        
        if subagent_id == "error_max_agents_reached":
            await self.ledger.credit(self.id, self.config.spawn_cost + budget_to_allocate, TransactionType.REFUND, "Refund for max agents reached.")
            return {"error": "Maximum agents reached."}

        self.subagents.append(subagent_id)
        return {"action": "delegate", "subagent_id": subagent_id}

    async def _use_tool(self, action: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = action.get("tool")
        if not tool_name: return {"error": "No 'tool' name was specified."}
        if not await self.ledger.charge(self.id, self.config.tool_use_cost, TransactionType.TOOL_USAGE, f"Using tool {tool_name}"):
            return {"error": "Insufficient funds for tool usage"}
        parameters = action.get("parameters", {})
        result = await self.toolbox.execute_tool(tool_name, parameters, self.id)
        return {"action": "use_tool", "tool": tool_name, "parameters": parameters, "result": result}

    async def _complete_task(self, action: Dict[str, Any]) -> Dict[str, Any]:
        self.state = AgentState.COMPLETED
        return {"action": "complete"}

    async def _is_task_complete(self) -> bool:
        if self.config.parent_id is None: # Founder logic
            if not self.plan_created or not self.plan: return False
            all_steps_delegated = len(self.subagents) == len(self.plan)
            if not all_steps_delegated: return False
            return all(self.orchestrator.agents.get(sid).state != AgentState.ACTIVE for sid in self.subagents if sid in self.orchestrator.agents)
        
        role = self.config.role.lower() # Worker logic
        if 'developer' in role or 'designer' in role:
            return any(res.get("action") == "use_tool" and res.get("tool") == "file_manager" and res.get("result", {}).get("status") == "success" for res in self.results)
        
        return len([r for r in self.results if "error" not in r]) >= 2
    

    # Add a new method for automatic file delivery
    async def _deliver_files(self) -> None:
        """Automatically deliver created files to the delivery folder."""
        if not self.toolbox.delivery_folder:
            self.logger.debug("No delivery folder configured, skipping automatic delivery")
            return
        
        # Find files that were created in this agent's workspace
        workspace_files = []
        try:
            list_result = await self.toolbox.execute_tool("file_manager", {"operation": "list", "path": "."}, self.id)
            if list_result.get("status") == "success":
                workspace_files = list_result.get("items", [])
        except Exception as e:
            self.logger.error(f"Failed to list workspace files for delivery: {e}")
            return
        
        # Deliver each file
        for filename in workspace_files:
            if filename.endswith(('.html', '.css', '.js', '.py', '.txt', '.json', '.xml')):
                try:
                    delivery_result = await self.toolbox.execute_tool(
                        "file_manager", 
                        {
                            "operation": "copy_to_delivery",
                            "path": filename,
                            "delivery_name": filename  # Keep original name
                        }, 
                        self.id
                    )
                    if delivery_result.get("status") == "success":
                        self.logger.info(f"Delivered {filename} to delivery folder")
                    else:
                        self.logger.warning(f"Failed to deliver {filename}: {delivery_result.get('error')}")
                except Exception as e:
                    self.logger.error(f"Error delivering {filename}: {e}")