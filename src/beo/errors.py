from __future__ import annotations

from typing import Any, Literal

BeoErrorCode = Literal[
    "HTTP_ERROR",
    "NETWORK_ERROR",
    "PARSE_ERROR",
    "VALIDATION_ERROR",
    "UNSUPPORTED_OPERATION",
]


class BeoError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: BeoErrorCode,
        status: int | None = None,
        url: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.name = "BeoError"
        self.message = message
        self.code = code
        self.status = status
        self.url = url
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "message": self.message,
            "code": self.code,
            "status": self.status,
            "url": self.url,
            "details": self.details,
        }

    @classmethod
    def http(cls, message: str, **kwargs: Any) -> BeoError:
        return cls(message, code="HTTP_ERROR", **kwargs)

    @classmethod
    def network(cls, message: str, **kwargs: Any) -> BeoError:
        return cls(message, code="NETWORK_ERROR", **kwargs)

    @classmethod
    def parse(cls, message: str, **kwargs: Any) -> BeoError:
        return cls(message, code="PARSE_ERROR", **kwargs)

    @classmethod
    def validation(cls, message: str, **kwargs: Any) -> BeoError:
        return cls(message, code="VALIDATION_ERROR", **kwargs)

    @classmethod
    def unsupported(cls, message: str, **kwargs: Any) -> BeoError:
        return cls(message, code="UNSUPPORTED_OPERATION", **kwargs)
