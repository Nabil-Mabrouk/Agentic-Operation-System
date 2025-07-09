import asyncio
import logging
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

# Handle optional openai import
try:
    import openai
except ImportError:
    openai = None

from .ledger import TransactionType

class AgentState(Enum):
    """Possible states of an agent"""
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"  # Ran out of funds

@dataclass
class AgentConfig:
    """Configuration for an agent"""
    role: str
    task: str
    budget: float
    parent_id: Optional[str] = None
    max_subagents: int = 5  # Increased from 3 to allow more delegation
    api_cost_per_call: float = 0.01

class Agent:
    """The fundamental unit of work in AOS"""
    
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
        self.results: List[str] = []
        
    async def initialize(self) -> bool:
        """Initialize the agent"""
        # Create account in ledger
        await self.ledger.create_account(self.id, self.config.budget)
        
        self.logger.info(f"Agent initialized: {self.config.role}")
        self.logger.info(f"Task: {self.config.task}")
        self.logger.info(f"Budget: ${self.config.budget:.2f}")
        
        return True
        
    async def think(self, context: str = "") -> str:
        """Agent thinks about its task (calls LLM)"""
        # Charge for API call
        if not await self.ledger.charge(
            self.id, 
            self.config.api_cost_per_call,
            TransactionType.API_CALL,
            "LLM thinking"
        ):
            self.state = AgentState.DEAD
            return "Out of funds - cannot think"
            
        # Prepare prompt (now async)
        prompt = await self._build_prompt(context)
        
        try:
            # Call LLM (using OpenAI as example)
            response = await self._call_llm(prompt)
            self.thoughts.append(response)
            self.logger.debug(f"Agent thought: {response[:100]}...")
            return response
        except Exception as e:
            self.logger.error(f"Error in think(): {str(e)}")
            return f"Error thinking: {str(e)}"
    
    async def act(self, thought: str) -> Dict[str, Any]:
        """Agent takes action based on its thought"""
        # Parse thought to determine action
        action = self._parse_action(thought)
        
        if action["type"] == "delegate":
            return await self._delegate_task(action)
        elif action["type"] == "use_tool":
            return await self._use_tool(action)
        elif action["type"] == "complete":
            return await self._complete_task(action)
        else:
            return {"error": "Unknown action type"}
            
    async def run(self) -> Dict[str, Any]:
        """Main execution loop for the agent"""
        self.logger.info("Agent starting execution")
        
        while self.state == AgentState.ACTIVE:
            # Think about the task
            thought = await self.think()
            
            if self.state == AgentState.DEAD:
                break
                
            # Act on the thought
            result = await self.act(thought)
            
            # Process result
            if "error" in result:
                self.logger.error(f"Action failed: {result['error']}")
                # Try to recover or fail gracefully
                if await self._should_fail():
                    self.state = AgentState.FAILED
                    break
            else:
                self.results.append(result)
                
            # Check if task is complete
            if await self._is_task_complete():
                self.state = AgentState.COMPLETED
                break
                
            # Small delay to prevent tight loops
            await asyncio.sleep(0.1)
            
        self.logger.info(f"Agent finished with state: {self.state.value}")
        return {
            "agent_id": self.id,
            "state": self.state.value,
            "results": self.results,
            "subagents": self.subagents,
            "final_balance": await self.ledger.get_balance(self.id)
        }
        
    async def _build_prompt(self, context: str) -> str:
        """Build prompt for LLM"""
        current_balance = await self.ledger.get_balance(self.id)
        available_tools = await self.toolbox.list_tools()
        
        return f"""You are an autonomous agent in the Agentic Operating System.

Role: {self.config.role}
Task: {self.config.task}
Current Budget: ${current_balance:.2f}
Available Tools: {available_tools}

Context: {context}

Previous thoughts: {self.thoughts[-3:] if self.thoughts else "None"}

IMPORTANT: You are part of a multi-agent system. For complex tasks, you should DELEGATE by spawning specialized sub-agents rather than trying to do everything yourself.

Your task "{self.config.task}" is complex. Consider:
1. What specialized skills are needed?
2. Can you break this into smaller sub-tasks?
3. Would spawning experts be more cost-effective?

Based on your role and task, decide on the best action:
1. DELEGATE: Break down the task and spawn a sub-agent with specific expertise
2. USE_TOOL: Use an available tool to make progress on a specific part
3. COMPLETE: Only if the task is truly finished

Respond in JSON format:
{{
    "reasoning": "Your reasoning here",
    "action": "DELEGATE|USE_TOOL|COMPLETE",
    "details": {{
        "role": "specific role for sub-agent (if DELEGATING)",
        "task": "specific task for sub-agent (if DELEGATING)",
        "budget": "budget to allocate to sub-agent (if DELEGATING)",
        "tool": "tool name (if USING_TOOL)",
        "parameters": {{tool parameters (if USING_TOOL)}}
    }}
}}"""
            
    async def _call_llm(self, prompt: str) -> str:
        """Call the language model"""
        # This is a placeholder - integrate with your preferred LLM
        if openai is None:
            # Smart fallback that alternates between delegation and tool usage
            import random
            if random.random() < 0.7:  # 70% chance to try delegation
                roles = ["Frontend Developer", "Backend Developer", "DevOps Engineer", "Database Specialist", "UI/UX Designer"]
                tasks = [
                    "Build responsive user interface",
                    "Create REST API endpoints", 
                    "Set up deployment pipeline",
                    "Design database schema",
                    "Create user authentication system"
                ]
                return json.dumps({
                    "reasoning": "This complex task requires multiple specialists. I'll delegate to sub-agents.",
                    "action": "DELEGATE",
                    "details": {
                        "role": random.choice(roles),
                        "task": random.choice(tasks),
                        "budget": 150.0
                    }
                })
            else:  # 30% chance to use tools
                tools = ["web_search", "code_executor", "file_manager"]
                return json.dumps({
                    "reasoning": "I'll use available tools to make progress on the web application.",
                    "action": "USE_TOOL",
                    "details": {
                        "tool": random.choice(tools),
                        "parameters": {
                            "query": "web application development best practices" if tools[0] == "web_search" else 
                                    "print('Hello, World!')" if tools[0] == "code_executor" else
                                    {"operation": "list", "path": "."}
                        }
                    }
                })
            
        try:
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            # Better fallback for errors
            return json.dumps({
                "reasoning": f"Error calling LLM: {str(e)}. I'll try a different approach.",
                "action": "USE_TOOL",
                "details": {
                    "tool": "code_executor",
                    "parameters": {
                        "code": "print('Hello, World!')",
                        "language": "python"
                    }
                }
            })
            
    def _parse_action(self, thought: str) -> Dict[str, Any]:
        """Parse the agent's thought to determine action"""
        try:
            # Try to parse as JSON
            data = json.loads(thought)
            return {
                "type": data.get("action", "COMPLETE").lower(),
                "reasoning": data.get("reasoning", ""),
                "details": data.get("details", {})
            }
        except:
            # Fallback parsing
            thought_lower = thought.lower()
            if "delegate" in thought_lower or "spawn" in thought_lower:
                return {"type": "delegate", "reasoning": thought, "details": {}}
            elif "tool" in thought_lower:
                return {"type": "use_tool", "reasoning": thought, "details": {}}
            else:
                return {"type": "complete", "reasoning": thought, "details": {}}
                
    async def _delegate_task(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Delegate a task to a new sub-agent"""
        # Check if we can spawn more agents
        if len(self.subagents) >= self.config.max_subagents:
            self.logger.warning(f"Agent {self.id} reached maximum subagents limit ({self.config.max_subagents})")
            return {"error": "Maximum subagents reached"}
            
        # Charge for spawning
        spawn_cost = 10.0  # This should come from config
        if not await self.ledger.charge(
            self.id, spawn_cost, TransactionType.SPAWN_AGENT, "Spawning sub-agent"
        ):
            return {"error": "Insufficient funds to spawn sub-agent"}
            
        # Create sub-agent
        details = action.get("details", {})
        subagent_role = details.get("role", "assistant")
        subagent_task = details.get("task", "Assist with task")
        subagent_budget = details.get("budget", self.config.budget * 0.3)
        
        subagent_id = await self.orchestrator.spawn_agent(
            role=subagent_role,
            task=subagent_task,
            budget=subagent_budget,
            parent_id=self.id
        )
        
        self.subagents.append(subagent_id)
        self.logger.info(f"Agent {self.id} spawned sub-agent {subagent_id} ({subagent_role})")
        
        return {
            "action": "delegate",
            "subagent_id": subagent_id,
            "role": subagent_role,
            "task": subagent_task,
            "budget": subagent_budget
        }
        
    async def _use_tool(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Use a tool to perform an action"""
        details = action.get("details", {})
        tool_name = details.get("tool")
        
        if not tool_name:
            return {"error": "No tool specified"}
            
        # Charge for tool usage
        if not await self.ledger.charge(
            self.id, 0.5, TransactionType.TOOL_USAGE, f"Using tool {tool_name}"
        ):
            return {"error": "Insufficient funds for tool usage"}
            
        # Execute tool
        parameters = details.get("parameters", {})
        result = await self.toolbox.execute_tool(tool_name, parameters, self.id)
        
        self.logger.info(f"Agent {self.id} used tool {tool_name}")
        return {
            "action": "use_tool",
            "tool": tool_name,
            "parameters": parameters,
            "result": result
        }
        
    async def _complete_task(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Mark the task as completed"""
        self.state = AgentState.COMPLETED
        message = action.get("details", {}).get("message", "Task completed successfully")
        self.logger.info(f"Agent {self.id} completed task: {message}")
        return {
            "action": "complete",
            "message": message,
            "final_balance": await self.ledger.get_balance(self.id)
        }
        
    async def _should_fail(self) -> bool:
        """Determine if the agent should fail"""
        # More lenient: fail after 10 consecutive errors or if out of funds
        error_count = sum(1 for r in self.results[-10:] if "error" in r)
        current_balance = await self.ledger.get_balance(self.id)
        return error_count >= 10 or current_balance < self.config.api_cost_per_call
        
    async def _is_task_complete(self) -> bool:
        """Check if the task is complete"""
        # More sophisticated completion check
        if len(self.subagents) > 0:
            # Check if all sub-agents have completed
            all_subagents_complete = True
            for subagent_id in self.subagents:
                # This would need to be implemented to check sub-agent status
                # For now, assume they're working
                all_subagents_complete = False
                break
            
            if all_subagents_complete and len(self.results) > 0:
                return True
        
        # Simple heuristic: check if we have meaningful results
        return len(self.results) > 5  # Require more results before considering complete