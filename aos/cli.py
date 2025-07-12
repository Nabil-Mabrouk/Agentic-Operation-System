# aos/cli.py
import typer
import asyncio
import os
import shutil
import webbrowser
import traceback

from .bootstrap import Bootstrap, SystemConfig
from .config import LLMConfig, AgentCapabilities

# Crée une application Typer
app = typer.Typer(
    name="aos",
    help="🚀 Agentic Operating System - A framework for building and running autonomous agent systems."
)

# --- COROUTINE PRINCIPALE ---
# Contient TOUTE la logique de la simulation.
async def _run_simulation(config: SystemConfig, visualize: bool):
    """La coroutine principale qui gère le cycle de vie complet de la simulation."""
    
    # Étape 1: Affichage initial et nettoyage
    typer.secho("🚀 Starting AOS Simulation...", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"Objective: {config.objective}")
    typer.echo("-" * 50)

    workspace_dir = config.workspace_path
    delivery_dir = config.delivery_path # Récupérer le chemin de livraison
    
    # Nettoyer le workspace
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    os.makedirs(workspace_dir)
    typer.secho(f"Workspace cleaned and recreated at '{workspace_dir}'", fg=typer.colors.YELLOW)
    
    # Nettoyer le delivery
    if os.path.exists(delivery_dir):
        shutil.rmtree(delivery_dir)
    os.makedirs(delivery_dir)
    typer.secho(f"Delivery folder cleaned and recreated at '{delivery_dir}'", fg=typer.colors.YELLOW)
    
    if visualize:
        visualizer_path = os.path.abspath('visualizer/index.html')
        webbrowser.open_new_tab(f'file://{visualizer_path}')
        typer.echo("Visualizer opened in new tab. Waiting for simulation to start...")

    # Étape 2: Exécution et gestion du cycle de vie
    bios = Bootstrap(config)
    try:
        # Lancement de la simulation
        results = await bios.boot()
        
        # Affichage des résultats en cas de succès
        typer.secho("\n" + "="*25 + " SIMULATION COMPLETE " + "="*25, fg=typer.colors.GREEN, bold=True)
        typer.echo("\n📊 Final Results:")
        typer.secho(f"  Total Agents Created: {results['final_state']['total_agents']}", fg=typer.colors.BRIGHT_GREEN)
        typer.secho(f"  Total System Cost: ${results['final_state']['total_cost']:.6f}", fg=typer.colors.BRIGHT_GREEN)
        
    except Exception as e:
        typer.secho(f"\n💥 SIMULATION FAILED: {e}", fg=typer.colors.RED, bold=True)
        traceback.print_exc() # Affiche le traceback complet pour le débogage
    finally:
        # Étape 3: Arrêt propre, quoi qu'il arrive
        typer.echo("\nShutting down...")
        await bios.shutdown()
        typer.secho("Shutdown complete.", fg=typer.colors.GREEN)

# --- COMMANDE CLI ---
# Est TRÈS simple. Ne fait que préparer et lancer la coroutine.
@app.command()
def run(
    objective: str = typer.Argument(..., help="The main objective for the simulation."),
    budget: float = typer.Option(100.0, "--budget", "-b", help="Initial budget for the simulation."),
    max_agents: int = typer.Option(10, "--max-agents", "-a", help="Maximum number of concurrent agents."),
    log_level: str = typer.Option("INFO", "--log-level", "-l", help="Logging level (DEBUG, INFO, WARNING, ERROR)."),
    visualize: bool = typer.Option(False, "--visualize", "-v", help="Open the live visualizer in a browser."),
    provider: str = typer.Option("openai", "--provider", "-p", help="LLM provider to use (e.g., openai, deepseek, kimi, groq)."),
    model: str = typer.Option(None, "--model", "-m", help="Specify the OpenAI model to use (e.g., gpt-4o-mini, kimi-k2-0711-preview)."), # <--- NOUVELLE OPTION
    # --- NOUVELLES OPTIONS DE CAPACITÉS ---
    messaging: bool = typer.Option(True, "--messaging/--no-messaging", help="Enable/Disable inter-agent messaging."),
    advanced_planning: bool = typer.Option(True, "--adv-planning/--no-adv-planning", help="Enable/Disable the advanced planning validation loop."),
    tool_creation: bool = typer.Option(False, "--tool-creation/--no-tool-creation", help="Enable/Disable the agent's ability to create new tools.")
):
    """
    Run a new AOS simulation with a given objective.
    """
    # Créer la config LLM
    llm_config = LLMConfig(provider=provider)
    if model: # Si un modèle est spécifié via le CLI, il surcharge la valeur par défaut
        llm_config.model = model
    # Créer la config des capacités
    capabilities = AgentCapabilities(
        allow_messaging=messaging,
        allow_advanced_planning=advanced_planning,
        allow_tool_creation=tool_creation
    )
    # Créer la configuration système
    config = SystemConfig(
        initial_budget=budget,
        objective=objective,
        max_agents=max_agents,
        log_level=log_level.upper(),
        llm=llm_config,  # Passer la configuration LLM
        capabilities=capabilities  # Passer la configuration des capacités
    )

    # L'unique point d'entrée asyncio.
    asyncio.run(_run_simulation(config, visualize))

@app.command()
def check():
    """
    Check environment and configuration (e.g., API keys).
    """
    typer.echo("Checking environment...")
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        typer.secho("✅ OPENAI_API_KEY is set.", fg=typer.colors.GREEN)
    else:
        typer.secho("❌ OPENAI_API_KEY is not found.", fg=typer.colors.RED)
        typer.echo("Please create a .env file or set the environment variable.")

if __name__ == "__main__":
    app()