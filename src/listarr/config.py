"""INI configuration loading and validation."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from listarr.errors import ConfigurationError


@dataclass(frozen=True)
class MDBListSettings:
    api_key: str
    base_url: str
    timeout: int


@dataclass(frozen=True)
class ArrSettings:
    url: str
    api_key: str


@dataclass(frozen=True)
class DestinationSettings:
    list_id: int | None
    list_name: str
    private: bool


class Configuration:
    def __init__(self, path: Path):
        self.path = path
        self.parser = configparser.ConfigParser()

        if not path.is_file():
            raise ConfigurationError(
                f"Configuration file not found: {path}. "
                "Copy example-listarr.conf and fill in your credentials."
            )

        try:
            with path.open(encoding="utf-8") as config_file:
                self.parser.read_file(config_file)
        except (OSError, configparser.Error) as error:
            raise ConfigurationError(f"Could not read {path}: {error}") from error

    @staticmethod
    def default_path() -> Path:
        return Path.home() / ".config" / "listarr.conf"

    def mdblist(self, timeout_override: int | None = None) -> MDBListSettings:
        if not self.parser.has_section("MDBList"):
            raise ConfigurationError("Missing [MDBList] configuration section")

        api_key = os.environ.get(
            "LISTARR_MDBLIST_API_KEY",
            self.parser.get("MDBList", "api_key", fallback=""),
        ).strip()
        if not api_key:
            raise ConfigurationError(
                "MDBList API key is empty; configure api_key or "
                "LISTARR_MDBLIST_API_KEY"
            )

        base_url = self.parser.get(
            "MDBList", "base_url", fallback="https://api.mdblist.com"
        ).strip().rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError("[MDBList] base_url must be an HTTP(S) URL")

        try:
            timeout = timeout_override or self.parser.getint(
                "MDBList", "timeout", fallback=30
            )
        except ValueError as error:
            raise ConfigurationError("[MDBList] timeout must be an integer") from error
        if timeout <= 0:
            raise ConfigurationError("[MDBList] timeout must be greater than zero")

        return MDBListSettings(api_key=api_key, base_url=base_url, timeout=timeout)

    def arr(self, source: str) -> ArrSettings:
        if not self.parser.has_section(source):
            raise ConfigurationError(f"Missing [{source}] configuration section")

        url = self.parser.get(source, "url", fallback="").strip().rstrip("/")
        api_key = self.parser.get(source, "api_key", fallback="").strip()
        parsed = urlsplit(url)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError(f"[{source}] url must be an HTTP(S) URL")
        if not api_key:
            raise ConfigurationError(f"[{source}] api_key is empty")

        return ArrSettings(url=url, api_key=api_key)

    def destination(self, source: str) -> DestinationSettings:
        raw_id = self.parser.get(
            source, "mdblist_list_id", fallback=""
        ).strip()
        try:
            list_id = int(raw_id) if raw_id else None
        except ValueError as error:
            raise ConfigurationError(
                f"[{source}] mdblist_list_id must be an integer"
            ) from error

        list_name = self.parser.get(
            source, "mdblist_list_name", fallback=source
        ).strip()
        if list_id is None and not list_name:
            raise ConfigurationError(
                f"[{source}] needs mdblist_list_id or mdblist_list_name"
            )

        try:
            private = self.parser.getboolean(
                source, "mdblist_list_private", fallback=True
            )
        except ValueError as error:
            raise ConfigurationError(
                f"[{source}] mdblist_list_private must be true or false"
            ) from error

        return DestinationSettings(
            list_id=list_id,
            list_name=list_name or source,
            private=private,
        )
