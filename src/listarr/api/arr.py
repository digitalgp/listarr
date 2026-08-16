"""Radarr and Sonarr API client."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote, urlsplit, urlunsplit

import requests

from listarr.errors import APIError, ConfigurationError
from listarr.models import FilterOptions, MediaItem


@dataclass(frozen=True)
class SourceDefinition:
    endpoint: str
    provider_field: str


SOURCES = {
    "Radarr": SourceDefinition(endpoint="movie", provider_field="tmdbId"),
    "Sonarr": SourceDefinition(endpoint="series", provider_field="tvdbId"),
}


class ArrClient:
    def __init__(
        self,
        source: str,
        url: str,
        api_key: str,
        timeout: int = 30,
        session: requests.Session | None = None,
    ):
        if source not in SOURCES:
            raise ConfigurationError(f"Unsupported Arr source: {source}")

        parsed = urlsplit(url.rstrip("/"))
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        netloc = f"{host}:{parsed.port}" if parsed.port else host

        self.source = source
        self.definition = SOURCES[source]
        self.base_url = urlunsplit(
            (parsed.scheme, netloc, parsed.path.rstrip("/"), "", "")
        )
        self.auth = (
            (unquote(parsed.username), unquote(parsed.password))
            if parsed.username is not None and parsed.password is not None
            else None
        )
        self.api_key = api_key
        self.timeout = timeout
        self.session = session or requests.Session()

    def _get(self, endpoint: str) -> list[dict]:
        try:
            response = self.session.get(
                f"{self.base_url}/api/v3/{endpoint}",
                params={"apikey": self.api_key},
                auth=self.auth,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            detail = f" HTTP {status}." if status else ""
            raise APIError(f"{self.source} API request failed.{detail}") from error
        except ValueError as error:
            raise APIError(f"{self.source} returned invalid JSON") from error

        if not isinstance(data, list):
            raise APIError(f"{self.source} returned an unexpected response")
        return data

    def _lookup_id(self, endpoint: str, field: str, wanted: str) -> int:
        wanted_folded = wanted.casefold()
        for item in self._get(endpoint):
            if str(item.get(field, "")).casefold() == wanted_folded:
                return int(item["id"])
        raise ConfigurationError(
            f"{self.source}: no {endpoint} named {wanted!r} was found"
        )

    def get_items(self, filters: FilterOptions) -> list[MediaItem]:
        quality_id = (
            self._lookup_id("qualityprofile", "name", filters.quality_profile)
            if filters.quality_profile
            else None
        )
        tag_id = (
            self._lookup_id("tag", "label", filters.tag) if filters.tag else None
        )
        wanted_genres = {genre.casefold() for genre in filters.genres}

        selected: list[MediaItem] = []
        for raw in self._get(self.definition.endpoint):
            provider_id = raw.get(self.definition.provider_field)
            if provider_id in (None, 0):
                continue

            monitored = bool(raw.get("monitored"))
            profile_id = raw.get("qualityProfileId")
            tags = tuple(int(tag) for tag in raw.get("tags", []))
            has_file = raw.get("hasFile") if self.source == "Radarr" else None
            genres = tuple(str(genre) for genre in raw.get("genres", []))

            if filters.monitored_only and not monitored:
                continue
            if quality_id is not None and profile_id != quality_id:
                continue
            if tag_id is not None and tag_id not in tags:
                continue
            if self.source == "Radarr" and filters.missing_only and has_file:
                continue
            if wanted_genres and not wanted_genres.intersection(
                genre.casefold() for genre in genres
            ):
                continue

            selected.append(
                MediaItem(
                    provider_id=int(provider_id),
                    imdb_id=raw.get("imdbId") or None,
                    title=str(raw.get("title") or provider_id),
                    monitored=monitored,
                    quality_profile_id=(
                        int(profile_id) if profile_id is not None else None
                    ),
                    tag_ids=tags,
                    has_file=has_file,
                    genres=genres,
                )
            )

        return selected

    def close(self) -> None:
        self.session.close()
