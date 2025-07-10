import asyncio
import sys
import os
import shutil

# Add the aos package to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aos.bootstrap import Bootstrap, SystemConfig

async def main():
    """
    Run a simulation with a more complex, multi-file objective.
    """
    # ### CHANGE: The objective now requires both HTML and CSS ###
    objective = (
        "Create a professional, single-page portfolio website for 'Alex Doe'. "
        "The website must be styled with a separate CSS file. "
        "The final output must be an `index.html` file and a `style.css` file in the `./workspace` directory. "
        "The HTML file must correctly link to the CSS file. "
        "The portfolio should feature a clean, modern design and list 'Python', 'Machine Learning', and 'Agentic Systems' as skills."
    )

    config = SystemConfig(
        initial_budget=100.0,
        objective=objective,
        max_agents=10,
        log_level="DEBUG",
        price_per_1m_input_tokens=5.0,
        price_per_1m_output_tokens=15.0,
        spawn_cost=0.01,
        tool_use_cost=0.005,
        delivery_folder="./delivery"  # Add delivery folder
    )
    
    print("🚀 Starting AOS-v0 Simulation (Styled Website Objective)")
    print(f"Objective: {config.objective}")
    print("-" * 50)
    
    workspace_dir = "./workspace"
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    os.makedirs(workspace_dir)
    print(f"Workspace cleaned and recreated at '{workspace_dir}'")
    
    bios = Bootstrap(config)
    try:
        results = await bios.boot()
        
        print("\n" + "="*25 + " SIMULATION COMPLETE " + "="*25)
        print("\n📊 Final Results:")
        print(f"Total Agents Created: {results['final_state']['total_agents']}")
        print(f"Total System Cost: ${results['final_state']['total_cost']:.6f}")
        
        # Update the verification section:
        print(f"\n📂 Final Workspace State:")
        agent_dirs = [d for d in os.listdir(workspace_dir) if os.path.isdir(os.path.join(workspace_dir, d))]
        for agent_dir in sorted(agent_dirs):
            print(f"  - {agent_dir}/")
            agent_workspace = os.path.join(workspace_dir, agent_dir)
            files = os.listdir(agent_workspace)
            for f in sorted(files):
                print(f"    - {f}")

        # Check delivery folder
        delivery_files = []
        if os.path.exists(config.delivery_folder):
            delivery_files = os.listdir(config.delivery_folder)
            print(f"\n📦 Delivery Folder ({config.delivery_folder}):")
            for f in sorted(delivery_files):
                print(f"  - {f}")

        # Check for files in delivery folder
        html_created = "index.html" in delivery_files
        css_created = "style.css" in delivery_files

        if html_created and css_created:
            # Check if the HTML file links to the CSS file
            html_path = os.path.join(config.delivery_folder, "index.html")
            with open(html_path, 'r') as f:
                html_content = f.read()
            if '<link rel="stylesheet" href="style.css">' in html_content or "<link rel='stylesheet' href='style.css'>" in html_content:
                print("\n✅ Primary Objective Met: index.html and style.css were created in delivery folder and correctly linked.")
            else:
                print("\n⚠️  Partial Success: Files were created in delivery folder, but index.html does not link to style.css.")
        elif html_created:
            print("\n❌ Primary Objective FAILED: index.html was created in delivery folder, but style.css is missing.")
        elif css_created:
            print("\n❌ Primary Objective FAILED: style.css was created in delivery folder, but index.html is missing.")
        else:
            print("\n❌ Primary Objective FAILED: Neither index.html nor style.css were created in delivery folder.")
    finally:
        await bios.shutdown()

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("🔴 OPENAI_API_KEY environment variable not found. Please create a .env file.")
    else:
        asyncio.run(main())