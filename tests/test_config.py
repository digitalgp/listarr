from pathlib import Path

import pytest

from listarr.config import Configuration
from listarr.errors import ConfigurationError


def write_config(path: Path, api_key: str = "mdb-key"):
    path.write_text(
        f"""
[MDBList]
api_key = {api_key}
timeout = 12

[Radarr]
url = http://localhost:7878
api_key = radarr-key
mdblist_list_name = Private Movies
mdblist_list_private = true
""".strip(),
        encoding="utf-8",
    )


def test_loads_only_selected_arr_section(tmp_path):
    path = tmp_path / "listarr.conf"
    write_config(path)

    config = Configuration(path)

    assert config.mdblist().timeout == 12
    assert config.arr("Radarr").url == "http://localhost:7878"
    assert config.destination("Radarr").private is True
    assert config.destination("Radarr").list_name == "Private Movies"


def test_environment_api_key_wins(tmp_path, monkeypatch):
    path = tmp_path / "listarr.conf"
    write_config(path, "file-key")
    monkeypatch.setenv("LISTARR_MDBLIST_API_KEY", "environment-key")

    assert Configuration(path).mdblist().api_key == "environment-key"


def test_missing_file_has_actionable_error(tmp_path):
    with pytest.raises(ConfigurationError, match="Copy example-listarr.conf"):
        Configuration(tmp_path / "missing.conf")


def test_invalid_list_id_is_rejected(tmp_path):
    path = tmp_path / "listarr.conf"
    write_config(path)
    with path.open("a", encoding="utf-8") as config_file:
        config_file.write("\nmdblist_list_id = nope\n")

    with pytest.raises(ConfigurationError, match="must be an integer"):
        Configuration(path).destination("Radarr")
