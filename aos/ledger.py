import asyncio
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

class TransactionType(Enum):
    API_CALL = "api_call"
    SPAWN_AGENT = "spawn_agent"
    TOOL_USAGE = "tool_usage"
    BUDGET_ALLOCATION = "budget_allocation"
    AGENT_DEATH = "agent_death"
    REFUND = "refund"

class LedgerError(Exception):
    """Base exception for ledger-related errors."""
    pass

class InsufficientFundsError(LedgerError):
    """Raised when an agent has insufficient funds for a transaction."""
    pass

class AccountNotFoundError(LedgerError):
    """Raised when attempting to operate on a non-existent account."""
    pass

@dataclass
class Transaction:
    timestamp: datetime
    agent_id: str
    transaction_type: TransactionType
    amount: float
    description: str
    metadata: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['transaction_type'] = self.transaction_type.value
        return data

class Ledger:
    def __init__(self):
        self.logger = logging.getLogger("AOS-Ledger")
        self.transactions: List[Transaction] = []
        self.agent_balances: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        
    async def initialize(self) -> None:
        self.logger.info("Ledger initialized")
        
    async def create_account(self, agent_id: str, initial_balance: float = 0.0) -> None:
        async with self._lock:
            if agent_id in self.agent_balances:
                raise ValueError(f"Account for agent {agent_id} already exists")
            if initial_balance < 0:
                raise ValueError("Initial balance cannot be negative")
            
            self.agent_balances[agent_id] = initial_balance
            self.logger.info(f"Account created for agent {agent_id} with balance ${initial_balance:.2f}")
            
    async def get_balance(self, agent_id: str) -> float:
        async with self._lock:
            return self.agent_balances.get(agent_id, 0.0)
            
    async def transfer(self, from_agent: str, to_agent: str, amount: float, description: str) -> bool:
        if amount <= 0:
            raise ValueError("Transfer amount must be positive")
            
        async with self._lock:
            if from_agent not in self.agent_balances:
                raise AccountNotFoundError(f"Source account {from_agent} not found")
            if to_agent not in self.agent_balances:
                raise AccountNotFoundError(f"Destination account {to_agent} not found")
            if self.agent_balances[from_agent] < amount:
                raise InsufficientFundsError(f"Agent {from_agent} has insufficient funds for ${amount:.2f}")
            
            self.agent_balances[from_agent] -= amount
            self.agent_balances[to_agent] += amount
            
            await self._record_transaction(from_agent, TransactionType.BUDGET_ALLOCATION, -amount, f"Transfer to {to_agent}: {description}")
            await self._record_transaction(to_agent, TransactionType.BUDGET_ALLOCATION, amount, f"Transfer from {from_agent}: {description}")
            
            self.logger.debug(f"Transferred ${amount:.2f} from {from_agent} to {to_agent}")
            return True
            
    async def charge(self, agent_id: str, amount: float, transaction_type: TransactionType, description: str) -> bool:
        if amount <= 0:
            raise ValueError("Charge amount must be positive")
            
        async with self._lock:
            if agent_id not in self.agent_balances:
                raise AccountNotFoundError(f"Account {agent_id} not found")
            if self.agent_balances[agent_id] < amount:
                self.logger.warning(f"Charge failed: Agent {agent_id} has insufficient funds for '{description}' (cost: ${amount:.2f})")
                await self._record_transaction(agent_id, TransactionType.AGENT_DEATH, 0, f"Agent died - insufficient funds for: {description}")
                return False
                
            self.agent_balances[agent_id] -= amount
            await self._record_transaction(agent_id, transaction_type, -amount, description)
            self.logger.debug(f"Charged agent {agent_id} ${amount:.2f} for '{description}'. New balance: ${self.agent_balances[agent_id]:.2f}")
            return True

    async def credit(self, agent_id: str, amount: float, transaction_type: TransactionType, description: str) -> bool:
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
            
        async with self._lock:
            if agent_id not in self.agent_balances:
                raise AccountNotFoundError(f"Account {agent_id} not found")
            
            self.agent_balances[agent_id] += amount
            await self._record_transaction(agent_id, transaction_type, amount, description)
            self.logger.debug(f"Credited agent {agent_id} ${amount:.2f} for '{description}'. New balance: ${self.agent_balances[agent_id]:.2f}")
            return True
            
    async def _record_transaction(self, agent_id: str, transaction_type: TransactionType, amount: float, description: str) -> None:
        transaction = Transaction(
            timestamp=datetime.now(), agent_id=agent_id, transaction_type=transaction_type,
            amount=amount, description=description
        )
        self.transactions.append(transaction)
        self.logger.debug(f"Transaction recorded: {transaction.to_dict()}")
        
    async def get_total_expenditure(self) -> float:
        return sum(abs(t.amount) for t in self.transactions if t.amount < 0)

    async def get_agent_transaction_history(self, agent_id: str) -> List[Transaction]:
        """Get the transaction history for a specific agent."""
        return [t for t in self.transactions if t.agent_id == agent_id]

    async def save_to_file(self, filepath: str) -> None:
        """Save the ledger state to a JSON file."""
        data = {
            "transactions": [t.to_dict() for t in self.transactions],
            "agent_balances": self.agent_balances
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        self.logger.info(f"Ledger state saved to {filepath}")

    async def load_from_file(self, filepath: str) -> None:
        """Load the ledger state from a JSON file."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self.transactions = []
            for t_data in data.get("transactions", []):
                t_data['timestamp'] = datetime.fromisoformat(t_data['timestamp'])
                t_data['transaction_type'] = TransactionType(t_data['transaction_type'])
                self.transactions.append(Transaction(**t_data))
            
            self.agent_balances = data.get("agent_balances", {})
            self.logger.info(f"Ledger state loaded from {filepath}")
        except FileNotFoundError:
            self.logger.warning(f"Ledger file {filepath} not found. Starting with empty ledger.")
        except Exception as e:
            self.logger.error(f"Failed to load ledger state: {e}")
            raise