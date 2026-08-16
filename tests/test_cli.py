from listarr.cli import build_parser, main


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
