import pytest

from listarr.api.mdblist import MDBListClient
from listarr.errors import APIError, RateLimitError
from listarr.models import MediaItem

from conftest import FakeResponse, FakeSession


def media(provider_id, imdb_id=None, title="Title"):
    return MediaItem(
        provider_id=provider_id,
        imdb_id=imdb_id,
        title=title,
        monitored=True,
        quality_profile_id=1,
        tag_ids=(),
        has_file=False,
        genres=(),
    )


def test_creates_private_static_list():
    session = FakeSession()
    session.queue(FakeResponse([]), FakeResponse({"id": 42}))
    client = MDBListClient("secret", session=session)

    list_id = client.resolve_static_list(None, "My Movies", True)

    assert list_id == 42
    assert session.params == {"apikey": "secret"}
    assert session.calls[0]["params"] == {"sort": "name"}
    assert session.calls[-1]["url"].endswith("/lists/user/add")
    assert session.calls[-1]["json"] == {
        "name": "My Movies",
        "private": True,
    }


def test_existing_list_lookup_is_case_insensitive_and_privacy_is_enforced():
    session = FakeSession()
    session.queue(
        FakeResponse([{"id": 7, "name": "Shows"}]),
        FakeResponse({"id": 7, "private": False}),
        FakeResponse({"success": True}),
    )
    client = MDBListClient("secret", session=session)

    assert client.resolve_static_list(None, "shows", True) == 7
    assert "unified" not in session.calls[0]["params"]
    assert session.calls[-1]["method"] == "PUT"
    assert session.calls[-1]["json"] == {"private": True}


def test_list_metadata_accepts_single_item_list_response():
    session = FakeSession()
    session.queue(
        FakeResponse([{"id": 7, "name": "Shows"}]),
        FakeResponse([{"id": 7, "name": "Shows", "private": True}]),
    )
    client = MDBListClient("secret", session=session)

    assert client.resolve_static_list(None, "Shows", True) == 7
    assert len(session.calls) == 2


def test_unexpected_list_metadata_has_actionable_error():
    session = FakeSession()
    session.queue(
        FakeResponse([{"id": 7, "name": "Shows"}]),
        FakeResponse([]),
    )
    client = MDBListClient("secret", session=session)

    with pytest.raises(APIError, match="unexpected list metadata"):
        client.resolve_static_list(None, "Shows", True)


def test_list_response_without_concrete_id_has_actionable_error():
    session = FakeSession()
    session.queue(FakeResponse([{"name": "Shows", "items": 10}]))
    client = MDBListClient("secret", session=session)

    with pytest.raises(APIError, match="configure mdblist_list_id explicitly"):
        client.resolve_static_list(None, "Shows", True)


def test_dry_run_does_not_create_missing_list():
    session = FakeSession()
    session.queue(FakeResponse([]))
    client = MDBListClient("secret", session=session)

    list_id = client.resolve_static_list(
        None, "New list", True, create=False, enforce_privacy=False
    )
    result = client.sync(
        source="Radarr",
        list_id=list_id,
        items=[media(10, "tt10")],
        dry_run=True,
    )

    assert list_id is None
    assert result.planned_add == 1
    assert result.added == 0
    assert len(session.calls) == 1


def test_incremental_radarr_sync_removes_then_adds():
    session = FakeSession()
    session.queue(
        FakeResponse(
            {
                "movies": [
                    {"ids": {"tmdb": 1, "imdb": "tt1"}},
                    {"ids": {"tmdb": 2, "imdb": "tt2"}},
                ],
                "shows": [{"ids": {"tvdb": 999}}],
                "pagination": {},
            }
        ),
        FakeResponse({"removed": {"movies": 1}}),
        FakeResponse({"added": {"movies": 1}}),
    )
    client = MDBListClient("secret", session=session)

    result = client.sync(
        source="Radarr",
        list_id=5,
        items=[media(2, "tt2"), media(3, "tt3")],
    )

    assert result.removed == 1
    assert result.added == 1
    assert result.planned_remove == 1
    assert result.planned_add == 1
    assert result.not_found == 0
    assert session.calls[1]["url"].endswith("/items/remove")
    assert session.calls[1]["json"] == {"movies": [{"tmdb": 1}]}
    assert session.calls[2]["url"].endswith("/items/add")
    assert session.calls[2]["json"] == {
        "movies": [{"tmdb": 3, "imdb": "tt3"}]
    }


def test_concatenate_never_removes():
    session = FakeSession()
    session.queue(
        FakeResponse(
            {
                "shows": [{"tvdb_id": 100, "imdb_id": "tt100"}],
                "pagination": {},
            }
        ),
        FakeResponse({"added": {"shows": 1}}),
    )
    client = MDBListClient("secret", session=session)

    result = client.sync(
        source="Sonarr",
        list_id=5,
        items=[media(200, "tt200")],
        concatenate=True,
    )

    assert result.removed == 0
    assert [call["url"] for call in session.calls[1:]] == [
        "https://api.mdblist.com/lists/5/items/add"
    ]


def test_sync_reports_actual_added_existing_and_not_found_counts():
    session = FakeSession()
    session.queue(
        FakeResponse({"shows": [], "pagination": {}}),
        FakeResponse(
            {
                "added": {"shows": 1},
                "existing": {"shows": 0},
                "not_found": {"shows": 1},
            }
        ),
    )
    client = MDBListClient("secret", session=session)

    result = client.sync(
        source="Sonarr",
        list_id=5,
        items=[media(100, "tt100"), media(200, "tt200")],
    )

    assert result.planned_add == 2
    assert result.added == 1
    assert result.existing == 0
    assert result.not_found == 1


def test_modification_counts_are_aggregated_across_batches():
    session = FakeSession()
    session.queue(
        FakeResponse({"added": {"shows": 1}}),
        FakeResponse(
            {"added": {"shows": []}, "not_found": {"shows": [{"tvdb": 2}]}}
        ),
    )
    client = MDBListClient("secret", session=session)
    client.BATCH_SIZE = 1

    result = client._modify(
        5,
        "add",
        "shows",
        [{"tvdb": 1}, {"tvdb": 2}],
    )

    assert result == {"added": 1, "removed": 0, "existing": 0, "not_found": 1}


def test_cursor_pagination_is_followed():
    session = FakeSession()
    session.queue(
        FakeResponse(
            {
                "shows": [{"tvdb_id": 1}],
                "pagination": {"next_cursor": "cursor-2"},
            },
            headers={"X-Has-More": "true"},
        ),
        FakeResponse(
            {"shows": [{"tvdb_id": 2}], "pagination": {}},
            headers={"X-Has-More": "false"},
        ),
    )
    client = MDBListClient("secret", session=session)

    items = client.get_items(8, "Sonarr")

    assert [item.provider_id for item in items] == [1, 2]
    assert session.calls[1]["params"]["cursor"] == "cursor-2"


def test_missing_cursor_with_more_items_fails_safely():
    session = FakeSession()
    session.queue(
        FakeResponse(
            {"movies": [], "pagination": {}},
            headers={"X-Has-More": "true"},
        )
    )
    client = MDBListClient("secret", session=session)

    with pytest.raises(APIError, match="no pagination cursor"):
        client.get_items(8, "Radarr")


def test_rate_limit_long_wait_fails_instead_of_sleeping():
    session = FakeSession()
    session.queue(
        FakeResponse(
            {"detail": "rate limited"},
            status_code=429,
            headers={"Retry-After": "3600", "X-RateLimit-Remaining": "0"},
        )
    )
    client = MDBListClient("secret", session=session, max_rate_limit_wait=60)

    with pytest.raises(RateLimitError, match="retry after: 3600s"):
        client.resolve_static_list(None, "Movies", True)
