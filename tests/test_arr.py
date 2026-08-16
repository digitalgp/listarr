from listarr.api.arr import ArrClient
from listarr.models import FilterOptions

from conftest import FakeResponse, FakeSession


def movie(
    tmdb_id,
    title,
    *,
    monitored=True,
    quality=1,
    tags=None,
    has_file=False,
    genres=None,
):
    return {
        "tmdbId": tmdb_id,
        "imdbId": f"tt{tmdb_id:07d}",
        "title": title,
        "monitored": monitored,
        "qualityProfileId": quality,
        "tags": tags or [],
        "hasFile": has_file,
        "genres": genres or [],
    }


def test_radarr_filters_are_combined():
    session = FakeSession()
    session.route(
        "/api/v3/qualityprofile",
        FakeResponse([{"id": 4, "name": "HD"}]),
    )
    session.route(
        "/api/v3/tag",
        FakeResponse([{"id": 7, "label": "recommended"}]),
    )
    session.route(
        "/api/v3/movie",
        FakeResponse(
            [
                movie(1, "Included", quality=4, tags=[7], genres=["Drama"]),
                movie(2, "Has file", quality=4, tags=[7], has_file=True),
                movie(3, "Wrong tag", quality=4, tags=[8]),
                movie(4, "Unmonitored", monitored=False, quality=4, tags=[7]),
            ]
        ),
    )
    client = ArrClient(
        "Radarr", "http://user:pass@localhost:7878", "key", session=session
    )

    items = client.get_items(
        FilterOptions(
            monitored_only=True,
            missing_only=True,
            quality_profile="hd",
            tag="Recommended",
            genres=("drama",),
        )
    )

    assert [item.title for item in items] == ["Included"]
    assert session.calls[-1]["auth"] == ("user", "pass")
    assert "user:pass" not in session.calls[-1]["url"]


def test_sonarr_uses_tvdb_id_and_ignores_missing_filter():
    session = FakeSession()
    session.route(
        "/api/v3/series",
        FakeResponse(
            [
                {
                    "tvdbId": 123,
                    "imdbId": "tt123",
                    "title": "Series",
                    "monitored": True,
                    "qualityProfileId": 1,
                    "tags": [],
                    "genres": [],
                }
            ]
        ),
    )
    client = ArrClient("Sonarr", "http://localhost:8989", "key", session=session)

    items = client.get_items(FilterOptions(missing_only=True))

    assert items[0].provider_id == 123
    assert items[0].has_file is None
