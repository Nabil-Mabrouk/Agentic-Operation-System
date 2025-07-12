#aos/orchestrator.py
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
from .exceptions import MaxAgentsReachedError
import websockets
import json
from .llm_clients.base import BaseLLMClient # <--- NOUVEL IMPORT
from collections import deque # Utiliser une deque pour une performance optimale
import shutil

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

    async def _create_agent(self, config: AgentConfig) -> str:
        """Creates an agent, its dedicated toolbox, and its workspace."""

        async with self._agent_creation_lock:
            if len(self.agents) >= self.config.max_agents:
                # Lève une exception claire au lieu de retourner une chaîne.
                raise MaxAgentsReachedError(f"Cannot spawn new agent. The system limit of {self.config.max_agents} agents has been reached.")

        agent_id = str(uuid.uuid4())[:8]
        # --- NOUVEAUTÉ : CRÉER UNE BOÎTE AUX LETTRES POUR LE NOUVEL AGENT ---
        self.mailboxes[agent_id] = deque()
        agent_workspace = os.path.join(self.config.workspace_path, agent_id)
        os.makedirs(agent_workspace, exist_ok=True)

        agent_toolbox = Toolbox(workspace_dir=agent_workspace, delivery_folder=self.config.delivery_path, orchestrator=self)
        await agent_toolbox.initialize()
        self.logger.debug(f"Initialized toolbox for agent {agent_id} in workspace '{agent_workspace}'")
        self.logger.info(f"Creating agent {agent_id} with role '{config.role}' in workspace '{agent_workspace}'")

        agent = self.AgentClass(
            agent_id=agent_id, 
            config=config, 
            ledger=self.ledger, 
            toolbox=agent_toolbox,
            orchestrator=self,
            llm_client=self.llm_client # <--- PASSE LE CLIENT À L'AGENT
        )
        await agent.initialize()
        self.agents[agent_id] = agent
        self.logger.info(f"Agent {agent_id} ({config.role}) created with workspace '{agent_workspace}'")

        # --- NOTIFICATION ---
        await self._notify_clients({
            "type": "agent_created",
            "payload": {
                "node": {"id": agent_id, "label": f"{config.role}\n({agent_id})", "title": config.task, "state": "active"},
                "edge": {"from": config.parent_id, "to": agent_id} if config.parent_id else None
            }
        })
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

    async def handle_tool_request(self, requester_id: str, description: str):
        """
        Handles a request from an agent to create a new tool by spawning a ToolForgingAgent.
        """
        # 1. Vérifier si la fonctionnalité est activée
        if not self.config.capabilities.allow_tool_creation:
            self.logger.warning(
                f"Agent {requester_id} requested a new tool, but creation is disabled by system configuration."
            )
            # Envoyer un message en retour à l'agent demandeur pour qu'il sache que sa requête est refusée
            await self.send_message(
                sender_id="AOS_SYSTEM", 
                recipient_id=requester_id,
                content={
                    "status": "tool_request_denied", 
                    "reason": "Tool creation is disabled in the system configuration."
                }
            )
            return

        self.logger.info(f"Tool request from {requester_id} approved. Spawning a Tool Forging Agent.")
        
        # 2. Définir la tâche précise pour l'agent forgeron
        # Ce prompt est crucial pour guider le forgeron.
        forging_task = (
            f"An agent has requested a new tool with the following description: '{description}'.\n"
            "Your mission is to fulfill this request by following these steps precisely:\n"
            "1.  **Design the Tool**: Based on the description, design a Python class that inherits from `BaseTool` from `aos.tools.base_tool`. It must have `__init__`, `get_schema`, and `execute` methods. The tool code must be self-contained and use only standard Python libraries.\n"
            "2.  **Write the Tool Code**: Use the `file_manager` to write the complete Python code for the tool into a file named `new_tool.py`.\n"
            "3.  **Write a Test**: Create a simple but effective test for the new tool using `pytest`. The test should validate the tool's core functionality. Save this test code into a file named `test_new_tool.py`.\n"
            "4.  **Validate your Work**: Use the `code_executor` tool to run `pytest` on your test file (`pytest test_new_tool.py`). The output must show that the test passed.\n"
            "5.  **Report Success**: If the test passes, use the `messaging` tool to send a final report to your parent agent (ID: {parent_id}) with the exact content: `{{'status': 'tool_creation_success', 'tool_code_path': 'new_tool.py', 'test_code_path': 'test_new_tool.py'}}`."
        )

        # 3. Spawner l'agent forgeron
        # L'agent demandeur devient le "manager" temporaire du forgeron pour recevoir le rapport.
        forger_budget = self.config.initial_budget * 0.2 # Allouer un budget conséquent
        await self.spawn_agent(
            role="Tool Forging Agent",
            task=forging_task,
            budget=forger_budget,
            parent_id=requester_id 
        )

    async def _process_system_events(self):
        """
        Scans mailboxes for system-level messages, like tool creation reports,
        and triggers corresponding actions.
        """
        # On itère sur une copie pour pouvoir modifier le dictionnaire si besoin
        for agent_id, mailbox in list(self.mailboxes.items()):
            agent = self.agents.get(agent_id)
            # On s'intéresse uniquement aux messages envoyés par les Forgerons
            if not agent or agent.config.role != "Tool Forging Agent":
                continue

            # On ne veut pas vider la boîte aux lettres du manager, mais celle du forgeron
            # Ici, le forgeron envoie un message à son parent (l'agent demandeur).
            # La logique doit donc être de lire la boîte du *parent*.
            parent_id = agent.config.parent_id
            if not parent_id or parent_id not in self.mailboxes:
                continue

            messages_to_process = await self.get_messages(parent_id)
            for msg in messages_to_process:
                # On vérifie que le message vient bien du forgeron
                if msg.get("from") != agent_id:
                    # Ce n'est pas le bon message, on le remet dans la boîte
                    await self.send_message(msg['from'], parent_id, msg['content'])
                    continue

                content = msg.get("content", {})
                if content.get("status") == "tool_creation_success":
                    self.logger.info(f"Detected successful tool creation report from {agent_id}.")
                    tool_path = content.get("tool_code_path")
                    
                    # Déclencher le déploiement
                    await self._deploy_new_tool(agent_id, parent_id, tool_path)
                    
                    # Le travail du forgeron est terminé
                    agent.state = AgentState.COMPLETED

    async def _deploy_new_tool(self, forger_agent_id: str, requester_agent_id: str, tool_path_in_workspace: str):
        """Deploys a new tool created by an agent."""
        self.logger.info(f"Deploying new tool '{tool_path_in_workspace}' from agent {forger_agent_id}...")
        
        # 1. Construire les chemins
        forger_workspace = os.path.join(self.config.workspace_path, forger_agent_id)
        source_path = os.path.join(forger_workspace, tool_path_in_workspace)
        
        if not os.path.exists(source_path):
            self.logger.error(f"Tool file '{source_path}' not found for deployment. Deployment failed.")
            return

        tool_name = os.path.basename(tool_path_in_workspace).replace('.py', '')
        # Nom de fichier unique pour éviter les conflits
        dest_filename = f"generated_{tool_name}_{forger_agent_id}.py"
        plugins_dir = os.path.join(os.path.dirname(__file__), 'tools', 'plugins')
        dest_path = os.path.join(plugins_dir, dest_filename)

        # 2. Copier le fichier de l'outil dans le répertoire des plugins
        try:
            shutil.copy(source_path, dest_path)
            self.logger.info(f"New tool '{dest_filename}' deployed to plugins directory.")
        except Exception as e:
            self.logger.error(f"Failed to copy new tool to plugins directory: {e}")
            return

        # 3. Forcer tous les Toolboxes à se rafraîchir
        await self._refresh_all_toolboxes()

        # 4. Notifier l'agent demandeur que son outil est prêt
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