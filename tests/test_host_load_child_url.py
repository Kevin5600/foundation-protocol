"""Regression tests for host child URL loading."""

from __future__ import annotations

from fp.host import Host


def test_load_restores_child_host_port_from_children_url() -> None:
    """Host.load should preserve child host port encoded in children URL."""
    parent = Host(name="hub", bind_host="0.0.0.0", port=7001)
    child = Host(name="ops", bind_host="0.0.0.0", port=7003)

    parent._set_child_host(child.get_wellknown())
    parent.save()

    loaded_parent = Host.load(parent.uid)
    loaded_child = loaded_parent.child_hosts[child.uid]

    assert loaded_child.port == 7003
    assert loaded_child.url == "http://127.0.0.1:7003"
