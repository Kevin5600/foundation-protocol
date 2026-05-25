"""Tests for fp.core.wellknown module."""

import pytest
from fp.core.wellknown import EntityCard, HostWellKnown
from fp.core.base import FPAddress


class TestEntityCard:
    """Test EntityCard class."""

    def test_create_entity_card(self):
        """创建 EntityCard"""
        address = FPAddress(address="host123:entity456")
        card = EntityCard(
            name="Alice",
            address=address,
            kind="agent",
            sign_public_key="test_sign_key",
            encrypt_public_key="test_encrypt_key",
            description="",
            is_public=True,
            entity_uid="entity456",
            host_uid="host123",
        )
        assert card.name == "Alice"
        assert card.address == address
        assert card.kind == "agent"
        assert card.entity_uid == "entity456"
        assert card.host_uid == "host123"


class TestHostWellKnown:
    """Test HostWellKnown class."""

    def test_create_host_wellknown(self):
        """创建 HostWellKnown"""
        wellknown = HostWellKnown(
            name="TestHost",
            uid="host123",
            url="http://localhost:8000",
            public_entities=[],
        )
        assert wellknown.name == "TestHost"
        assert wellknown.uid == "host123"
        assert wellknown.url == "http://localhost:8000"
        assert wellknown.public_entities == []

    def test_host_wellknown_with_entities(self):
        """创建带有公开实体的 HostWellKnown"""
        address = FPAddress(address="host123:entity456")
        card = EntityCard(
            name="Alice",
            address=address,
            kind="agent",
            sign_public_key="test_sign_key",
            encrypt_public_key="test_encrypt_key",
            description="",
            is_public=True,
            entity_uid="entity456",
            host_uid="host123",
        )
        wellknown = HostWellKnown(
            name="TestHost",
            uid="host123",
            url="http://localhost:8000",
            public_entities=[card],
        )
        assert len(wellknown.public_entities) == 1
        assert wellknown.public_entities[0].name == "Alice"
