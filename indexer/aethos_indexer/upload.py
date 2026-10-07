"""HTTP client for the Aethos ingest API, with size-bounded batching."""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Iterator
from typing import Any

import httpx

MAX_BATCH_BYTES = 1_200_000
MAX_FILES_PER_BATCH = 200
MAX_EDGES_PER_BATCH = 5000
RETRIES = 3


def batched(
    items: list[dict[str, Any]], max_items: int, max_bytes: int = MAX_BATCH_BYTES
) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    size = 0
    for item in items:
        item_size = len(json.dumps(item, separators=(",", ":")))
        if batch and (len(batch) >= max_items or size + item_size > max_bytes):
            yield batch
            batch, size = [], 0
        batch.append(item)
        size += item_size
    if batch:
        yield batch


class IndexApi:
    def __init__(self, base_url: str, token: str, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/") + "/api/index", timeout=60.0
        )
        self._headers = {"Authorization": f"Bearer {token}"}

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        last: Exception | None = None
        for attempt in range(RETRIES):
            try:
                response = self._client.request(method, path, json=body, headers=self._headers)
                if response.status_code < 400:
                    return response.json()
                if response.status_code < 500:
                    raise RuntimeError(
                        f"{method} {path} -> {response.status_code}: {response.text[:300]}"
                    )
                last = RuntimeError(f"{method} {path} -> {response.status_code}")
            except httpx.TransportError as exc:
                last = exc
            time.sleep(2**attempt)
        raise RuntimeError(f"{method} {path} failed after {RETRIES} attempts: {last}")

    def state(self) -> dict[str, Any]:
        result: dict[str, Any] = self._call("GET", "/state")
        return result

    def begin(self, sha: str, files: list[dict[str, str]]) -> dict[str, Any]:
        result: dict[str, Any] = self._call("POST", "/begin", {"sha": sha, "files": files})
        return result

    def files(self, sha: str, files: list[dict[str, Any]]) -> None:
        self._call("POST", "/files", {"sha": sha, "files": files})

    def edges(self, edges: list[dict[str, Any]], *, first: bool) -> None:
        self._call("POST", "/edges", {"first": first, "edges": edges})

    def finalize(self, sha: str) -> dict[str, Any]:
        result: dict[str, Any] = self._call("POST", "/finalize", {"sha": sha})
        return result

    def fail(self) -> None:
        with contextlib.suppress(RuntimeError):
            self._call("POST", "/fail", {})
