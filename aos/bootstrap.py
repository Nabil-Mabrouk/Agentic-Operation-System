import asyncio
import logging
from typing import Dict, Any, Optional
from .config import SystemConfig
from .orchestrator import Orchestrator
from .ledger import Ledger
from .toolbox import Toolbox
from .utils.logger import setup_logging
from .llm_clients import get_llm_client # <--- NOUVEL IMPORT

class Bootstrap:
    """The BIOS of the Agentic Operating System"""
    
    def __init__(self, config: SystemConfig):
        self.config = config
        # This call sets up the logging for the entire application.
        setup_logging(config.log_level)
        # This gets a specific logger for this component.
        self.logger = logging.getLogger("AOS-BIOS")
        self.ledger: Optional[Ledger] = None
        self.toolbox: Optional[Toolbox] = None
        self.orchestrator: Optional[Orchestrator] = None
        self.llm_client = None # <--- NOUVEL ATTRIBUT
        
    async def initialize(self) -> None:
        """Initialize all system components"""
        self.logger.info("Initializing AOS-v0...")
        
        try:
            self.logger.debug("Initializing Ledger...")
            self.ledger = Ledger()
            await self.ledger.initialize()
            
            # --- MODIFICATION DE L'ORDRE ---

            # 1. Initialiser le client LLM
            self.logger.debug(f"Initializing LLM client for provider: {self.config.llm.provider}")
            self.llm_client = get_llm_client(self.config.llm.provider)
            
            # 2. Initialiser l'Orchestrateur D'ABORD
            self.logger.debug("Initializing Orchestrator...")
            self.orchestrator = Orchestrator(
                ledger=self.ledger,
                config=self.config,
                llm_client=self.llm_client
            )
            await self.orchestrator.initialize()

            # 3. Initialiser le Toolbox ENSUITE, en lui passant l'orchestrateur
            self.logger.debug("Initializing Bootstrap's root Toolbox...")
            self.toolbox = Toolbox(
                workspace_dir=self.config.workspace_path,
                delivery_folder=self.config.delivery_path,
                orchestrator=self.orchestrator # <--- PASSER LA RÉFÉRENCE
            )
            await self.toolbox.initialize()
            
            self.logger.info("AOS-v0 initialization complete")
        except Exception as e:
            self.logger.error(f"Initialization failed: {e}", exc_info=True) # Ajout de exc_info
            await self.shutdown()
            raise
        
    async def boot(self) -> Dict[str, Any]:
        """Boot the system and start the founder agent"""
        await self.initialize()
        
        founder_id = await self.orchestrator.spawn_founder_agent(
            objective=self.config.objective,
            budget=self.config.initial_budget
        )
        
        self.logger.info(f"System booted. Founder agent {founder_id} created.")
        
        results = await self.orchestrator.run()
        
        self.logger.info("Simulation finished. Collecting final results.")
        return {
            "founder_id": founder_id,
            "final_state": results,
        }
        
    async def shutdown(self) -> None:
        """Gracefully shutdown the system"""
        if self.orchestrator:
            await self.orchestrator.shutdown()
        self.logger.info("AOS-v0 shutdown complete")