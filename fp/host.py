"""Host config read/write helpers shared by CLI and server."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from loguru import logger
from pydantic import BaseModel, Field

from .core.base import EntityKind, EntityUid, HostUid
from .core.checkpoint import (
    ApprovalResponseCheckPoint,
    CallbackCheckPoint,
    CarbonCopyCheckpoint,
    FriendCheckPoint,
    FriendRequestCheckPoint,
    HandlerBridgeCheckPoint,
)
from .core.wellknown import EntityCard, FPAddress, HostWellKnown
from .entity import Entity
from .handler import BaseHandler, HandlerConfig
from .mail import Mail
from .message import Message, MessageKind
from .trade.arbiter_checkpoint import ArbiterCheckPoint, _CONTRACT_PAY_KINDS
from .trade.checkpoints import (
    ContractApprovalCheckPoint,
    PayClaimCheckPoint,
    PayCollectInboundCheckPoint,
    PayConfirmReceiptCheckPoint,
)
from .utils.common import default_mailbox_path, generate_entity_key_material


class Host(BaseModel):
    """Host configuration with data and business logic.

    A Pydantic model representing a host's configuration and identity.
    All child hosts and entities are strongly typed.
    """

    name: str
    address: FPAddress | None = Field(default=None, frozen=True)
    pid: int | None = None
    bind_host: str = "0.0.0.0"
    advertise_host: str | None = None  # 对外宣告地址，用于其他 Host 连接此 Host
    port: int = 7001

    parent_host: Host | None = None
    child_hosts: dict[HostUid, Host] = Field(default_factory=dict)
    known_public_entities: list[EntityCard] = Field(default_factory=list)
    entities: dict[EntityUid, Entity] = Field(default_factory=dict)
    class Config:
        arbitrary_types_allowed = True

    @property
    def uid(self) -> HostUid:
        return self.address.host_uid

    @property
    def url(self) -> str:
        """HTTP URL for other hosts to connect."""
        host = self.advertise_host or self._infer_advertise_host()
        return f"http://{host}:{self.port}"

    def _infer_advertise_host(self) -> str:
        """推断对外地址"""
        if self.bind_host == "0.0.0.0":
            return "127.0.0.1"
        return self.bind_host

    def model_post_init(self, __context: Any) -> None:
        """自动生成 address"""
        # TODO: FPAddress 生成逻辑待优化
        if self.address is None:
            address = FPAddress.create()  # 生成 "uuid:0"
            object.__setattr__(self, "address", address)

    def _default_mailbox_path(self, entity_uid: EntityUid) -> str:
        """Return the default mailbox path for one local entity."""
        return default_mailbox_path(entity_uid, self.uid)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Host:
        """Create Host from dict with proper type conversion."""
        data = data.copy()

        # Parse parent_host (可以为 None)
        parent_raw = data.get("parent_host")
        if isinstance(parent_raw, dict):
            data["parent_host"] = Host.from_dict(parent_raw)

        # Parse child_hosts (可以为空 dict)
        children_raw = data.get("child_hosts")
        if isinstance(children_raw, dict):
            data["child_hosts"] = {
                uid: Host.from_dict(child_data)
                if isinstance(child_data, dict)
                else child_data
                for uid, child_data in children_raw.items()
            }

        # Parse entities (可以为空 dict)
        entities_raw = data.get("entities")
        if isinstance(entities_raw, dict):
            data["entities"] = {
                entity_uid: Entity.from_dict(entity_data)
                if isinstance(entity_data, dict)
                else entity_data
                for entity_uid, entity_data in entities_raw.items()
            }

        return cls.model_validate(data)

    @classmethod
    def from_wellknown(cls, wellknown: HostWellKnown) -> Host:
        """从 HostWellKnown 创建一个轻量级的 Host 代理对象"""
        parsed = urlparse(wellknown.url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 7001

        return cls(
            name=wellknown.name,
            address=FPAddress(address=f"{wellknown.uid}:0"),
            bind_host=host,
            advertise_host=host,
            port=port,
            entities={},
            child_hosts={},
            known_public_entities=list(wellknown.public_entities),
        )

    # NOTE:【功能边界】FP文件夹里面不提供持久化的功能,只提供反序列化的逻辑，持久化逻辑在应用层去做
    def to_dict(self) -> dict[str, Any]:
        """Convert Host to dict for serialization."""
        return self.model_dump(exclude_none=True, mode="json")

    # NOTE:核心方法：用来发现所有此 host 可通讯的 pubilc entities
    @staticmethod
    def _deduplicate_entity_cards(entity_cards: list[EntityCard]) -> list[EntityCard]:
        """Deduplicate entity cards by address while keeping latest entry."""
        deduplicated: dict[str, EntityCard] = {}
        for card in entity_cards:
            deduplicated[card.address.address] = card
        return list(deduplicated.values())

    def _collect_self_public_entities(self) -> list[EntityCard]:
        """Collect this host public entities from runtime or cached wellknown."""
        if self.entities:
            return [entity.entity_card for entity in self.entities.values() if entity.is_public]
        return list(self.known_public_entities)

    def get_discoverable_entities(self, include_parent: bool = False) -> list[EntityCard]:
        """Get all public entities accessible from this host.

        Includes:
        - This host's public entities
        - All children hosts' public entities
        - Parent host's public entities (when include_parent=True)
        """
        public_entities: list[EntityCard] = self._collect_self_public_entities()

        #TODO:这里要在 HostSever 重写
        # child 的 entity 要本地保存，而不是每次都从 child_host 里获取， child 太多了，请求太多了。
        # parent 的 entity 可以请求一次，Parent 的 child 的 entity 也是 Parent 的服务器存着呢。
        for child in self.child_hosts.values():
            public_entities.extend(child.get_discoverable_entities(include_parent=False))

        if include_parent and self.parent_host:
            public_entities.extend(
                self.parent_host.get_discoverable_entities(include_parent=False)
            )

        return self._deduplicate_entity_cards(public_entities)

    @property
    def ws_url(self) -> str:
        """WebSocket URL."""
        return f"ws://{self.bind_host}:{self.port}"

    def get_wellknown(self) -> HostWellKnown:
        """Build .well-known payload from current host state.

        Note: Only includes entities on THIS host, not children or parent.
        """
        return HostWellKnown(
            name=self.name,
            uid=self.uid,
            url=self.url,
            public_entities=self._collect_self_public_entities(),
        )

    def get_entity(self, entity_uid: EntityUid) -> Entity | None:
        """Get entity by ID."""
        return self.entities.get(entity_uid)

    def get_entity_by_id(self, entity_uid: EntityUid) -> Entity | None:
        """Get entity by ID."""
        return self.entities.get(entity_uid)

    def get_host_by_uid(self, host_uid: HostUid) -> Host | HostWellKnown | None:
        """Get host by uid from parent or children."""
        # Check parent
        if self.parent_host and self.parent_host.uid == host_uid:
            return self.parent_host

        # Check children
        return self.child_hosts.get(host_uid)

    def get_host_by_address(self, address: FPAddress) -> Host | Entity | None:
        """Get Host or Entity on Host(Self) by FPAddress."""
        host_uid, entity_uid = address.address.split(":")

        # Find target host
        if host_uid == self.uid:
            target_host = self
        elif self.parent_host and self.parent_host.uid == host_uid:
            target_host = self.parent_host
        else:
            target_host = self.child_hosts.get(host_uid)

        if not target_host:
            return None

        # Return Host or Entity based on address type
        return (
            target_host
            if address.is_host_address
            else target_host.entities.get(entity_uid)
        )

    # [CORE]建立 parent-child 关系
    def set_parent_host(self, host: Host | HostWellKnown) -> None:
        """Set parent host."""
        if isinstance(host, HostWellKnown):
            host = Host.from_wellknown(host)

        self.set_host(host, is_parent=True)
        # NOTE: 通知父 host 将自己添加为 child
        # NOTE: server上 parent-host 在接收到set_parent请求后会自动执行↓↓↓
        # 所以这里设置为内部函数，但是手动执行一下，
        # Pass：HostServer 要重写覆盖这个函数
        host._set_child_host(self)

        # 如果父 Host 有 Arbiter，传播给自己的所有 entity
        parent_arbiter = host.get_arbiter()
        if parent_arbiter:
            self._propagate_arbiter(parent_arbiter.address)

    def _set_child_host(self, host: Host | HostWellKnown) -> None:
        """内部方法：添加 child host"""
        # 如果是 HostWellKnown，转换为 Host
        if isinstance(host, HostWellKnown):
            host = Host.from_wellknown(host)

        self.set_host(host, is_parent=False)

    def delete_host_by_uid(self, host_uid: HostUid) -> bool:
        # NOTE:非核心方法只写一行 docstring 就行
        """Delete host by uid from parent or children."""
        # Check and delete parent
        if self.parent_host and self.parent_host.uid == host_uid:
            logger.info(f"Deleting parent host {host_uid}")
            self.parent_host = None
            self.save()
            return True

        # Check and delete from children
        if host_uid in self.child_hosts:
            logger.info(f"Deleting child host {host_uid}")
            del self.child_hosts[host_uid]
            self.save()
            return True

        return False

    # 只接受 Host 类型的 host 参数，HostWellKnown 只能通过 from_wellknown 转换
    def set_host(self, host: Host, is_parent: bool) -> None:
        """Set parent or child host."""
        host_uid = host.uid
        relation = "parent" if is_parent else "child"

        if host_uid == self.uid:
            raise ValueError(
                f"Cannot set self host uid={host_uid} as {relation} host"
            )

        existing_host = self.get_host_by_uid(host_uid)

        if is_parent:
            # Parent 允许覆盖更新
            if existing_host:
                logger.info(f"Parent host {host_uid} already exists, deleting first")
                self.delete_host_by_uid(host_uid)
            logger.info(f"Adding new parent {host_uid}")
            self.parent_host = host
            self.save()
        else:
            # Child 如果已存在，只更新信息，不删除（避免关闭 WebSocket）
            if existing_host:
                logger.info(f"Child host {host_uid} already exists, updating info only")
                self.child_hosts[host_uid] = host
                self.save()
            else:
                logger.info(f"Adding new child {host_uid}")
                self.child_hosts[host_uid] = host
                self.save()

    # NOTE：核心方法，Host 的核心功能为路由 Mail
    async def route_mail(self, mail: Mail) -> None:
        """Route incoming mail based on recipient addresses."""
        mail_id = mail.mail_id if hasattr(mail, 'mail_id') else ""

        # Update status to DELIVERING when host starts routing
        from .core import MailStatus
        mail.status = MailStatus.DELIVERING

        # Extract recipient entity UIDs for logging
        recipient_uids = [r.entity_uid for r in mail.recipient]
        logger.info(
            f"[Host {self.name}] 🔀 路由中 [{mail.status.value.upper()}] "
            f"→ {', '.join(recipient_uids)} | mail_id={mail_id}"
        )

        # Group recipients by host_uid
        recipients_by_host: dict[HostUid, list[EntityUid]] = defaultdict(list)
        for recipient in mail.recipient:
            host_uid, entity_uid = recipient.address.split(":")
            recipients_by_host[host_uid].append(entity_uid)

        parent_recipients: list[FPAddress] = []

        for host_uid, entity_uids in recipients_by_host.items():
            # Check if recipient is a child
            if host_uid in self.child_hosts:
                logger.debug(f"[Host {self.name}] 转发至子 Host {host_uid}")
                # Create mail copy for this child with only their recipients
                child_recipients = [
                    FPAddress(address=f"{host_uid}:{eid}") for eid in entity_uids
                ]
                child_mail = mail.model_copy(update={"recipient": child_recipients})
                await self._forward_to_child(host_uid, child_mail)
                continue

            # Check if recipient is on this host
            if host_uid == self.uid:
                for entity_uid in entity_uids:
                    entity = self.entities.get(entity_uid)
                    if entity:
                        # Create mail copy with single recipient for this entity
                        entity_mail = mail.model_copy(
                            update={
                                "recipient": [
                                    FPAddress(address=f"{host_uid}:{entity_uid}")
                                ]
                            }
                        )
                        task = asyncio.create_task(entity.receive_mail(entity_mail))
                        task.add_done_callback(
                            lambda t, eid=entity_uid: t.exception() and logger.error(
                                f"[Host {self.name}] receive_mail failed for {eid}: {t.exception()}"
                            )
                        )
                    else:
                        # Entity not found: mark as FAILED
                        logger.warning(f"[Host {self.name}] ❌ 实体不存在: {entity_uid}")
                        failed_mail = mail.model_copy(update={"status": MailStatus.FAILED})  # noqa: F841
                        # TODO: Notify sender about FAILED status
                        # await self._notify_sender_status(failed_mail, MailStatus.FAILED)
                continue

            # Collect recipients for parent forwarding
            logger.debug(f"[Host {self.name}] 收集转发至父 Host: {host_uid}")
            for entity_uid in entity_uids:
                parent_recipients.append(FPAddress(address=f"{host_uid}:{entity_uid}"))

        # Forward to parent once with all parent-bound recipients
        if parent_recipients:
            if self.parent_host:
                parent_mail = mail.model_copy(update={"recipient": parent_recipients})
                # TODO: Check if parent WebSocket is connected, if not set status to QUEUED
                await self._forward_to_parent(parent_mail)
            else:
                # No parent configured: mark as FAILED
                logger.warning(
                    f"[Host {self.name}] ❌ 无父 Host 配置，路由失败"
                )
                failed_mail = mail.model_copy(update={"status": MailStatus.FAILED})  # noqa: F841
                # TODO: Notify sender about FAILED status
                # await self._notify_sender_status(failed_mail, MailStatus.FAILED)

    async def _forward_to_child(self, child_uid: HostUid, mail: Mail) -> None:
        """Forward mail to a child host."""
        child_host = self.child_hosts[child_uid]
        if not isinstance(child_host, Host):
            logger.error(
                f"Child host {child_uid} is HostWellKnown, cannot route mail directly"
            )
            return
        await child_host.route_mail(mail)

    async def _forward_to_parent(self, mail: Mail) -> None:
        """Forward mail to parent host."""
        if not isinstance(self.parent_host, Host):
            logger.error("Parent host is HostWellKnown, cannot route mail directly")
            return
        await self.parent_host.route_mail(mail)

    async def push_to_web(self, entity_uid: EntityUid, message: Message) -> None:
        """Push message to web UI via WebSocket.

        Base implementation does nothing. HostServer overrides this to actually push.
        """
        pass

    def get_arbiter(self) -> Entity | None:
        """获取本 Host 上的 Arbiter entity。"""
        for entity in self.entities.values():
            if self._entity_kind_value(entity) == EntityKind.ARBITER.value:
                return entity
        return None

    @staticmethod
    def _entity_kind_value(entity: Entity) -> str:
        """Extract kind value string from entity."""
        return entity.kind.value if isinstance(entity.kind, EntityKind) else str(entity.kind).lower()

    def _propagate_arbiter(self, arbiter_address: FPAddress) -> None:
        """Set arbiter on all entities that don't already have one."""
        for entity in self.entities.values():
            if entity.arbiter is None and entity.address != arbiter_address:
                entity.arbiter = arbiter_address

    @staticmethod
    def _setup_default_checkpoints(entity: Entity) -> None:
        """Attach default checkpoints to a newly created entity."""
        entity.add_checkpoint(
            ApprovalResponseCheckPoint(
                name="approval_response_handler",
                order=150,
                message_kinds={MessageKind.APPROVAL_RESPONSE},
            )
        )
        entity.add_checkpoint(
            FriendRequestCheckPoint(
                name="friend_request_handler",
                order=210,
                message_kinds={
                    MessageKind.FRIEND_REQUEST,
                    MessageKind.FRIEND_ACCEPT,
                    MessageKind.FRIEND_REJECT,
                },
                call_owner_policy="always_call" if entity.owner else "always_pass",
            )
        )
        entity.add_checkpoint(
            FriendCheckPoint(
                name="friend_check",
                order=200,
                message_kinds={MessageKind.INVOKE},
            )
        )
        entity.add_checkpoint(
            ContractApprovalCheckPoint(
                name="contract_approval",
                order=400,
                message_kinds={
                    MessageKind.CONTRACT_STATUS,
                    MessageKind.CONTRACT_TIMEOUT,
                },
                call_owner_policy="always_call" if entity.owner else "always_pass",
            )
        )
        entity.add_checkpoint(
            PayCollectInboundCheckPoint(
                name="pay_collect_inbound_approval",
                order=420,
                message_kinds={MessageKind.PAY_COLLECT},
                call_owner_policy="always_call" if entity.owner else "always_pass",
            )
        )
        entity.add_checkpoint(
            PayClaimCheckPoint(
                name="pay_claim_approval",
                order=450,
                message_kinds={MessageKind.PAY_CLAIM_COMPLETED},
                call_owner_policy="always_call" if entity.owner else "always_pass",
            )
        )
        entity.add_checkpoint(
            PayConfirmReceiptCheckPoint(
                name="pay_confirm_receipt_approval",
                order=460,
                message_kinds={MessageKind.PAY_CONFIRM_RECEIPT},
                call_owner_policy="always_call" if entity.owner else "always_pass",
            )
        )
        entity.add_checkpoint(
            CarbonCopyCheckpoint(
                name="carbon_copy_handler",
                order=800,
                message_kinds=set(MessageKind),
            )
        )

    def register_entity(
        self,
        name: str,
        kind: EntityKind | str,
        visible: bool = True,
        enabled: bool = True,
        is_public: bool = False,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        handler: BaseHandler | Callable[[Any], Awaitable[None]] | None = None,
        provider: str | None = None,
        system_prompt: str | None = None,
        handler_config: HandlerConfig | dict[str, Any] | None = None,
        owner: FPAddress | None = None,
        arbiter: FPAddress | None = None,
    ) -> Entity:
        """注册一个新 Entity 到本 Host（协议层）"""
        address = FPAddress.create(self.uid)
        keys = generate_entity_key_material()
        mailbox_path = self._default_mailbox_path(address.entity_uid)

        entity_metadata = metadata or {}
        if provider:
            entity_metadata["provider"] = provider

        kind_value = kind.value if isinstance(kind, EntityKind) else str(kind).lower()

        entity = Entity(
            name=name,
            address=address,
            kind=kind,
            sign_public_key=keys["sign_public_key"],
            sign_private_key=keys["sign_private_key"],
            encrypt_public_key=keys["encrypt_public_key"],
            decrypt_private_key=keys["decrypt_private_key"],
            description=description,
            mailbox_path=mailbox_path,
            visible=visible,
            enabled=enabled,
            is_public=is_public,
            metadata=entity_metadata,
            host=self,
            owner=owner,
            arbiter=arbiter,
        )

        # Set up execution checkpoint (order=900)
        if kind_value == EntityKind.ARBITER.value and handler is None:
            entity.add_checkpoint(ArbiterCheckPoint(
                name="arbiter", order=900, message_kinds=_CONTRACT_PAY_KINDS,
            ))
        elif callable(handler) and not isinstance(handler, BaseHandler):
            entity.add_checkpoint(CallbackCheckPoint(
                name="callback_handler", order=900,
                message_kinds=set(MessageKind), callback=handler,
            ))
        else:
            resolved = self._resolve_entity_handler(
                entity=entity, handler=handler, provider=provider,
                system_prompt=system_prompt, handler_config=handler_config,
            )
            if resolved is not None:
                entity.add_checkpoint(HandlerBridgeCheckPoint(
                    name="handler_bridge", order=900,
                    message_kinds=set(MessageKind), handler=resolved,
                ))

        self._setup_default_checkpoints(entity)

        if entity.uid in self.entities:
            raise ValueError(f"Entity already exists: {entity.uid}")
        self.entities[entity.uid] = entity

        self.save()
        return entity

    def _resolve_entity_handler(
        self,
        entity: Entity,
        handler: BaseHandler | Callable[[Any], Awaitable[None]] | None,
        provider: str | None,
        system_prompt: str | None,
        handler_config: HandlerConfig | dict[str, Any] | None,
    ) -> BaseHandler | None:
        """Resolve one entity handler from explicit input or defaults.

        Returns None when handler is None — subclass (HostServer) overrides
        to provide application-layer handler creation.
        """
        if handler is None:
            return None

        if isinstance(handler, BaseHandler):
            return handler

        raise TypeError(f"Unsupported handler type: {type(handler)}")

    def update_entity(
        self,
        entity_uid: EntityUid,
        name: str | None = None,
        description: str | None = None,
        visible: bool | None = None,
        enabled: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Entity:
        """更新实体配置（字段级更新）."""
        entity = self.entities.get(entity_uid)
        if entity is None:
            raise ValueError(f"Entity not found: {entity_uid}")

        # Update fields
        if name is not None:
            entity.name = name
        if description is not None:
            entity.description = description
        if visible is not None:
            entity.visible = visible
        if enabled is not None:
            entity.enabled = enabled
        if metadata is not None:
            entity.metadata.update(metadata)

        self.save()
        return entity

    def delete_entity(self, entity_uid: EntityUid) -> None:
        """删除实体."""
        if entity_uid not in self.entities:
            raise ValueError(f"Entity not found: {entity_uid}")

        # Remove from friends lists
        for existing_entity in self.entities.values():
            existing_entity.friends.pop(entity_uid, None)

        del self.entities[entity_uid]
        self.save()

    def save(self) -> None:
        """保存host状态到存储"""
        from .utils.storage import (
            ChildHostEntry,
            EntityConfigEntry,
            HostConfigEntry,
            HostMeta,
            get_storage_manager,
        )

        storage = get_storage_manager()

        # 1. 保存host meta
        meta = HostMeta(
            uid=self.uid,
            name=self.name,
            address=self.address.address,
            bind_host=self.bind_host,
            port=self.port,
            url=self.url,
            parent_uid=self.parent_host.uid if self.parent_host else None,
            parent_url=getattr(self, "parent_url", None),
            default_owner=getattr(self, "default_owner", None) and self.default_owner.address,
        )
        storage.save_host_meta(meta)

        # 2. 保存children列表（包含每个child的public entities）
        if self.child_hosts:
            children = [
                ChildHostEntry(
                    uid=child.uid,
                    name=child.name,
                    url=child.url,
                    public_entities=[
                        entity.model_dump(mode="json")
                        for entity in child.known_public_entities
                    ],
                )
                for child in self.child_hosts.values()
            ]
            storage.save_host_children(self.uid, children)

        # 3. 更新config.json
        config = storage.load_config()

        config.hosts[self.uid] = HostConfigEntry(
            name=self.name,
            bind_host=self.bind_host,
            port=self.port,
            parent_uid=self.parent_host.uid if self.parent_host else None,
            parent_url=getattr(self, "parent_url", None),
            enabled=True,
        )

        # 4. 清理config中属于当前host但已不存在的entities
        entities_to_remove = [
            entity_uid
            for entity_uid, entity_config in config.entities.items()
            if entity_config.host_uid == self.uid and entity_uid not in self.entities
        ]
        for entity_uid in entities_to_remove:
            del config.entities[entity_uid]

        # 5. 保存所有entities
        for entity_uid, entity in self.entities.items():
            entity.save()

            # 更新config.json中的entity索引
            config.entities[entity_uid] = EntityConfigEntry(
                name=entity.name,
                kind=entity.kind if isinstance(entity.kind, str) else entity.kind.value,
                host_uid=self.uid,
                is_public=entity.is_public,
                enabled=entity.enabled,
                metadata=entity.metadata,
            )

        storage.save_config(config)

        # 6. 保存 Arbiter 状态（contracts, payments, ledger）
        for entity in self.entities.values():
            arbiter_cp = entity.get_checkpoint(ArbiterCheckPoint)
            if arbiter_cp is not None:
                arbiter_cp.save_state(self.uid)

        logger.info(f"Host {self.name} ({self.uid}) saved to storage")

    @classmethod
    def load(cls, host_uid: str) -> Host:
        """从存储加载host"""
        from .utils.storage import get_storage_manager

        storage = get_storage_manager()

        # 加载host meta
        meta = storage.load_host_meta(host_uid)
        if not meta:
            raise ValueError(f"Host {host_uid} not found in storage")

        # 创建Host对象
        host = cls(
            name=meta.name,
            address=FPAddress(address=meta.address),
            bind_host=meta.bind_host,
            port=meta.port,
        )

        # 设置parent_url（如果有）
        if meta.parent_url:
            object.__setattr__(host, "parent_url", meta.parent_url)

        # 恢复 default_owner（应用层字段，base Host 无此属性则跳过）
        if meta.default_owner and hasattr(host, "default_owner"):
            host.default_owner = FPAddress(address=meta.default_owner)

        # 加载parent host（如果有）- 直接用 parent_url 创建，不依赖本地文件
        if meta.parent_uid and meta.parent_url:
            parsed = urlparse(meta.parent_url)
            if not parsed.hostname:
                parsed = urlparse(f"http://{meta.parent_url}")
            parent_port = parsed.port if parsed.port and parsed.port > 0 else 7001
            parent_host = cls(
                name=f"parent-{meta.parent_uid[:8]}",
                address=FPAddress(address=f"{meta.parent_uid}:0"),
                bind_host=parsed.hostname or "0.0.0.0",
                port=parent_port,
            )
            host.parent_host = parent_host
            logger.info(f"Created parent host from URL: {meta.parent_url} ({meta.parent_uid})")

        # 加载children（包含每个child的public entities）
        children = storage.load_host_children(host_uid)
        for child_entry in children:
            public_entities = []
            for entity_dict in child_entry.public_entities:
                try:
                    public_entities.append(EntityCard(**entity_dict))
                except Exception as e:
                    logger.warning(f"Failed to parse child entity: {e}")

            parsed_child_url = urlparse(child_entry.url)
            if not parsed_child_url.hostname:
                parsed_child_url = urlparse(f"http://{child_entry.url}")
            child_port = (
                parsed_child_url.port
                if parsed_child_url.port and parsed_child_url.port > 0
                else 7001
            )

            # 创建简化的child host对象（不递归加载所有数据）
            child = cls(
                name=child_entry.name,
                address=FPAddress(address=f"{child_entry.uid}:0"),
                bind_host=parsed_child_url.hostname or "127.0.0.1",
                advertise_host=parsed_child_url.hostname or "127.0.0.1",
                port=child_port,
                known_public_entities=public_entities,
            )
            host.child_hosts[child_entry.uid] = child

        host._load_entities_from_config(host_uid)
        host._apply_load_policies()

        logger.info(f"Host {host.name} ({host.uid}) loaded from storage")
        return host

    def _load_entities_from_config(self, host_uid: str) -> int:
        """Load entities belonging to this host from config. Returns count loaded."""
        from .utils.storage import get_storage_manager

        storage = get_storage_manager()
        config = storage.load_config()
        count = 0

        for entity_uid, entity_config in config.entities.items():
            if entity_config.host_uid != host_uid:
                continue
            try:
                entity = Entity.load(entity_uid, self)
                self.entities[entity_uid] = entity

                if self._entity_kind_value(entity) == EntityKind.ARBITER.value:
                    arbiter_cp = ArbiterCheckPoint(
                        name="arbiter", order=900, message_kinds=_CONTRACT_PAY_KINDS,
                    )
                    arbiter_cp.load_state(host_uid)
                    entity.add_checkpoint(arbiter_cp)
                else:
                    provider = entity.metadata.get("provider")
                    system_prompt = entity.metadata.get("system_prompt")
                    resolved = self._resolve_entity_handler(
                        entity=entity,
                        handler=None,
                        provider=provider,
                        system_prompt=system_prompt,
                        handler_config=None,
                    )
                    if resolved is not None:
                        entity.add_checkpoint(HandlerBridgeCheckPoint(
                            name="handler_bridge", order=900,
                            message_kinds=set(MessageKind), handler=resolved,
                        ))

                self._setup_default_checkpoints(entity)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to load entity {entity_uid}: {e}")

        return count

    def _apply_load_policies(self) -> None:
        """Apply policies after loading entities. Subclass overrides for app policies."""
        pass
