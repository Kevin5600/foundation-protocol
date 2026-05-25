"""Pytest configuration and shared fixtures."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_fp_home(monkeypatch):
    """自动隔离 FP_HOME 和 mailbox 路径，防止测试污染真实环境"""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("FP_HOME", tmpdir)
        tmp = Path(tmpdir)
        monkeypatch.setattr(
            "fp.host.Host._default_mailbox_path",
            lambda self, entity_uid: str(tmp / "mailboxes" / f"{entity_uid}.jsonl"),
        )
        yield tmp


@pytest.fixture
def temp_dir():
    """创建临时目录供测试使用"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
