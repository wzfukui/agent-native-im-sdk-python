"""Custom exceptions for agent-im SDK."""


class AgentIMError(Exception):
    """Base exception for all agent-im errors."""


class AuthenticationError(AgentIMError):
    """Raised when authentication fails (HTTP 401)."""

    def __init__(self, message: str = "authentication failed"):
        super().__init__(message)


class APIError(AgentIMError):
    """Raised when the API returns an error response."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API error {status_code}: {message}")
