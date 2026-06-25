import requests
import time
from fs25_parser import ServerSnapshot, FieldInfo
from alerts import AlertManager


def make_snapshot(players=None, owned_fields=None, production_counts=None):
    return ServerSnapshot(
        server_name="s",
        game="g",
        version="v",
        map_name="m",
        slots_capacity=4,
        slots_used=0,
        players=set(players or []),
        mods=[],
        owned_fields=owned_fields or {},
        stock={},
        production_counts=production_counts or {},
        vehicles=[],
    )


def test_send_retries(monkeypatch):
    calls = []

    class FailResp:
        def raise_for_status(self):
            raise requests.HTTPError("boom")

    def fake_post(url, json, timeout):
        calls.append(1)
        return FailResp()

    monkeypatch.setattr(requests, "post", fake_post)
    # avoid real sleeping
    monkeypatch.setattr(time, "sleep", lambda s: None)

    manager = AlertManager("http://example")
    manager.send("hello")

    # default max_attempts is 3 in send()
    assert len(calls) == 3


def test_process_join_leave(monkeypatch):
    sent = []

    def fake_send(self, msg):
        sent.append(msg)

    monkeypatch.setattr(AlertManager, "send", fake_send, raising=False)

    manager = AlertManager("")

    before = make_snapshot(players=[], owned_fields={})
    after = make_snapshot(players=["alice"], owned_fields={"1": FieldInfo(id="1", area=1.0, value=100.0)})

    # first process should mark_online and set last_snapshot
    manager.process(after)
    assert any("online" in msg.lower() for msg in sent)

    sent.clear()
    manager.last_snapshot = after

    # simulate player joining
    newer = make_snapshot(players=["alice", "bob"], owned_fields=after.owned_fields)
    manager.process(newer)
    assert any("joined" in msg.lower() for msg in sent)

    sent.clear()
    # simulate player leaving
    manager.process(after)
    assert any("left" in msg.lower() for msg in sent)
