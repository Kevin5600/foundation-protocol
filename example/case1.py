"""跨 host 发送消息示例：Alice 和 Bob 分别注册在 不同的 LocalHost 上，通过 CloudHost 关联。
Alice 向 Bob 发送好友请求，之后发送消息。"""

import asyncio

from fp import EntityKind, Host, Message, MessageKind
from fp.message import FriendRequestPayload


async def main():
    """Create a simple 3-host organization and send mail."""
    cloudhost = Host(name="CloudHost")
    localhostA = Host(name="LocalHostA")
    localhostB = Host(name="LocalHostB")

    localhostA.set_parent_host(cloudhost)
    localhostB.set_parent_host(cloudhost)

    alice = localhostA.register_entity(name="Alice", kind=EntityKind.HUMAN)
    bob = localhostB.register_entity(name="Bob", kind=EntityKind.HUMAN)

    # Alice 发送好友请求给 Bob
    # 现在是自动接收申请，Bob 会自动成为 Alice 的好友，后续可以正常通信
    await alice.send_message(
        to=bob.entity_card,
        message=Message(
            kind=MessageKind.FRIEND_REQUEST,
            payload=FriendRequestPayload(
                sender_card=alice.entity_card,
                text=f"{alice.name} wants to add you as a friend",
            ),
        ),
    )

    # 等待消息传递完成
    await asyncio.sleep(0.1)

    # 现在 Alice 和 Bob 互为好友，可以正常通信
    await alice.send_message(
        to="Bob",
        message=Message(
            kind=MessageKind.INVOKE,
            payload={
                "jsonrpc": "2.0",
                "id": "alice-hello-1",
                "method": "chat.hello",
                "params": {"text": "Hello Bob! This is Alice."},
            },
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
