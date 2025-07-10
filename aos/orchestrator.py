import asyncio
import logging
import uuid
import os
import shutil
from typing import Dict, Any, List, Optional
from .agent import Agent, AgentConfig, AgentState
from .config import SystemConfig
from .ledger import Ledger
from .toolbox import Toolbox

# Constants
SIMULATION_TIMEOUT = 600.0  # seconds
SHUTDOWN_TIMEOUT = 10.0  # seconds to wait for tasks to cancel
PROGRESS_REPORT_INTERVAL = 30.0  # seconds

class Orchestrator:
    def __init__(self, ledger: Ledger, config: SystemConfig):
        self.ledger = ledger
        self.config = config
        self.logger = logging.getLogger("AOS-Orchestrator")
        self.agents: Dict[str, Agent] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.system_start_time: Optional[float] = None
        self._agent_creation_lock = asyncio.Lock()
        self._last_progress_report_time: Optional[float] = None

    async def initialize(self) -> None:
        self.logger.info("Orchestrator initialized")
        self.system_start_time = asyncio.get_event_loop().time()

    async def spawn_founder_agent(self, objective: str, budget: float) -> str:
        self.logger.info(f"Spawning founder agent with objective: '{objective}'")
        
        founder_config = AgentConfig(
            role="Founder",
            task=f"Oversee the project to achieve the primary objective: {objective}",
            budget=budget,
            max_subagents=self.config.max_agents - 1,
            price_per_1m_input_tokens=self.config.price_per_1m_input_tokens,
            price_per_1m_output_tokens=self.config.price_per_1m_output_tokens,
            spawn_cost=self.config.spawn_cost,
            tool_use_cost=self.config.tool_use_cost
        )
        return await self._create_agent(founder_config)

    async def spawn_agent(self, role: str, task: str, budget: float, parent_id: Optional[str] = None) -> str:
        self.logger.info(f"Spawning new agent. Role: {role}, Parent: {parent_id}")
        
        agent_config = AgentConfig(
            role=role,
            task=task,
            budget=budget,
            parent_id=parent_id,
            price_per_1m_input_tokens=self.config.price_per_1m_input_tokens,
            price_per_1m_output_tokens=self.config.price_per_1m_output_tokens,
            spawn_cost=self.config.spawn_cost,
            tool_use_cost=self.config.tool_use_cost
        )
        return await self._create_agent(agent_config)

    async def _create_agent(self, config: AgentConfig) -> str:
        """Creates an agent, its dedicated toolbox, and its workspace."""
        async with self._agent_creation_lock:
            if len(self.agents) >= self.config.max_agents:
                return "error_max_agents_reached"

            agent_id = str(uuid.uuid4())[:8]
            
            agent_workspace = f"./workspace/{agent_id}"
            os.makedirs(agent_workspace, exist_ok=True)
            
            agent_toolbox = Toolbox(workspace_dir=agent_workspace)
            await agent_toolbox.initialize()

            agent = Agent(
                agent_id=agent_id, 
                config=config, 
                ledger=self.ledger, 
                toolbox=agent_toolbox,
                orchestrator=self
            )
            await agent.initialize()
            self.agents[agent_id] = agent
            self.logger.info(f"Agent {agent_id} ({config.role}) created with workspace '{agent_workspace}'")
            return agent_id

    async def run(self) -> Dict[str, Any]:
        self.logger.info("Starting orchestrator event loop...")
        self._last_progress_report_time = self.system_start_time
        
        while True:
            active_tasks = self._get_active_tasks()
            self.logger.debug(f"Orchestrator loop tick. Running tasks: {len(active_tasks)}/{len(self.agents)} agents.")

            await self._start_new_agent_tasks()
            
            # Check if all tasks are completed
            if not active_tasks and self._all_agents_completed():
                self.logger.info("All agent tasks have completed. Exiting orchestrator loop.")
                break

            # Check for timeout
            if self._is_simulation_timed_out():
                self.logger.warning("System-wide timeout reached. Shutting down.")
                break
            
            await self._report_progress_if_needed()
            await asyncio.sleep(1.0)

        await self._cancel_all_running_tasks()
        self.logger.info("Orchestrator event loop finished. Collecting results.")
        return await self._collect_results()

    def _get_active_tasks(self) -> List[asyncio.Task]:
        return [task for task in self.running_tasks.values() if not task.done()]

    def _all_agents_completed(self) -> bool:
        """Check if all agents have completed their tasks (either successfully or failed)"""
        if not self.agents:
            return False
        
        for agent in self.agents.values():
            if agent.state == AgentState.ACTIVE:
                return False
        return True

    async def _start_new_agent_tasks(self) -> None:
        for agent_id, agent in self.agents.items():
            if agent.state == AgentState.ACTIVE and agent_id not in self.running_tasks:
                self.logger.info(f"Starting task for newly spawned agent: {agent_id}")
                task = asyncio.create_task(self._run_agent(agent))
                self.running_tasks[agent_id] = task

    def _is_simulation_timed_out(self) -> bool:
        return (asyncio.get_event_loop().time() - self.system_start_time) > SIMULATION_TIMEOUT

    async def _report_progress_if_needed(self) -> None:
        current_time = asyncio.get_event_loop().time()
        if self._last_progress_report_time is None or (current_time - self._last_progress_report_time) > PROGRESS_REPORT_INTERVAL:
            active_tasks = self._get_active_tasks()
            total_cost = await self.ledger.get_total_expenditure()
            self.logger.info(f"Progress Report - Active Agents: {len(active_tasks)}, Total Agents: {len(self.agents)}, Total Cost: ${total_cost:.4f}")
            self._last_progress_report_time = current_time

    async def _cancel_all_running_tasks(self) -> None:
        tasks_to_cancel = self._get_active_tasks()
        if tasks_to_cancel:
            self.logger.info(f"Cancelling {len(tasks_to_cancel)} remaining tasks...")
            try:
                await asyncio.wait_for(asyncio.gather(*tasks_to_cancel, return_exceptions=True), timeout=SHUTDOWN_TIMEOUT)
            except asyncio.TimeoutError:
                self.logger.warning("Some tasks did not cancel gracefully within the timeout.")

    async def _run_agent(self, agent: Agent) -> None:
        task = asyncio.current_task()
        task.set_name(agent.id)
        try:
            await agent.run()
        except asyncio.CancelledError:
            self.logger.warning(f"Agent {agent.id} task was cancelled.")
            agent.state = AgentState.FAILED
        except Exception as e:
            self.logger.error(f"Agent {agent.id} crashed with an unhandled exception: {e}", exc_info=True)
            agent.state = AgentState.FAILED

    async def _collect_results(self) -> Dict[str, Any]:
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
            if agent.config.parent_id:
                if agent.config.parent_id not in results["hierarchy"]:
                    results["hierarchy"][agent.config.parent_id] = []
                results["hierarchy"][agent.config.parent_id].append(agent_id)
        return results

    async def shutdown(self) -> None:
        self.logger.info("Shutting down orchestrator...")
        tasks_to_cancel = [task for task in self.running_tasks.values() if not task.done()]
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        self.logger.info("Orchestrator shutdown complete")