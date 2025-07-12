import asyncio
import sys
import os
import shutil

# Add the aos package to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aos.bootstrap import Bootstrap, SystemConfig

async def main():
    """
    Run a simulation to create and execute a Python script.
    """
    objective = (
        "Write a Python script named `add.py` that defines a function to add two numbers and then calls the function with the numbers 5 and 7, printing the result. "
        "The script must be saved to the final delivery folder. "
        "After creating the script, it must be executed to verify the output is '12'."
    )

    config = SystemConfig(
        initial_budget=100.0,
        objective=objective,
        max_agents=10,
        log_level="INFO",
        price_per_1m_input_tokens=5.0,
        price_per_1m_output_tokens=15.0,
        spawn_cost=0.01,
        tool_use_cost=0.005,
        delivery_folder="./delivery_python_script"
    )
    
    print("🚀 Starting AOS-v0 Simulation (Python Scripting Objective)")
    print(f"Objective: {config.objective}")
    print("-" * 50)
    
    # Setup directories
    workspace_dir = "./workspace"
    delivery_dir = config.delivery_folder
    for d in [workspace_dir, delivery_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)
    print(f"Workspace and Delivery folders cleaned and recreated.")
    
    bios = Bootstrap(config)
    try:
        results = await bios.boot()
        
        print("\n" + "="*25 + " SIMULATION COMPLETE " + "="*25)
        print("\n📊 Final Results:")
        print(f"Total Agents Created: {results['final_state']['total_agents']}")
        print(f"Total System Cost: ${results['final_state']['total_cost']:.6f}")
        
        print(f"\n📦 Delivery Folder ({delivery_dir}):")
        delivery_files = os.listdir(delivery_dir)
        if not delivery_files:
            print("  Delivery folder is empty.")
        else:
            for f in sorted(delivery_files):
                print(f"  - {f}")

        # Verification
        script_created = "add.py" in delivery_files

        if script_created:
            # Try to run the created script and check its output
            try:
                import subprocess
                script_path = os.path.join(delivery_dir, "add.py")
                process = subprocess.run(
                    [sys.executable, script_path], 
                    capture_output=True, text=True, check=True, timeout=5
                )
                output = process.stdout.strip()
                if output == "12":
                    print(f"\n✅ Primary Objective Met: `add.py` was created and executed successfully with the correct output ('{output}').")
                else:
                    print(f"\n⚠️  Partial Success: Script created, but output was '{output}', not '12'.")
            except Exception as e:
                print(f"\n❌ Primary Objective FAILED: Script was created but failed to execute. Error: {e}")
        else:
            print("\n❌ Primary Objective FAILED: The `add.py` script was not created.")

    finally:
        await bios.shutdown()

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("🔴 OPENAI_API_KEY environment variable not found.")
    else:
        asyncio.run(main())