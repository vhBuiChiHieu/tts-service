import json
from urllib.parse import urlencode

import requests


def parse_batchexecute_audio_base64(body: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("[[") and "jQ1olc" in line:
            outer = json.loads(line)
            payload = outer[0][2]
            inner = json.loads(payload)
            return inner[0]
    raise ValueError("cannot parse batchexecute response")


class GoogleTranslateAdapter:
    def __init__(self, token_manager, request_timeout_sec: int, user_agent: str) -> None:
        self.token_manager = token_manager
        self.request_timeout_sec = request_timeout_sec
        self.user_agent = user_agent

    def synthesize_base64(self, text: str, lang: str, reqid: int) -> str:
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
        f_req = json.dumps([[["jQ1olc", json.dumps([text, lang, None]), None, "generic"]]])
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
        return parse_batchexecute_audio_base64(response.text)
