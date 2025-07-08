# components.py
import os
import re
import uuid
from openai import OpenAI
from dotenv import load_dotenv

import tools # Notre fichier d'outils

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class Ledger:
    def __init__(self):
        self.balances = {}
        self.transactions = []

    def get_balance(self, agent_id):
        return self.balances.get(agent_id, 0.0)

    def record_transaction(self, agent_id, amount, description):
        if agent_id not in self.balances:
            self.balances[agent_id] = 0.0
        self.balances[agent_id] += amount
        self.transactions.append({"agent_id": agent_id, "amount": amount, "description": description})
        print(f"💰 Ledger: {agent_id} | Amount: {amount:.4f} | New Balance: {self.balances[agent_id]:.4f} | Desc: {description}")

    def transfer_funds(self, from_agent_id, to_agent_id, amount):
        if self.get_balance(from_agent_id) >= amount:
            self.record_transaction(from_agent_id, -amount, f"Transfer to {to_agent_id}")
            self.record_transaction(to_agent_id, amount, f"Transfer from {from_agent_id}")
            return True
        return False

class Toolbox:
    def __init__(self):
        self.tools = {
            "delegate_task": tools.delegate_task,
            "execute_shell": tools.execute_shell,
            "task_complete": tools.task_complete,
        }

    def get_tools_prompt(self):
        prompt = "Tu as accès aux outils suivants. Utilise-les au format <tool_call name='nom_outil' params={{'arg1': 'val1', 'arg2': 'val2'}}/>:\n"
        for name, func in self.tools.items():
            prompt += f"- {name}: {func.__doc__}\n"
        return prompt

    def use_tool(self, tool_name, params, agent):
        if tool_name in self.tools:
            try:
                # Hack: on passe la référence de l'orchestrateur aux outils
                tools.ORCHESTRATOR = agent.orchestrator
                tools.ORCHESTRATOR.current_agent_executing = agent
                
                result = self.tools[tool_name](**params)
                
                tools.ORCHESTRATOR.current_agent_executing = None
                return result
            except Exception as e:
                return f"Erreur lors de l'appel de l'outil '{tool_name}': {e}"
        return f"Erreur: Outil '{tool_name}' non trouvé."

class Agent:
    def __init__(self, agent_id, parent_id, task, role, orchestrator, budget=0.0):
        self.id = agent_id
        self.parent_id = parent_id
        self.task = task
        self.role = role
        self.orchestrator = orchestrator
        self.history = []
        self.is_done = False
        
        system_prompt = f"""
        Tu es un agent IA avec le rôle '{self.role}'. Ton ID est '{self.id}'.
        Ta mission actuelle est: "{self.task}".
        Ton budget est géré par l'Orchestrateur. Chaque action que tu prends a un coût. Sois efficace.
        Tu dois décomposer les problèmes complexes en sous-tâches simples et les déléguer si nécessaire.
        Ne fais qu'une seule chose à la fois. Si une tâche est trop complexe, délègue-la.
        Réponds uniquement en appelant un outil. N'ajoute aucun autre texte.
        {self.orchestrator.toolbox.get_tools_prompt()}
        """
        self.history.append({"role": "system", "content": system_prompt})

    def run(self):
        print(f"\n▶️  Agent {self.id} ({self.role}) démarre. Tâche: {self.task}")
        
        # Le premier message de l'utilisateur est la tâche
        self.history.append({"role": "user", "content": f"Voici ta mission : {self.task}"})
        
        while not self.is_done:
            balance = self.orchestrator.ledger.get_balance(self.id)
            if balance <= 0:
                print(f"Agent {self.id} est en faillite. Tâche échouée.")
                self.report_to_parent("FAILURE: Budget exhausted.")
                break

            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini", #ou gpt-3.5-turbo
                    messages=self.history,
                    temperature=0.4,
                )
                
                # Coût de l'appel
                cost = 0.00000005 * response.usage.prompt_tokens + 0.00000015 * response.usage.completion_tokens # Prix de gpt-4o-mini
                self.orchestrator.ledger.record_transaction(self.id, -cost, "LLM API Call")

                # Parser et exécuter l'outil
                assistant_message = response.choices[0].message.content
                self.history.append({"role": "assistant", "content": assistant_message})
                
                tool_call_match = re.search(r"<tool_call name='([^']*)' params=\{(.*)\}/>", assistant_message, re.DOTALL)
                
                if tool_call_match:
                    tool_name = tool_call_match.group(1)
                    params_str = tool_call_match.group(2)
                    
                    try:
                        # Convertir la chaîne de paramètres en dictionnaire
                        params = eval(f"dict({params_str})")
                    except Exception as e:
                        tool_result = f"Erreur de parsing des paramètres: {e}"
                        params = {}
                    else:
                        print(f"  ↪️ Agent {self.id} appelle l'outil: {tool_name} avec params: {params}")
                        tool_result = self.orchestrator.toolbox.use_tool(tool_name, params, self)
                    
                    if isinstance(tool_result, str) and tool_result.startswith("TASK_COMPLETE:"):
                        self.is_done = True
                        report = tool_result.replace("TASK_COMPLETE: ", "")
                        self.report_to_parent(report)
                        print(f"✅ Agent {self.id} a terminé sa tâche.")
                    else:
                        self.history.append({"role": "user", "content": f"Résultat de l'outil:\n{tool_result}"})

                else:
                    self.history.append({"role": "user", "content": "Erreur: Tu n'as pas appelé un outil correctement. Réessaye."})

            except Exception as e:
                print(f"Erreur dans la boucle de l'agent {self.id}: {e}")
                self.history.append({"role": "user", "content": f"Une erreur système s'est produite: {e}. Réfléchis et continue."})

    def report_to_parent(self, report):
        if self.parent_id in self.orchestrator.agents:
            parent_agent = self.orchestrator.agents[self.parent_id]
            # Ajouter le rapport à l'historique du parent pour qu'il puisse réagir
            parent_agent.history.append({
                "role": "user", 
                "content": f"Rapport du sous-agent {self.id}: {report}"
            })

class Orchestrator:
    def __init__(self):
        self.agents = {}
        self.ledger = Ledger()
        self.toolbox = Toolbox()
        self.current_agent_executing = None # Pour le hack des outils

    def run_objective(self, objective, budget):
        print(f"🚀 AOS V0 Démarrage. Objectif: '{objective}', Budget Global: {budget}")
        
        # Créer l'agent "Fondateur"
        founder_id = f"agent_{uuid.uuid4().hex[:6]}"
        founder = Agent(founder_id, parent_id=None, task=objective, role="founder", orchestrator=self)
        self.agents[founder_id] = founder
        
        # Allouer le budget initial
        self.ledger.record_transaction(founder_id, budget, "Initial budget allocation")
        
        # Lancer le système
        founder.run()
        print("🏁 AOS V0 a terminé son exécution.")

    def spawn_agent(self, parent_agent, role, task, budget):
        if not self.ledger.transfer_funds(parent_agent.id, f"pending_{role}", budget):
            return f"Echec de la délégation: budget insuffisant sur l'agent {parent_agent.id}."
        
        new_agent_id = f"agent_{uuid.uuid4().hex[:6]}"
        new_agent = Agent(new_agent_id, parent_id=parent_agent.id, task=task, role=role, orchestrator=self)
        self.agents[new_agent_id] = new_agent
        
        # Finaliser le transfert de fonds
        self.ledger.transfer_funds(f"pending_{role}", new_agent_id, budget)

        # Lancer le nouvel agent dans un thread serait mieux, mais pour la V0 on fait en séquentiel
        new_agent.run()
        
        return f"Délégation réussie. Le nouvel agent {new_agent_id} a été créé et a exécuté sa tâche."