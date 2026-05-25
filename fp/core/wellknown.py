from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, field_validator

from .base import EntityUid, HostUid, FPAddress


class EntityCard(BaseModel):
    """Entity discovery card with identity information."""

    name: str
    address: FPAddress
    kind: str
    sign_public_key: str
    encrypt_public_key: str
    description: str = ""
    is_public: bool
    entity_uid: EntityUid
    host_uid: HostUid
    has_avatar: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class HostWellKnown(BaseModel):
    """Root .well-known payload for host discovery.、
    包含host的基本信息和公开实体列表，供其他主机发现和交互使用。
    但是不包含 child 的 entities,需要获取所有可发现 entitis，调用 Host.get_discoverable_entities() 方法获取。
    """

    name: str
    uid: HostUid
    url: str
    public_entities: list[EntityCard] = Field(default_factory=list)
