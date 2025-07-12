# tests/test_ledger.py
import pytest
from aos.ledger import Ledger, TransactionType

# Le Ledger étant asynchrone, nous utiliserons pytest-asyncio
@pytest.mark.asyncio
async def test_account_creation():
    """Vérifie qu'un compte est créé avec le solde initial correct."""
    ledger = Ledger()
    await ledger.initialize()
    agent_id = "test_agent"
    initial_budget = 100.0
    
    await ledger.create_account(agent_id, initial_budget)
    balance = await ledger.get_balance(agent_id)
    
    assert balance == initial_budget

@pytest.mark.asyncio
async def test_successful_charge():
    """Vérifie qu'un débit valide est correctement appliqué."""
    ledger = Ledger()
    await ledger.initialize()
    agent_id = "test_agent"
    await ledger.create_account(agent_id, 100.0)
    
    charge_amount = 10.5
    success = await ledger.charge(agent_id, charge_amount, TransactionType.API_CALL, "Test charge")
    
    assert success is True
    
    new_balance = await ledger.get_balance(agent_id)
    assert new_balance == 100.0 - charge_amount
    
    total_expenditure = await ledger.get_total_expenditure()
    assert total_expenditure == charge_amount

@pytest.mark.asyncio
async def test_charge_fails_on_insufficient_funds():
    """Vérifie qu'un débit est refusé si les fonds sont insuffisants."""
    ledger = Ledger()
    await ledger.initialize()
    agent_id = "test_agent"
    await ledger.create_account(agent_id, 10.0)
    
    charge_amount = 15.0 # Plus que le solde
    success = await ledger.charge(agent_id, charge_amount, TransactionType.TOOL_USAGE, "Overdraft attempt")
    
    assert success is False
    
    # Le solde ne doit pas avoir changé
    balance = await ledger.get_balance(agent_id)
    assert balance == 10.0
    
    # Aucune dépense ne doit avoir été enregistrée
    total_expenditure = await ledger.get_total_expenditure()
    assert total_expenditure == 0.0

@pytest.mark.asyncio
async def test_successful_credit():
    """Vérifie qu'un crédit est correctement appliqué."""
    ledger = Ledger()
    await ledger.initialize()
    agent_id = "test_agent"
    await ledger.create_account(agent_id, 50.0)
    
    credit_amount = 25.0
    await ledger.credit(agent_id, credit_amount, TransactionType.REFUND, "Test refund")
    
    new_balance = await ledger.get_balance(agent_id)
    assert new_balance == 50.0 + credit_amount

@pytest.mark.asyncio
async def test_get_balance_for_nonexistent_account():
    """Vérifie que la lecture du solde d'un compte inexistant retourne 0."""
    ledger = Ledger()
    await ledger.initialize()
    
    balance = await ledger.get_balance("nonexistent_agent")
    
    assert balance == 0.0