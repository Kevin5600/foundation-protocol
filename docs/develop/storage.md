# Storage

Foundation Protocol persists every long-lived piece of state — host descriptors, entity cards, private keys, mailboxes, the Arbiter ledger — under a single root directory on disk. This page documents the layout, the override knobs, and the model types in `fp/utils/storage.py` that read and write each file.

There is no database. JSON for structured records, JSONL for append-only logs. Backups are a directory copy.

## The root: `~/.fp`

By default everything lives under `~/.fp`. The location is resolved by `fp.utils.path.get_fp_home()` and can be redirected with environment variables:

| Variable | What it overrides |
|---|---|
| `FP_HOME` | the entire root (`~/.fp`) |
| `FP_CONFIG_PATH` | just `config.json` |

```python
import os
os.environ["FP_HOME"] = "/tmp/my-fp-test"   # before importing fp
```

Both variables are read once when the path helpers run, so set them before instantiating any `Host`. The directory tree is created lazily by `StorageManager._ensure_directory_structure()` on first write — there is no `fp init` step.

## Directory layout

```text
~/.fp/
├── config.json              # global config: hosts, entities, default settings
├── runtime.json             # runtime state: pids, ui_pid, last_sync
├── hosts/
│   └── {host_uid}/
│       ├── meta.json                    # HostMeta — name, address, parent, owner
│       ├── children.json                # HostChildren — registered child hosts
│       ├── offline_mail_queues.json     # mail queued for offline entities
│       ├── arbiter_state.json           # Arbiter contracts + payments + ledger
│       ├── market_state.json            # MarketStore (where used)
│       └── mailboxes/
│           └── {entity_uid}.jsonl       # this entity's signed mail log
├── entities/
│   └── {entity_uid}/
│       ├── meta.json                    # EntityMeta — card, owner, kind, metadata
│       ├── friends.json                 # EntityFriends — established peers
│       ├── sessions.json                # multi-turn conversation state
│       ├── pending_approvals.json       # owner-pending operations
│       └── avatar.{png,jpg,…}           # optional display image
├── keys/
│   ├── hosts/{host_uid}.key             # host signing key (chmod 0700 dir)
│   └── entities/{entity_uid}.key        # EntityKeys — sign + decrypt private keys
├── logs/
│   └── hosts/{host_uid}.log
└── cache/
```

The `keys/` directory is set to `0700` and individual `.key` files to `0600` on creation. If the host is running with insufficient permissions to set those modes, `StorageManager` logs a warning rather than failing.

## What lives in `config.json`

`config.json` is the single source of truth for *which* hosts and entities this machine knows about. Each host process loads it on start and writes back any changes through a `fcntl` file lock.

```python
# fp/utils/storage.py
class GlobalConfig(BaseModel):
    version: str = "1.0"
    default_host: str | None = None
    hosts: dict[str, HostConfigEntry] = {}        # keyed by host_uid
    entities: dict[str, EntityConfigEntry] = {}   # keyed by entity_uid
    settings: GlobalSettings = GlobalSettings()


class HostConfigEntry(BaseModel):
    name: str
    bind_host: str
    advertise_host: str | None = None
    port: int
    address: str | None = None
    url: str | None = None
    parent_uid: str | None = None
    parent_url: str | None = None
    enabled: bool = True


class EntityConfigEntry(BaseModel):
    name: str
    kind: str
    host_uid: str
    is_public: bool
    enabled: bool
    metadata: dict[str, Any] = {}


class GlobalSettings(BaseModel):
    auto_backup: bool = False
    log_level: str = "INFO"
    encrypt_keys: bool = False
```

Everything richer — the host's URL after binding, the entity's keys, the entity's mailbox — is stored in the per-host or per-entity folders, not in `config.json`.

## What lives in `runtime.json`

`runtime.json` is ephemeral process state: PIDs, the most recent sync timestamps, the UI process id if one is attached. It is rewritten frequently and is the only state file that is expected to be wrong if a host process crashes — restart clears it.

```python
class RuntimeState(BaseModel):
    pids: dict[str, int] = {}
    ui_pid: int | None = None
    last_sync: dict[str, str] = {}
    updated_at: str | None = None
```

## Mailboxes

Each entity's inbound + outbound mail is appended to a single JSONL file:

```text
~/.fp/hosts/{host_uid}/mailboxes/{entity_uid}.jsonl
```

Each line is one signed `Mail` envelope, serialized with `model_dump_json`. The `Mailbox` class in `fp/mailbox.py` exposes:

```python
mailbox.save_inbound(mail)
mailbox.save_outbound(mail)
mailbox.list_mails(is_read=…, is_handled=…, direction=…)
mailbox.mark_as_read(mail_id)
mailbox.mark_as_handled(mail_id)
mailbox.mark_mail_status(mail_id, status)
```

JSONL was chosen for the obvious reasons: no database dependency, append-friendly writes, trivial to back up, replay, or relocate.

## Trade subsystem state

When a host runs an Arbiter (`EntityKind.ARBITER`), its contracts, payments, and virtual ledger are serialized as one file:

```text
~/.fp/hosts/{host_uid}/arbiter_state.json
```

The shape comes from `fp/trade/models.py`:

```python
class ArbiterState(BaseModel):
    contracts: list[Contract] = []
    payments: list[Payment] = []
    ledger: LedgerSnapshot = LedgerSnapshot()
```

The Arbiter writes this file on every state-changing action, so a crash loses at most the action currently in flight.

## Programmatic access

For application code that wants to read or modify on-disk state directly, `StorageManager` (`fp/utils/storage.py`) is the supported surface. A singleton is exposed via `get_storage_manager()`:

```python
from fp.utils.storage import get_storage_manager

storage = get_storage_manager()

config = storage.load_config()
print(config.default_host, list(config.hosts))

meta = storage.load_entity_meta("alice-uid")
friends = storage.load_entity_friends("alice-uid")
```

Direct file access works too — every record is plain JSON and the Pydantic models double as schemas — but going through `StorageManager` gives you the file-lock and permission handling for free.

## Backup and relocation

Because state is a directory of plain files, both operations are trivial:

```bash
# Back up
cp -a ~/.fp ~/.fp-backup-$(date +%Y%m%d)

# Move to a new machine
rsync -a ~/.fp/ new-host:.fp/

# Run against an isolated copy without touching the original
FP_HOME=/tmp/fp-sandbox python my_script.py
```

The only file that is not safe to copy while a host is running is the mailbox JSONL of an entity currently receiving mail — writes are atomic per-line but a `cp` mid-write can see a half-written final line. Stop the host first, or back up after a quiescent period.

Next: [MCP Bridge](mcp-bridge.md).
