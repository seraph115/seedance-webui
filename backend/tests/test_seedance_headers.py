import seedance
import settings_store


def test_headers_read_live_key(monkeypatch):
    monkeypatch.setattr(settings_store, "get_api_key", lambda: "live-key-123")
    assert seedance._headers()["Authorization"] == "Bearer live-key-123"
    assert seedance._headers()["Content-Type"] == "application/json"
