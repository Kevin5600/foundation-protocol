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


def ensure_parent_dir(file_path: Path) -> Path:
    """确保文件的父目录存在"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    return file_path


def ensure_dir(dir_path: Path) -> Path:
    """确保目录存在"""
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path
