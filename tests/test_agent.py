# tests/test_agent.py
import pytest
from unittest.mock import MagicMock, AsyncMock

from aos.agent import Agent, AgentConfig, AgentState
from aos.ledger import Ledger
from aos.llm_clients.base import BaseLLMClient # Ajouter l'import
# --- Fixtures ---

# Mettre à jour la fixture pour inclure le mock du client LLM
@pytest.fixture
def mock_dependencies():
    """Crée un tuple de mocks pour les dépendances de l'Agent."""
    mock_ledger = AsyncMock(spec=Ledger)
    mock_toolbox = AsyncMock()
    mock_orchestrator = AsyncMock()
    mock_llm_client = AsyncMock(spec=BaseLLMClient) # Créer le mock
    # Retourner le mock
    return mock_ledger, mock_toolbox, mock_orchestrator, mock_llm_client

# --- Tests ---

@pytest.mark.asyncio
async def test_agent_initializes_and_creates_ledger_account(mock_dependencies):
    """Vérifie que l'agent appelle create_account lors de son initialisation."""
    mock_ledger, mock_toolbox, mock_orchestrator, mock_llm_client = mock_dependencies
    agent_id = "test-agent"
    config = AgentConfig(role="tester", task="testing", budget=100.0)

    agent = Agent(agent_id, config, mock_ledger, mock_toolbox, mock_orchestrator, mock_llm_client)
    await agent.initialize()
    
    # Vérifie que la méthode create_account a été appelée une fois avec les bons arguments
    mock_ledger.create_account.assert_called_once_with(agent_id, 100.0)

@pytest.mark.asyncio
async def test_agent_enters_dead_state_on_budget_exhaustion(mock_dependencies):
    """
    Vérifie que l'agent passe à l'état DEAD s'il n'a plus de budget
    avant même de penser.
    """
    mock_ledger, mock_toolbox, mock_orchestrator, mock_llm_client = mock_dependencies
    agent_id = "bankrupt-agent"
    config = AgentConfig(role="tester", task="testing", budget=0.0)
    
    # Simuler un solde à zéro
    mock_ledger.get_balance.return_value = 0.0

    agent = Agent(agent_id, config, mock_ledger, mock_toolbox, mock_orchestrator, mock_llm_client)
    await agent.initialize()
    
    # L'agent tente de penser, mais devrait immédiatement mourir
    thought = await agent.think()
    
    assert agent.state == AgentState.DEAD
    assert thought == "Out of funds"

@pytest.mark.asyncio
@pytest.mark.skip(reason="Le mocking de _call_llm est nécessaire, à faire plus tard")
async def test_agent_dies_after_costly_llm_call(mock_dependencies):
    """
    Vérifie que l'agent passe à l'état DEAD si le coût de l'appel LLM
    dépasse son solde.
    """
    # Ce test est plus complexe car il nécessite de mocker _call_llm
    # et la séquence d'appels à ledger. On le garde pour plus tard.
    pass