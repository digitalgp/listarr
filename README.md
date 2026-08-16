# Listarr

Listarr synchronizes movies from Radarr and series from Sonarr to static
[MDBList](https://mdblist.com/) lists. Lists are private by default.

## Attribution

Listarr is based on [retraktarr](https://github.com/zakkarry/retraktarr) by
[zakary / zakkarry](https://github.com/zakkarry). retraktarr provided the
original Arr-to-list concept, Arr API handling, filtering behavior, and CLI
workflow. Listarr replaces the Trakt destination with an MDBList-only
implementation.

The original and modified work are distributed under the MIT License. See
[LICENSE](LICENSE) and [NOTICE](NOTICE).

## Features

- Radarr movies synchronized by TMDB ID
- Sonarr series synchronized by TVDB ID
- Private MDBList creation and privacy enforcement
- Incremental add/remove synchronization
- Append (`--cat`), wipe, filtering, dry-run, and cursor pagination
- Actual added, removed, existing, and not-found result reporting
- Rate-limit handling using MDBList's `Retry-After` response header
- No Trakt credentials or Trakt API calls


## Installation

Python 3.10 or newer is required.

```bash
python -m pip install .
```

For development:

```bash
python -m pip install -e ".[dev]"
pytest
```

## Configuration

Copy `example-listarr.conf` to one of these locations:

- Linux/macOS: `~/.config/listarr.conf`
- Windows: `%USERPROFILE%\.config\listarr.conf`

You can also pass any path with `--config`.

Create an API key in the [MDBList preferences](https://mdblist.com/preferences/#api)
and place it under `[MDBList]`. Alternatively, set
`LISTARR_MDBLIST_API_KEY` in the environment so the secret does not need to be
stored in the file.

`mdblist_list_id` is preferred when an existing list should be used. If it is
empty, Listarr looks up `mdblist_list_name` and creates a static list when no
match exists. Newly created lists are private by default.

Listarr performs name lookup against MDBList's concrete static-list response,
not its merged `unified` representation. If MDBList cannot provide a writable
ID, configure `mdblist_list_id` explicitly.

## Usage

```bash
# Synchronize both applications
listarr --all

# Radarr or Sonarr only
listarr --radarr
listarr --sonarr

# Preview without writing to MDBList
listarr --all --dry-run

# Only monitored entries
listarr --all --mon

# Add without removing existing list entries
listarr --radarr --cat

# Replace all movies in the configured Radarr list
listarr --radarr --wipe

# Filter by quality profile, tag, or comma-separated genres
listarr --radarr --qualityprofile "HD-1080p" --tag recommended
listarr --sonarr --genre "Drama,Documentary"
```

Run `listarr --help` for all options.

After a real synchronization, Listarr reports both planned and accepted
changes. For example:

```text
[Sonarr] SYNCED -> MDBList 201379
  Selected: 950  Added: 933/950  Removed: 0/0  Existing: 0  Not found: 17
  Warning: MDBList could not match some provider IDs; those entries were not added or removed.
```

`Not found` means MDBList could not match the supplied TMDB, TVDB, or IMDb ID.
These entries remain absent from the destination list and are not counted as
successfully added.

## Synchronization safety

Normal synchronization removes stale entries only from the media type being
processed. A Sonarr run does not remove movies, and a Radarr run does not
remove shows, even when both use the same MDBList list.

Use `--dry-run` before the first real synchronization. `--wipe` removes every
existing item of the current media type before re-adding the selected Arr
library. `--cat` never removes items and cannot be combined with `--wipe`.

## MDBList API

Listarr uses the documented static-list endpoints at
[api.mdblist.com](https://api.mdblist.com/), including cursor pagination and
API-key authentication. MDBList account and daily request limits still apply.

See [CHANGELOG.md](CHANGELOG.md) for release history.
