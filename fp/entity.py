"""Entity models and utilities."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, TypeVar

from loguru import logger
from pydantic import BaseModel, Field

from .core import EntityKind, EntityUid, MailStatus, SessionId
from .core.checkpoint import CheckPoint, CheckPointResult
from .core.session import Session
from .core.wellknown import EntityCard, FPAddress
from .mail import Mail
from .mailbox import Mailbox
from .message import ErrorPayload, Message, MessageKind

if TYPE_CHECKING:
    from .host import Host

EntityName = str
Description = str
_T = TypeVar("_T")

FRIENDSHIP_REQUIRED_KINDS = (
    {MessageKind.INVOKE, MessageKind.HEARTBEAT}
    | {k for k in MessageKind if k.value.startswith("contract_")}
    | {k for k in MessageKind if k.value.startswith("pay_")}
)


class FriendshipRequiredError(ValueError):
    """Raised when sending a business message to a non-friend entity."""

    def __init__(self, sender_name: str, recipient_id: str, message_kind: str) -> None:
        self.sender_name = sender_name
        self.recipient_id = recipient_id
        self.message_kind = message_kind
        super().__init__(
            f"[{sender_name}] 无法发送 {message_kind} 给 {recipient_id}：对方不是好友。"
            f"请先运行 aln friend request -e {sender_name} --to {recipient_id}"
        )


class PendingApproval(BaseModel):
    """Stored context for a pending owner approval (deferred after timeout)."""

    request_id: str
    original_kind: str
    original_payload: dict[str, Any]
    original_sender_address: str
    original_mail_id: str
    original_preview: str | None = None
    created_at: float
    checkpoint_name: str


def _serialize_payload(payload: Any) -> dict[str, Any] | None:
    """Serialize a message payload to dict for CC forwarding."""
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return payload
    return None


class Entity(BaseModel):
    """Complete entity configuration.

    Represents a full entity with all configuration, identity, and relationship data.
    """

    name: EntityName
    kind: EntityKind | str
    address: FPAddress = Field(frozen=True)
    sign_public_key: str
    sign_private_key: str
    encrypt_public_key: str
    decrypt_private_key: str
    description: Description = ""
    mailbox_path: str

    host: Host = Field(exclude=True)
    friends: dict[EntityUid, EntityCard] = Field(default_factory=dict)
    sessions: dict[SessionId, Session] = Field(default_factory=dict)
    checkpoints: list[CheckPoint] = Field(
        default_factory=list, description="Message processing pipeline (ordered by checkpoint.order)"
    )
    pending_approvals: dict[str, PendingApproval] = Field(
        default_factory=dict, description="Pending owner approvals keyed by request_id"
    )

    metadata: dict[str, Any] = Field(default_factory=dict)
    visible: bool = True
    enabled: bool = True
    is_public: bool = False
    owner: FPAddress | None = Field(default=None, description="Owner entity to receive carbon copies")
    arbiter: FPAddress | None = Field(default=None, description="Arbiter entity for contract management")
    on_status_update: Callable[[str, dict[str, str]], Awaitable[None]] | None = Field(
        default=None, exclude=True, description="Callback: (entity_uid, status_data) -> None"
    )

    class Config:
        arbitrary_types_allowed = True
        use_enum_values = True

    @property
    def uid(self) -> EntityUid:
        """Get entity_uid from address"""
        return self.address.entity_uid

    def add_checkpoint(self, checkpoint: CheckPoint) -> None:
        """Add checkpoint and maintain order-sorted list."""
        self.checkpoints.append(checkpoint)
        self.checkpoints.sort(key=lambda cp: cp.order)

    def get_checkpoint(self, checkpoint_type: type[_T]) -> _T | None:
        """Get first checkpoint matching the given type."""
        for cp in self.checkpoints:
            if isinstance(cp, checkpoint_type):
                return cp
        return None

    async def notify_handler(self, message: Message) -> None:
        """Directly invoke the handler bridge checkpoint with a message."""
        from .core.checkpoint import HandlerBridgeCheckPoint

        bridge = self.get_checkpoint(HandlerBridgeCheckPoint)
        if bridge is not None:
            await bridge.handler.handle(message)
        else:
            logger.debug(f"[{self.name}] No handler bridge, skip notify")

    @property
    def entity_card(self) -> EntityCard:
        """Convert to EntityCard for public display."""
        return EntityCard(
            name=self.name,
            address=self.address,
            kind=self.kind.value if isinstance(self.kind, EntityKind) else self.kind,
            sign_public_key=self.sign_public_key,
            encrypt_public_key=self.encrypt_public_key,
            description=self.description,
            is_public=self.is_public,
            entity_uid=self.uid,
            host_uid=self.host.uid,
            metadata=self.metadata,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Entity:
        """Create Entity from dict."""
        payload = data.copy()
        kind_value = payload.get("kind", "agent")
        payload["kind"] = (
            EntityKind(kind_value) if isinstance(kind_value, str) else kind_value
        )

        # Backward compatibility for old field names.
        payload.setdefault("sign_public_key", payload.get("public_key", ""))
        payload.setdefault("sign_private_key", payload.get("private_key_path", ""))
        payload.setdefault("encrypt_public_key", payload.get("public_key", ""))
        payload.setdefault("decrypt_private_key", payload.get("private_key_path", ""))

        return cls.model_validate(payload)

    def to_dict(self) -> dict[str, Any]:
        """Convert Entity to dict for serialization."""
        return self.model_dump(exclude={"sessions", "handler", "host"}, mode="json")

    def save(self) -> None:
        """保存entity状态到存储"""
        from .utils.storage import EntityKeyInfo, EntityKeys, EntityMeta, FriendEntry, get_storage_manager

        storage = get_storage_manager()

        # 1. 保存entity meta（不含私钥）
        meta = EntityMeta(
            uid=self.uid,
            name=self.name,
            kind=self.kind if isinstance(self.kind, str) else self.kind.value,
            host_uid=self.host.uid,
            address=self.address.address,
            keys=EntityKeyInfo(
                sign_public_key=self.sign_public_key,
                encrypt_public_key=self.encrypt_public_key,
                key_file=f"keys/entities/{self.uid}.key",
            ),
            mailbox_path=self.mailbox_path,
            description=self.description,
            is_public=self.is_public,
            visible=self.visible,
            enabled=self.enabled,
            owner=self.owner.address if self.owner else None,
            arbiter=self.arbiter.address if self.arbiter else None,
            metadata=self.metadata,
        )
        storage.save_entity_meta(meta)

        # 2. 保存私钥（单独文件，权限600）
        keys = EntityKeys(
            uid=self.uid,
            sign_private_key=self.sign_private_key,
            decrypt_private_key=self.decrypt_private_key,
        )
        storage.save_entity_keys(keys)

        # 3. 保存friends列表
        friends_list = [
            FriendEntry(
                entity_uid=card.entity_uid,
                name=card.name,
                address=card.address.address,
                kind=card.kind,
                host_uid=card.host_uid,
                sign_public_key=card.sign_public_key,
                encrypt_public_key=card.encrypt_public_key,
                description=card.description,
                is_public=card.is_public,
                metadata=card.metadata,
            )
            for card in self.friends.values()
        ]
        storage.save_entity_friends(self.uid, friends_list)

        # 4. 保存sessions（允许写空，确保删除最后一个 session 时持久化同步）
        sessions_dict = {
            sid: session.model_dump() for sid, session in self.sessions.items()
        }
        storage.save_entity_sessions(self.uid, sessions_dict)

        # 5. 保存pending_approvals
        pa_data = {k: v.model_dump(mode="json") for k, v in self.pending_approvals.items()}
        storage.save_entity_pending_approvals(self.uid, pa_data)

        logger.debug(f"Entity {self.name} ({self.uid}) saved to storage")

    @classmethod
    def load(cls, entity_uid: str, host: Host) -> Entity:
        """从存储加载entity"""
        from .utils.storage import get_storage_manager

        storage = get_storage_manager()

        # 1. 加载entity meta
        meta = storage.load_entity_meta(entity_uid)
        if not meta:
            raise ValueError(f"Entity {entity_uid} not found in storage")

        # 2. 加载私钥
        keys = storage.load_entity_keys(entity_uid)
        if not keys:
            raise ValueError(f"Keys for entity {entity_uid} not found")

        # 3. 创建Entity对象
        entity = cls(
            name=meta.name,
            kind=meta.kind,
            address=FPAddress(address=meta.address),
            sign_public_key=meta.keys.sign_public_key,
            sign_private_key=keys.sign_private_key,
            encrypt_public_key=meta.keys.encrypt_public_key,
            decrypt_private_key=keys.decrypt_private_key,
            description=meta.description,
            mailbox_path=meta.mailbox_path,
            host=host,
            visible=meta.visible,
            enabled=meta.enabled,
            is_public=meta.is_public,
            owner=FPAddress(address=meta.owner) if meta.owner else None,
            arbiter=FPAddress(address=meta.arbiter) if meta.arbiter else None,
            metadata=meta.metadata,
        )

        # 4. 加载friends
        friends_list = storage.load_entity_friends(entity_uid)
        for friend_entry in friends_list:
            friend_card = EntityCard(
                name=friend_entry.name,
                address=FPAddress(address=friend_entry.address),
                kind=friend_entry.kind,
                sign_public_key=friend_entry.sign_public_key,
                encrypt_public_key=friend_entry.encrypt_public_key,
                description=friend_entry.description,
                is_public=friend_entry.is_public,
                entity_uid=friend_entry.entity_uid,
                host_uid=friend_entry.host_uid,
                metadata=friend_entry.metadata,
            )
            entity.friends[friend_card.entity_uid] = friend_card

        # 5. 加载sessions（可选）
        sessions_dict = storage.load_entity_sessions(entity_uid)
        for sid, session_data in sessions_dict.items():
            entity.sessions[sid] = Session(**session_data)

        # 6. 加载pending_approvals
        pa_data = storage.load_entity_pending_approvals(entity_uid)
        for req_id, pa_dict in pa_data.items():
            entity.pending_approvals[req_id] = PendingApproval(**pa_dict)

        logger.debug(f"Entity {entity.name} ({entity.uid}) loaded from storage")
        return entity

    def add_friend(self, card: EntityCard) -> None:
        """Add friend"""
        self.friends[card.entity_uid] = card
        logger.debug(f"[{self.uid}] Added friend: {card.entity_uid}")

    def remove_friend(self, entity_uid: EntityUid) -> None:
        """Remove friend"""
        if entity_uid in self.friends:
            del self.friends[entity_uid]
            logger.debug(f"[{self.uid}] Removed friend: {entity_uid}")

    def resolve_name(self, address: str) -> str | None:
        """Resolve entity display name from address (friends → host entities → self)."""
        entity_uid = address.split(":")[-1] if ":" in address else address
        if entity_uid in self.friends:
            return self.friends[entity_uid].name
        if entity_uid in self.host.entities:
            return self.host.entities[entity_uid].name
        if entity_uid == self.uid:
            return self.name
        return None

    def _get_friend_by_name(self, name: str) -> EntityCard | None:
        """Get friend's EntityCard by name"""
        for card in self.friends.values():
            if card.name == name:
                return card
        return None

    def _get_friend_by_uid(self, entity_uid: EntityUid) -> EntityCard | None:
        """Get friend's EntityCard by entity_uid"""
        return self.friends.get(entity_uid)

    def _normalize_address(
        self, to: FPAddress | EntityUid | EntityName | EntityCard
    ) -> tuple[FPAddress, EntityCard | None]:
        """Normalize various address formats to FPAddress and optional EntityCard.

        Returns the card only if it's in friends,
        otherwise returns None for public message.
        """
        if isinstance(to, EntityCard):
            # Check if this entity is in friends
            friend_card = self.friends.get(to.entity_uid)
            return to.address, friend_card

        if isinstance(to, FPAddress):
            card = self.friends.get(to.entity_uid)
            return to, card

        if isinstance(to, str):
            card = self.friends.get(to) or self._get_friend_by_name(to)
            if not card:
                raise ValueError(f"Friend not found: {to}")
            return card.address, card

        raise TypeError(f"Unsupported type for 'to': {type(to)}")

    def _get_encrypt_key(self, card: EntityCard | None) -> str:
        """Get encryption public key from EntityCard"""
        if not card:
            raise ValueError("Cannot get encrypt key: recipient card not found")
        return card.encrypt_public_key

    async def call_owner(self, message: Message) -> Mail | None:
        """Forward a message to this entity's owner (as a new message from self)."""
        if self.owner is None:
            logger.warning(f"[{self.name}] call_owner: no owner configured, dropping {message.kind}")
            return None
        return await self.send_message(to=self.owner, message=message)

    async def send_message(
        self, to: FPAddress | EntityUid | EntityName | EntityCard, message: Message
    ) -> Mail:
        """Send message to specified entity"""
        recipient_address, recipient_card = self._normalize_address(to)

        if recipient_card is None and message.kind in FRIENDSHIP_REQUIRED_KINDS:
            raise FriendshipRequiredError(
                sender_name=self.name,
                recipient_id=recipient_address.entity_uid,
                message_kind=message.kind.value,
            )

        encrypt_public_key = (
            self._get_encrypt_key(recipient_card) if recipient_card else None
        )

        # Outbound mailbox: save sign-only version (readable by sender)
        outbound_mail = Mail.seal(
            sender=self.address,
            recipient=recipient_address,
            message=message,
            sign_private_key=self.sign_private_key,
            encrypt_public_key=None,
        )
        outbound_mail.status = MailStatus.SENT
        mailbox = Mailbox(self.uid, Path(self.mailbox_path))
        mailbox.save_outbound(outbound_mail)

        # Wire mail: encrypt if recipient is a friend
        if encrypt_public_key:
            wire_mail = Mail.seal(
                sender=self.address,
                recipient=recipient_address,
                message=message,
                sign_private_key=self.sign_private_key,
                encrypt_public_key=encrypt_public_key,
            )
        else:
            wire_mail = outbound_mail
        wire_mail.status = MailStatus.SENT

        logger.info(
            f"[{self.name}] 📤 发送邮件 [{wire_mail.status.value.upper()}] "
            f"→ {recipient_address.entity_uid} | mail_id={outbound_mail.mail_id}"
            f"{' [encrypted]' if encrypt_public_key else ''}"
        )

        await self.host.route_mail(wire_mail)

        # 出站消息抄送给 owner（避免 CarbonCopy 循环，且发给 owner 的消息不抄送）
        if (
            self.owner
            and message.kind != MessageKind.CARBON_COPY
            and not message.metadata.get("_skip_cc")
            and recipient_address.address != self.owner.address
        ):
            await self._send_carbon_copy_to_owner(
                sender_address=self.address.address,
                recipient_address=recipient_address.address,
                recipient_name=recipient_card.name if recipient_card else None,
                message=message,
                direction="outbound",
            )

        return outbound_mail

    async def _send_carbon_copy_to_owner(
        self,
        sender_address: str,
        recipient_address: str,
        recipient_name: str | None,
        message: Message,
        direction: str,
    ) -> None:
        """发送 CarbonCopy 给 owner。"""
        from datetime import datetime

        from .message import CarbonCopyPayload

        # Extract summary from payload
        text = message.extract_text()
        summary = (text[:100] + "...") if len(text) > 100 else text if text else None

        # Serialize original payload for full forwarding
        original_payload = _serialize_payload(message.payload)

        cc_payload = CarbonCopyPayload(
            original_sender=sender_address,
            original_sender_name=self.name,
            original_recipient=recipient_address,
            original_recipient_name=recipient_name,
            original_kind=message.kind.value if isinstance(message.kind, MessageKind) else str(message.kind),
            original_message_id=message.message_id,
            direction=direction,
            timestamp=datetime.utcnow().isoformat(),
            summary=summary,
            original_payload=original_payload,
        )

        cc_message = Message(
            kind=MessageKind.CARBON_COPY,
            payload=cc_payload,
            metadata={"forwarded_from": self.uid},
        )

        try:
            await self.send_message(to=self.owner, message=cc_message)
            logger.debug(f"[{self.name}] 📤 CarbonCopy (outbound) sent to owner {self.owner.entity_uid}")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to send CarbonCopy to owner: {e}")

    async def _send_status_update(self, mail_id: str, sender_address: str, new_status: MailStatus) -> None:
        """Send mail status update back to sender via callback."""
        if not self.on_status_update:
            return
        try:
            status_data = {
                "mail_id": mail_id,
                "status": new_status.value,
                "timestamp": datetime.utcnow().isoformat(),
            }
            sender_entity_uid = sender_address.split(":")[-1] if ":" in sender_address else sender_address
            await self.on_status_update(sender_entity_uid, status_data)
            logger.debug(f"[{self.name}] 通知状态更新 [{new_status.value.upper()}] → {sender_entity_uid}")
        except Exception as e:
            logger.warning(f"[{self.name}] 状态更新失败: {e}")

    async def _send_error(
        self,
        recipient: FPAddress,
        error_code: str,
        error_message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Send error message to recipient"""
        # Try to find friend card for encrypted error message
        friend_card = self._get_friend_by_uid(recipient.entity_uid)
        if friend_card is None:
            # Cannot send error to non-friend, just log it
            logger.warning(
                f"[{self.uid}] Cannot send error to non-friend {recipient}: "
                f"{error_code} - {error_message}"
            )
            return

        error_payload = ErrorPayload(
            error_code=error_code, error_message=error_message, details=details
        )
        error_msg = Message(kind=MessageKind.ERROR, payload=error_payload)
        await self.send_message(friend_card, error_msg)
        logger.debug(f"[{self.uid}] Sent error message to {recipient}: {error_code}")

    async def _points_checking(
        self, message: Message, mail: Mail
    ) -> tuple[bool, bool, str | None, str | None]:
        """Execute checkpoint validation for the message."""
        # Add sender info to metadata
        message.metadata["sender_uid"] = mail.sender.entity_uid
        message.metadata["sender_address"] = str(mail.sender)

        for checkpoint in sorted(self.checkpoints, key=lambda cp: cp.order):
            if message.kind in checkpoint.message_kinds:
                result: CheckPointResult = await checkpoint.execute(message, self, mail)

                if result.handled:
                    # Message was handled by checkpoint, stop processing
                    return (True, True, None, None)

                if not result.passed:
                    logger.warning(
                        f"[{self.uid}] Checkpoint '{checkpoint.name}' failed "
                        f"for message {message.message_id}: {result.error_code}"
                    )
                    return (False, False, result.error_code, result.error_message)

        return (True, False, None, None)

    async def receive_mail(self, mail: Mail) -> None:
        """接收并处理邮件。流程：unseal → mailbox → checkpoints pipeline"""
        mail_id = mail.mail_id if hasattr(mail, 'mail_id') else ""
        sender_address = mail.sender.address if hasattr(mail.sender, 'address') else str(mail.sender)
        sender_uid = mail.sender.entity_uid

        logger.info(
            f"[{self.name}] 📬 收到邮件 ← {sender_uid} | mail_id={mail_id}"
        )

        # 1. Unseal: verify signature + decrypt if encrypted
        friend_card = self._get_friend_by_uid(mail.sender.entity_uid)
        verify_key = friend_card.sign_public_key if friend_card else None
        if verify_key is None and mail.sender.address == self.address.address:
            verify_key = self.sign_public_key
        unsealed_mail = mail.unseal(
            verify_public_key=verify_key,
            decrypt_private_key=self.decrypt_private_key,
        )

        if unsealed_mail is None:
            await self._send_error(
                mail.sender,
                error_code="UNSEAL_FAILED",
                error_message="Failed to unseal mail (verification or decryption failed)",
                details={"sender_entity_uid": mail.sender.entity_uid},
            )
            return

        # 2. 存入 mailbox（存解密后的明文）
        unsealed_mail.status = MailStatus.RECEIVED
        mailbox = Mailbox(self.uid, Path(self.mailbox_path))
        mailbox.save_inbound(unsealed_mail)

        # 3. 通知发送方已收到
        if mail_id:
            await self._send_status_update(mail_id, sender_address, MailStatus.RECEIVED)

        # 4. 执行 checkpoint pipeline（校验 + 执行，统一管道）
        message = unsealed_mail.message
        message.metadata["sender_address"] = sender_address
        message.metadata["mail_id"] = mail_id

        passed, handled, error_code, error_message = await self._points_checking(
            message, unsealed_mail
        )
        if not passed:
            await self._send_error(
                mail.sender,
                error_code=error_code or "CHECKPOINT_FAILED",
                error_message=error_message or "Message failed checkpoint validation",
                details={"message_id": message.message_id},
            )
            return

        # 5. 标记 DONE
        unsealed_mail.status = MailStatus.DONE
        if mail_id:
            mailbox.mark_as_handled_by_mail_id(mail_id)
            await self._send_status_update(mail_id, sender_address, MailStatus.DONE)
