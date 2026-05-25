"""Tests for fp.mail module."""

import pytest

from fp.core.base import FPAddress
from fp.core.cryptor import Ed25519SignerVerifier, X25519EncryptorDecryptor
from fp.mail import Mail
from fp.message import Message, MessageKind
from fp.utils import generate_encrypt_keypair, generate_sign_keypair


@pytest.fixture
def signer():
    """创建 signer 实例"""
    return Ed25519SignerVerifier()


@pytest.fixture
def cipher():
    """创建 cipher 实例"""
    return X25519EncryptorDecryptor()


@pytest.fixture
def temp_keys():
    """创建临时密钥对"""
    sender_sign_public, sender_sign_private = generate_sign_keypair()
    recipient_sign_public, recipient_sign_private = generate_sign_keypair()
    recipient_encrypt_public, recipient_decrypt_private = generate_encrypt_keypair()

    yield {
        "sender_sign_private": sender_sign_private,
        "sender_sign_public": sender_sign_public,
        "recipient_sign_private": recipient_sign_private,
        "recipient_sign_public": recipient_sign_public,
        "recipient_decrypt_private": recipient_decrypt_private,
        "recipient_encrypt_public": recipient_encrypt_public,
    }


class TestMail:
    """Test Mail class."""

    def test_create_mail(self, signer, cipher):
        """创建 Mail 实例"""
        sender = FPAddress(address="host1:entity1")
        recipient = FPAddress(address="host2:entity2")
        message = Message(kind=MessageKind.HELLO, payload={"text": "Hello"})

        mail = Mail(
            sender=sender,
            recipient=[recipient],
            message=message,
            signature="",
            signer=signer,
            cipher=cipher,
        )

        assert mail.sender == sender
        assert mail.recipient == [recipient]
        assert mail.message == message

    def test_seal_mail(self, temp_keys):
        """测试 seal 方法（加密并签名）"""
        sender = FPAddress(address="host1:entity1")
        recipient = FPAddress(address="host2:entity2")
        message = Message(kind=MessageKind.HELLO, payload={"text": "Hello"})

        sealed_mail = Mail.seal(
            sender=sender,
            recipient=recipient,
            message=message,
            sign_private_key=temp_keys["sender_sign_private"],
            encrypt_public_key=temp_keys["recipient_encrypt_public"],
        )

        assert sealed_mail.sender == sender
        assert sealed_mail.recipient == [recipient]
        assert sealed_mail.signature != ""
        assert isinstance(sealed_mail.message, str)

    def test_verify_signature(self, temp_keys):
        """测试签名验证"""
        sender = FPAddress(address="host1:entity1")
        recipient = FPAddress(address="host2:entity2")
        message = Message(kind=MessageKind.HELLO, payload={"text": "Hello"})

        sealed_mail = Mail.seal(
            sender=sender,
            recipient=recipient,
            message=message,
            sign_private_key=temp_keys["sender_sign_private"],
            encrypt_public_key=temp_keys["recipient_encrypt_public"],
        )

        assert sealed_mail._verify_signature(temp_keys["sender_sign_public"])

    def test_decrypt_message(self, temp_keys):
        """测试消息解密"""
        sender = FPAddress(address="host1:entity1")
        recipient = FPAddress(address="host2:entity2")
        message = Message(kind=MessageKind.HELLO, payload={"text": "Hello"})

        sealed_mail = Mail.seal(
            sender=sender,
            recipient=recipient,
            message=message,
            sign_private_key=temp_keys["sender_sign_private"],
            encrypt_public_key=temp_keys["recipient_encrypt_public"],
        )

        decrypted_mail = sealed_mail._decrypt_message(temp_keys["recipient_decrypt_private"])
        assert isinstance(decrypted_mail.message, Message)
        assert decrypted_mail.message.kind == MessageKind.HELLO
        assert decrypted_mail.message.payload == {"text": "Hello"}

    def test_to_dict_and_from_dict(self, signer, cipher):
        """测试序列化和反序列化"""
        sender = FPAddress(address="host1:entity1")
        recipient = FPAddress(address="host2:entity2")
        message = Message(kind=MessageKind.HELLO, payload={"text": "Hello"})

        mail = Mail(
            sender=sender,
            recipient=[recipient],
            message=message,
            signature="test_signature",
            signer=signer,
            cipher=cipher,
        )

        mail_dict = mail.to_dict()
        assert "signer" not in mail_dict
        assert "cipher" not in mail_dict
        assert mail_dict["sender"]["address"] == "host1:entity1"

        restored_mail = Mail.from_dict(mail_dict, signer=signer, cipher=cipher)
        assert restored_mail.sender.address == "host1:entity1"
        assert restored_mail.recipient[0].address == "host2:entity2"
        assert restored_mail.signature == "test_signature"

    def test_seal_unseal_encrypted_roundtrip(self, temp_keys):
        """Encrypted mail: seal → unseal restores original message"""
        sender = FPAddress(address="host1:entity1")
        recipient = FPAddress(address="host2:entity2")
        message = Message(kind=MessageKind.HELLO, payload={"text": "secret"})

        sealed = Mail.seal(
            sender=sender,
            recipient=recipient,
            message=message,
            sign_private_key=temp_keys["sender_sign_private"],
            encrypt_public_key=temp_keys["recipient_encrypt_public"],
        )
        assert isinstance(sealed.message, str)

        unsealed = sealed.unseal(
            verify_public_key=temp_keys["sender_sign_public"],
            decrypt_private_key=temp_keys["recipient_decrypt_private"],
        )
        assert unsealed is not None
        assert isinstance(unsealed.message, Message)
        assert unsealed.message.kind == MessageKind.HELLO
        assert unsealed.message.payload == {"text": "secret"}

    def test_seal_unseal_signed_only_with_explicit_key(self, temp_keys):
        """Sign-only mail: unseal with explicit verify_public_key succeeds"""
        sender = FPAddress(address="host1:entity1")
        recipient = FPAddress(address="host2:entity2")
        message = Message(kind=MessageKind.INVOKE, payload={"text": "hello"})

        sealed = Mail.seal(
            sender=sender,
            recipient=recipient,
            message=message,
            sign_private_key=temp_keys["sender_sign_private"],
            encrypt_public_key=None,
        )
        assert isinstance(sealed.message, Message)

        unsealed = sealed.unseal(
            verify_public_key=temp_keys["sender_sign_public"],
        )
        assert unsealed is not None
        assert unsealed.message.kind == MessageKind.INVOKE

    def test_seal_unseal_signed_only_with_sender_card(self, temp_keys):
        """Sign-only mail with sender_card in payload: unseal extracts key from payload"""
        from fp.core.wellknown import EntityCard

        sender = FPAddress(address="host1:entity1")
        recipient = FPAddress(address="host2:entity2")
        sender_card = EntityCard(
            name="Sender",
            address=sender,
            kind="agent",
            sign_public_key=temp_keys["sender_sign_public"],
            encrypt_public_key=temp_keys["recipient_encrypt_public"],
            description="",
            is_public=True,
            entity_uid="entity1",
            host_uid="host1",
        )
        message = Message(
            kind=MessageKind.FRIEND_REQUEST,
            payload={"sender_card": sender_card.model_dump(), "text": "hi"},
        )

        sealed = Mail.seal(
            sender=sender,
            recipient=recipient,
            message=message,
            sign_private_key=temp_keys["sender_sign_private"],
            encrypt_public_key=None,
        )

        unsealed = sealed.unseal(verify_public_key=None)
        assert unsealed is not None

    def test_unseal_fails_with_wrong_key(self, temp_keys):
        """Unseal fails when verify key doesn't match signer"""
        sender = FPAddress(address="host1:entity1")
        recipient = FPAddress(address="host2:entity2")
        message = Message(kind=MessageKind.HELLO, payload={"text": "data"})

        sealed = Mail.seal(
            sender=sender,
            recipient=recipient,
            message=message,
            sign_private_key=temp_keys["sender_sign_private"],
            encrypt_public_key=None,
        )

        unsealed = sealed.unseal(
            verify_public_key=temp_keys["recipient_sign_public"],
        )
        assert unsealed is None

