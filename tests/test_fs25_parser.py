import xml.etree.ElementTree as ET
import pytest
import requests
from fs25_parser import parse_snapshot, fetch_xml


def test_parse_example_xml():
    with open("example.xml", "r", encoding="utf-8") as fh:
        text = fh.read()

    root = ET.fromstring(text)
    snapshot = parse_snapshot(root)

    assert snapshot.server_name == "The Patch Farming"
    assert snapshot.map_name == "Riverbend Springs"
    assert "matthew" in snapshot.players
    assert snapshot.slots_capacity == 4
    # Owned fields should include at least field '2' as per example
    assert "2" in snapshot.owned_fields
    # Mods should be present
    assert len(snapshot.mods) > 0
    # Stock should include known fill types (e.g. LETTUCE appears)
    assert any(k in ("LETTUCE", "CANOLA_OIL", "HONEY") for k in snapshot.stock.keys())


def test_fetch_xml_invalid_url_raises():
    with pytest.raises(ValueError):
        fetch_xml("", timeout=1)


def test_fetch_xml_invalid_xml_raises(monkeypatch):
    class DummyResponse:
        text = "<Server><Bad></Server>"
        def raise_for_status(self):
            return None

    def fake_get(url, timeout):
        return DummyResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(ET.ParseError):
        fetch_xml("http://example.com/bad.xml", timeout=1)
