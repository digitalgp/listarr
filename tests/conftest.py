from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import requests


class FakeResponse:
    def __init__(
        self,
        json_data: Any = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ):
        self.json_data = json_data
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        if isinstance(self.json_data, Exception):
            raise self.json_data
        return self.json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}", response=self
            )


class FakeSession:
    def __init__(self):
        self.params: dict[str, str] = {}
        self.responses: deque[FakeResponse] = deque()
        self.route_responses: dict[str, deque[FakeResponse]] = defaultdict(deque)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def queue(self, *responses: FakeResponse):
        self.responses.extend(responses)

    def route(self, suffix: str, *responses: FakeResponse):
        self.route_responses[suffix].extend(responses)

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError(f"No fake response queued for {method} {url}")
        return self.responses.popleft()

    def get(self, url, **kwargs):
        self.calls.append({"method": "GET", "url": url, **kwargs})
        for suffix, responses in self.route_responses.items():
            if url.endswith(suffix):
                if not responses:
                    raise AssertionError(f"No fake response left for {suffix}")
                return responses.popleft()
        if self.responses:
            return self.responses.popleft()
        raise AssertionError(f"No fake response configured for GET {url}")

    def close(self):
        self.closed = True
