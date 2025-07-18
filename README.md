# AOS: Agentic Operation System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
![Status](https://img.shields.io/badge/status-active_development-green)

**AOS is a sophisticated framework for building, running, and observing complex, collaborative multi-agent systems. It moves beyond simple ReAct loops to enable robust, hierarchical agent teams that can plan, delegate, communicate, and even create their own tools to solve complex problems.**

This project is not just a codebase; it's an exploration into the future of autonomous systems, built on principles of modularity, observability, and strategic thinking.

![Visualizer Screenshot](https://via.placeholder.com/800x400.png?text=AOS+Live+Visualizer+Screenshot+Here)
*(A screenshot of the live visualizer in action would be powerful here)*

---

## 🌟 Core Philosophy & Features

AOS is designed from the ground up to address the fundamental challenges of creating reliable and scalable agentic workflows.

*   **Hierarchical Task Decomposition:** Instead of a single "God-mode" agent, AOS uses a "Founder" agent that plans, validates its strategy, and delegates sub-tasks to a team of specialized agents.
*   **Dynamic Tool Creation (Tool Forging):** The system is self-improving. When an agent lacks a necessary tool, it can request one. A specialized "Tool Forging Agent" is then spawned to write, test, and dynamically deploy the new tool during the same simulation.
*   **Rich Inter-Agent Communication:** Agents collaborate through a built-in messaging system, allowing them to report status, ask for clarification, and pass artifacts to the next agent in a pipeline.
*   **Robust & Resilient by Design:**
    *   **Sandboxed Workspaces:** Every agent operates in its own isolated file system directory.
    *   **Resource Management:** A built-in `Ledger` tracks costs (token usage, tool calls), preventing budget overruns.
    *   **Fault Tolerance:** The Orchestrator ensures that the failure of a single agent does not crash the entire system.
*   **Advanced Observability:**
    *   **Live Visualizer:** A web-based UI shows the agent hierarchy, communication, and status changes in real-time.
    *   **Structured Logging:** Detailed, machine-readable logs for in-depth post-mortem analysis.
*   **Configurable & Extensible:**
    *   **CLI Control:** A powerful command-line interface to run simulations with fine-grained control over models, budgets, and advanced capabilities.
    *   **Plugin-Based Tool System:** Adding new tools is as simple as dropping a Python file into a directory.
    *   **Multi-Provider LLM Support:** Easily switch between LLM providers (OpenAI, Groq, Deepseek, etc.) via a single command-line option.

---

## 🚀 Getting Started

### Prerequisites

*   Python 3.12+
*   An OpenAI API key (or keys for other supported providers like Groq, Deepseek).

### 1. Clone the Repository

```bash
git clone https://github.com/Nabil-Mabrouk/Agentic-Operation-System.git
cd Agentic-Operation-System
```

### 2. Set Up the Environment

It is highly recommended to use a virtual environment.

```bash
# Create and activate the virtual environment
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure API Keys

Create a `.env` file in the root of the project by copying the example file:

```bash
cp .env.example .env
```

Now, edit the `.env` file and add your API keys:

```dotenv
OPENAI_API_KEY="sk-..."
GROQ_API_KEY="gsk_..."
# Add other keys as needed
```

### 4. Run Your First Simulation

Use the powerful CLI to launch a simulation. The system will create an `output/` directory for all generated files.

**Basic Example (Web Development):**
```bash
python -m aos run "Create a professional, single-page portfolio website for 'Alex Doe' with a separate CSS file." --visualize
```
*   `--visualize` (or `-v`) will automatically open the live visualizer in your browser.

**Advanced Example (Tool Forging):**
This command disables the `code_executor` tool, forcing the agents to request and build a new tool to solve the problem.
```bash
python -m aos run "Take the text 'HELLO AOS' and save its SHA256 hash into a file named 'hash.txt'." --tool-creation --disable-tool code_executor -v
```

**Using a Different LLM Provider (e.g., Groq):**
```bash
python -m aos run "Write a short poem about the future of AI." --provider groq --model llama3-8b-8192
```

To see all available commands and options:
```bash
python -m aos --help
```

---

## 🏛️ Project Architecture

AOS is built on a modular, operating system-inspired architecture:

*   **`aos/`:** The core source code.
    *   **`orchestrator.py` (The Kernel):** Manages the entire agent lifecycle, tasks, and system-level events like communication and tool deployment.
    *   **`agent.py` (The Process):** The core logic of an agent, including its state machine and decision-making loop. *(Future work: This will be refactored into specialized agent classes like `ManagerAgent` and `WorkerAgent`).*
    *   **`bootstrap.py` (The BIOS):** Initializes all system components in the correct order.
    *   **`tools/` (The Drivers):**
        *   `base_tool.py`: The abstract base class for all tools.
        *   `plugins/`: A directory where new tools are dynamically loaded from.
    *   **`llm_clients/` (The Communication Layer):** Abstracted clients for different LLM APIs (OpenAI, Groq, etc.).
    *   **`ledger.py` (The Resource Manager):** Tracks costs and budgets.
    *   **`config.py` (The Registry):** Centralized dataclasses for all system configurations.
    *   **`cli.py` (The Shell):** The user-facing command-line interface.
*   **`visualizer/`:** The simple HTML/JS frontend for the real-time graph visualization.
*   **`tests/`:** The `pytest` suite for ensuring code quality and preventing regressions.
*   **`output/`:** The default directory for all generated `workspaces` and final `delivery` files (ignored by git).

---

## 🛣️ Roadmap & Future Vision

This project is an active exploration. The goal is to build a platform capable of handling truly complex, real-world tasks. Key areas for future development include:

-   [ ] **Architectural Consolidation:**
    -   [ ] Refactor the `Agent` class into a specialized hierarchy (`BaseAgent`, `ManagerAgent`, `WorkerAgent`).
    -   [ ] Extract core logic from the `Orchestrator` into dedicated services (`MessagingService`, `DeploymentService`).
-   [ ] **Enhanced Intelligence & Collaboration:**
    -   [ ] Implement a "Board of Directors" model for plan validation, where multiple specialized agents critique a plan before execution.
    -   [ ] Improve agent memory and context management.
    -   [ ] Enable more complex, graph-based communication topologies.
-   [ ] **Industrialization & Production-Readiness:**
    -   [ ] **Serialization:** Implement the ability to save a successful agent team architecture (`--save-arch`) and reload it.
    -   [ ] **Microservice Deployment:** Create a `aos serve` command to expose a saved agent team as a `FastAPI` endpoint.
    -   [ ] **Knowledge Base:** Vectorize successful simulation logs to create a knowledge base that future agents can query to solve similar problems more efficiently.

---

## 👨‍💻 Who I Am

My name is Nabil Mabrouk. This project is the confluence of a lifelong passion for technology and a new, determined focus on the world of Artificial Intelligence.

With a **PhD in Computer Science** and as an expert in **complex system theory**, I've always been fascinated by how intricate, interacting parts create emergent, intelligent behavior. For years, I've applied this thinking as a **Sales Manager in an engineering company**, solving complex problems for clients.

Now, at 50, I am embarking on a deliberate and exciting pivot into AI. AOS is more than a project for me; it is my sandbox, my research lab, and my bridge into this new frontier. It's an attempt to apply the principles of robust, complex systems to the chaotic and powerful world of autonomous agents. I believe the future lies not in single, monolithic AIs, but in well-orchestrated teams of specialized agents, and this project is my hands-on exploration of that future.

You can connect with me on [LinkedIn](https://www.linkedin.com/in/nabil-mabrouk-19477a23/) or follow my journey on [GitHub](https://github.com/Nabil-Mabrouk).

---

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
```