"""MDBList static-list API client and synchronization logic."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import requests

from listarr.errors import APIError, RateLimitError
from listarr.models import MediaItem, SyncResult


@dataclass(frozen=True)
class ExistingItem:
    provider_id: int | None
    imdb_id: str | None


class MDBListClient:
    BATCH_SIZE = 500
    MEDIA = {
        "Radarr": ("movies", "movie", "tmdb"),
        "Sonarr": ("shows", "show", "tvdb"),
    }

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.mdblist.com",
        timeout: int = 30,
        session: requests.Session | None = None,
        max_rate_limit_wait: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_rate_limit_wait = max_rate_limit_wait
        self.session = session or requests.Session()
        self.session.params.update({"apikey": api_key})

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        for attempt in range(2):
            try:
                response = self.session.request(
                    method,
                    f"{self.base_url}{path}",
                    timeout=self.timeout,
                    **kwargs,
                )
            except requests.RequestException as error:
                raise APIError("MDBList API connection failed") from error

            if response.status_code == 429:
                try:
                    retry_after = int(response.headers.get("Retry-After", "1"))
                except ValueError:
                    retry_after = 1

                if attempt == 0 and retry_after <= self.max_rate_limit_wait:
                    time.sleep(max(retry_after, 0))
                    continue

                remaining = response.headers.get("X-RateLimit-Remaining", "0")
                raise RateLimitError(
                    "MDBList rate limit reached "
                    f"(remaining: {remaining}, retry after: {retry_after}s)"
                )

            try:
                response.raise_for_status()
            except requests.HTTPError as error:
                raise APIError(
                    f"MDBList API request failed with HTTP {response.status_code}"
                ) from error
            return response

        raise APIError("MDBList API request failed after retry")  # pragma: no cover

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._request(method, path, **kwargs)
        try:
            return response.json()
        except ValueError as error:
            raise APIError("MDBList returned invalid JSON") from error

    def resolve_static_list(
        self,
        list_id: int | None,
        name: str,
        private: bool,
        *,
        create: bool = True,
        enforce_privacy: bool = True,
    ) -> int | None:
        if list_id is not None:
            self._enforce_privacy(list_id, private, enforce_privacy)
            return list_id

        lists = self._json(
            "GET", "/lists/user", params={"sort": "name", "unified": "true"}
        )
        if not isinstance(lists, list):
            raise APIError("MDBList returned an unexpected list response")

        matches = [item for item in lists if item.get("name") == name]
        if len(matches) > 1:
            raise APIError(
                f"Several MDBList lists are named {name!r}; configure mdblist_list_id"
            )
        if matches:
            resolved = int(matches[0]["id"])
            self._enforce_privacy(resolved, private, enforce_privacy)
            return resolved
        if not create:
            return None

        created = self._json(
            "POST", "/lists/user/add", json={"name": name, "private": private}
        )
        try:
            return int(created["id"])
        except (KeyError, TypeError, ValueError) as error:
            raise APIError("MDBList did not return the created list ID") from error

    def _enforce_privacy(
        self, list_id: int, private: bool, enforce_privacy: bool
    ) -> None:
        metadata = self._json("GET", f"/lists/{list_id}")
        current = bool(metadata.get("private", False))
        if enforce_privacy and current != private:
            self._json(
                "PUT", f"/lists/{list_id}", json={"private": private}
            )

    @staticmethod
    def _next_cursor(page: dict[str, Any]) -> str | None:
        pagination = page.get("pagination") or {}
        return pagination.get("next_cursor") or page.get("next_cursor")

    def get_items(self, list_id: int, source: str) -> list[ExistingItem]:
        bucket, media_type, provider = self.MEDIA[source]
        cursor: str | None = None
        existing: list[ExistingItem] = []

        while True:
            params: dict[str, Any] = {
                "limit": 1000,
                "mediatype": media_type,
            }
            if cursor:
                params["cursor"] = cursor

            response = self._request(
                "GET", f"/lists/{list_id}/items", params=params
            )
            try:
                page = response.json()
            except ValueError as error:
                raise APIError("MDBList returned invalid list item JSON") from error

            for item in page.get(bucket, []):
                ids = item.get("ids") or {}
                provider_id = ids.get(provider) or item.get(f"{provider}_id")
                if provider == "tmdb" and provider_id is None:
                    provider_id = item.get("id")
                imdb_id = ids.get("imdb") or item.get("imdb_id") or None
                existing.append(
                    ExistingItem(
                        provider_id=(
                            int(provider_id) if provider_id is not None else None
                        ),
                        imdb_id=imdb_id,
                    )
                )

            cursor = self._next_cursor(page)
            if not cursor:
                if response.headers.get("X-Has-More", "false").lower() == "true":
                    raise APIError(
                        "MDBList reported more items but returned no pagination cursor"
                    )
                return existing

    @staticmethod
    def _batches(items: Sequence[dict[str, Any]], size: int) -> Iterable[list[dict]]:
        for index in range(0, len(items), size):
            yield list(items[index : index + size])

    def _modify(
        self,
        list_id: int,
        action: str,
        bucket: str,
        items: Sequence[dict[str, Any]],
    ) -> None:
        for batch in self._batches(items, self.BATCH_SIZE):
            self._json(
                "POST",
                f"/lists/{list_id}/items/{action}",
                json={bucket: batch},
            )

    def sync(
        self,
        *,
        source: str,
        list_id: int | None,
        items: Sequence[MediaItem],
        concatenate: bool = False,
        wipe: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        if source not in self.MEDIA:
            raise APIError(f"Unsupported source: {source}")
        if list_id is None and not dry_run:
            raise APIError("A real synchronization requires an MDBList list ID")

        bucket, _media_type, provider = self.MEDIA[source]
        current = self.get_items(list_id, source) if list_id is not None else []

        desired_by_provider = {item.provider_id: item for item in items}
        desired_imdb = {item.imdb_id for item in items if item.imdb_id}
        current_provider = {
            item.provider_id for item in current if item.provider_id is not None
        }
        current_imdb = {item.imdb_id for item in current if item.imdb_id}

        additions = []
        for item in items:
            already_present = item.provider_id in current_provider or (
                item.imdb_id is not None and item.imdb_id in current_imdb
            )
            if wipe or not already_present:
                payload: dict[str, Any] = {provider: item.provider_id}
                if item.imdb_id:
                    payload["imdb"] = item.imdb_id
                additions.append(payload)

        removals = []
        if not concatenate:
            for item in current:
                still_wanted = (
                    item.provider_id is not None
                    and item.provider_id in desired_by_provider
                ) or (item.imdb_id is not None and item.imdb_id in desired_imdb)
                if wipe or not still_wanted:
                    if item.provider_id is not None:
                        removals.append({provider: item.provider_id})
                    elif item.imdb_id:
                        removals.append({"imdb": item.imdb_id})

        if not dry_run:
            assert list_id is not None
            self._modify(list_id, "remove", bucket, removals)
            self._modify(list_id, "add", bucket, additions)

        return SyncResult(
            source=source,
            list_id=list_id,
            selected=len(items),
            added=len(additions),
            removed=len(removals),
            dry_run=dry_run,
        )

    def close(self) -> None:
        self.session.close()
