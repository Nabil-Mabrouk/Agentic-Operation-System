# AOS-v0: The Agentic Operating System

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## 🌟 Overview

AOS-v0 is the foundational implementation of the **Agentic Operating System**, a groundbreaking framework designed to run a society of autonomous AI agents. This project moves beyond single-agent scripts to a hierarchical, recursive, and resource-aware system where agents can collaborate, delegate tasks, and even spawn new agents to achieve complex objectives.

The core philosophy is inspired by organizational growth in startups: a system that starts with a single "founder" agent and can scale dynamically by creating specialized "employee" agents, all while operating under strict budgetary constraints.

### 🎯 Key Innovation: An Economy of Agents

Instead of a monolithic agent trying to solve a problem, AOS creates a **micro-economy** where every action has a cost and every task can be delegated as an "investment." This introduces a selective pressure that forces the system to be efficient, innovative, and strategic.

## 🏛️ Architecture

The AOS is built on four key, decoupled components that work in concert:

### 1. **Bootstrap** (The BIOS)
- **File**: `aos/bootstrap.py`
- **Purpose**: Single entry point that initializes the system
- **Key Features**:
  - Sets overall objective and budget
  - Initializes all system components
  - Creates the founder agent
  - Manages system lifecycle

### 2. **Orchestrator** (The OS Kernel)
- **File**: `aos/orchestrator.py`
- **Purpose**: Deterministic heart of the system
- **Key Features**:
  - Manages agent lifecycle (spawning, shutting down)
  - No LLM itself - purely deterministic
  - Bridge between agents and system services
  - Handles system-wide coordination

### 3. **Agent** (The Process)
- **File**: `aos/agent.py`
- **Purpose**: Fundamental unit of work
- **Key Features**:
  - Each agent has a role, task, and budget
  - Main `run()` loop: think → act → report
  - Can spawn sub-agents
  - Manages its own lifecycle

### 4. **Toolbox** (The Shared Library)
- **File**: `aos/toolbox.py`
- **Purpose**: Central registry of capabilities
- **Key Features**:
  - Dynamic tool registration
  - Agents can create new tools
  - Shared capabilities across all agents

### 5. **Ledger** (The Central Bank)
- **File**: `aos/ledger.py`
- **Purpose**: Single source of truth for all economic transactions
- **Key Features**:
  - Tracks all agent balances
  - Records every expenditure
  - Enforces budget constraints

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/Nabil-Mabrouk/agentic-operating-system.git
cd agentic-operating-system

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

### Basic Usage

```python
import asyncio
from aos.bootstrap import Bootstrap, SystemConfig

async def main():
    # Configure the system
    config = SystemConfig(
        initial_budget=1000.0,
        objective="Build a simple web application",
        max_agents=10,
        log_level="INFO"
    )
    
    # Run the system
    bios = Bootstrap(config)
    results = await bios.boot()
    
    print(f"System completed. Total cost: ${results['total_cost']:.2f}")

# Run the simulation
asyncio.run(main())
```

### Running the Example

```bash
python examples/startup_simulation.py
```

## 📖 Core Concepts

### 1. **Hierarchical Delegation**

Agents don't execute complex tasks directly. Instead, they:
- Break down tasks into simpler sub-tasks
- Delegate to specialized agents they spawn
- This process is recursive, allowing arbitrary complexity

```python
# Example: A manager agent might think:
"I need to build a web app. I'll spawn:
- A frontend developer agent
- A backend developer agent  
- A DevOps agent for deployment"
```

### 2. **Economic Scarcity**

Every action has a cost:
- API calls: $0.01 per call
- Spawning agents: $10.00 per agent
- Tool usage: Variable costs
- Running out of funds = agent "death"

This creates **selective pressure** for efficient solutions.

### 3. **Dynamic Specialization**

Agents aren't hard-coded with fixed roles:
- Manager agents decide what specialists to create
- Can spawn "R&D" agents to create new tools
- System defines its own organizational structure

### 4. **Emergent Intelligence**

By combining these principles, intelligent behavior emerges:
- **Cost-benefit analysis**: "Should I search for an existing solution or build from scratch?"
- **Risk management**: "I'll fund a small proof-of-concept before the full project"
- **Resource optimization**: "I'll use cheaper tools when possible"

## 🔧 Agent Development

### Creating a Custom Tool

```python
from aos.tools.base_tool import BaseTool

class MyCustomTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="my_custom_tool",
            description="Does something amazing"
        )
        
    async def execute(self, parameters: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        # Your tool logic here
        return {"result": "success", "data": "your data"}
        
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string"}
            },
            "required": ["input"]
        }

# Register the tool
await toolbox.register_tool(MyCustomTool())
```

### Agent Behavior

Agents follow a simple loop:

1. **Think**: Call LLM to analyze situation
2. **Act**: Execute chosen action (delegate, use tool, or complete)
3. **Report**: Update state and results

The agent's decision-making process is guided by:
- Current budget
- Available tools
- Task requirements
- Previous actions

## 📊 Monitoring and Debugging

### Logging

AOS uses structured logging at multiple levels:

```python
# Set log level in config
config = SystemConfig(
    log_level="DEBUG",  # DEBUG, INFO, WARNING, ERROR
    # ... other config
)
```

### Ledger Export

Export all transactions for analysis:

```python
# Export ledger to JSON
await ledger.export_ledger("transaction_log.json")
```

### Agent States

Monitor agent lifecycle:
- `ACTIVE`: Currently working
- `COMPLETED`: Finished successfully
- `FAILED`: Failed to complete task
- `DEAD`: Ran out of funds

## 🛠️ Configuration

### SystemConfig Options

```python
config = SystemConfig(
    initial_budget=1000.0,        # Starting budget for founder agent
    objective="Your objective",   # System objective
    max_agents=10,               # Maximum concurrent agents
    api_cost_per_call=0.01,      # Cost per LLM call
    spawn_cost=10.0,             # Cost to spawn new agent
    log_level="INFO"             # Logging level
)
```

### AgentConfig Options

```python
config = AgentConfig(
    role="Developer",            # Agent's role
    task="Build API endpoint",   # Specific task
    budget=100.0,               # Agent's budget
    parent_id="parent123",       # Parent agent ID (optional)
    max_subagents=3,            # Max sub-agents this agent can spawn
    api_cost_per_call=0.01      # Cost per LLM call
)
```

## 🔍 Advanced Features

### Dynamic Tool Creation

Agents can create new tools at runtime:

```python
# Agent decides to create a new tool
tool_code = '''
from aos.tools.base_tool import BaseTool

class DatabaseTool(BaseTool):
    def __init__(self):
        super().__init__("database", "Database operations")
        
    async def execute(self, params, agent_id):
        # Implementation here
        pass
'''

# Load the tool dynamically
await toolbox.load_dynamic_tool(tool_code, "DatabaseTool")
```

### Custom Agent Behaviors

Extend the base Agent class for specialized behaviors:

```python
class SpecializedAgent(Agent):
    async def custom_behavior(self):
        # Custom logic here
        pass
        
    async def run(self):
        # Override run loop
        await self.custom_behavior()
        return await super().run()
```

## 🧪 Testing

Run the test suite:

```bash
# Install test dependencies
pip install -e .[dev]

# Run tests
pytest tests/

# Run with coverage
pytest --cov=aos tests/
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone and setup
git clone https://github.com/your-org/aos-v0.git
cd aos-v0

# Install in development mode
pip install -e .[dev]

# Run tests
pytest

# Format code
black aos/ tests/

# Type checking
mypy aos/
```

## 📈 Performance Considerations

### Optimization Tips

1. **Budget Allocation**: Start with higher budgets for exploration
2. **Agent Limits**: Set `max_agents` based on your API rate limits
3. **Tool Efficiency**: Create specialized tools for common operations
4. **Async Operations**: All I/O operations are async for concurrency

### Monitoring Costs

```python
# Track costs in real-time
total_cost = await ledger.get_total_expenditure()
print(f"Total spent: ${total_cost:.2f}")

# Get agent-specific costs
agent_cost = await ledger.get_transaction_history(agent_id)
```

## 🚨 Common Issues

### 1. Agents Running Out of Budget

**Symptom**: Agents die quickly
**Solution**: Increase initial budget or reduce action costs

### 2. System Timeout

**Symptom**: System stops after 5 minutes
**Solution**: Increase timeout in orchestrator or optimize agent efficiency

### 3. API Rate Limits

**Symptom**: LLM calls fail
**Solution**: Implement rate limiting or use multiple API keys

## 📚 Examples

Check the `examples/` directory for:
- `startup_simulation.py`: Basic startup scenario
- `complex_project.py`: Multi-agent project development
- `tool_creation.py`: Dynamic tool creation example

## 🔮 Roadmap

- [ ] **Persistent Storage**: SQLite/PostgreSQL backend
- [ ] **Web Dashboard**: Real-time monitoring interface
- [ ] **Agent Learning**: Experience-based optimization
- [ ] **Plugin System**: Easy third-party extensions
- [ ] **Distributed Mode**: Multi-machine agent networks
- [ ] **Security Sandbox**: Secure dynamic code execution

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Inspired by organizational theory and economic principles
- Built on modern async Python patterns
- Thanks to the open-source community for tools and inspiration

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/Nabil-Mabrouk/agentic-operating-system/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Nabil-Mabrouk/agentic-operating-system/discussions)
- **Documentation**: [Full Docs](https://aos-v0.readthedocs.io/)

**Star ⭐ this repo if you find it interesting!**