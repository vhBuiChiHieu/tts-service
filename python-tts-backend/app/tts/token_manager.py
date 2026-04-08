import re
import time
from dataclasses import dataclass

import requests


def parse_tokens(html: str) -> dict[str, str]:
    fsid = re.search(r'"FdrFJe":"(.*?)"', html)
    bl = re.search(r'"cfb2h":"(.*?)"', html)
    at = re.search(r'"SNlM0e":"(.*?)"', html)
    if not fsid or not bl:
        raise ValueError("cannot parse tokens")
    return {"f.sid": fsid.group(1), "bl": bl.group(1), "at": at.group(1) if at else ""}


@dataclass
class TokenCache:
    tokens: dict[str, str] | None = None
    expires_at: float = 0.0


class TokenManager:
    def __init__(self, ttl_sec: int, user_agent: str) -> None:
        self.ttl_sec = ttl_sec
        self.user_agent = user_agent
        self.cache = TokenCache()

    def get_tokens(self) -> dict[str, str]:
        now = time.time()
        if self.cache.tokens and now < self.cache.expires_at:
            return self.cache.tokens

        response = requests.get(
            "https://translate.google.com/",
            headers={"User-Agent": self.user_agent},
            timeout=15,
        )
        response.raise_for_status()

        tokens = parse_tokens(response.text)
        self.cache.tokens = tokens
        self.cache.expires_at = now + self.ttl_sec
        return tokens

    def invalidate(self) -> None:
        self.cache = TokenCache()
