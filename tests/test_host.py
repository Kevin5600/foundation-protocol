"""Tests for fp.host module."""

import pytest
import tempfile
from pathlib import Path
from fp.host import Host
from fp.core.base import EntityKind


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def host(temp_dir):
    """创建 Host 实例"""
    host = Host(
        name="TestHost",
        data_dir=str(temp_dir),
        bind_host="localhost",
        port=8000,
    )
    return host


class TestHost:
    """Test Host class."""

    def test_host_creation(self, host):
        """测试 Host 创建"""
        assert host.name == "TestHost"
        assert host.bind_host == "localhost"
        assert host.port == 8000
        assert host.uid is not None

    def test_register_entity(self, host):
        """测试注册 Entity"""
        entity = host.register_entity(
            name="Alice",
            kind=EntityKind.AGENT,
            is_public=True,
        )

        assert entity.name == "Alice"
        assert entity.kind == EntityKind.AGENT
        assert entity.uid in host.entities

    def test_get_entity(self, host):
        """测试获取 Entity"""
        entity = host.register_entity(
            name="Alice",
            kind=EntityKind.AGENT,
        )

        retrieved = host.get_entity(entity.uid)
        assert retrieved is not None
        assert retrieved.name == "Alice"

    def test_delete_entity(self, host):
        """测试删除 Entity"""
        entity = host.register_entity(
            name="Alice",
            kind=EntityKind.AGENT,
        )

        assert entity.uid in host.entities
        host.delete_entity(entity.uid)
        assert entity.uid not in host.entities

    def test_public_entities(self, host):
        """测试公开实体列表"""
        host.register_entity(
            name="Alice",
            kind=EntityKind.AGENT,
            is_public=True,
        )
        host.register_entity(
            name="Bob",
            kind=EntityKind.AGENT,
            is_public=False,
        )

        public_entities = host._collect_self_public_entities()
        assert len(public_entities) == 1
        assert public_entities[0].name == "Alice"

    def test_set_parent_host(self, temp_dir):
        """测试设置父 Host"""
        parent = Host(
            name="ParentHost",
            data_dir=str(temp_dir / "parent"),
        )
        child = Host(
            name="ChildHost",
            data_dir=str(temp_dir / "child"),
        )

        child.set_parent_host(parent)
        assert child.parent_host == parent
        assert child.uid in parent.child_hosts

    def test_auto_friend(self, temp_dir):
        """测试注册多个 entity 后手动添加好友"""
        host = Host(
            name="TestHost",
            data_dir=str(temp_dir),
        )

        alice = host.register_entity(
            name="Alice",
            kind=EntityKind.AGENT,
        )
        bob = host.register_entity(
            name="Bob",
            kind=EntityKind.AGENT,
        )

        # auto_friend 已移除，注册后不会自动互为好友
        assert bob.uid not in alice.friends
        assert alice.uid not in bob.friends

    def test_get_wellknown(self, host):
        """测试 get_wellknown 方法"""
        host.register_entity(
            name="Alice",
            kind=EntityKind.AGENT,
            is_public=True,
        )

        wellknown = host.get_wellknown()
        assert wellknown.name == "TestHost"
        assert wellknown.uid == host.uid
        assert len(wellknown.public_entities) == 1
        assert wellknown.public_entities[0].name == "Alice"
