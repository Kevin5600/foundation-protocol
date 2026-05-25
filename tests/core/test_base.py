"""Tests for fp.core.base module."""

import pytest
from fp.core.base import FPAddress, EntityKind


class TestFPAddress:
    """Test FPAddress class."""

    def test_create_host_address(self):
        """创建 Host 地址"""
        addr = FPAddress.create()
        assert addr.is_host_address
        assert not addr.is_entity_address
        assert addr.entity_uid == "0"

    def test_create_entity_address(self):
        """创建 Entity 地址"""
        host_uid = "test_host"
        addr = FPAddress.create(host_uid=host_uid)
        assert addr.is_entity_address
        assert not addr.is_host_address
        assert addr.host_uid == host_uid
        assert addr.entity_uid != "0"

    def test_validate_address_format_valid(self):
        """验证有效地址格式"""
        addr = FPAddress(address="host123:entity456")
        assert addr.address == "host123:entity456"
        assert addr.host_uid == "host123"
        assert addr.entity_uid == "entity456"

    def test_validate_address_format_invalid(self):
        """验证无效地址格式"""
        with pytest.raises(Exception):
            FPAddress(address="invalid")

        with pytest.raises(Exception):
            FPAddress(address="host:")

        with pytest.raises(Exception):
            FPAddress(address=":entity")

    def test_is_valid(self):
        """测试 is_valid 方法"""
        assert FPAddress.is_valid("host:entity")
        assert FPAddress.is_valid(FPAddress(address="host:entity"))
        assert not FPAddress.is_valid("invalid")
        assert not FPAddress.is_valid(123)

    def test_parts(self):
        """测试 parts 方法"""
        addr = FPAddress(address="host123:entity456")
        host, entity = addr.parts()
        assert host == "host123"
        assert entity == "entity456"

    def test_str(self):
        """测试 __str__ 方法"""
        addr = FPAddress(address="host:entity")
        assert str(addr) == "host:entity"


class TestEntityKind:
    """Test EntityKind enum."""

    def test_entity_kinds(self):
        """测试 EntityKind 枚举值"""
        assert EntityKind.HOST.value == "host"
        assert EntityKind.HUMAN.value == "human"
        assert EntityKind.AGENT.value == "agent"
        assert EntityKind.TOOL.value == "tool"
        assert EntityKind.RESOURCE.value == "resource"
        assert EntityKind.SERVICE.value == "service"

    def test_entity_kind_from_string(self):
        """测试从字符串创建 EntityKind"""
        assert EntityKind("agent") == EntityKind.AGENT
        assert EntityKind("human") == EntityKind.HUMAN
