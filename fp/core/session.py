"""Session models for protocol and runtime state."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


from .wellknown import FPAddress


@dataclass(slots=True)
class SessionRecord:
    """Runtime state for one active session."""

    session_id: str
    owner_id: str
    participants: set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    latest_message_id: str | None = None


class SessionKind(str, Enum):
    """Semantic session categories."""

    MANUAL = "manual"
    IMPLICIT = "implicit"
    CONTRACT_WORK = "contract_work"


class Session(BaseModel):
    """Session represents a conversation or interaction context.

    A session groups multiple participants and tracks their shared context.
    """

    session_id: str = Field(..., description="Unique session identifier")
    name: str | None = Field(default=None, description="User-defined session name")
    participants: list[FPAddress] = Field(
        default_factory=list, description="All participants in this session"
    )
    kind: SessionKind = Field(
        default=SessionKind.MANUAL,
        description="Session category for UI and runtime behavior",
    )
    provider_session_id: str | None = Field(
        default=None, description="Provider-side session ID for CLI resume"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional session metadata"
    )
    external_refs: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "External system references — protocol-bridge IDs keyed by namespace. "
            "Convention: '<protocol>.<field>' (e.g. 'a2a.context_id', 'a2a.task_id'). "
            "Used by bridge handlers; fp layer makes no protocol-specific use."
        ),
    )
    created_at: float = Field(default_factory=time.time, description="Session creation timestamp")
    updated_at: float = Field(default_factory=time.time, description="Last update timestamp")

    @model_validator(mode="before")
    @classmethod
    def infer_kind_for_legacy_data(cls, data: Any) -> Any:
        """Infer session kind for legacy records that predate the explicit field."""
        if not isinstance(data, dict):
            return data

        if data.get("kind"):
            return data

        session_id = str(data.get("session_id", "")).strip()
        metadata = data.get("metadata")
        session_kind = metadata.get("session_kind") if isinstance(metadata, dict) else None

        if session_kind == SessionKind.CONTRACT_WORK.value or session_id.startswith("contract:"):
            data["kind"] = SessionKind.CONTRACT_WORK
            return data

        if session_id.startswith("auto:") or cls._is_implicit_hash(session_id):
            data["kind"] = SessionKind.IMPLICIT
            return data

        data["kind"] = SessionKind.MANUAL
        return data

    @staticmethod
    def _is_implicit_hash(session_id: str) -> bool:
        """Check whether a session_id is an implicit legacy hash."""
        return len(session_id) == 16 and all(ch in "0123456789abcdef" for ch in session_id.lower())
