# NOTE:这个文件是 protocol 协议的内容，只保留泛型 TypeVar 的高度抽象，还原 protocol 设计
# Core文件夹是实现协议的内容，包含具体的实现细节和工具函数等，比如 Mail(MailPtc)
from __future__ import annotations

from typing import Any, TypeVar, Generic
from pydantic import BaseModel, Field, field_validator
from enum import Enum

# Type aliases for UIDs
type EntityUid = str
type HostUid = str
type SessionId = str

# Generic type variables
SenderT = TypeVar("SenderT")
RecipientT = TypeVar("RecipientT")
MessageT = TypeVar("MessageT")
SignatureT = TypeVar("SignatureT")
MessageKindT = TypeVar("MessageKindT", bound=str)


class FPAddress(BaseModel):
    """FP address in format 'HostUid:EntityUid'.

    - Host address: 'HostUid:0'
    - Entity address: 'HostUid:EntityUid'
    """

    address: str = Field(
        ..., description="FP address (HostUid:EntityUid or HostUid:0 for host)"
    )

    @field_validator("address")
    @classmethod
    def validate_address_format(cls, v: str) -> str:
        """Validate address format is 'HostUid:EntityUid'."""
        if not isinstance(v, str):
            raise ValueError("Address must be a string")

        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("Address must be in format 'HostUid:EntityUid'")

        host_uid, entity_uid = parts
        if not host_uid or not entity_uid:
            raise ValueError("Both HostUid and EntityUid must be non-empty")

        return v

    @classmethod
    def is_valid(cls, value: Any) -> bool:
        """Check if a value is a valid FPAddress."""
        try:
            if isinstance(value, FPAddress):
                return True
            if isinstance(value, str):
                cls(address=value)
                return True
            return False
        except Exception:
            return False

    @classmethod
    def create(cls, host_uid: HostUid | None = None) -> FPAddress:
        """创建 FPAddress

        - 如果传入 host_uid: 生成 "host_uid:uuid" (Entity 地址)
        - 如果为空: 生成 "uuid:0" (Host 地址)

        TODO: FPAddress 生成逻辑待优化
        """
        from uuid import uuid4

        if host_uid:
            # 生成 Entity 地址
            entity_uid = uuid4().hex[:8]
            return cls(address=f"{host_uid}:{entity_uid}")
        else:
            # 生成 Host 地址
            new_host_uid = uuid4().hex[:8]
            return cls(address=f"{new_host_uid}:0")

    @property
    def is_host_address(self) -> bool:
        """Check if this address points to a Host (entity_uid is '0')."""
        _, entity_uid = self.address.split(":")
        return entity_uid == "0"

    @property
    def is_entity_address(self) -> bool:
        """Check if this address points to an Entity (entity_uid is not '0')."""
        return not self.is_host_address

    @property
    def host_uid(self) -> HostUid:
        """获取 host_uid 部分"""
        return self.address.split(":")[0]

    @property
    def entity_uid(self) -> EntityUid:
        """获取 entity_uid 部分"""
        return self.address.split(":")[1]

    def parts(self) -> tuple[HostUid, EntityUid]:
        """返回 (host_uid, entity_uid) 元组"""
        parts = self.address.split(":")
        return parts[0], parts[1]

    def __str__(self) -> str:
        return self.address


class MailStatus(str, Enum):
    """Mail lifecycle status.

    Sender perspective flow:
    - Agent: SENT → DELIVERING → RECEIVED → PROCESSING → DONE
    - Human: SENT → DELIVERING → RECEIVED → DONE (skip PROCESSING)

    Exception branches:
    - SENT → DELIVERING → QUEUED (recipient offline, awaiting retry)
    - SENT → DELIVERING → FAILED (recipient entity not found)

    Detailed states:
    - SENT: Mail sent from entity
    - DELIVERING: Host routing in progress
    - QUEUED: Target host WebSocket disconnected, queued for retry
    - FAILED: Delivery failed (entity not found or network unavailable)
    - RECEIVED: Entered recipient mailbox
    - PROCESSING: Being processed by handler (Agent only)
    - DONE: Processing completed
    """

    SENT = "sent"
    DELIVERING = "delivering"
    QUEUED = "queued"
    FAILED = "failed"
    RECEIVED = "received"
    PROCESSING = "processing"
    DONE = "done"


class MailBase(BaseModel, Generic[SenderT, RecipientT, MessageT, SignatureT]):
    """Generic mail base for host-to-host communication.

    The mail pattern separates transport concerns (routing, security)
    from application concerns (message content).

    Protocol version is tracked via 'fp' field for backward compatibility.

    Envelope provides a generic wrapper for routing and security:
    - mail_id: unique identifier for this mail envelope (for deduplication)
    - sender/recipient: routing information (generic types)
    - message: actual content (generic type)
    - signature: cryptographic signature (generic type)
    - status: current lifecycle status (MailStatus)
    - fp: protocol version for backward compatibility
    """

    mail_id: str = Field(default_factory=lambda: __import__('uuid').uuid4().hex, description="Unique mail envelope ID")
    sender: SenderT = Field(..., description="Sender address")
    recipient: RecipientT = Field(
        ..., description="Recipient address or list of recipients"
    )
    message: MessageT = Field(..., description="Actual message content")
    signature: SignatureT = Field(..., description="Cryptographic signature")
    status: MailStatus = Field(default=MailStatus.SENT, description="Mail lifecycle status")
    fp: str = Field(default="0.1", description="FP protocol version")


class EntityKind(str, Enum):
    """Entity type categories."""

    HOST = "host"
    HUMAN = "human"
    AGENT = "agent"
    TOOL = "tool"
    RESOURCE = "resource"
    SERVICE = "service"
    ARBITER = "arbiter"
    ORGANIZATION = "organization"


class EntityStatus(str, Enum):
    """Entity online status."""

    ONLINE = "online"
    OFFLINE = "offline"
    DELETED = "deleted"
