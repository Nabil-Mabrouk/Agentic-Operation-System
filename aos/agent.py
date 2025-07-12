import asyncio
import logging
import json
import os
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv
from .exceptions import MaxAgentsReachedError

load_dotenv()


from .ledger import TransactionType
# Fix the import - use direct import instead of module import
from .prompts import (
    FOUNDER_PLANNING_PROMPT, 
    FOUNDER_DELEGATION_PROMPT, 
    FOUNDER_WAITING_PROMPT, 
    WORKER_AGENT_PROMPT, 
    ARCHITECT_VALIDATION_PROMPT # <--- NOM CORRECT
)
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
    completion_criteria: Optional[Dict[str, Any]] = None  # <--- NOUVELLE LIGNE
    parent_id: Optional[str] = None
    max_subagents: int = 5
    price_per_1m_input_tokens: float = 5.0
    price_per_1m_output_tokens: float = 15.0
    spawn_cost: float = 0.01
    tool_use_cost: float = 0.005

class Agent:
    def __init__(self, agent_id: str, config: AgentConfig, ledger, toolbox, orchestrator, llm_client):
        self.id = agent_id
        self.config = config
        self.ledger = ledger
        self.toolbox = toolbox
        self.orchestrator = orchestrator
        self.llm_client = llm_client # <--- NOUVELLE LIGNE
        self.logger = logging.getLogger(f"AOS-Agent-{agent_id}")
        self.state = AgentState.ACTIVE
        self.subagents: List[str] = []
        # Dictionnaire pour mapper un subagent_id à l'index de l'étape du plan qu'il exécute
        self.delegated_tasks: Dict[str, int] = {}
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

        # --- MODIFICATION MAJEURE ---
        # Doit être identique à la logique dans _create_plan
        response_text, input_tokens, output_tokens = await self.llm_client.call_llm(
            prompt, self.orchestrator.config.llm
        )
        
        cost = ((input_tokens / 1_000_000) * self.config.price_per_1m_input_tokens) + \
               ((output_tokens / 1_000_000) * self.config.price_per_1m_output_tokens)
        
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
        elif action_type == "delegate": 
            # On passe l'index de l'étape à la méthode de délégation
            step_index = action.get("details", {}).get("step_index")
            return await self._delegate_task(action, step_index)

        elif action_type == "use_tool": return await self._use_tool(action)
        elif action_type == "request_new_tool":
            return await self._request_new_tool(action)
        elif action_type == "complete": return await self._complete_task(action)
        elif action_type == "fail": 
            self.state = AgentState.FAILED # L'action FAIL doit changer l'état
            return {"error": thought}
        else: return {"error": f"Unknown action type: {action_type}"}

    async def run(self) -> Dict[str, Any]:
        self.logger.info(f"Starting main execution loop.")
        
        # Création du plan si c'est le fondateur
        if self.config.parent_id is None and not self.plan_created:
            await self._create_plan()
            if self.state != AgentState.ACTIVE: # La planification peut échouer
                 self.logger.warning("Plan creation failed. Halting execution.")
                 return {"agent_id": self.id, "state": self.state.value}


        while self.state == AgentState.ACTIVE:
            action_to_take = None
            if self.config.parent_id is None: # Logique du Manager/Fondateur
                action_to_take = await self._get_next_action_from_plan()
                if not action_to_take:
                    # Si pas d'action, le manager attend. On met un petit sleep
                    # pour ne pas surcharger le CPU.
                    await asyncio.sleep(2)
                    continue # On repart au début de la boucle while
            else: # Logique de l'Ouvrier/Worker
                context = f"History of your previous actions and their results: {self.results[-3:]}" if self.results else "This is your first action."
                thought = await self.think(context)
                if self.state != AgentState.ACTIVE: break # Le 'think' peut changer l'état (ex: faillite)
                # L'ouvrier a une action à faire (basée sur sa pensée)
                result = await self.act(thought)
                self.results.append(result)

            # Si le manager a une action (DELEGATE), il l'exécute
            if action_to_take:
                thought_for_act = json.dumps(action_to_take)
                result = await self.act(thought_for_act)
                self.results.append(result)

            # Gestion des erreurs pour tout le monde
            if "error" in self.results[-1]:
                self.logger.error(f"Action error: {self.results[-1]['error']}")
                self.consecutive_errors += 1
                if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS: 
                    self.state = AgentState.FAILED
            else:
                self.consecutive_errors = 0
            
            # Les ouvriers vérifient s'ils ont terminé leur tâche individuelle
            if self.config.parent_id is not None and await self._is_task_complete():
                await self._deliver_files() # <-- Cette logique pourrait être déplacée dans act()
                self.state = AgentState.COMPLETED
            
            await asyncio.sleep(0.1)
        
        self.logger.info(f"Finished execution with state: {self.state.value}")
        return {"agent_id": self.id, "state": self.state.value}

    async def _create_plan(self):
        self.logger.info("Founder is creating a project plan...")
        
        # Phase 1: Génération initiale
        initial_plan_json = await self._generate_initial_plan()
        if not initial_plan_json:
            self.state = AgentState.FAILED
            return

        # Phase 2: Validation et Raffinement (si activé)
        final_plan_data = initial_plan_json
        if self.orchestrator.config.capabilities.allow_advanced_planning:
            self.logger.info("Initiating advanced plan validation...")
            validation_result = await self._validate_plan(initial_plan_json)
            
            if not validation_result.get("is_valid", False):
                self.logger.warning(f"Plan deemed invalid. Reason: {validation_result.get('reasoning')}. Attempting to refine...")
                # Ici, on pourrait boucler, mais pour commencer, une seule passe de raffinement est plus simple.
                final_plan_data = await self._generate_initial_plan(refinement_prompt=validation_result.get('reasoning'))
        
        # Phase 3: Traitement du plan final
        if final_plan_data:
            plan = final_plan_data.get("plan", [])
            if plan:
                self.plan = plan
                self.plan_created = True
                self.logger.info(f"Final plan created with {len(self.plan)} steps.")
                return
        
        self.logger.error("Failed to create a valid final plan.")
        self.state = AgentState.FAILED

    async def _generate_initial_plan(self, refinement_prompt: Optional[str] = None) -> Optional[Dict]:
        prompt_content = FOUNDER_PLANNING_PROMPT.format(task=self.config.task)
        if refinement_prompt:
            prompt_content += f"\n\nPlease refine the plan based on the following feedback: {refinement_prompt}"

        response_text, i, o = await self.llm_client.call_llm(prompt_content, self.orchestrator.config.llm)
        # ... (calcul du coût et gestion des erreurs de l'appel LLM) ...
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            return None

    async def _validate_plan(self, plan_json: Dict) -> Dict:
        prompt_content = ARCHITECT_VALIDATION_PROMPT.format(
            objective=self.config.task,
            plan_json=json.dumps(plan_json, indent=2)
        )
        response_text, i, o = await self.llm_client.call_llm(prompt_content, self.orchestrator.config.llm)
        # ... (calcul du coût) ...
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            return {"is_valid": False, "reasoning": "Failed to get a valid validation response from architect."}


    async def _get_next_action_from_plan(self) -> Optional[Dict[str, Any]]:
        if not self.plan_created or not self.plan:
            return None

        # 1. Lire les messages et mettre à jour le statut des tâches terminées
        messages = await self.orchestrator.get_messages(self.id)
        completed_artifacts = {} # stocke les résultats des tâches finies
        
        for msg in messages:
            sender_id = msg.get("from")
            content = msg.get("content", {})
            if sender_id in self.delegated_tasks and content.get("status") == "task_completed":
                step_index = self.delegated_tasks[sender_id]
                artifacts = content.get("artifacts", [])
                completed_artifacts[step_index] = artifacts
                self.logger.info(f"Step {step_index + 1} confirmed complete by agent {sender_id} with artifacts: {artifacts}")
                # On pourrait aussi retirer la tâche de `delegated_tasks` pour ne pas la traiter à nouveau
        
        # 2. Déterminer la prochaine étape à exécuter
        # La prochaine étape est la première qui n'a pas encore été déléguée
        next_step_index = len(self.subagents)

        if next_step_index >= len(self.plan):
            # Toutes les étapes ont été déléguées. Le manager attend que tout soit fini.
            all_children_done = all(
                self.orchestrator.agents.get(sid).state != AgentState.ACTIVE 
                for sid in self.subagents
            )
            if all_children_done:
                self.logger.info("All plan steps delegated and all agents finished. Founder's task is complete.")
                self.state = AgentState.COMPLETED
            return None

        # 3. Vérifier si les dépendances de l'étape suivante sont satisfaites
        # Logique simple : on ne lance l'étape N que si l'étape N-1 est terminée
        if next_step_index > 0:
            previous_step_index = next_step_index - 1
            previous_agent_id = self.subagents[previous_step_index]
            
            # Si l'agent précédent est toujours actif, on attend
            if self.orchestrator.agents.get(previous_agent_id).state == AgentState.ACTIVE:
                self.logger.debug(f"Waiting for agent {previous_agent_id} (step {previous_step_index + 1}) to complete.")
                return None

        # 4. Préparer et retourner l'action de délégation pour la prochaine étape
        self.logger.info(f"Ready to execute step {next_step_index + 1} of the plan.")
        
        next_step_action = self.plan[next_step_index]
        # Ajouter l'index de l'étape pour le suivi
        next_step_action["details"]["step_index"] = next_step_index

        # Enrichir la tâche avec le contexte des étapes précédentes
        if next_step_index > 0 and (next_step_index - 1) in completed_artifacts:
            artifacts = completed_artifacts[next_step_index - 1]
            context_for_next_task = f"\n\nCONTEXT FROM PREVIOUS STEP: Your colleague has produced the following artifacts: {artifacts}. You should use them as input."
            next_step_action["details"]["task"] += context_for_next_task
            
        return next_step_action

    async def _build_prompt(self, context: str) -> str:
        # --- NOUVELLE LOGIQUE DE LECTURE DES MESSAGES ---
        # Dans _build_prompt
        messages = []
        if self.orchestrator.config.capabilities.allow_messaging:
            messages = await self.orchestrator.get_messages(self.id)
            message_context = ""
        if messages:
            formatted_messages = "\n".join([f"- From {m['from']}: {json.dumps(m['content'])}" for m in messages])
            message_context = f"\n--- NEW MESSAGES ---\nYou have received the following messages:\n{formatted_messages}\n--- END OF MESSAGES ---\n"
        
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
                context=context, tools_formatted=tools_formatted,
                parent_id=self.config.parent_id,
                message_context=message_context
            )

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

    async def _delegate_task(self, action: Dict[str, Any], step_index: Optional[int]) -> Dict[str, Any]:
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
        completion_criteria = details.get("completion_criteria") # <--- NOUVELLE LIGNE

        try:
            subagent_id = await self.orchestrator.spawn_agent(
                role=details.get("role", "Specialist"), 
                task=details.get("task", "Complete assigned sub-task."), 
                budget=budget_to_allocate, 
                parent_id=self.id,
                completion_criteria=completion_criteria # <--- NOUVEAU PARAMÈTRE
            )

            # Si le spawn réussit, on continue ici
            self.subagents.append(subagent_id)
            # Si on a un index, on l'enregistre
            if step_index is not None:
                self.delegated_tasks[subagent_id] = step_index
            return {"action": "delegate", "subagent_id": subagent_id, "step_index": step_index}
        
        except MaxAgentsReachedError as e:
            # Gère l'échec de manière propre si l'exception est levée.
            self.logger.warning(f"Failed to spawn agent: {e}")
            await self.ledger.credit(self.id, self.config.spawn_cost + budget_to_allocate, TransactionType.REFUND, "Refund for max agents reached.")
            return {"error": "Maximum number of agents has been reached.", "details": str(e)}
        
        except Exception as e:
            # Sécurité pour intercepter d'autres erreurs de spawn inattendues
            self.logger.error(f"An unexpected error occurred during agent spawn: {e}", exc_info=True)
            await self.ledger.credit(self.id, self.config.spawn_cost + budget_to_allocate, TransactionType.REFUND, "Refund for unexpected spawn failure.")
            return {"error": "An unexpected error occurred during agent spawn.", "details": str(e)}

    async def _use_tool(self, action: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = action.get("tool")
        if not tool_name: return {"error": "No 'tool' name was specified."}
        if not await self.ledger.charge(self.id, self.config.tool_use_cost, TransactionType.TOOL_USAGE, f"Using tool {tool_name}"):
            return {"error": "Insufficient funds for tool usage"}
        parameters = action.get("parameters", {})
        result = await self.toolbox.execute_tool(tool_name, parameters, self.id)
        return {"action": "use_tool", "tool": tool_name, "parameters": parameters, "result": result}

    async def _request_new_tool(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handles the agent's request to create a new tool."""
        description = action.get("details", {}).get("description")
        if not description:
            return {"error": "Tool description is required to request a new tool."}
        
        self.logger.info(f"Requesting creation of a new tool: '{description}'")
        
        # Délègue la gestion de la requête à l'orchestrateur
        await self.orchestrator.handle_tool_request(self.id, description)
        
        # L'agent a soumis sa requête. Il doit maintenant attendre.
        # On retourne un résultat pour l'historique.
        return {"action": "request_new_tool", "status": "request_submitted", "description": description}
    
    async def _complete_task(self, action: Dict[str, Any]) -> Dict[str, Any]:
        self.state = AgentState.COMPLETED
        return {"action": "complete"}

    async def _is_task_complete(self) -> bool:
        # La logique du Founder reste la même : il est complet quand tous ses enfants le sont.
        if self.config.parent_id is None: 
            if not self.plan_created or not self.plan: return False
            all_steps_delegated = len(self.subagents) == len(self.plan)
            if not all_steps_delegated: return False
            return all(
                sid in self.orchestrator.agents and self.orchestrator.agents.get(sid).state != AgentState.ACTIVE
                for sid in self.subagents
            )
        
        # Logique pour les agents ouvriers/workers
        criteria = self.config.completion_criteria
        if not criteria:
            # Fallback si aucun critère n'est défini (comportement ancien, plus sûr de le garder)
            return len([r for r in self.results if "error" not in r]) >= 2

        # Vérification dynamique des critères
        # Nous allons vérifier si une des actions passées correspond parfaitement au critère.
        # Pour une robustesse accrue, on pourrait faire une comparaison de sous-dictionnaire.
        for result in reversed(self.results): # On part de la fin, c'est plus probable
            if "error" in result:
                continue

            action_taken = {
                "action": result.get("action"),
                "tool": result.get("tool"),
                "parameters": result.get("parameters", {})
            }

            # Comparaison simple pour l'instant
            if (action_taken["action"] == criteria.get("action") and
                action_taken["tool"] == criteria.get("tool") and
                action_taken["parameters"] == criteria.get("parameters")):
                self.logger.info(f"Completion criteria met: {criteria}")
                return True
        
        return False
    
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