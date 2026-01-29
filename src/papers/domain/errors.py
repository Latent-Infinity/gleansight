from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    NO_OPEN_PDF = "NO_OPEN_PDF"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    CORRUPT_PDF = "CORRUPT_PDF"
    PROTECTED_PDF = "PROTECTED_PDF"
    CONVERTER_TIMEOUT = "CONVERTER_TIMEOUT"
    CONVERTER_OOM = "CONVERTER_OOM"
    EMPTY_OUTPUT = "EMPTY_OUTPUT"
    CONVERSION_FAILED = "CONVERSION_FAILED"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    LLM_ERROR = "LLM_ERROR"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    OUTPUT_PARSE_FAILED = "OUTPUT_PARSE_FAILED"
    OUTPUT_VALIDATION_FAILED = "OUTPUT_VALIDATION_FAILED"


class BaseModuleError(Exception):
    """Base exception for the papers module."""


class ValidationError(BaseModuleError):
    """Input validation failed."""


class NotFoundError(BaseModuleError):
    """Requested resource was not found."""


class ConflictError(BaseModuleError):
    """Operation conflicts with current state."""


class ExternalServiceError(BaseModuleError):
    """External service failed in a recoverable or permanent way."""


class DatabaseError(ExternalServiceError):
    """Database operation failed."""


class APIClientError(ExternalServiceError):
    """Remote API request failed."""


class ConfigurationError(BaseModuleError):
    """Configuration is missing or invalid."""


class InvalidStateTransition(BaseModuleError):
    """Pipeline or job state transition is invalid."""


class NotReadyError(BaseModuleError):
    """Operation cannot proceed because prerequisites are missing."""


class OutputValidationFailed(BaseModuleError):
    """Structured output failed schema or required field validation."""


class OutputParseFailed(BaseModuleError):
    """Structured output could not be parsed."""


class PipelineError(BaseModuleError):
    """Pipeline error with a canonical error code."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
