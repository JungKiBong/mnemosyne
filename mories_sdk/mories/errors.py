"""
Mories SDK Error Exceptions
"""

class MoriesError(Exception):
    """Base exception for all Mories SDK errors."""
    def __init__(self, message, code=None, status_code=None, details=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

class AuthenticationError(MoriesError):
    """Raised when authentication fails or token is missing/invalid."""
    pass

class AuthorizationError(MoriesError):
    """Raised when the provided token lacks specific permissions."""
    pass

class ValidationError(MoriesError):
    """Raised when the server rejects input parameters."""
    pass

class NotFoundError(MoriesError):
    """Raised when a resource cannot be found."""
    pass

class SystemError(MoriesError):
    """Raised when a backend system or configuration error occurs."""
    pass

def parse_api_error(status_code: int, error_data: dict) -> MoriesError:
    """Parses a structured JSON error response into a specific MoriesError."""
    err = error_data.get("error", {})
    code = err.get("code", "UNKNOWN_ERROR")
    message = err.get("message", "An unknown error occurred.")
    details = err.get("details", {})

    kwargs = {
        "message": message,
        "code": code,
        "status_code": status_code,
        "details": details
    }

    if status_code == 401 or code == "UNAUTHORIZED":
        return AuthenticationError(**kwargs)
    elif status_code == 403 or code == "FORBIDDEN":
        return AuthorizationError(**kwargs)
    elif status_code == 400 or code == "VALIDATION_ERROR":
        return ValidationError(**kwargs)
    elif status_code == 404 or code == "NOT_FOUND":
        return NotFoundError(**kwargs)
    elif status_code >= 500:
        return SystemError(**kwargs)
    
    return MoriesError(**kwargs)
