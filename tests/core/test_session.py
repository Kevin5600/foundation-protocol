"""Tests for fp.core.session.Session."""

from __future__ import annotations

from fp.core.session import Session, SessionKind


def test_session_external_refs_default_empty() -> None:
    session = Session(session_id="s-1")
    assert session.external_refs == {}


def test_session_external_refs_roundtrip() -> None:
    session = Session(session_id="s-1")
    session.external_refs["a2a.context_id"] = "ctx-abc"
    session.external_refs["a2a.task_id"] = "task-xyz"

    payload = session.model_dump_json()
    restored = Session.model_validate_json(payload)

    assert restored.external_refs == {
        "a2a.context_id": "ctx-abc",
        "a2a.task_id": "task-xyz",
    }


def test_session_external_refs_backward_compatible_missing_key() -> None:
    """Legacy JSON without external_refs deserializes with empty default."""
    legacy_json = '{"session_id": "s-legacy", "kind": "manual"}'
    session = Session.model_validate_json(legacy_json)
    assert session.external_refs == {}
    assert session.kind == SessionKind.MANUAL
