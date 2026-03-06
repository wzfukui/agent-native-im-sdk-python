"""Custom exceptions for agent-im SDK with v2.3+ structured error support."""

from typing import Optional, Dict, Any
from datetime import datetime, timezone


class AgentIMError(Exception):
    """Base exception for all agent-im errors."""


class APIError(AgentIMError):
    """Raised when the API returns an error response (v2.3+ structured format)."""

    def __init__(
        self,
        status_code: int,
        message: str,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.status_code = status_code
        self.message = message
        self.code = code or "UNKNOWN"
        self.request_id = request_id
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Format error message
        error_msg = f"API error {status_code}: {message}"
        if code:
            error_msg = f"[{code}] {error_msg}"
        if request_id:
            error_msg += f" (Request ID: {request_id})"

        super().__init__(error_msg)

    @classmethod
    def from_response(cls, status_code: int, body: Dict[str, Any]) -> "APIError":
        """Create APIError from API response (handles both old and new formats)."""
        # Check for v2.3+ structured error format
        if isinstance(body.get("error"), dict):
            error = body["error"]
            return cls(
                status_code=error.get("status", status_code),
                message=error.get("message", "Unknown error"),
                code=error.get("code"),
                request_id=error.get("request_id"),
                details=error.get("details"),
            )
        # Legacy error format (pre-v2.3)
        else:
            return cls(
                status_code=status_code,
                message=body.get("error", "Unknown error"),
            )


class AuthenticationError(APIError):
    """Raised when authentication fails (HTTP 401)."""

    def __init__(self, message: str = "authentication failed", request_id: Optional[str] = None):
        super().__init__(
            status_code=401,
            message=message,
            code="AUTH_INVALID",
            request_id=request_id,
        )


class ConnectionClosedError(AgentIMError):
    """Raised when WebSocket connection is closed unexpectedly."""


class ValidationError(APIError):
    """Raised when request validation fails."""

    def __init__(self, field: str, message: str, request_id: Optional[str] = None):
        super().__init__(
            status_code=400,
            message=f"Validation error on field '{field}': {message}",
            code="VALIDATION_ERROR",
            request_id=request_id,
            details={"field": field, "error": message},
        )


class NotFoundError(APIError):
    """Raised when a resource is not found."""

    def __init__(self, resource: str, request_id: Optional[str] = None):
        super().__init__(
            status_code=404,
            message=f"{resource} not found",
            code=f"{resource.upper().replace(' ', '_')}_NOT_FOUND",
            request_id=request_id,
        )


class ConflictError(APIError):
    """Raised when there's a conflict (e.g., duplicate resource)."""

    def __init__(self, message: str, request_id: Optional[str] = None, details: Optional[Dict] = None):
        super().__init__(
            status_code=409,
            message=message,
            code="CONFLICT",
            request_id=request_id,
            details=details,
        )


class RateLimitError(APIError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        retry_after: Optional[int] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            status_code=429,
            message="Rate limit exceeded",
            code="RATE_LIMIT_EXCEEDED",
            request_id=request_id,
            details={"retry_after": retry_after} if retry_after else {},
        )
