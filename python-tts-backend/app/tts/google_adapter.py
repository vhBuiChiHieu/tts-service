import json
import logging
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)


def parse_batchexecute_audio_base64(body: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("[[") and "jQ1olc" in line:
            try:
                outer = json.loads(line)
                payload = outer[0][2]
                inner = json.loads(payload)
                return inner[0]
            except (TypeError, json.JSONDecodeError, IndexError):
                break
    raise ValueError("cannot parse batchexecute response")


class GoogleTranslateAdapter:
    def __init__(self, token_manager, request_timeout_sec: int, user_agent: str) -> None:
        self.token_manager = token_manager
        self.request_timeout_sec = request_timeout_sec
        self.user_agent = user_agent

    def _build_rpc_payload(self, text: str, lang: str, speed: float) -> str:
        if speed == 1.0:
            inner = [text, lang, None]
        else:
            inner = [text, lang, None, speed]
        return json.dumps([[["jQ1olc", json.dumps(inner), None, "generic"]]])

    def _post_batchexecute(self, f_req: str, reqid: int) -> str:
        tokens = self.token_manager.get_tokens()
        query = {
            "rpcids": "jQ1olc",
            "f.sid": tokens["f.sid"],
            "bl": tokens["bl"],
            "hl": "en",
            "soc-app": "1",
            "soc-platform": "1",
            "soc-device": "1",
            "_reqid": str(reqid),
            "rt": "c",
        }
        body = urlencode({"f.req": f_req, "at": tokens["at"]})
        response = requests.post(
            f"https://translate.google.com/_/TranslateWebserverUi/data/batchexecute?{urlencode(query)}",
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                "User-Agent": self.user_agent,
            },
            timeout=self.request_timeout_sec,
        )
        response.raise_for_status()
        return response.text

    def synthesize_base64(self, text: str, lang: str, reqid: int, speed: float = 1.0) -> str:
        f_req = self._build_rpc_payload(text, lang, speed)
        response_text = self._post_batchexecute(f_req=f_req, reqid=reqid)
        try:
            return parse_batchexecute_audio_base64(response_text)
        except ValueError:
            logger.warning("batchexecute parse failed; reqid=%s speed=%s raw=%r textInput=%s", reqid, speed, response_text, text)
            if speed == 1.0:
                raise

        fallback_f_req = self._build_rpc_payload(text, lang, 1.0)
        fallback_response = self._post_batchexecute(fallback_f_req, reqid=reqid)
        try:
            return parse_batchexecute_audio_base64(fallback_response)
        except ValueError:
            logger.warning("batchexecute parse failed on fallback; reqid=%s raw=%r", reqid, fallback_response)
            raise
