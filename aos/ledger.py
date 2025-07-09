import asyncio
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

class TransactionType(Enum):
    """Types of transactions in the system"""
    API_CALL = "api_call"
    SPAWN_AGENT = "spawn_agent"
    TOOL_USAGE = "tool_usage"
    BUDGET_ALLOCATION = "budget_allocation"
    AGENT_DEATH = "agent_death"

@dataclass
class Transaction:
    """A single transaction in the ledger"""
    timestamp: datetime
    agent_id: str
    transaction_type: TransactionType
    amount: float
    description: str
    metadata: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """Convert transaction to dictionary"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['transaction_type'] = self.transaction_type.value
        return data

class Ledger:
    """The Central Bank of the AOS - tracks all economic transactions"""
    
    def __init__(self):
        self.logger = logging.getLogger("AOS-Ledger")
        self.transactions: List[Transaction] = []
        self.agent_balances: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        
    async def initialize(self) -> None:
        """Initialize the ledger"""
        self.logger.info("Ledger initialized")
        
    async def create_account(self, agent_id: str, initial_balance: float = 0.0) -> None:
        """Create a new account for an agent"""
        async with self._lock:
            if agent_id in self.agent_balances:
                raise ValueError(f"Account for agent {agent_id} already exists")
            self.agent_balances[agent_id] = initial_balance
            self.logger.debug(f"Account created for agent {agent_id} with balance ${initial_balance:.2f}")
            
    async def get_balance(self, agent_id: str) -> float:
        """Get the current balance of an agent"""
        async with self._lock:
            return self.agent_balances.get(agent_id, 0.0)
            
    async def transfer(self, from_agent: str, to_agent: str, amount: float, description: str) -> bool:
        """Transfer funds between agents"""
        async with self._lock:
            if self.agent_balances.get(from_agent, 0) < amount:
                return False
                
            self.agent_balances[from_agent] -= amount
            self.agent_balances[to_agent] = self.agent_balances.get(to_agent, 0) + amount
            
            # Record transactions
            await self._record_transaction(
                from_agent, TransactionType.BUDGET_ALLOCATION, -amount,
                f"Transfer to {to_agent}: {description}"
            )
            await self._record_transaction(
                to_agent, TransactionType.BUDGET_ALLOCATION, amount,
                f"Transfer from {from_agent}: {description}"
            )
            
            return True
            
    async def charge(self, agent_id: str, amount: float, transaction_type: TransactionType, description: str) -> bool:
        """Charge an agent for a service"""
        async with self._lock:
            if self.agent_balances.get(agent_id, 0) < amount:
                await self._record_transaction(
                    agent_id, TransactionType.AGENT_DEATH, 0,
                    f"Agent died - insufficient funds for: {description}"
                )
                return False
                
            self.agent_balances[agent_id] -= amount
            await self._record_transaction(agent_id, transaction_type, -amount, description)
            return True
            
    async def _record_transaction(self, agent_id: str, transaction_type: TransactionType, amount: float, description: str) -> None:
        """Record a transaction in the ledger"""
        transaction = Transaction(
            timestamp=datetime.now(),
            agent_id=agent_id,
            transaction_type=transaction_type,
            amount=amount,
            description=description
        )
        self.transactions.append(transaction)
        self.logger.debug(f"Transaction recorded: {transaction.to_dict()}")
        
    async def get_transaction_history(self, agent_id: Optional[str] = None) -> List[Transaction]:
        """Get transaction history for an agent or all agents"""
        if agent_id:
            return [t for t in self.transactions if t.agent_id == agent_id]
        return self.transactions.copy()
        
    async def get_total_expenditure(self) -> float:
        """Get total expenditure across all agents"""
        return sum(abs(t.amount) for t in self.transactions if t.amount < 0)
        
    async def export_ledger(self, filename: str) -> None:
        """Export the ledger to a JSON file"""
        data = {
            "balances": self.agent_balances,
            "transactions": [t.to_dict() for t in self.transactions]
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        self.logger.info(f"Ledger exported to {filename}")