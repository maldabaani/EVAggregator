"""Task 1.1 — maps internal exceptions to OCPI `status_code` ranges (2xxx
client error, 3xxx server error) per the OCPI spec appendix, so a malformed
request never surfaces as a generic 500.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import IntEnum

from pydantic import ValidationError


class OcpiErrorCode(IntEnum):
    SUCCESS = 1000
    INVALID_PARAMETERS = 2001
    NOT_ENOUGH_INFORMATION = 2002
    UNKNOWN_LOCATION = 2003
    UNKNOWN_TOKEN = 2004
    UNKNOWN_TARIFF = 2005
    GENERIC_SERVER_ERROR = 3000
    UNABLE_TO_USE_CLIENT_API = 3001
    UNSUPPORTED_VERSION = 3002
    NO_MATCHING_ENDPOINTS = 3003


HTTP_STATUS_BY_ERROR_CODE: dict[OcpiErrorCode, int] = {
    OcpiErrorCode.INVALID_PARAMETERS: 400,
    OcpiErrorCode.NOT_ENOUGH_INFORMATION: 400,
    OcpiErrorCode.UNKNOWN_LOCATION: 404,
    OcpiErrorCode.UNKNOWN_TOKEN: 401,
    OcpiErrorCode.UNKNOWN_TARIFF: 404,
    OcpiErrorCode.GENERIC_SERVER_ERROR: 500,
    OcpiErrorCode.UNABLE_TO_USE_CLIENT_API: 500,
    OcpiErrorCode.UNSUPPORTED_VERSION: 406,
    OcpiErrorCode.NO_MATCHING_ENDPOINTS: 404,
}


class OcpiError(Exception):
    def __init__(self, status_code: OcpiErrorCode, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)

    @property
    def http_status(self) -> int:
        return HTTP_STATUS_BY_ERROR_CODE.get(self.status_code, 500)

    def to_response_body(self) -> dict:
        return {
            "status_code": int(self.status_code),
            "status_message": self.message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def map_exception_to_ocpi_error(exc: Exception) -> OcpiError:
    """Central mapping used by every OCPI route's error handler — internal
    exceptions never leak as a generic 500; unrecognized ones become a 3000
    (generic server error) rather than exposing internals."""
    if isinstance(exc, OcpiError):
        return exc
    if isinstance(exc, (ValidationError, ValueError, TypeError, KeyError)):
        return OcpiError(OcpiErrorCode.INVALID_PARAMETERS, str(exc))
    return OcpiError(OcpiErrorCode.GENERIC_SERVER_ERROR, "internal server error")
