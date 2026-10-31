import unittest
from unittest.mock import Mock

from diagnose_ids import diagnose, rejected_items, lookup, add_confirmed


class DiagnoseTests(unittest.TestCase):
    item = {"title": "Example", "type": "show", "ids": {"tvdb": 123, "imdb": "tt1234567"}}

    def test_parse_rejected_only(self):
        result = rejected_items(" - Example [TVDB: 123, IMDb: tt1234567]\n - Film [TMDB: 456]\nSelected: 900")
        self.assertEqual(result[0], self.item)
        self.assertEqual(result[1]["type"], "movie")

    def test_imdb_fallback_is_single_confirmed_id(self):
        def fetch(kind, provider, identifier):
            if provider == "tvdb":
                return {"status": "not_found"}
            return {"status": "found", "title": "Example", "ids": {"imdb": "tt1234567", "tmdb": 99}}
        result = diagnose(self.item, fetch)
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["candidates"], [{"imdb": "tt1234567"}])
        client = Mock()
        client.post.return_value.status_code = 200
        client.post.return_value.json.return_value = {"added": {"shows": 1}}
        add_confirmed(client, "https://example.com", 42, result, 10)
        self.assertEqual(result["status"], "added")
        self.assertEqual(client.post.call_args.kwargs["json"], {"shows": [{"imdb": "tt1234567"}]})

    def test_conflicting_id_never_becomes_candidate(self):
        result = diagnose(self.item, lambda *args: {"status": "found", "title": "Example", "ids": {"tvdb": 999}})
        self.assertEqual(result["status"], "id_conflict")
        self.assertEqual(result["candidates"], [])

    def test_missing_is_distinct_from_api_error(self):
        self.assertEqual(diagnose(self.item, lambda *args: {"status": "not_found"})["status"], "missing_for_supplied_ids")
        self.assertEqual(diagnose(self.item, lambda *args: {"status": "api_error"})["status"], "api_error")

    def test_wrong_title_or_year_needs_review(self):
        result = diagnose(self.item, lambda *args: {"status": "found", "title": "Different", "ids": {}})
        self.assertEqual(result["status"], "title_needs_review")
        item = {**self.item, "title": "Example (2024)"}
        result = diagnose(item, lambda *args: {"status": "found", "title": "Example", "year": 2020, "ids": {}})
        self.assertEqual(result["status"], "title_needs_review")

    def test_lookup_requires_echoed_id_and_type(self):
        session = Mock()
        session.get.return_value.status_code = 200
        session.get.return_value.json.return_value = {"title": "Example", "type": "movie", "imdb_id": "tt1234567"}
        self.assertEqual(lookup(session, "https://example.com", "show", "imdb", "tt1234567", 10)["status"], "unconfirmed")
        session.get.return_value.status_code = 429
        self.assertEqual(lookup(session, "https://example.com", "show", "imdb", "tt1234567", 10)["status"], "api_error")


if __name__ == "__main__":
    unittest.main()
