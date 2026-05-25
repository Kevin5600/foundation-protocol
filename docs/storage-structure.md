# FP 存储结构设计文档

## 📋 文档信息

- **版本**: 1.0
- **创建时间**: 2026-04-02
- **最后更新**: 2026-04-02
- **状态**: 设计中

## 🎯 设计目标

1. **清晰分离**: 配置、状态、密钥、日志、数据分离
2. **易于备份**: 可以选择性备份（如排除日志）
3. **安全性**: 密钥独立存储，便于加密和权限控制
4. **可扩展**: 为未来功能预留空间
5. **性能优化**: 避免单文件过大，支持快速查询

## 📁 文件夹结构

```
~/.fp/
├── config.json                 # 全局配置（启动恢复的核心文件）
├── runtime.json               # 运行时状态（PID、临时状态等）
│
├── hosts/                     # Host相关数据
│   └── {host_uid}/
│       ├── meta.json          # Host元数据（name, address, parent等）
│       └── children.json      # Child hosts列表
│
├── entities/                  # Entity相关数据
│   └── {entity_uid}/
│       ├── meta.json          # Entity元数据（name, kind, host_uid等）
│       ├── friends.json       # 好友列表
│       └── sessions.json      # Session状态
│
├── keys/                      # 密钥存储（敏感，应加密）
│   ├── hosts/
│   │   └── {host_uid}.key     # Host密钥（如果需要）
│   └── entities/
│       └── {entity_uid}.key   # Entity密钥（包含sign和encrypt私钥）
│
├── mailboxes/                 # 邮箱数据
│   └── {entity_uid}.jsonl     # Entity邮箱（JSONL格式，追加写）
│
├── logs/                      # 日志文件
│   ├── hosts/
│   │   └── {host_uid}.log     # Host日志
│   ├── entities/
│   │   └── {entity_uid}.log   # Entity日志（如果需要）
│   └── system.log             # 系统日志
│
├── cache/                     # 缓存数据（可删除）
│   ├── wellknown/             # 缓存的wellknown信息
│   └── discovery/             # 发现的entity缓存
│
└── backups/                   # 备份（可选）
    └── {timestamp}/
```

### 文件夹说明

| 目录 | 用途 | 是否必须 | 是否备份 |
|------|------|---------|---------|
| `config.json` | 全局配置索引 | ✅ 必须 | ✅ 必须 |
| `runtime.json` | 运行时状态 | ❌ 可选 | ❌ 不需要 |
| `hosts/` | Host元数据 | ✅ 必须 | ✅ 必须 |
| `entities/` | Entity元数据 | ✅ 必须 | ✅ 必须 |
| `keys/` | 密钥文件 | ✅ 必须 | ⚠️ 谨慎 |
| `mailboxes/` | 邮箱数据 | ✅ 必须 | ✅ 可选 |
| `logs/` | 日志文件 | ❌ 可选 | ❌ 不需要 |
| `cache/` | 缓存数据 | ❌ 可选 | ❌ 不需要 |
| `backups/` | 自动备份 | ❌ 可选 | ❌ 不需要 |

## 📄 文件格式详解

### 1. `config.json` - 全局配置文件

**用途**: 系统启动的唯一入口，记录所有资源的索引

```json
{
  "version": "1.0",
  "default_host": "9d71242b",

  "hosts": {
    "9d71242b": {
      "name": "default",
      "bind_host": "0.0.0.0",
      "port": 7001,
      "parent_uid": null,
      "enabled": true
    },
    "4e934bc8": {
      "name": "hostB",
      "bind_host": "0.0.0.0",
      "port": 7002,
      "parent_uid": "9d71242b",
      "enabled": true
    }
  },

  "entities": {
    "40588f71": {
      "name": "GYF",
      "kind": "human",
      "host_uid": "9d71242b",
      "is_public": true,
      "enabled": true
    },
    "f296e24e": {
      "name": "GYF-codex",
      "kind": "agent",
      "host_uid": "9d71242b",
      "is_public": true,
      "enabled": true,
      "metadata": {
        "provider": "codex"
      }
    }
  },

  "settings": {
    "auto_backup": false,
    "log_level": "INFO",
    "encrypt_keys": false
  }
}
```

**设计原则**:
- ✅ 轻量级，只记录索引和基本信息
- ✅ 一眼就能看出系统有哪些host和entity
- ✅ 通过uid关联其他文件
- ✅ 快速启动，不需要遍历文件系统

### 2. `runtime.json` - 运行时状态

**用途**: 临时状态，可随时删除

```json
{
  "updated_at": "2026-04-02T22:00:00Z",
  "pids": {
    "9d71242b": 71317,
    "4e934bc8": 71321
  },
  "ui_pid": 12345,
  "last_sync": {
    "9d71242b": "2026-04-02T21:59:00Z"
  }
}
```

### 3. `hosts/{host_uid}/meta.json` - Host元数据

```json
{
  "uid": "9d71242b",
  "name": "default",
  "address": "9d71242b:0",
  "bind_host": "0.0.0.0",
  "port": 7001,
  "url": "http://0.0.0.0:7001",

  "parent_uid": null,
  "parent_url": "http://172.31.0.5:7001",

  "settings": {},

  "created_at": "2026-04-01T10:00:00Z",
  "updated_at": "2026-04-02T21:00:00Z"
}
```

### 4. `hosts/{host_uid}/children.json` - Child hosts列表

```json
{
  "children": [
    {
      "uid": "4e934bc8",
      "name": "hostB",
      "url": "http://0.0.0.0:7002",
      "last_seen": "2026-04-02T21:59:00Z"
    }
  ]
}
```

### 5. `entities/{entity_uid}/meta.json` - Entity元数据

```json
{
  "uid": "40588f71",
  "name": "GYF",
  "kind": "human",
  "host_uid": "9d71242b",
  "address": "9d71242b:40588f71",

  "keys": {
    "sign_public_key": "-----BEGIN PUBLIC KEY-----\n...",
    "encrypt_public_key": "-----BEGIN PUBLIC KEY-----\n...",
    "key_file": "keys/entities/40588f71.key"
  },

  "mailbox_path": "mailboxes/40588f71.jsonl",
  "description": "",
  "is_public": true,
  "visible": true,
  "enabled": true,
  "metadata": {},

  "created_at": "2026-04-02T21:27:00Z",
  "updated_at": "2026-04-02T21:27:00Z"
}
```

### 6. `entities/{entity_uid}/friends.json` - 好友列表

```json
{
  "friends": [
    {
      "entity_uid": "f296e24e",
      "name": "GYF-codex",
      "address": "9d71242b:f296e24e",
      "kind": "agent",
      "host_uid": "9d71242b",
      "sign_public_key": "-----BEGIN PUBLIC KEY-----\n...",
      "encrypt_public_key": "-----BEGIN PUBLIC KEY-----\n...",
      "added_at": "2026-04-02T21:30:00Z"
    }
  ]
}
```

### 7. `entities/{entity_uid}/sessions.json` - Session状态

```json
{
  "sessions": {
    "session_001": {
      "session_id": "session_001",
      "remote_entity": "9d71242b:f296e24e",
      "state": "active",
      "created_at": "2026-04-02T21:30:00Z",
      "last_activity": "2026-04-02T21:59:00Z"
    }
  }
}
```

### 8. `keys/entities/{entity_uid}.key` - Entity私钥

```json
{
  "uid": "40588f71",
  "sign_private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "decrypt_private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "created_at": "2026-04-02T21:27:00Z"
}
```

**安全考虑**:
- 文件权限设置为 `600` (owner only)
- 未来可以加密（使用master password）
- 可以单独备份或不备份keys目录

### 9. `mailboxes/{entity_uid}.jsonl` - Entity邮箱

JSONL格式（每行一个JSON对象），支持追加写入：

```jsonl
{"mail": {...}, "metadata": {"timestamp": "2026-04-02T21:27:00Z", "is_read": false, "direction": "inbound"}}
{"mail": {...}, "metadata": {"timestamp": "2026-04-02T21:28:00Z", "is_read": false, "direction": "outbound"}}
```

## 🔐 文件权限设置

```bash
~/.fp/                    # 700 (drwx------)
├── config.json           # 644 (-rw-r--r--)
├── runtime.json          # 644 (-rw-r--r--)
├── hosts/                # 755 (drwxr-xr-x)
│   └── {host_uid}/       # 755 (drwxr-xr-x)
├── entities/             # 755 (drwxr-xr-x)
│   └── {entity_uid}/     # 755 (drwxr-xr-x)
├── keys/                 # 700 (drwx------)  ⚠️ 最敏感
│   ├── hosts/            # 700 (drwx------)
│   └── entities/         # 700 (drwx------)
│       └── *.key         # 600 (-rw-------)  ⚠️ 最敏感
├── mailboxes/            # 700 (drwx------)  🔒 隐私数据
│   └── *.jsonl           # 600 (-rw-------)
├── logs/                 # 755 (drwxr-xr-x)
└── cache/                # 755 (drwxr-xr-x)
```

## 💻 代码实现设计

### 方案：混合模式（函数 + 类）

**核心思路**:
- **`fp/utils/path.py`**: 纯函数，只负责返回路径（Path对象）
- **`fp/storage.py`**: StorageManager类，负责读写操作、验证、初始化

**优点**:
- ✅ 分离关注点：路径获取 vs 数据操作
- ✅ 函数式路径获取，简单直接
- ✅ 类封装复杂操作，便于扩展
- ✅ 遵循单一职责原则

### 1. 路径管理 - `fp/utils/path.py`

```python
"""Filesystem path helpers for FP global state.

规范：
- 一律使用 Pathlib 来处理路径，除非有特殊需求必须使用 os.path
- 返回值一律为 Path 对象，除非需要兼容第三方库接口必须使用字符串路径
- path 为文件路径，dir 为文件夹路径
- get_xxx_path/dir() 用于获取文件/文件夹路径，不进行路径存在性检查
- ensure_xxx_path/dir() 用于获取文件/文件夹路径，并确保父目录存在
"""

from __future__ import annotations

import os
from pathlib import Path


# ============================================================================
# 全局路径
# ============================================================================

def get_fp_home() -> Path:
    """返回FP根目录 (~/.fp)"""
    value = os.getenv("FP_HOME", "~/.fp")
    return Path(value).expanduser().resolve()


def get_config_path() -> Path:
    """返回全局配置文件路径 (~/.fp/config.json)"""
    override = os.getenv("FP_CONFIG_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return get_fp_home() / "config.json"


def get_runtime_path() -> Path:
    """返回运行时状态文件路径 (~/.fp/runtime.json)"""
    return get_fp_home() / "runtime.json"


# ============================================================================
# 目录路径
# ============================================================================

def get_hosts_dir() -> Path:
    """返回hosts目录 (~/.fp/hosts)"""
    return get_fp_home() / "hosts"


def get_entities_dir() -> Path:
    """返回entities目录 (~/.fp/entities)"""
    return get_fp_home() / "entities"


def get_keys_dir() -> Path:
    """返回keys目录 (~/.fp/keys)"""
    return get_fp_home() / "keys"


def get_mailboxes_dir() -> Path:
    """返回mailboxes目录 (~/.fp/mailboxes)"""
    return get_fp_home() / "mailboxes"


def get_logs_dir() -> Path:
    """返回logs目录 (~/.fp/logs)"""
    return get_fp_home() / "logs"


def get_cache_dir() -> Path:
    """返回cache目录 (~/.fp/cache)"""
    return get_fp_home() / "cache"


def get_backups_dir() -> Path:
    """返回backups目录 (~/.fp/backups)"""
    return get_fp_home() / "backups"


# ============================================================================
# Host相关路径
# ============================================================================

def get_host_dir(host_uid: str) -> Path:
    """返回host目录 (~/.fp/hosts/{host_uid})"""
    return get_hosts_dir() / host_uid


def get_host_meta_path(host_uid: str) -> Path:
    """返回host元数据文件路径 (~/.fp/hosts/{host_uid}/meta.json)"""
    return get_host_dir(host_uid) / "meta.json"


def get_host_children_path(host_uid: str) -> Path:
    """返回host children文件路径 (~/.fp/hosts/{host_uid}/children.json)"""
    return get_host_dir(host_uid) / "children.json"


def get_host_key_path(host_uid: str) -> Path:
    """返回host密钥文件路径 (~/.fp/keys/hosts/{host_uid}.key)"""
    return get_keys_dir() / "hosts" / f"{host_uid}.key"


def get_host_log_path(host_uid: str) -> Path:
    """返回host日志文件路径 (~/.fp/logs/hosts/{host_uid}.log)"""
    return get_logs_dir() / "hosts" / f"{host_uid}.log"


# ============================================================================
# Entity相关路径
# ============================================================================

def get_entity_dir(entity_uid: str) -> Path:
    """返回entity目录 (~/.fp/entities/{entity_uid})"""
    return get_entities_dir() / entity_uid


def get_entity_meta_path(entity_uid: str) -> Path:
    """返回entity元数据文件路径 (~/.fp/entities/{entity_uid}/meta.json)"""
    return get_entity_dir(entity_uid) / "meta.json"


def get_entity_friends_path(entity_uid: str) -> Path:
    """返回entity好友列表文件路径 (~/.fp/entities/{entity_uid}/friends.json)"""
    return get_entity_dir(entity_uid) / "friends.json"


def get_entity_sessions_path(entity_uid: str) -> Path:
    """返回entity sessions文件路径 (~/.fp/entities/{entity_uid}/sessions.json)"""
    return get_entity_dir(entity_uid) / "sessions.json"


def get_entity_key_path(entity_uid: str) -> Path:
    """返回entity密钥文件路径 (~/.fp/keys/entities/{entity_uid}.key)"""
    return get_keys_dir() / "entities" / f"{entity_uid}.key"


def get_entity_mailbox_path(entity_uid: str) -> Path:
    """返回entity邮箱文件路径 (~/.fp/mailboxes/{entity_uid}.jsonl)"""
    return get_mailboxes_dir() / f"{entity_uid}.jsonl"


def get_entity_log_path(entity_uid: str) -> Path:
    """返回entity日志文件路径 (~/.fp/logs/entities/{entity_uid}.log)"""
    return get_logs_dir() / "entities" / f"{entity_uid}.log"


# ============================================================================
# 辅助函数
# ============================================================================

def ensure_parent_dir(file_path: Path) -> Path:
    """确保文件的父目录存在"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    return file_path


def ensure_dir(dir_path: Path) -> Path:
    """确保目录存在"""
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path
```

### 2. 存储管理 - `fp/storage.py`

```python
"""FP存储管理器 - 负责所有文件的读写操作"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from .utils.path import (
    get_config_path,
    get_runtime_path,
    get_host_meta_path,
    get_host_children_path,
    get_host_key_path,
    get_entity_meta_path,
    get_entity_friends_path,
    get_entity_sessions_path,
    get_entity_key_path,
    ensure_parent_dir,
    ensure_dir,
    get_keys_dir,
)


class StorageManager:
    """FP存储管理器 - 统一管理所有文件的读写操作

    职责：
    1. 初始化目录结构
    2. 读写配置文件
    3. 读写entity和host数据
    4. 管理密钥文件
    5. 权限设置
    """

    def __init__(self):
        """初始化存储管理器"""
        self._ensure_directory_structure()

    def _ensure_directory_structure(self) -> None:
        """确保所有必要的目录存在"""
        from .utils.path import (
            get_hosts_dir,
            get_entities_dir,
            get_keys_dir,
            get_mailboxes_dir,
            get_logs_dir,
            get_cache_dir,
        )

        ensure_dir(get_hosts_dir())
        ensure_dir(get_entities_dir())
        ensure_dir(get_mailboxes_dir())
        ensure_dir(get_logs_dir())
        ensure_dir(get_cache_dir())

        # keys目录需要特殊权限
        keys_dir = ensure_dir(get_keys_dir())
        self._set_secure_permissions(keys_dir)
        ensure_dir(keys_dir / "hosts")
        ensure_dir(keys_dir / "entities")

    @staticmethod
    def _set_secure_permissions(path: Path) -> None:
        """设置安全权限（仅owner可访问）"""
        try:
            path.chmod(0o700)
        except Exception as e:
            logger.warning(f"Failed to set secure permissions on {path}: {e}")

    # ========================================================================
    # 全局配置文件操作
    # ========================================================================

    def load_config(self) -> dict[str, Any]:
        """加载全局配置文件"""
        config_path = get_config_path()
        if not config_path.exists():
            return self._create_default_config()

        try:
            with config_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse config.json: {e}")
            raise

    def save_config(self, config: dict[str, Any]) -> None:
        """保存全局配置文件"""
        config_path = get_config_path()
        ensure_parent_dir(config_path)

        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def _create_default_config(self) -> dict[str, Any]:
        """创建默认配置文件"""
        default_config = {
            "version": "1.0",
            "default_host": None,
            "hosts": {},
            "entities": {},
            "settings": {
                "auto_backup": False,
                "log_level": "INFO",
                "encrypt_keys": False,
            }
        }
        self.save_config(default_config)
        return default_config

    # ========================================================================
    # Runtime状态文件操作
    # ========================================================================

    def load_runtime(self) -> dict[str, Any]:
        """加载运行时状态文件"""
        runtime_path = get_runtime_path()
        if not runtime_path.exists():
            return {"pids": {}, "updated_at": None}

        with runtime_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_runtime(self, runtime: dict[str, Any]) -> None:
        """保存运行时状态文件"""
        runtime["updated_at"] = datetime.now().isoformat()
        runtime_path = get_runtime_path()

        with runtime_path.open("w", encoding="utf-8") as f:
            json.dump(runtime, f, indent=2, ensure_ascii=False)

    def update_host_pid(self, host_uid: str, pid: int | None) -> None:
        """更新host的PID"""
        runtime = self.load_runtime()
        if pid is None:
            runtime["pids"].pop(host_uid, None)
        else:
            runtime["pids"][host_uid] = pid
        self.save_runtime(runtime)

    # ========================================================================
    # Host数据操作
    # ========================================================================

    def save_host_meta(self, host_uid: str, meta: dict[str, Any]) -> None:
        """保存host元数据"""
        meta_path = get_host_meta_path(host_uid)
        ensure_parent_dir(meta_path)

        meta.setdefault("updated_at", datetime.now().isoformat())

        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    def load_host_meta(self, host_uid: str) -> dict[str, Any] | None:
        """加载host元数据"""
        meta_path = get_host_meta_path(host_uid)
        if not meta_path.exists():
            return None

        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_host_children(self, host_uid: str, children: list[dict[str, Any]]) -> None:
        """保存host的children列表"""
        children_path = get_host_children_path(host_uid)
        ensure_parent_dir(children_path)

        with children_path.open("w", encoding="utf-8") as f:
            json.dump({"children": children}, f, indent=2, ensure_ascii=False)

    def load_host_children(self, host_uid: str) -> list[dict[str, Any]]:
        """加载host的children列表"""
        children_path = get_host_children_path(host_uid)
        if not children_path.exists():
            return []

        with children_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("children", [])

    # ========================================================================
    # Entity数据操作
    # ========================================================================

    def save_entity_meta(self, entity_uid: str, meta: dict[str, Any]) -> None:
        """保存entity元数据"""
        meta_path = get_entity_meta_path(entity_uid)
        ensure_parent_dir(meta_path)

        meta.setdefault("updated_at", datetime.now().isoformat())

        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    def load_entity_meta(self, entity_uid: str) -> dict[str, Any] | None:
        """加载entity元数据"""
        meta_path = get_entity_meta_path(entity_uid)
        if not meta_path.exists():
            return None

        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_entity_friends(self, entity_uid: str, friends: list[dict[str, Any]]) -> None:
        """保存entity的friends列表"""
        friends_path = get_entity_friends_path(entity_uid)
        ensure_parent_dir(friends_path)

        with friends_path.open("w", encoding="utf-8") as f:
            json.dump({"friends": friends}, f, indent=2, ensure_ascii=False)

    def load_entity_friends(self, entity_uid: str) -> list[dict[str, Any]]:
        """加载entity的friends列表"""
        friends_path = get_entity_friends_path(entity_uid)
        if not friends_path.exists():
            return []

        with friends_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("friends", [])

    def save_entity_sessions(self, entity_uid: str, sessions: dict[str, Any]) -> None:
        """保存entity的sessions"""
        sessions_path = get_entity_sessions_path(entity_uid)
        ensure_parent_dir(sessions_path)

        with sessions_path.open("w", encoding="utf-8") as f:
            json.dump({"sessions": sessions}, f, indent=2, ensure_ascii=False)

    def load_entity_sessions(self, entity_uid: str) -> dict[str, Any]:
        """加载entity的sessions"""
        sessions_path = get_entity_sessions_path(entity_uid)
        if not sessions_path.exists():
            return {}

        with sessions_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("sessions", {})

    # ========================================================================
    # 密钥操作
    # ========================================================================

    def save_entity_keys(
        self,
        entity_uid: str,
        sign_private_key: str,
        decrypt_private_key: str,
    ) -> None:
        """保存entity密钥（私钥）"""
        key_path = get_entity_key_path(entity_uid)
        ensure_parent_dir(key_path)

        key_data = {
            "uid": entity_uid,
            "sign_private_key": sign_private_key,
            "decrypt_private_key": decrypt_private_key,
            "created_at": datetime.now().isoformat(),
        }

        with key_path.open("w", encoding="utf-8") as f:
            json.dump(key_data, f, indent=2, ensure_ascii=False)

        # 设置密钥文件权限为600（仅owner可读写）
        self._set_secure_permissions(key_path)

    def load_entity_keys(self, entity_uid: str) -> dict[str, str] | None:
        """加载entity密钥（私钥）"""
        key_path = get_entity_key_path(entity_uid)
        if not key_path.exists():
            return None

        with key_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def delete_entity_keys(self, entity_uid: str) -> None:
        """删除entity密钥"""
        key_path = get_entity_key_path(entity_uid)
        if key_path.exists():
            key_path.unlink()

    # ========================================================================
    # 批量操作
    # ========================================================================

    def delete_entity_all_data(self, entity_uid: str) -> None:
        """删除entity的所有数据（meta、friends、sessions、keys）"""
        from .utils.path import get_entity_dir
        import shutil

        # 删除entity目录
        entity_dir = get_entity_dir(entity_uid)
        if entity_dir.exists():
            shutil.rmtree(entity_dir)

        # 删除密钥
        self.delete_entity_keys(entity_uid)

        logger.info(f"Deleted all data for entity {entity_uid}")

    def delete_host_all_data(self, host_uid: str) -> None:
        """删除host的所有数据"""
        from .utils.path import get_host_dir
        import shutil

        host_dir = get_host_dir(host_uid)
        if host_dir.exists():
            shutil.rmtree(host_dir)

        logger.info(f"Deleted all data for host {host_uid}")


# 全局单例
_storage_manager: StorageManager | None = None


def get_storage_manager() -> StorageManager:
    """获取全局StorageManager单例"""
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = StorageManager()
    return _storage_manager
```

### 3. 使用示例

```python
# ============================================================================
# 示例1: 简单场景 - 只需要路径
# ============================================================================
from fp.utils.path import get_entity_meta_path

# 获取路径
path = get_entity_meta_path("40588f71")
# Path('/Users/guyongfeng/.fp/entities/40588f71/meta.json')

# 自己读写
import json
with path.open("r") as f:
    data = json.load(f)


# ============================================================================
# 示例2: 复杂场景 - 使用StorageManager
# ============================================================================
from fp.storage import get_storage_manager

storage = get_storage_manager()

# 保存entity元数据
storage.save_entity_meta("40588f71", {
    "uid": "40588f71",
    "name": "GYF",
    "kind": "human",
    "host_uid": "9d71242b",
    "is_public": True,
})

# 加载entity元数据
meta = storage.load_entity_meta("40588f71")

# 保存密钥（自动设置权限为600）
storage.save_entity_keys(
    "40588f71",
    sign_private_key="-----BEGIN PRIVATE KEY-----\n...",
    decrypt_private_key="-----BEGIN PRIVATE KEY-----\n...",
)

# 更新运行时PID
storage.update_host_pid("9d71242b", 71317)


# ============================================================================
# 示例3: 启动恢复流程
# ============================================================================
def restore_from_storage():
    storage = get_storage_manager()

    # 1. 加载全局配置
    config = storage.load_config()

    # 2. 恢复所有hosts
    for host_uid, host_info in config["hosts"].items():
        # 加载host元数据
        host_meta = storage.load_host_meta(host_uid)

        # 加载children
        children = storage.load_host_children(host_uid)

        # 创建Host对象
        host = Host.from_dict(host_meta)

    # 3. 恢复所有entities
    for entity_uid, entity_info in config["entities"].items():
        # 加载entity元数据
        entity_meta = storage.load_entity_meta(entity_uid)

        # 加载密钥
        keys = storage.load_entity_keys(entity_uid)

        # 加载friends
        friends = storage.load_entity_friends(entity_uid)

        # 创建Entity对象
        entity = Entity.from_dict({
            **entity_meta,
            "sign_private_key": keys["sign_private_key"],
            "decrypt_private_key": keys["decrypt_private_key"],
        })

        # 关联到host
        host.entities[entity_uid] = entity
```

## 📊 启动恢复流程

```
1. 读取 config.json
   ├─> 获取所有hosts和entities的uid列表
   │
2. 对每个host:
   ├─> 读取 hosts/{host_uid}/meta.json
   ├─> 读取 hosts/{host_uid}/children.json
   └─> 创建Host对象
   │
3. 对每个entity:
   ├─> 读取 entities/{entity_uid}/meta.json
   ├─> 读取 keys/entities/{entity_uid}.key
   ├─> 读取 entities/{entity_uid}/friends.json
   ├─> 读取 entities/{entity_uid}/sessions.json（可选）
   └─> 创建Entity对象，关联到对应Host
   │
4. 启动Host:
   ├─> 根据config.json中的bind_host、port启动
   ├─> 记录PID到runtime.json
   └─> 连接parent host（如果有）
```

## 🔄 迁移策略

从旧结构迁移到新结构的步骤：

```python
def migrate_storage():
    """从旧存储结构迁移到新结构"""
    from fp.storage import get_storage_manager
    from aln.app import HostConfig
    import json

    storage = get_storage_manager()
    old_config = HostConfig()

    # 1. 创建新的config.json
    new_config = {
        "version": "1.0",
        "default_host": None,
        "hosts": {},
        "entities": {},
        "settings": {
            "auto_backup": False,
            "log_level": "INFO",
            "encrypt_keys": False,
        }
    }

    # 2. 迁移hosts
    for host_name, host_data in old_config.get_hosts().items():
        host_uid = host_data["address"].split(":")[0]

        # 保存到new_config
        new_config["hosts"][host_uid] = {
            "name": host_name,
            "bind_host": host_data.get("bind_host", "0.0.0.0"),
            "port": host_data.get("port", 7000),
            "parent_uid": None,
            "enabled": True,
        }

        # 保存host meta
        storage.save_host_meta(host_uid, {
            "uid": host_uid,
            "name": host_name,
            "address": host_data["address"],
            "bind_host": host_data.get("bind_host", "0.0.0.0"),
            "port": host_data.get("port", 7000),
            "url": host_data.get("url"),
            "parent_url": host_data.get("parent_url"),
        })

        # 3. 迁移state.json中的entities
        state_path = old_config.get_host_state_path(host_name)
        if state_path.exists():
            with open(state_path) as f:
                state = json.load(f)

            # 迁移entities
            for entity_uid, entity_data in state.get("entities", {}).items():
                # 保存到new_config
                new_config["entities"][entity_uid] = {
                    "name": entity_data.get("name"),
                    "kind": entity_data.get("kind"),
                    "host_uid": host_uid,
                    "is_public": entity_data.get("is_public", False),
                    "enabled": True,
                }

                # 保存entity meta（不含私钥）
                storage.save_entity_meta(entity_uid, {
                    "uid": entity_uid,
                    "name": entity_data.get("name"),
                    "kind": entity_data.get("kind"),
                    "host_uid": host_uid,
                    "address": entity_data.get("address"),
                    "keys": {
                        "sign_public_key": entity_data.get("sign_public_key"),
                        "encrypt_public_key": entity_data.get("encrypt_public_key"),
                        "key_file": f"keys/entities/{entity_uid}.key",
                    },
                    "is_public": entity_data.get("is_public", False),
                    "visible": entity_data.get("visible", True),
                    "enabled": entity_data.get("enabled", True),
                })

                # 保存私钥
                storage.save_entity_keys(
                    entity_uid,
                    sign_private_key=entity_data.get("sign_private_key"),
                    decrypt_private_key=entity_data.get("decrypt_private_key"),
                )

                # 保存friends
                friends = [
                    friend for friend in entity_data.get("friends", {}).values()
                ]
                storage.save_entity_friends(entity_uid, friends)

    # 4. 保存新config.json
    storage.save_config(new_config)

    print("Migration completed!")
```

## 🎯 设计优势总结

1. **清晰分离**: 配置、数据、密钥、日志完全分开
2. **安全性**: 密钥独立存储，权限隔离（600）
3. **可扩展**: 每个entity一个folder，便于添加新数据类型
4. **性能**: 按需加载，避免读取整个state文件
5. **易维护**: 文件组织清晰，便于备份和恢复
6. **代码质量**:
   - 路径函数纯净无副作用
   - StorageManager封装复杂逻辑
   - 分离关注点，单一职责
7. **遵循规范**: 使用Pathlib，返回Path对象

## 📝 注意事项

1. **兼容性**: 需要实现迁移脚本从旧结构迁移到新结构
2. **事务性**: 未来可以考虑添加事务支持（原子写入）
3. **并发**: 当前未考虑并发写入，如需要可加文件锁
4. **备份**: 建议定期备份config.json和keys目录
5. **加密**: 未来可以对keys目录整体加密

## 🚀 下一步

1. ✅ 完成文档设计
2. ⏳ 实现新的path.py
3. ⏳ 实现StorageManager类
4. ⏳ 实现迁移脚本
5. ⏳ 更新Host/Entity的save/load逻辑
6. ⏳ 更新启动恢复流程
7. ⏳ 测试新存储结构
8. ⏳ 发布新版本

---

**文档版本**: 1.0
**最后更新**: 2026-04-02
**作者**: Foundation Protocol Team
