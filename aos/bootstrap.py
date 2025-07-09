import asyncio
import logging
from typing import Dict, Any, Optional
from .config import SystemConfig  # Import from config module
from .orchestrator import Orchestrator
from .ledger import Ledger
from .toolbox import Toolbox
from .utils.logger import setup_logger

class Bootstrap:
    """The BIOS of the Agentic Operating System"""
    
    def __init__(self, config: SystemConfig):
        self.config = config
        self.logger = setup_logger("AOS-BIOS", config.log_level)
        self.ledger: Optional[Ledger] = None
        self.toolbox: Optional[Toolbox] = None
        self.orchestrator: Optional[Orchestrator] = None
        
    async def initialize(self) -> None:
        """Initialize all system components"""
        self.logger.info("Initializing AOS-v0...")
        
        # Initialize the Ledger (Central Bank)
        self.ledger = Ledger()
        await self.ledger.initialize()
        
        # Initialize the Toolbox (Shared Library)
        self.toolbox = Toolbox()
        await self.toolbox.initialize()
        
        # Initialize the Orchestrator (OS Kernel)
        self.orchestrator = Orchestrator(
            ledger=self.ledger,
            toolbox=self.toolbox,
            config=self.config
        )
        await self.orchestrator.initialize()
        
        self.logger.info("AOS-v0 initialization complete")
        
    async def boot(self) -> Dict[str, Any]:
        """Boot the system and start the founder agent"""
        await self.initialize()
        
        # Create founder agent with initial budget
        founder_id = await self.orchestrator.spawn_founder_agent(
            objective=self.config.objective,
            budget=self.config.initial_budget
        )
        
        self.logger.info(f"System booted. Founder agent {founder_id} created.")
        
        # Start the orchestrator event loop
        results = await self.orchestrator.run()
        
        return {
            "founder_id": founder_id,
            "final_state": results,
            "total_cost": await self.ledger.get_total_expenditure()
        }
        
    async def shutdown(self) -> None:
        """Gracefully shutdown the system"""
        if self.orchestrator:
            await self.orchestrator.shutdown()
        self.logger.info("AOS-v0 shutdown complete")

async def main(config: SystemConfig) -> Dict[str, Any]:
    """Main entry point for AOS"""
    bios = Bootstrap(config)
    try:
        results = await bios.boot()
        return results
    finally:
        await bios.shutdown()

if __name__ == "__main__":
    config = SystemConfig()
    results = asyncio.run(main(config))
    print(f"System completed. Total cost: ${results['total_cost']:.2f}")