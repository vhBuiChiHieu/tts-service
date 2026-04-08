from app.tts.google_adapter import parse_batchexecute_audio_base64
from app.tts.token_manager import parse_tokens


def test_parse_tokens_from_html():
    html = '"FdrFJe":"fsid123","cfb2h":"bl123","SNlM0e":"at123"'
    tokens = parse_tokens(html)
    assert tokens["f.sid"] == "fsid123"
    assert tokens["bl"] == "bl123"
    assert tokens["at"] == "at123"


def test_parse_batchexecute_payload():
    body = '123\n[["wrb.fr","jQ1olc","[\\"BASE64_AUDIO\\"]"]]'
    assert parse_batchexecute_audio_base64(body) == "BASE64_AUDIO"


def test_parse_tokens_without_snlm0e_allows_missing_at():
    html = '"FdrFJe":"fsid123","cfb2h":"bl123"'
    tokens = parse_tokens(html)
    assert tokens["f.sid"] == "fsid123"
    assert tokens["bl"] == "bl123"
    assert tokens["at"] == ""
