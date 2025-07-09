import asyncio
import sys
import os

# Add the aos package to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aos.config import SystemConfig  # Import from config module
from aos.bootstrap import Bootstrap, SystemConfig

async def main():
    """Run a startup simulation"""
    config = SystemConfig(
        initial_budget=1000.0,
        objective="Build a simple web application with user authentication",
        max_agents=20,  # Increase from 10 to 20
        api_cost_per_call=0.01,
        spawn_cost=10.0,
        log_level="INFO"
    )
    
    print("🚀 Starting AOS-v0 Startup Simulation")
    print(f"Objective: {config.objective}")
    print(f"Initial Budget: ${config.initial_budget:.2f}")
    print("-" * 50)
    
    # Run the simulation
    bios = Bootstrap(config)
    try:
        results = await bios.boot()
        
        print("\n📊 Simulation Results:")
        print(f"Total Agents Created: {results['final_state']['total_agents']}")
        print(f"Total System Cost: ${results['final_state']['total_cost']:.2f}")
        print(f"Founder Agent ID: {results['founder_id']}")
        
        print("\n👥 Agent Hierarchy:")
        for parent, children in results['final_state']['hierarchy'].items():
            print(f"  {parent} -> {', '.join(children)}")
            
        print("\n💰 Final Agent States:")
        for agent_id, state in results['final_state']['agent_states'].items():
            print(f"  {agent_id} ({state['role']}): {state['state']} - ${state['final_balance']:.2f}")
            
    finally:
        await bios.shutdown()

if __name__ == "__main__":
    asyncio.run(main())