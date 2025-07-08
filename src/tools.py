# tools.py
import subprocess

# NOTE: Dans une vraie version, ces outils interagiraient avec l'Orchestrateur
# pour appeler ses méthodes. Pour la V0, on va utiliser un hack avec des variables globales
# pour que les outils aient accès à l'Orchestrateur.

# C'est une solution temporaire pour éviter la complexité des injections de dépendances.
ORCHESTRATOR = None

def delegate_task(task: str, budget: float, agent_role: str = "worker"):
    """
    Délègue une nouvelle tâche à un nouvel agent.
    :param task: La description de la tâche à accomplir.
    :param budget: Le budget alloué au nouvel agent pour cette tâche.
    :param agent_role: Le rôle du nouvel agent (ex: 'worker', 'manager').
    """
    if ORCHESTRATOR is None:
        return "Erreur: Orchestrateur non initialisé."
    
    # L'agent appelant est stocké dans l'orchestrateur pendant l'exécution de l'outil
    parent_agent = ORCHESTRATOR.current_agent_executing
    return ORCHESTRATOR.spawn_agent(parent_agent, agent_role, task, budget)

def execute_shell(command: str):
    """Exécute une commande shell et retourne le résultat."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=30
        )
        output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        return output
    except Exception as e:
        return f"Erreur lors de l'exécution de la commande: {e}"

def task_complete(report: str):
    """
    Signale que la tâche de l'agent est terminée.
    :param report: Un rapport final sur le résultat de la tâche.
    """
    # Ce mot-clé spécial sera intercepté par la boucle de l'agent
    return f"TASK_COMPLETE: {report}"