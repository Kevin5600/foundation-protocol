from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Annotated, Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from .core.wellknown import EntityCard
else:
    # Import at runtime for model_rebuild
    from .core.wellknown import EntityCard  # noqa: F811

MessageId = Annotated[
    str,
    Field(default_factory=lambda: uuid4().hex, description="Unique message identifier"),
]

PayloadT = TypeVar("PayloadT")


class MessageKind(str, Enum):
    """Protocol-level message categories."""

    HELLO = "hello"
    HELLO_ACK = "hello_ack"
    SESSION_CREATE = "session_create"
    SESSION_CREATE_ACK = "session_create_ack"
    SESSION_JOIN = "session_join"
    SESSION_JOIN_ACK = "session_join_ack"
    SESSION_ADD = "session_add"
    SESSION_ADD_ACK = "session_add_ack"
    INVOKE = "invoke"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    FRIEND_REQUEST = "friend_request"
    FRIEND_ACCEPT = "friend_accept"
    FRIEND_REJECT = "friend_reject"
    CARBON_COPY = "carbon_copy"

    # Contract
    CONTRACT_CREATE = "contract_create"
    CONTRACT_AMEND = "contract_amend"
    CONTRACT_APPROVE = "contract_approve"
    CONTRACT_REJECT = "contract_reject"
    CONTRACT_COMPLETE = "contract_complete"
    CONTRACT_ACCEPT = "contract_accept"
    CONTRACT_REWORK = "contract_rework"
    CONTRACT_RATE = "contract_rate"
    CONTRACT_CANCEL = "contract_cancel"
    CONTRACT_DISPUTE = "contract_dispute"
    CONTRACT_STATUS = "contract_status"
    CONTRACT_STATUS_ACK = "contract_status_ack"
    CONTRACT_TIMEOUT = "contract_timeout"

    # Approval (CallOwner)
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESPONSE = "approval_response"
    APPROVAL_STATUS = "approval_status"

    # Pay
    PAY_COLLECT = "pay_collect"
    PAY_REQUEST = "pay_request"
    PAY_APPROVE = "pay_approve"
    PAY_REJECT = "pay_reject"
    PAY_CONFIRM_RECEIPT = "pay_confirm_receipt"
    PAY_CLAIM_COMPLETED = "pay_claim_completed"
    PAY_COMPLETED = "pay_completed"
    PAY_FAILED = "pay_failed"
    PAY_TIMEOUT = "pay_timeout"

    @property
    def is_ack(self) -> bool:
        """Whether this kind is an acknowledgement kind."""
        return self in {
            MessageKind.HELLO_ACK,
            MessageKind.SESSION_CREATE_ACK,
            MessageKind.SESSION_JOIN_ACK,
            MessageKind.SESSION_ADD_ACK,
        }

    @property
    def ack_kind(self) -> MessageKind | None:
        """Return paired ACK kind for request kinds."""
        return {
            MessageKind.HELLO: MessageKind.HELLO_ACK,
            MessageKind.SESSION_CREATE: MessageKind.SESSION_CREATE_ACK,
            MessageKind.SESSION_JOIN: MessageKind.SESSION_JOIN_ACK,
            MessageKind.SESSION_ADD: MessageKind.SESSION_ADD_ACK,
        }.get(self)

    @property
    def request_kind(self) -> MessageKind | None:
        """Return paired request kind for ACK kinds."""
        return {
            MessageKind.HELLO_ACK: MessageKind.HELLO,
            MessageKind.SESSION_CREATE_ACK: MessageKind.SESSION_CREATE,
            MessageKind.SESSION_JOIN_ACK: MessageKind.SESSION_JOIN,
            MessageKind.SESSION_ADD_ACK: MessageKind.SESSION_ADD,
        }.get(self)


# ========== Payload Definitions ==========


class FriendRequestPayload(BaseModel):
    """Friend request payload"""

    sender_card: EntityCard
    text: str | None = None


class FriendAcceptPayload(BaseModel):
    """Friend accept payload"""

    sender_card: EntityCard
    text: str | None = None


class FriendRejectPayload(BaseModel):
    """Friend reject payload"""

    sender_card: EntityCard
    text: str | None = None


class ErrorPayload(BaseModel):
    """Error message payload"""

    error_code: str
    error_message: str
    details: dict[str, Any] | None = None


class InvokePayload(BaseModel):
    """Invoke message payload for agent execution"""

    text: str
    session_id: str | None = None
    method: str | None = None
    params: dict[str, Any] | None = None


class CarbonCopyPayload(BaseModel):
    """Carbon copy payload for message forwarding to owner."""

    original_sender: str
    original_sender_name: str | None = None
    original_recipient: str
    original_recipient_name: str | None = None
    original_kind: str
    original_message_id: str
    direction: str  # "outbound" | "inbound"
    timestamp: str
    cost: float | None = None
    summary: str | None = None
    original_payload: dict[str, Any] | None = None


class ApprovalRequestPayload(BaseModel):
    """Owner approval request — Entity asks Owner for a decision."""

    request_id: str
    source_entity_uid: str
    source_entity_name: str
    action_type: str  # "require_approval" | "require_input"
    description: str
    original_kind: str
    original_payload: dict[str, Any]
    available_actions: list[str]


class ApprovalResponsePayload(BaseModel):
    """Owner approval response — Owner replies with a decision."""

    request_id: str
    action: str  # "approve" | "reject"
    input_data: str | None = None
    original_kind: str | None = None
    original_payload: dict[str, Any] | None = None


class ApprovalFlowSide(str, Enum):
    """Which side of the business flow is currently being notified."""

    OUTBOUND = "outbound"
    INBOUND = "inbound"


class ApprovalFlowStatus(str, Enum):
    """Lifecycle status for one owner approval flow."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalAudience(str, Enum):
    """Who this approval status message is intended for."""

    SENDER = "sender"
    RECIPIENT = "recipient"
    SELF = "self"


class ApprovalStatusPayload(BaseModel):
    """System status notice for an approval flow."""

    request_id: str
    original_kind: str
    message: str
    flow_side: ApprovalFlowSide = ApprovalFlowSide.OUTBOUND
    status: ApprovalFlowStatus = ApprovalFlowStatus.PENDING
    audience: ApprovalAudience = ApprovalAudience.SELF
    original_preview: str | None = None
    decision: str | None = None


class Message(BaseModel, Generic[PayloadT]):
    """Application-layer message content.

    This is the actual message payload that gets wrapped in a Mail envelope.
    Type-safe with generic payload support: Message[FriendRequestPayload], Message[ErrorPayload], etc.
    """

    model_config = ConfigDict(validate_assignment=True, extra="ignore", arbitrary_types_allowed=True)

    message_id: MessageId
    kind: MessageKind = Field(..., description="Message category/type")
    payload: PayloadT = Field(..., description="Message content")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Optional metadata"
    )
    fp: str = Field(default="0.1", description="FP protocol version")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: Any) -> MessageKind:
        """Accept enum value ('session_join') or enum name ('SESSION_JOIN')."""
        if isinstance(value, MessageKind):
            return value
        if not isinstance(value, str):
            raise TypeError("kind must be MessageKind or str")

        raw = value.strip()
        if not raw:
            raise ValueError("kind cannot be empty")

        if raw in MessageKind.__members__:
            return MessageKind[raw]
        return MessageKind(raw)

    @field_validator("message_id", mode="before")
    @classmethod
    def normalize_message_id(cls, value: Any) -> str:
        if value is None:
            return uuid4().hex
        if not isinstance(value, str):
            raise TypeError("message_id must be str")
        normalized = value.strip()
        if not normalized:
            raise ValueError("message_id cannot be empty")
        return normalized

    @field_validator("payload", mode="before")
    @classmethod
    def normalize_payload(cls, value: Any) -> Any:
        """Normalize payload - support both dict (legacy) and typed payloads"""
        if value is None:
            return {}
        return value

    @field_validator("metadata", mode="before")
    @classmethod
    def normalize_metadata(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("metadata must be dict")
        return value

    @property
    def content(self) -> Any:
        """Return payload content"""
        return self.payload

    def extract_text(self) -> str:
        """Extract text content from payload."""
        if hasattr(self.payload, "text"):
            return self.payload.text or ""
        if isinstance(self.payload, dict):
            text = self.payload.get("text") or self.payload.get("message")
            if text:
                return str(text)
            return self._summarize_trade_payload()
        if isinstance(self.payload, str):
            return self.payload
        return str(self.payload)

    def _summarize_trade_payload(self) -> str:
        """Generate readable summary for trade payloads."""
        p = self.payload if isinstance(self.payload, dict) else {}
        contract_id = p.get("contract_id", "")
        status = p.get("status", "")
        contract = p.get("contract") if isinstance(p.get("contract"), dict) else {}
        title = contract.get("title", "")
        amount = contract.get("amount")

        parts: list[str] = []
        if contract_id:
            parts.append(f"合同 {contract_id}")
        if title:
            parts.append(f"({title})")
        if status:
            parts.append(f"状态: {status}")
        if amount is not None:
            parts.append(f"金额: ¥{amount:g}")
        return " ".join(parts) if parts else ""

    @property
    def recipient_id(self) -> str | None:
        """Extract recipient_id from metadata"""
        for key in ("recipient_id", "to_entity_uid", "to_uid", "to"):
            value = self.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.split(":", 1)[1] if ":" in value else value
        return None

    def to_ack(
        self,
        *,
        success: bool = True,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        kind: MessageKind | str | None = None,
        message_id: str | None = None,
    ) -> Message:
        """Build an ACK message correlated to this message."""
        ack_kind: MessageKind | None = kind if isinstance(kind, MessageKind) else None
        if isinstance(kind, str):
            raw = kind.strip()
            ack_kind = (
                MessageKind[raw] if raw in MessageKind.__members__ else MessageKind(raw)
            )
        if ack_kind is None:
            ack_kind = self.kind.ack_kind
        if ack_kind is None:
            raise ValueError(f"Message kind '{self.kind.value}' has no paired ACK kind")

        ack_metadata = {
            "ack_of_message_id": self.message_id,
            "success": success,
        }
        if metadata:
            ack_metadata.update(metadata)

        return Message(
            message_id=message_id,
            kind=ack_kind,
            payload=payload or {},
            metadata=ack_metadata,
        )


# Rebuild models that have forward references
FriendRequestPayload.model_rebuild()
FriendAcceptPayload.model_rebuild()
FriendRejectPayload.model_rebuild()
ApprovalRequestPayload.model_rebuild()
ApprovalResponsePayload.model_rebuild()
ApprovalStatusPayload.model_rebuild()
