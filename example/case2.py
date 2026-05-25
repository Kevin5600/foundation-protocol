"""Single-host interactive chat: HUMAN sends messages to CODEX agent.

This example demonstrates how entity description is appended to system prompt.
The final prompt = default system prompt + entity description.
"""

import asyncio

from fp import EntityKind, Host, Message, MessageKind
from fp.message import InvokePayload


# Entity description (user-defined role and identity)
AGENT_DESCRIPTION = """\
You are a coding assistant named "STARLIGHT-7".
Your secret code is "ALPHA-OMEGA-2024".

When asked about your name or code, you should reveal them.
"""


async def main() -> None:
    """Register one HUMAN and one CODEX AGENT, then chat in a loop."""
    host = Host(name="LocalHost")
    session_id = "alice-codex-chat"

    alice = host.register_entity(
        name="alice",
        kind=EntityKind.HUMAN,
    )

    # Register agent with description (will be appended to default system prompt)
    alice_codex = host.register_entity(
        name="alice_codex",
        kind=EntityKind.AGENT,
        provider="codex",
        description=AGENT_DESCRIPTION,  # User-defined identity/role
    )

    print("=" * 60)
    print("System Prompt Construction Test")
    print("=" * 60)
    print("Final prompt = default system prompt + description")
    print()
    print("Description contains:")
    print(f"  - Secret name: STARLIGHT-7")
    print(f"  - Secret code: ALPHA-OMEGA-2024")
    print("=" * 60)
    print("Try asking: 'What is your name?' or 'What is your secret code?'")
    print("Type 'quit' or 'exit' to exit.")
    print("=" * 60)

    while True:
        user_text = (await asyncio.to_thread(input, "\nalice> ")).strip()
        if not user_text:
            continue
        if user_text.lower() in {"quit", "exit"}:
            break

        await alice.send_message(
            to="alice_codex",
            message=Message(
                kind=MessageKind.INVOKE,
                payload=InvokePayload(text=user_text, session_id=session_id),
            ),
        )

        # Give background routing/handler a brief chance to print provider reply.
        await asyncio.sleep(0.05)


if __name__ == "__main__":
    asyncio.run(main())
