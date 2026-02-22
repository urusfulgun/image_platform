"""Domain error types shared across Image Platform services."""


class ImagePlatformError(Exception):
    """Base exception for all Image Platform domain errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(ImagePlatformError):
    """Raised when a requested resource does not exist."""


class ForbiddenError(ImagePlatformError):
    """Raised when the caller does not have permission to access a resource."""


class ConflictError(ImagePlatformError):
    """Raised when an operation conflicts with the current resource state."""


class ProcessingError(ImagePlatformError):
    """Raised during image processing failures."""
