# bootstrap.py
from components import Orchestrator

if __name__ == "__main__":
    # Objectif de test qui force la délégation
    initial_objective = (
        "Crée un dossier 'project_v0', puis délègue la tâche de créer un fichier 'hello.txt' "
        "à l'intérieur de ce dossier avec le contenu 'Hello from a delegated agent!'."
    )
    
    initial_budget = 0.10 # 10 cents

    # Créer et lancer l'Orchestrateur
    orchestrator = Orchestrator()
    orchestrator.run_objective(initial_objective, initial_budget)