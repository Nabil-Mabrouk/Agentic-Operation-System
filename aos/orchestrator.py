#aos/orchestrator.py
# aos/orchestrator.py
import asyncio
import logging
import uuid
import os
import shutil
import re
import json
from collections import deque
from typing import Dict, Any, List, Optional, Deque

from .agent import Agent, AgentConfig, AgentState
from .config import SystemConfig
from .ledger import Ledger
from .toolbox import Toolbox
from .exceptions import MaxAgentsReachedError
from .llm_clients.base import BaseLLMClient
import websockets

# Constants
SIMULATION_TIMEOUT = 600.0  # seconds
PROGRESS_REPORT_INTERVAL = 30.0  # seconds

class Orchestrator:
    def __init__(self, ledger: Ledger, config: SystemConfig,  llm_client: BaseLLMClient):
        self.ledger = ledger
        self.config = config
        self.llm_client = llm_client # <--- NOUVEL ATTRIBUT
        self.logger = logging.getLogger("AOS-Orchestrator")
        self.agents: Dict[str, Agent] = {}
        self.AgentClass = Agent # <--- NOUVELLE LIGNE : Permet de substituer Agent dans les tests
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.system_start_time: Optional[float] = None
        self._agent_creation_lock = asyncio.Lock()
        self._last_progress_report_time: Optional[float] = None
        self.simulation_timeout = config.simulation_timeout if hasattr(config, 'simulation_timeout') else 600.0
        self.shutdown_timeout = config.shutdown_timeout if hasattr(config, 'shutdown_timeout') else 10.0
        # --- NOUVEAUTÉS POUR LA VISUALISATION ---
        self.websocket_server = None
        self.connected_clients = set()
        self.mailboxes: Dict[str, deque[Dict[str, Any]]] = {}
        # Ensemble des descriptions d'outils dont la création est déjà en cours
        self.pending_tool_requests: Dict[str, str] = {}

    async def _notify_clients(self, event: Dict[str, Any]):
        """Envoie un événement JSON à tous les clients connectés."""
        if self.connected_clients:
            message = json.dumps(event)
            # Crée une tâche pour chaque envoi pour ne pas bloquer
            tasks = [asyncio.create_task(client.send(message)) for client in self.connected_clients]
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _websocket_handler(self, websocket):
        """Gère les connexions WebSocket entrantes."""
        self.connected_clients.add(websocket)
        self.logger.info(f"Visualizer client connected: {websocket.remote_address}")
        try:
            # Envoie l'état initial du graphe au nouveau client
            initial_state = self._get_graph_state()
            await self._notify_clients({"type": "full_sync", "payload": initial_state})
            
            # Garde la connexion ouverte
            async for message in websocket:
                pass
        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f"Visualizer client disconnected: {websocket.remote_address}")
        finally:
            self.connected_clients.remove(websocket)

    def _get_graph_state(self) -> Dict[str, Any]:
        """Construit un snapshot de l'état actuel du graphe."""
        nodes = [
            {"id": agent.id, "label": f"{agent.config.role}\n({agent.id})", "title": agent.config.task, "state": agent.state.value}
            for agent in self.agents.values()
        ]
        edges = [
            {"from": agent.config.parent_id, "to": agent.id}
            for agent in self.agents.values() if agent.config.parent_id
        ]
        return {"nodes": nodes, "edges": edges}

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

    async def spawn_agent(self, role: str, task: str, budget: float, parent_id: Optional[str] = None, completion_criteria: Optional[Dict[str, Any]] = None) -> str:
        self.logger.info(f"Spawning new agent. Role: {role}, Parent: {parent_id}")
        
        agent_config = AgentConfig(
            role=role,
            task=task,
            budget=budget,
            parent_id=parent_id,
            completion_criteria=completion_criteria, # <--- NOUVELLE LIGNE
            price_per_1m_input_tokens=self.config.price_per_1m_input_tokens,
            price_per_1m_output_tokens=self.config.price_per_1m_output_tokens,
            spawn_cost=self.config.spawn_cost,
            tool_use_cost=self.config.tool_use_cost
        )
        return await self._create_agent(agent_config)

# Dans la classe Orchestrator
    async def _create_agent(self, config: AgentConfig) -> str:
        """Creates an agent, its dedicated toolbox, and its workspace."""
        async with self._agent_creation_lock:
            if len(self.agents) >= self.config.max_agents:
                raise MaxAgentsReachedError(f"Cannot spawn new agent. The system limit of {self.config.max_agents} agents has been reached.")

            agent_id = str(uuid.uuid4())[:8]
            self.mailboxes[agent_id] = deque()
            
            agent_workspace = os.path.join(self.config.workspace_path, agent_id)
            os.makedirs(agent_workspace, exist_ok=True)
            
            # --- LOGIQUE DE PRIVILÈGE POUR LE FORGERON ---
            # Sauvegarder la config des outils désactivés
            original_disabled_tools = list(self.config.disabled_tools)
            is_forger = config.role == "Tool Forging Agent"
            if is_forger:
                # Le forgeron ne doit avoir aucun outil désactivé pour pouvoir travailler
                self.config.disabled_tools = []
                self.logger.info(f"Granting temporary full tool access to Tool Forging Agent {agent_id}.")

            agent_toolbox = Toolbox(
                workspace_dir=agent_workspace,
                delivery_folder=self.config.delivery_path,
                orchestrator=self
            )
            await agent_toolbox.initialize()
            
            # Restaurer la configuration originale après l'initialisation du toolbox
            self.config.disabled_tools = original_disabled_tools
            # --- FIN DE LA LOGIQUE DE PRIVILÈGE ---

            agent = self.AgentClass(
                agent_id=agent_id, 
                config=config, 
                ledger=self.ledger, 
                toolbox=agent_toolbox,
                orchestrator=self,
                llm_client=self.llm_client
            )
            await agent.initialize()
            self.agents[agent_id] = agent
            self.logger.info(f"Agent {agent_id} ({config.role}) created with workspace '{agent_workspace}'")
            return agent_id
    
    # --- NOUVELLE MÉTHODE POUR LA COMMUNICATION ---
    async def send_message(self, sender_id: str, recipient_id: str, content: Dict[str, Any]):
        """Place un message dans la boîte aux lettres du destinataire."""
        if recipient_id not in self.mailboxes:
            self.logger.error(f"Agent {sender_id} tried to send a message to a non-existent agent {recipient_id}.")
            return False
            
        message = {
            "from": sender_id,
            "to": recipient_id,
            "content": content,
            "timestamp": asyncio.get_event_loop().time()
        }
        self.mailboxes[recipient_id].append(message)
        self.logger.info(f"Message from {sender_id} to {recipient_id} queued.")
        return True
    
    # --- NOUVELLE MÉTHODE POUR LA LECTURE ---
    async def get_messages(self, agent_id: str) -> List[Dict[str, Any]]:
        """Récupère et vide la boîte aux lettres d'un agent."""
        if agent_id not in self.mailboxes:
            return []
            
        messages = list(self.mailboxes[agent_id])
        self.mailboxes[agent_id].clear() # Vider la boîte après lecture
        return messages
    
    async def run(self) -> Dict[str, Any]:

        # --- DÉMARRAGE DU SERVEUR WEBSOCKET ---
        self.websocket_server = await websockets.serve(self._websocket_handler, "localhost", 8765)
        self.logger.info("Visualizer WebSocket server started on ws://localhost:8765")
        self.logger.info("Starting orchestrator event loop...")

        self._last_progress_report_time = self.system_start_time
        
        while True:
            active_tasks = self._get_active_tasks()
            self.logger.debug(f"Orchestrator loop tick. Running tasks: {len(active_tasks)}/{len(self.agents)} agents.")
            await self._process_system_events()
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
        return (asyncio.get_event_loop().time() - self.system_start_time) > self.simulation_timeout # Utilise la variable d'instance

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
                # Utilise la variable d'instance configurable
                await asyncio.wait_for(asyncio.gather(*tasks_to_cancel, return_exceptions=True), timeout=self.shutdown_timeout)
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
        finally: # <--- AJOUTER UN BLOC FINALLY
            # --- NOTIFICATION ---
            await self._notify_clients({
                "type": "agent_state_changed",
                "payload": {"id": agent.id, "state": agent.state.value}
            })

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
                # --- ARRÊT DU SERVEUR WEBSOCKET ---
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()
            self.logger.info("Visualizer WebSocket server stopped.")

        self.logger.info("Shutting down orchestrator...")
        tasks_to_cancel = [task for task in self.running_tasks.values() if not task.done()]
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        self.logger.info("Orchestrator shutdown complete")

# Dans la classe Orchestrator
    async def handle_tool_request(self, requester_id: str, description: str):
        """
        Handles a request from an agent to create a new tool by spawning a ToolForgingAgent.
        """
        # 1. Vérifier si la fonctionnalité est activée
        if not self.config.capabilities.allow_tool_creation:
            self.logger.warning(f"Agent {requester_id} requested a new tool, but creation is disabled.")
            await self.send_message(
                sender_id="AOS_SYSTEM", 
                recipient_id=requester_id,
                content={"status": "tool_request_denied", "reason": "Tool creation is disabled."}
            )
            return
            
        # 2. Vérification anti-spam
        if requester_id in self.pending_tool_requests:
            self.logger.warning(f"Agent {requester_id} already has a pending tool request. Ignoring duplicate.")
            await self.send_message(
                sender_id="AOS_SYSTEM",
                recipient_id=requester_id,
                content={"status": "tool_request_duplicate", "reason": "A tool request is already being processed."}
            )
            return

        self.pending_tool_requests[requester_id] = description
        self.logger.info(f"Tool request for '{description}' from {requester_id} approved. Spawning a Tool Forging Agent.")

        # 3. Préparer un Toolbox temporaire pour éduquer le Forgeron
        forger_toolbox = Toolbox(workspace_dir="temp_forger_space", orchestrator=self)
        original_disabled_tools = list(self.config.disabled_tools)
        self.config.disabled_tools = [] # Le forgeron doit voir tous les outils pour son prompt
        await forger_toolbox.initialize()
        self.config.disabled_tools = original_disabled_tools
        
        tools_for_forger_prompt = await forger_toolbox.list_tools_for_prompt()
        tools_for_forger_json = json.dumps(tools_for_forger_prompt, indent=2)

        # 4. Définir la tâche précise pour l'agent forgeron
        # 2. Définir la tâche précise pour l'agent forgeron
        forging_task = (
            f"An agent has requested a new tool with the following description: '{description}'.\n"
            "Your mission is to create and validate this tool. You MUST follow these steps SEQUENTIALLY and EXACTLY. Do not skip any steps.\n\n"
            "--- STEP 1: WRITE THE TOOL ---\n"
            "Based on the description, write the complete Python code for a new tool class that inherits from `BaseTool`. "
            "Save this code into a file named `new_tool.py` using the `file_manager` tool.\n\n"
            
            "--- STEP 2: WRITE THE TEST ---\n"
            "Create a test file named `test_new_tool.py` using `pytest` conventions. This test MUST be robust enough to validate the tool's core functionality.\n\n"

            "--- STEP 3: EXECUTE THE TEST ---\n"
            "This is a CRITICAL VALIDATION step. You MUST use the `pytest_runner` tool to execute `test_new_tool.py`. "
            "You will analyze the result from `pytest_runner`.\n\n"

            "--- STEP 4: FINAL REPORT ---\n"
            "**IF AND ONLY IF** the `return_code` from the `pytest_runner` in STEP 3 was `0`, you must send a success message to your parent agent (ID: {parent_id}). "
            "The message MUST have the exact content: `{{'status': 'tool_creation_success', 'tool_code_path': 'new_tool.py'}}`. "
            "If the test failed, you must instead send a failure message: `{{'status': 'tool_creation_failed', 'reason': 'The created tool did not pass its own tests.'}}`\n\n"

            "--- YOUR AVAILABLE TOOLS ---\n"
            f"{tools_for_forger_json}\n"
            "--- END OF TOOLS ---"
        )

        # 5. Spawner l'agent forgeron
        forger_budget = self.config.initial_budget * 0.2
        await self.spawn_agent(
            role="Tool Forging Agent",
            task=forging_task,
            budget=forger_budget,
            parent_id=requester_id 
        )

# Dans la classe Orchestrator
    def _extract_tool_description_from_task(self, forger_task: str) -> Optional[str]:
        """
        Extracts the original tool description from the forging agent's task prompt
        using regular expressions. This is a helper method for _process_system_events.
        """
        # Looks for the text between single quotes after 'description:'
        match = re.search(r"description: '(.*?)'", forger_task, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        self.logger.warning("Could not extract original tool description from forger's task.")
        return None

    async def _process_system_events(self):
        """
        Scans all mailboxes for system-level messages (like tool creation reports)
        and triggers corresponding orchestrator actions (like deployment).
        This method is designed to be safe against race conditions.
        """
        # Iterate over a copy of agent IDs to handle potential modifications
        for agent_id in list(self.agents.keys()):
            # Check if the agent and its mailbox exist
            agent = self.agents.get(agent_id)
            if not agent or agent_id not in self.mailboxes:
                continue

            # Read the agent's entire mailbox once
            messages_to_process = await self.get_messages(agent_id)
            if not messages_to_process:
                continue

            messages_to_keep_for_agent = []  # List for non-system messages

            for msg in messages_to_process:
                sender_id = msg.get("from")
                content = msg.get("content", {})
                sender_agent = self.agents.get(sender_id)

                # Identify a system message: a successful tool creation report from a Forging Agent
                is_system_message = (
                    sender_agent and
                    sender_agent.config.role == "Tool Forging Agent" and
                    content.get("status") == "tool_creation_success"
                )

                if is_system_message:
                    self.logger.info(f"Orchestrator detected successful tool creation report from {sender_id} in {agent_id}'s mailbox.")
                    tool_path = content.get("tool_code_path")
                    
                    # Trigger deployment
                    await self._deploy_new_tool(sender_id, agent_id, tool_path)
                    
                    # Clean up the pending request
                    original_description = self._extract_tool_description_from_task(sender_agent.config.task)
                    if original_description:
                        self.pending_tool_requests.discard(original_description)

                    # The forger's job is done
                    sender_agent.state = AgentState.COMPLETED
                else:
                    # If it's not a system message, keep it for the agent to process
                    messages_to_keep_for_agent.append(msg)
            
            # Put back any non-system messages into the agent's mailbox
            if messages_to_keep_for_agent:
                # Use extendleft with reversed list to preserve the original order
                self.mailboxes[agent_id].extendleft(reversed(messages_to_keep_for_agent))

    async def _deploy_new_tool(self, forger_agent_id: str, requester_agent_id: str, tool_path_in_workspace: str):
        """Deploys a new tool created by an agent by copying it to the plugins directory."""
        self.logger.info(f"Deploying new tool '{tool_path_in_workspace}' from agent {forger_agent_id}...")
        
        # 1. Build paths
        forger_workspace = os.path.join(self.config.workspace_path, forger_agent_id)
        source_path = os.path.join(forger_workspace, tool_path_in_workspace)
        
        if not os.path.exists(source_path):
            self.logger.error(f"Tool file '{source_path}' not found for deployment. Deployment failed.")
            return

        tool_name = os.path.basename(tool_path_in_workspace).replace('.py', '')
        # Create a unique filename to avoid conflicts
        dest_filename = f"generated_{tool_name}_{forger_agent_id}.py"
        plugins_dir = os.path.join(os.path.dirname(__file__), 'tools', 'plugins')
        dest_path = os.path.join(plugins_dir, dest_filename)

        # 2. Copy the tool file to the plugins directory
        try:
            shutil.copy(source_path, dest_path)
            self.logger.info(f"New tool '{dest_filename}' deployed to plugins directory.")
        except Exception as e:
            self.logger.error(f"Failed to copy new tool to plugins directory: {e}")
            return

        # 3. Refresh all toolboxes so they discover the new tool
        await self._refresh_all_toolboxes()
        # --- NOUVELLE LOGIQUE ---
        # Retirer la requête de la liste d'attente une fois l'outil déployé
        if requester_agent_id in self.pending_tool_requests:
            del self.pending_tool_requests[requester_agent_id]
            self.logger.info(f"Cleared pending tool request for agent {requester_agent_id}.")

        # 4. Notify the original agent that its requested tool is ready
        await self.send_message(
            sender_id="AOS_SYSTEM",
            recipient_id=requester_agent_id,
            content={"status": "tool_request_fulfilled", "tool_name": tool_name}
        )

    async def _refresh_all_toolboxes(self):
        """Asks all agent toolboxes to reload their tools."""
        self.logger.info("Broadcasting toolbox refresh to all agents...")
        for agent in self.agents.values():
            if hasattr(agent, 'toolbox') and agent.toolbox:
                await agent.toolbox.refresh()