"""Tests for fp.entity module."""

import pytest
import tempfile
from pathlib import Path
from fp.entity import Entity
from fp.core.base import FPAddress, EntityKind
from fp.core.wellknown import EntityCard


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_host(temp_dir):
    """创建真实 Host 对象"""
    from fp.host import Host

    host = Host(
        name="TestHost",
        data_dir=str(temp_dir),
        bind_host="localhost",
        port=8000,
    )
    return host


@pytest.fixture
def entity(mock_host, temp_dir):
    """创建 Entity 实例"""
    from fp.utils import generate_encrypt_keypair, generate_sign_keypair

    address = FPAddress(address="test_host:entity1")
    sign_public_key, sign_private_key = generate_sign_keypair()
    encrypt_public_key, decrypt_private_key = generate_encrypt_keypair()

    entity = Entity(
        name="TestEntity",
        kind=EntityKind.AGENT,
        address=address,
        sign_public_key=sign_public_key,
        sign_private_key=sign_private_key,
        encrypt_public_key=encrypt_public_key,
        decrypt_private_key=decrypt_private_key,
        description="",
        mailbox_path=str(temp_dir / "mailbox"),
        host=mock_host,
    )

    return entity


class TestEntity:
    """Test Entity class."""

    def test_entity_creation(self, entity):
        """测试 Entity 创建"""
        assert entity.name == "TestEntity"
        assert entity.kind == EntityKind.AGENT
        assert entity.uid is not None
        assert entity.visible is True
        assert entity.enabled is True

    def test_entity_card_property(self, entity):
        """测试 entity_card property"""
        card = entity.entity_card

        assert isinstance(card, EntityCard)
        assert card.name == "TestEntity"
        assert card.entity_uid == entity.uid
        assert card.host_uid == entity.host.uid
        assert card.kind == "agent"

    def test_add_friend(self, entity):
        """测试添加好友"""
        friend_address = FPAddress(address="other_host:entity2")
        friend_card = EntityCard(
            name="Friend",
            address=friend_address,
            kind="agent",
            sign_public_key="friend_sign_public_key",
            encrypt_public_key="friend_encrypt_public_key",
            description="",
            is_public=True,
            entity_uid="entity2",
            host_uid="other_host",
        )

        entity.add_friend(friend_card)
        assert "entity2" in entity.friends
        assert entity.friends["entity2"].name == "Friend"

    def test_remove_friend(self, entity):
        """测试移除好友"""
        friend_address = FPAddress(address="other_host:entity2")
        friend_card = EntityCard(
            name="Friend",
            address=friend_address,
            kind="agent",
            sign_public_key="friend_sign_public_key",
            encrypt_public_key="friend_encrypt_public_key",
            description="",
            is_public=True,
            entity_uid="entity2",
            host_uid="other_host",
        )

        entity.add_friend(friend_card)
        assert "entity2" in entity.friends

        entity.remove_friend("entity2")
        assert "entity2" not in entity.friends

    def test_get_friend_by_name(self, entity):
        """测试通过名称获取好友"""
        friend_address = FPAddress(address="other_host:entity2")
        friend_card = EntityCard(
            name="Friend",
            address=friend_address,
            kind="agent",
            sign_public_key="friend_sign_public_key",
            encrypt_public_key="friend_encrypt_public_key",
            description="",
            is_public=True,
            entity_uid="entity2",
            host_uid="other_host",
        )

        entity.add_friend(friend_card)
        found = entity._get_friend_by_name("Friend")
        assert found is not None
        assert found.name == "Friend"

    def test_to_dict(self, entity):
        """测试序列化为字典"""
        entity_dict = entity.to_dict()
        assert entity_dict["name"] == "TestEntity"
        assert "sessions" not in entity_dict
        assert "handler" not in entity_dict
        assert "host" not in entity_dict
