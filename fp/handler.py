"""Base handler interfaces and configuration for entity message processing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from loguru import logger

from .message import Message

if TYPE_CHECKING:
    from .entity import Entity

MessageCallback = Callable[[Any], Awaitable[None]]


# ── Configuration ────────────────────────────────────────────


class TrustLevel(str, Enum):
    """Agent execution trust level (protocol abstraction)."""

    UNTRUSTED = "untrusted"
    SEMI_TRUSTED = "semi_trusted"
    FULLY_TRUSTED = "fully_trusted"


class InteractionMode(str, Enum):
    """Interaction mode with user/system."""

    INTERACTIVE = "interactive"
    BATCH = "batch"


@dataclass(slots=True)
class HandlerConfig:
    """Agent handler runtime configuration.

    Semantic config format for all handlers, independent of provider CLI.
    CLIAdapter maps these fields to provider-specific CLI arguments.
    """

    trust_level: TrustLevel = TrustLevel.FULLY_TRUSTED
    workdir: str | None = None
    allowed_tools: list[str] | None = None
    timeout: float = 600.0
    max_budget_usd: float | None = None
    interaction_mode: InteractionMode = InteractionMode.BATCH
    stream_output: bool = False
    output_format: Literal["text", "json", "stream-json"] = "json"
    model: str | None = None
    provider_extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def merge(self, overrides: dict[str, Any] | None) -> HandlerConfig:
        if not overrides:
            return self
        data = self.to_dict()
        data.update(overrides)
        return HandlerConfig.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HandlerConfig:
        trust_level = data.get("trust_level", TrustLevel.FULLY_TRUSTED)
        if isinstance(trust_level, str):
            trust_level = TrustLevel(trust_level)

        interaction_mode = data.get("interaction_mode", InteractionMode.BATCH)
        if isinstance(interaction_mode, str):
            interaction_mode = InteractionMode(interaction_mode)

        return cls(
            trust_level=trust_level,
            workdir=data.get("workdir"),
            allowed_tools=data.get("allowed_tools"),
            timeout=data.get("timeout", 600.0),
            max_budget_usd=data.get("max_budget_usd"),
            interaction_mode=interaction_mode,
            stream_output=data.get("stream_output", False),
            output_format=data.get("output_format", "json"),
            model=data.get("model"),
            provider_extras=data.get("provider_extras", {}),
        )


# ── Handler base classes ─────────────────────────────────────


class BaseHandler(ABC):
    """Base message handler interface for one entity."""

    def __init__(self, entity: Entity) -> None:
        self.entity = entity

    @abstractmethod
    async def handle(self, message: Message) -> None:
        """Handle one message."""

    def _log_message(self, message: Message, *, handler_name: str) -> None:
        sender_address = message.metadata.get("sender_address", "unknown")
        sender_uid = sender_address.split(":")[-1] if ":" in sender_address else sender_address

        text_preview = ""
        if isinstance(message.payload, dict):
            text = message.payload.get("text", "")
            text_preview = text[:50] + "..." if len(text) > 50 else text

        logger.info(
            f"[{self.entity.name}] {handler_name} 收到消息 ← {sender_uid} | "
            f"kind={message.kind.value} | text={text_preview}"
        )


class CallbackHandler(BaseHandler):
    """Adapter to use a custom async callback as handler."""

    def __init__(self, entity: Entity, callback: MessageCallback) -> None:
        super().__init__(entity)
        self._callback = callback

    async def handle(self, message: Message) -> None:
        await self._callback(message)
