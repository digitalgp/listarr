from listarr.cli import _display, build_parser, main
from listarr.models import NotFoundItem, SyncResult


def test_cli_keeps_familiar_source_flags():
    args = build_parser().parse_args(["--all", "--mon", "--dry-run"])

    assert args.all is True
    assert args.mon is True
    assert args.dry_run is True


def test_cli_requires_a_source(capsys):
    result = main([])

    assert result == 1
    assert "Select --radarr, --sonarr, or --all" in capsys.readouterr().err


def test_cli_rejects_cat_and_wipe(capsys):
    result = main(["--radarr", "--cat", "--wipe"])

    assert result == 1
    assert "cannot be used together" in capsys.readouterr().err


def test_cli_displays_actual_not_found_result(capsys):
    _display(
        SyncResult(
            source="Sonarr",
            list_id=12345,
            selected=100,
            planned_add=100,
            planned_remove=0,
            added=98,
            removed=0,
            existing=0,
            not_found=2,
            dry_run=False,
            not_found_items=(
                NotFoundItem(
                    title="Rejected show",
                    provider="tvdb",
                    provider_id=123,
                    imdb_id="tt123",
                ),
                NotFoundItem(
                    title="Rejected without IMDb",
                    provider="tvdb",
                    provider_id=456,
                    imdb_id=None,
                ),
            ),
        ),
        "sonarr",
    )

    output = capsys.readouterr().out
    assert "Added: 98/100" in output
    assert "Not found: 2" in output
    assert "Warning:" in output
    assert "Not found items:" in output
    assert "Rejected show [TVDB: 123, IMDb: tt123]" in output
    assert "Rejected without IMDb [TVDB: 456]" in output
    assert output.index("Not found: 2") < output.index("Rejected show")


def test_cli_displays_planned_dry_run_counts(capsys):
    _display(
        SyncResult(
            source="Radarr",
            list_id=None,
            selected=10,
            planned_add=8,
            planned_remove=2,
            added=0,
            removed=0,
            existing=0,
            not_found=0,
            dry_run=True,
        ),
        "radarr",
    )

    output = capsys.readouterr().out
    assert "Would add: 8" in output
    assert "Would remove: 2" in output
