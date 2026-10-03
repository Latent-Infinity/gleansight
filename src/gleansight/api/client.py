from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from pydantic import JsonValue, ValidationError

from gleansight.api.models import (
    ErrorData,
    ErrorDetail,
    Failure,
    OperationDescription,
    OperationError,
    Result,
    Success,
)
from gleansight.api.operation import RegisteredOperation
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.domain.errors import (
    BaseModuleError,
    ConfigurationError,
    ConflictError,
    ExternalServiceError,
    InvalidStateTransition,
    NotFoundError,
    NotReadyError,
    PipelineError,
)


class GleansightAPI:
    """Use one operation registry for embedded callers and the JSON CLI."""

    def __init__(
        self,
        configuration: ApiConfiguration | None = None,
        *,
        operations: Sequence[RegisteredOperation] | None = None,
    ) -> None:
        if operations is None:
            from gleansight.api.catalog import default_operations

            operations = default_operations()
        self._operations = {operation.name: operation for operation in operations}
        if len(self._operations) != len(operations):
            raise OperationError("operation_conflict", "Operation names must be unique.")
        self._runtime = ApiRuntime(configuration or ApiConfiguration())

    def operations(self, namespace: str | None = None) -> tuple[OperationDescription, ...]:
        return tuple(
            operation.describe()
            for name, operation in sorted(self._operations.items())
            if namespace is None or name.startswith(namespace + ".")
        )

    def describe(self, name: str) -> OperationDescription:
        return self._lookup(name).describe()

    def call(self, name: str, parameters: Mapping[str, JsonValue]) -> Result:
        try:
            data = self._lookup(name).invoke(self._runtime, parameters)
        except OperationError as exc:
            error = ErrorData(code=exc.code, message=str(exc), retryable=exc.retryable)
        except ValidationError as exc:
            error = ErrorData(
                code="invalid_request",
                message="Request does not match the operation schema.",
                details=tuple(
                    ErrorDetail(location=row["loc"], code=row["type"], message=row["msg"])
                    for row in exc.errors(include_input=False, include_context=False)
                ),
            )
        except ConfigurationError:
            error = ErrorData(
                code="configuration_error", message="Application configuration failed."
            )
        except NotFoundError as exc:
            error = ErrorData(code="not_found", message=str(exc))
        except (ConflictError, InvalidStateTransition) as exc:
            error = ErrorData(code="conflict", message=str(exc))
        except NotReadyError as exc:
            error = ErrorData(code="not_ready", message=str(exc))
        except PipelineError as exc:
            error = ErrorData(code=exc.code.value, message=str(exc))
        except ExternalServiceError as exc:
            error = ErrorData(code="external_service_error", message=str(exc))
        except (ValueError, BaseModuleError) as exc:
            error = ErrorData(code="invalid_request", message=str(exc))
        except OSError:
            error = ErrorData(code="io_error", message="Local I/O failed.")
        except Exception as exc:  # BROAD_EXCEPT_OK: isolate unexpected adapter failures.
            logging.getLogger("gleansight.api").error(
                "operation_failed", extra={"operation": name, "error_type": type(exc).__name__}
            )
            error = ErrorData(code="internal_error", message="The operation failed unexpectedly.")
        else:
            return Success(operation=name, data=data)
        return Failure(operation=name, error=error)

    def _lookup(self, name: str) -> RegisteredOperation:
        operation = self._operations.get(name)
        if operation is None:
            raise OperationError("unknown_operation", f"Unknown operation: {name}")
        return operation
