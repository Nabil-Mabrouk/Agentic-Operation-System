# aos/exceptions.py

"""
Custom exceptions for the Agentic Operating System (AOS).
"""

class AOSException(Exception):
    """Base exception for all custom exceptions in the AOS application."""
    pass

class MaxAgentsReachedError(AOSException):
    """Raised when an attempt is made to spawn an agent beyond the configured limit."""
    pass

# Vous pourrez ajouter d'autres exceptions ici à l'avenir,
# par exemple: InsufficientFundsError, ToolNotFoundError, etc.