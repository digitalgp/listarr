"""Listarr command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from listarr import __version__
from listarr.api import ArrClient, MDBListClient
from listarr.config import Configuration, DestinationSettings
from listarr.errors import ListarrError
from listarr.models import FilterOptions, SyncResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize Radarr/Sonarr libraries to MDBList lists"
    )
    source = parser.add_argument_group("sources")
    source.add_argument(
        "--radarr", "-r", action="store_true", help="Synchronize Radarr movies"
    )
    source.add_argument(
        "--sonarr", "-s", action="store_true", help="Synchronize Sonarr series"
    )
    source.add_argument(
        "--all", "-a", action="store_true", help="Synchronize Radarr and Sonarr"
    )

    filters = parser.add_argument_group("filters")
    filters.add_argument(
        "--mon", "-m", action="store_true", help="Only include monitored content"
    )
    filters.add_argument(
        "--missing",
        action="store_true",
        help="Only include missing Radarr movies (ignored for Sonarr)",
    )
    filters.add_argument(
        "--qualityprofile", "-qp", help="Only include this quality profile"
    )
    filters.add_argument("--tag", "-t", help="Only include this Arr tag")
    filters.add_argument(
        "--genre",
        "-g",
        help="Comma-separated genres; an item may match any supplied genre",
    )

    behavior = parser.add_argument_group("synchronization")
    behavior.add_argument(
        "--cat",
        "-c",
        action="store_true",
        help="Append without removing existing MDBList entries",
    )
    behavior.add_argument(
        "--wipe",
        "-w",
        action="store_true",
        help="Replace every list entry of the current media type",
    )
    behavior.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without creating or modifying MDBList lists",
    )
    behavior.add_argument(
        "--list-id", type=int, help="Override the configured MDBList list ID"
    )
    behavior.add_argument(
        "--list-name", help="Override the configured MDBList list name"
    )
    privacy = behavior.add_mutually_exclusive_group()
    privacy.add_argument(
        "--private",
        dest="private",
        action="store_const",
        const=True,
        help="Create/enforce a private list",
    )
    privacy.add_argument(
        "--public",
        dest="private",
        action="store_const",
        const=False,
        help="Create/enforce a public list",
    )

    parser.add_argument(
        "--timeout", type=int, help="HTTP request timeout in seconds"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Configuration.default_path(),
        help="Configuration file path (default: %(default)s)",
    )
    parser.add_argument(
        "--version", action="version", version=f"listarr {__version__}"
    )
    return parser


def _sources(args: argparse.Namespace) -> list[str]:
    selected = []
    if args.radarr or args.all:
        selected.append("Radarr")
    if args.sonarr or args.all:
        selected.append("Sonarr")
    return selected


def _filters(args: argparse.Namespace) -> FilterOptions:
    genres = tuple(
        genre.strip() for genre in (args.genre or "").split(",") if genre.strip()
    )
    return FilterOptions(
        monitored_only=args.mon,
        missing_only=args.missing,
        quality_profile=args.qualityprofile,
        tag=args.tag,
        genres=genres,
    )


def _destination(
    configured: DestinationSettings, args: argparse.Namespace
) -> DestinationSettings:
    return DestinationSettings(
        list_id=args.list_id if args.list_id is not None else configured.list_id,
        list_name=args.list_name or configured.list_name,
        private=(
            args.private if args.private is not None else configured.private
        ),
    )


def _display(result: SyncResult, list_name: str) -> None:
    mode = "DRY RUN" if result.dry_run else "SYNCED"
    list_ref = result.list_id if result.list_id is not None else f"{list_name} (new)"
    print(f"[{result.source}] {mode} -> MDBList {list_ref}")
    if result.dry_run:
        print(
            f"  Selected: {result.selected}  "
            f"Would add: {result.planned_add}  "
            f"Would remove: {result.planned_remove}"
        )
        return

    print(
        f"  Selected: {result.selected}  "
        f"Added: {result.added}/{result.planned_add}  "
        f"Removed: {result.removed}/{result.planned_remove}  "
        f"Existing: {result.existing}  Not found: {result.not_found}"
    )
    if result.not_found:
        print(
            "  Warning: MDBList could not match some provider IDs; "
            "those entries were not added or removed."
        )


def run(args: argparse.Namespace) -> int:
    sources = _sources(args)
    if not sources:
        raise ListarrError("Select --radarr, --sonarr, or --all")
    if args.cat and args.wipe:
        raise ListarrError("--cat and --wipe cannot be used together")
    if args.timeout is not None and args.timeout <= 0:
        raise ListarrError("--timeout must be greater than zero")

    config = Configuration(args.config)
    mdblist_settings = config.mdblist(args.timeout)
    mdblist = MDBListClient(
        api_key=mdblist_settings.api_key,
        base_url=mdblist_settings.base_url,
        timeout=mdblist_settings.timeout,
    )

    try:
        for source in sources:
            arr_settings = config.arr(source)
            destination = _destination(config.destination(source), args)
            arr = ArrClient(
                source=source,
                url=arr_settings.url,
                api_key=arr_settings.api_key,
                timeout=args.timeout or 30,
            )
            try:
                items = arr.get_items(_filters(args))
            finally:
                arr.close()

            list_id = mdblist.resolve_static_list(
                destination.list_id,
                destination.list_name,
                destination.private,
                create=not args.dry_run,
                enforce_privacy=not args.dry_run,
            )
            result = mdblist.sync(
                source=source,
                list_id=list_id,
                items=items,
                concatenate=args.cat,
                wipe=args.wipe,
                dry_run=args.dry_run,
            )
            _display(result, destination.list_name)
    finally:
        mdblist.close()

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except ListarrError as error:
        print(f"listarr: error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
