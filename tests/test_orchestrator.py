# tests/test_orchestrator.py
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from aos.orchestrator import Orchestrator
from aos.config import SystemConfig
from aos.agent import Agent, AgentConfig, AgentState
from aos.ledger import Ledger
from aos.exceptions import MaxAgentsReachedError
from aos.llm_clients.base import BaseLLMClient # Ajouter l'import
# --- Fixtures et Mocks ---

@pytest.fixture
def mock_ledger():
    """Crée un mock du Ledger pour les tests."""
    ledger = AsyncMock(spec=Ledger)
    ledger.get_total_expenditure.return_value = 0.0
    return ledger

@pytest.fixture
def base_config():
    """Crée une configuration de base pour les tests."""
    return SystemConfig(log_level="DEBUG")

class StubAgent(Agent):
    """Un Agent "bouchon" pour les tests, qui ne fait rien d'intelligent."""
    def __init__(self, agent_id="stub_id", config=None, **kwargs):
        # On utilise des mocks pour les dépendances non nécessaires au test
        self.id = agent_id
        
        # --- MODIFICATION ICI ---
        # Si aucune config n'est passée, on en crée une basique.
        if config is None:
            self.config = AgentConfig(role="stub", task="stub_task", budget=10)
        else:
            self.config = config
        
        self.state = AgentState.ACTIVE
        self.subagents = [] # Important pour _collect_results
        self.ledger = AsyncMock(spec=Ledger) # Donnons-lui un mock de ledger
        # Pas d'appel à super().__init__ pour éviter les initialisations complexes

    async def initialize(self):
        pass

    async def run(self):
        # Par défaut, un agent de test ne fait rien et se termine.
        self.state = AgentState.COMPLETED
        await asyncio.sleep(0)

class NeverEndingAgent(StubAgent):
    """Un agent conçu pour ne jamais se terminer, afin de tester le timeout."""
    async def run(self):
        self.state = AgentState.ACTIVE
        while True:
            await asyncio.sleep(0.1)

# --- Tests ---
# Nouvelle fixture pour le mock du client LLM
@pytest.fixture
def mock_llm_client():
    return AsyncMock(spec=BaseLLMClient)

@pytest.mark.asyncio
async def test_spawn_agent_respects_max_limit(mock_ledger,  mock_llm_client):
    """
    Vérifie que l'Orchestrateur lève bien MaxAgentsReachedError
    lorsque la limite d'agents est atteinte.
    """
    # 1. Configuration
    config = SystemConfig(max_agents=1, log_level="DEBUG")
    orchestrator = Orchestrator(ledger=mock_ledger, config=config, llm_client=mock_llm_client)
    
    # Mock de la dépendance Agent pour contrôler sa création
    # Note: On doit patcher le chemin où 'Agent' est importé DANS orchestrator.py
    orchestrator.AgentClass = StubAgent 

    # 2. Action
    # Spawner le premier agent (devrait réussir)
    founder_config = AgentConfig(role="Founder", task="test", budget=10.0)
    agent_id_1 = await orchestrator._create_agent(founder_config)
    assert agent_id_1 is not None
    assert len(orchestrator.agents) == 1

    # Tenter de spawner un deuxième agent (devrait échouer)
    worker_config = AgentConfig(role="Worker", task="subtest", budget=5.0)
    
    # 3. Assertion
    with pytest.raises(MaxAgentsReachedError):
        await orchestrator._create_agent(worker_config)
    
    # Vérifier que le nombre d'agents n'a pas augmenté
    assert len(orchestrator.agents) == 1

# tests/test_orchestrator.py

@pytest.mark.asyncio
async def test_simulation_stops_on_timeout(mock_ledger, mock_llm_client):
    """
    Vérifie que la boucle run() de l'Orchestrateur se termine
    lorsque le timeout de la simulation est atteint.
    """
    # 1. Configuration
    TIMEOUT_TEST_VALUE = 0.5 
    SHUTDOWN_TIMEOUT_TEST = 1.0 # On utilise un timeout court pour le test
    
    # --- MODIFICATION ICI ---
    # On passe le timeout via le SystemConfig, la méthode propre.

    
    config = SystemConfig(
        log_level="DEBUG",
        simulation_timeout=TIMEOUT_TEST_VALUE,
        shutdown_timeout=SHUTDOWN_TIMEOUT_TEST # On configure le timeout d'arrêt
    )
    
    orchestrator = Orchestrator(ledger=mock_ledger, config=config, llm_client=mock_llm_client)
    # La ligne 'orchestrator.SIMULATION_TIMEOUT = ...' est supprimée car incorrecte.

    orchestrator.AgentClass = NeverEndingAgent
    await orchestrator.initialize()

    agent_config = AgentConfig(role="Looper", task="loop forever", budget=10)
    agent_id = await orchestrator._create_agent(agent_config)

    orchestrator.agents[agent_id].ledger = mock_ledger
    mock_ledger.get_balance.return_value = 5.0 

    # 2. Action
    start_time = asyncio.get_event_loop().time()
    results = await orchestrator.run()
    end_time = asyncio.get_event_loop().time()

    # 3. Assertion
    duration = end_time - start_time
    
    # --- MODIFICATION DE L'ASSERTION ---
    # La durée attendue est maintenant le timeout de la simulation PLUS le timeout d'arrêt.
    duration = end_time - start_time
    
    expected_min_duration = TIMEOUT_TEST_VALUE + SHUTDOWN_TIMEOUT_TEST
    expected_max_duration = expected_min_duration + 1.0

    print(f"Test duration: {duration}, Expected range: [{expected_min_duration}, {expected_max_duration}]")

    assert expected_min_duration <= duration < expected_max_duration
  

    final_agent_state = results['agent_states'][agent_id]['state']
    assert final_agent_state == AgentState.FAILED.value