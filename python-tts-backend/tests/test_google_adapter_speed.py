import json

from app.tts.google_adapter import GoogleTranslateAdapter


class DummyTokenManager:
    def get_tokens(self):
        return {"f.sid": "fsid", "bl": "bl", "at": "at"}


def test_adapter_fallbacks_to_default_speed_when_custom_payload_invalid(monkeypatch):
    adapter = GoogleTranslateAdapter(token_manager=DummyTokenManager(), request_timeout_sec=20, user_agent="ua")

    calls = {"count": 0}

    class DummyResponse:
        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self):
            return None

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return DummyResponse("not-parseable")
        return DummyResponse('123\n[["wrb.fr","jQ1olc","[\\"BASE64_AUDIO\\"]"]]')

    monkeypatch.setattr("app.tts.google_adapter.requests.post", fake_post)

    audio = adapter.synthesize_base64("xin chao", "vi", reqid=10001, speed=1.3)
    assert audio == "BASE64_AUDIO"
    assert calls["count"] == 2
