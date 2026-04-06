"""
Mories API Custom Exceptions
"""

class MoriesAPIError(Exception):
    """Base exception for all Mories API errors."""
    def __init__(self, message, code="INTERNAL_ERROR", status_code=500, details=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self):
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details
            }
        }

class AuthenticationError(MoriesAPIError):
    def __init__(self, message="Authentication required", details=None):
        super().__init__(message, code="UNAUTHORIZED", status_code=401, details=details)

class AuthorizationError(MoriesAPIError):
    def __init__(self, message="Permission denied", details=None):
        super().__init__(message, code="FORBIDDEN", status_code=403, details=details)

class ValidationError(MoriesAPIError):
    def __init__(self, message="Invalid input parameters", details=None):
        super().__init__(message, code="VALIDATION_ERROR", status_code=400, details=details)

class NotFoundError(MoriesAPIError):
    def __init__(self, message="Resource not found", details=None):
        super().__init__(message, code="NOT_FOUND", status_code=404, details=details)

class SystemError(MoriesAPIError):
    def __init__(self, message="System configuration or backend error", details=None):
        super().__init__(message, code="SYSTEM_ERROR", status_code=500, details=details)
