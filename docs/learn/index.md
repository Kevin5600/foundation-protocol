# Learn

Learn covers the **reference Python runtime** — how Foundation Protocol works on the wire, in process, and in storage. If you want to understand how an FP message gets from `Alice` to `Bob`, what runs between them, and what state the runtime keeps along the way, you're in the right place.

For build-and-ship recipes, see [Develop](../develop/index.md). For the trade and arbitration layer, see [Trade & Trust](../trade-and-trust/index.md).

## What's in this section

<div class="grid cards" markdown>

-   [:material-shield-key-outline: __Checkpoint Pipeline__](checkpoint.md)

    The ordered policy chain every inbound message walks before
    reaching a handler. The runtime's primary trust and governance
    seam.

-   [:material-email-outline: __Mail__](mail.md)

    The signed envelope every message travels in. Routing, signing,
    optional encryption, and the seven-state lifecycle from `sent` to
    `done`.

-   [:material-message-text-outline: __Message__](message.md)

    The business payload inside the envelope. `MessageKind`, payload
    types, and how Mail and Message divide responsibility.

-   [:material-content-copy: __Carbon Copy__](carbon-copy.md)

    How an entity's owner observes the conversations of every entity
    they own — outbound and inbound copies, deduplicated by original
    message id.

</div>
