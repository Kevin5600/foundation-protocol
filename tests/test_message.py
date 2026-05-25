"""Tests for fp.message module."""

import pytest
from fp.message import Message, MessageKind


class TestMessageKind:
    """Test MessageKind enum."""

    def test_message_kinds(self):
        """测试 MessageKind 枚举值"""
        assert MessageKind.HELLO.value == "hello"
        assert MessageKind.INVOKE.value == "invoke"
        assert MessageKind.ERROR.value == "error"

    def test_is_ack(self):
        """测试 is_ack 属性"""
        assert MessageKind.HELLO_ACK.is_ack
        assert MessageKind.SESSION_CREATE_ACK.is_ack
        assert not MessageKind.HELLO.is_ack
        assert not MessageKind.INVOKE.is_ack

    def test_ack_kind(self):
        """测试 ack_kind 属性"""
        assert MessageKind.HELLO.ack_kind == MessageKind.HELLO_ACK
        assert MessageKind.SESSION_CREATE.ack_kind == MessageKind.SESSION_CREATE_ACK
        assert MessageKind.INVOKE.ack_kind is None

    def test_request_kind(self):
        """测试 request_kind 属性"""
        assert MessageKind.HELLO_ACK.request_kind == MessageKind.HELLO
        assert MessageKind.SESSION_CREATE_ACK.request_kind == MessageKind.SESSION_CREATE
        assert MessageKind.HELLO.request_kind is None


class TestMessage:
    """Test Message class."""

    def test_create_message(self):
        """创建消息"""
        msg = Message(kind=MessageKind.HELLO, payload={"text": "Hello"})
        assert msg.kind == MessageKind.HELLO
        assert msg.payload == {"text": "Hello"}
        assert msg.message_id is not None

    def test_message_with_custom_id(self):
        """创建带自定义 ID 的消息"""
        msg = Message(
            kind=MessageKind.HELLO,
            payload={"text": "Hello"},
            message_id="custom_id",
        )
        assert msg.message_id == "custom_id"

    def test_normalize_kind_from_string(self):
        """从字符串规范化 kind"""
        msg = Message(kind="hello", payload={})
        assert msg.kind == MessageKind.HELLO

    def test_normalize_kind_from_enum_name(self):
        """从枚举名称规范化 kind"""
        msg = Message(kind="HELLO", payload={})
        assert msg.kind == MessageKind.HELLO

    def test_is_ack(self):
        """测试 is_ack 属性"""
        msg_ack = Message(kind=MessageKind.HELLO_ACK, payload={})
        assert msg_ack.kind.is_ack

        msg_hello = Message(kind=MessageKind.HELLO, payload={})
        assert not msg_hello.kind.is_ack

    def test_content_property(self):
        """测试 content 属性"""
        msg = Message(kind=MessageKind.HELLO, payload={"text": "Hello"})
        assert msg.content == {"text": "Hello"}

        msg_no_text = Message(kind=MessageKind.HELLO, payload={"data": "value"})
        assert msg_no_text.content == {"data": "value"}

    def test_to_ack(self):
        """测试 to_ack 方法"""
        msg = Message(kind=MessageKind.HELLO, payload={"text": "Hello"})
        ack = msg.to_ack(success=True, payload={"status": "ok"})

        assert ack.kind == MessageKind.HELLO_ACK
        assert ack.metadata["ack_of_message_id"] == msg.message_id
        assert ack.metadata["success"] is True
        assert ack.payload == {"status": "ok"}

    def test_to_ack_no_paired_kind(self):
        """测试没有配对 ACK kind 的消息"""
        msg = Message(kind=MessageKind.INVOKE, payload={})
        with pytest.raises(ValueError, match="has no paired ACK kind"):
            msg.to_ack()

    def test_recipient_id_property(self):
        """测试 recipient_id 属性"""
        msg = Message(
            kind=MessageKind.INVOKE,
            payload={},
            metadata={"recipient_id": "entity:123"},
        )
        assert msg.recipient_id == "123"

        msg_no_prefix = Message(
            kind=MessageKind.INVOKE,
            payload={},
            metadata={"to_entity_uid": "456"},
        )
        assert msg_no_prefix.recipient_id == "456"
