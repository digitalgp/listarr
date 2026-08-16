"""Data shared by Arr sources and MDBList synchronization."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FilterOptions:
    monitored_only: bool = False
    missing_only: bool = False
    quality_profile: str | None = None
    tag: str | None = None
    genres: tuple[str, ...] = ()


@dataclass(frozen=True)
class MediaItem:
    provider_id: int
    imdb_id: str | None
    title: str
    monitored: bool
    quality_profile_id: int | None
    tag_ids: tuple[int, ...]
    has_file: bool | None
    genres: tuple[str, ...]


@dataclass(frozen=True)
class NotFoundItem:
    title: str
    provider: str
    provider_id: int | None
    imdb_id: str | None


@dataclass(frozen=True)
class SyncResult:
    source: str
    list_id: int | None
    selected: int
    planned_add: int
    planned_remove: int
    added: int
    removed: int
    existing: int
    not_found: int
    dry_run: bool
    not_found_items: tuple[NotFoundItem, ...] = ()
