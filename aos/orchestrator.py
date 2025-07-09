import asyncio
import logging
import uuid
from typing import Dict, List, Any, Optional
from .config import SystemConfig  # Import from config module
from .agent import Agent, AgentConfig, AgentState
from .ledger import Ledger
from .toolbox import Toolbox

class Orchestrator:
    """The OS Kernel - manages the lifecycle of all agents"""
    
    def __init__(self, ledger: Ledger, toolbox: Toolbox, config: SystemConfig):
        self.ledger = ledger
        self.toolbox = toolbox
        self.config = config
        self.logger = logging.getLogger("AOS-Orchestrator")
        self.agents: Dict[str, Agent] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.system_start_time = None
        
    async def initialize(self) -> None:
        """Initialize the orchestrator"""
        self.logger.info("Orchestrator initialized")
        self.system_start_time = asyncio.get_event_loop().time()
        
    async def spawn_founder_agent(self, objective: str, budget: float) -> str:
        """Spawn the founder agent"""
        founder_config = AgentConfig(
            role="Founder",
            task=f"Build and manage a team to achieve: {objective}",
            budget=budget,
            max_subagents=self.config.max_agents - 1
        )
        
        return await self._create_agent(founder_config)
        
    async def spawn_agent(self, role: str, task: str, budget: float, parent_id: Optional[str] = None) -> str:
        """Spawn a new agent"""
        agent_config = AgentConfig(
            role=role,
            task=task,
            budget=budget,
            parent_id=parent_id,
            api_cost_per_call=self.config.api_cost_per_call
        )
        
        return await self._create_agent(agent_config)
        
    async def _create_agent(self, config: AgentConfig) -> str:
        """Create a new agent"""
        agent_id = str(uuid.uuid4())[:8]  # Short ID for readability
        
        # Check system limits
        if len(self.agents) >= self.config.max_agents:
            raise ValueError("Maximum number of agents reached")
            
        # Create agent
        agent = Agent(
            agent_id=agent_id,
            config=config,
            ledger=self.ledger,
            toolbox=self.toolbox,
            orchestrator=self
        )
        
        # Initialize agent
        await agent.initialize()
        
        # Store agent
        self.agents[agent_id] = agent
        
        self.logger.info(f"Agent {agent_id} created: {config.role}")
        return agent_id
        
    async def run(self) -> Dict[str, Any]:
        """Run the orchestrator event loop"""
        self.logger.info("Starting orchestrator event loop")
        
        # Start all agents
        for agent_id, agent in self.agents.items():
            if agent.state == AgentState.ACTIVE:
                task = asyncio.create_task(self._run_agent(agent))
                self.running_tasks[agent_id] = task
                
        # Wait for all agents to complete or system timeout
        try:
            completed, pending = await asyncio.wait(
                self.running_tasks.values(),
                timeout=300,  # 5 minute timeout
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                
        except asyncio.TimeoutError:
            self.logger.warning("System timeout reached")
            
        # Collect results
        results = await self._collect_results()
        
        self.logger.info("Orchestrator event loop finished")
        return results
        
    async def _run_agent(self, agent: Agent) -> None:
        """Run a single agent"""
        try:
            result = await agent.run()
            self.logger.info(f"Agent {agent.id} finished with state {result['state']}")
        except Exception as e:
            self.logger.error(f"Agent {agent.id} crashed: {str(e)}")
            agent.state = AgentState.FAILED
            
    async def _collect_results(self) -> Dict[str, Any]:
        """Collect results from all agents"""
        results = {
            "total_agents": len(self.agents),
            "agent_states": {},
            "hierarchy": {},
            "total_cost": await self.ledger.get_total_expenditure()
        }
        
        for agent_id, agent in self.agents.items():
            results["agent_states"][agent_id] = {
                "state": agent.state.value,
                "role": agent.config.role,
                "parent": agent.config.parent_id,
                "subagents": agent.subagents,
                "final_balance": await self.ledger.get_balance(agent_id)
            }
            
            # Build hierarchy
            if agent.config.parent_id:
                if agent.config.parent_id not in results["hierarchy"]:
                    results["hierarchy"][agent.config.parent_id] = []
                results["hierarchy"][agent.config.parent_id].append(agent_id)
                
        return results
        
    async def shutdown(self) -> None:
        """Gracefully shutdown the orchestrator"""
        self.logger.info("Shutting down orchestrator")
        
        # Cancel all running tasks
        for task in self.running_tasks.values():
            if not task.done():
                task.cancel()
                
        # Wait for tasks to finish
        if self.running_tasks:
            await asyncio.gather(*self.running_tasks.values(), return_exceptions=True)
            
        self.logger.info("Orchestrator shutdown complete")