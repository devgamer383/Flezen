"""
Flezen API Exceptions
"""


class FlezenError(Exception):
    """Base exception for all Flezen errors."""
    pass


class FlezenAuthError(FlezenError):
    """Raised when authentication fails or session expires."""
    pass


class FlezenAPIError(FlezenError):
    """Raised when an API endpoint returns an error status code."""
    def __init__(self, message: str, status_code: int = None, response_text: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

    def __str__(self):
        code_str = f" [HTTP {self.status_code}]" if self.status_code is not None else ""
        return f"{super().__str__()}{code_str}"


class FlezenUploadError(FlezenError):
    """Raised when file upload fails during initiate, chunk transfer, or completion."""
    pass
