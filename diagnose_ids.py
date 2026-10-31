#!/usr/bin/env python3
"""Diagnose rejected Listarr IDs; optionally retry confirmed single-ID additions."""
import argparse
import configparser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import unicodedata

import requests


def rejected_items(text):
    items = []
    for title, provider, identifier, imdb in re.findall(
        r"^\s*- (.+?) \[(TVDB|TMDB): (\d+)(?:, IMDb: (tt\d+))?\]\s*$",
        text, re.MULTILINE,
    ):
        item = {"title": title, "type": "show" if provider == "TVDB" else "movie",
                "ids": {provider.lower(): int(identifier)}}
        if imdb:
            item["ids"]["imdb"] = imdb
        if item not in items:
            items.append(item)
    return items


def normalize(title):
    title = re.sub(r"\s*\(\d{4}\)\s*$", "", title)
    return "".join(c for c in unicodedata.normalize("NFKC", title).casefold() if c.isalnum())


def media_ids(data):
    ids = dict(data.get("ids") or {})
    for provider in ("tvdb", "tmdb", "imdb"):
        if data.get(provider + "_id") is not None:
            ids.setdefault(provider, data[provider + "_id"])
    # MDBList's media-info schema exposes `id` as the TMDB identifier.
    if data.get("id") is not None:
        ids.setdefault("tmdb", data["id"])
    return ids


def lookup(session, base, media_type, provider, identifier, timeout):
    try:
        response = session.get(f"{base}/{provider}/{media_type}/{identifier}", timeout=timeout)
    except requests.RequestException:
        return {"status": "api_error", "error": "Connection failed"}
    if response.status_code == 404:
        return {"status": "not_found"}
    if response.status_code != 200:
        return {"status": "api_error", "http_status": response.status_code}
    try:
        data = response.json()
    except ValueError:
        return {"status": "api_error", "error": "Invalid JSON"}
    if not isinstance(data, dict) or not data.get("title"):
        return {"status": "unconfirmed", "error": "Missing media metadata"}
    ids = media_ids(data)
    if str(ids.get(provider)) != str(identifier) or data.get("type") != media_type:
        return {"status": "unconfirmed", "title": data.get("title"), "ids": ids,
                "error": "Response did not confirm requested ID and media type"}
    return {"status": "found", "title": data["title"],
            "title_en": data.get("title_en"), "year": data.get("year"), "ids": ids}


def diagnose(item, fetch):
    results = {provider: fetch(item["type"], provider, identifier)
               for provider, identifier in item["ids"].items()}
    report = {**item, "lookups": results, "status": "unresolved", "candidates": []}
    if all(value["status"] == "not_found" for value in results.values()):
        report["status"] = "missing_for_supplied_ids"
        return report
    if any(value["status"] == "api_error" for value in results.values()):
        report["status"] = "api_error"
        return report
    found = [(provider, value) for provider, value in results.items() if value["status"] == "found"]
    # A returned cross-provider ID must never contradict a supplied ID.
    conflict = any(str(value["ids"][p]) != str(identifier)
                   for _, value in found for p, identifier in item["ids"].items()
                   if value["ids"].get(p) is not None)
    # Independently resolved IDs must also agree with one another.
    for _, left in found:
        for _, right in found:
            conflict |= any(str(left["ids"][p]) != str(right["ids"][p])
                            for p in left["ids"].keys() & right["ids"].keys()
                            if left["ids"][p] is not None and right["ids"][p] is not None)
    if conflict:
        report["status"] = "id_conflict"
        return report
    expected_year = re.search(r"\((\d{4})\)\s*$", item["title"])
    for provider, value in found:
        if expected_year and str(value.get("year")) != expected_year.group(1):
            continue
        if any(normalize(title) == normalize(item["title"])
               for title in (value["title"], value.get("title_en")) if title):
            report["candidates"].append({provider: item["ids"][provider]})
    if report["candidates"]:
        report["status"] = "confirmed"
    elif found:
        report["status"] = "title_needs_review"
    return report


def response_count(data, key, bucket):
    count = data.get(key, 0)
    if isinstance(count, dict):
        count = count.get(bucket, 0)
    return count if isinstance(count, int) else len(count) if isinstance(count, list) else 0


def add_confirmed(session, base, list_id, report, timeout):
    bucket = "shows" if report["type"] == "show" else "movies"
    attempts = report.setdefault("add_attempts", [])
    for candidate in report["candidates"]:
        try:
            response = session.post(f"{base}/lists/{list_id}/items/add",
                                    json={bucket: [candidate]}, timeout=timeout)
            if response.status_code != 200:
                report["status"] = "add_api_error"
                attempts.append({"id": candidate, "http_status": response.status_code})
                return
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid response")
        except (requests.RequestException, ValueError):
            report["status"] = "add_api_error"
            return
        attempts.append({"id": candidate, "result": data})
        if response_count(data, "added", bucket) == 1:
            report["status"] = "added"
            return
        if response_count(data, "existing", bucket) == 1:
            report["status"] = "already_present"
            return
        if response_count(data, "not_found", bucket) != 1:
            report["status"] = "add_unconfirmed"
            return
    report["status"] = "found_but_add_rejected"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/config/listarr.conf")
    parser.add_argument("--log", required=True, help="Listarr log containing Not found items")
    parser.add_argument("--report", default="/state/id-report.json")
    parser.add_argument("--apply", action="store_true", help="Add confirmed matches, never remove")
    args = parser.parse_args()
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(args.config):
        parser.error("Configuration file not found")
    key = os.getenv("LISTARR_MDBLIST_API_KEY") or config.get("MDBList", "api_key", fallback="")
    if not key:
        parser.error("Missing MDBList API key")
    base = config.get("MDBList", "base_url", fallback="https://api.mdblist.com").rstrip("/")
    timeout = config.getint("MDBList", "timeout", fallback=30)
    items = rejected_items(Path(args.log).read_text(encoding="utf-8", errors="replace"))
    if not items:
        parser.error("No rejected title/ID lines found in log")
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "applied": args.apply,
              "note": "Missing means no lookup for supplied IDs, not proof the title is absent under other IDs.",
              "items": []}
    destination = Path(args.report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        session.params.update({"apikey": key})
        for item in items:
            result = diagnose(item, lambda kind, provider, identifier:
                              lookup(session, base, kind, provider, identifier, timeout))
            if args.apply and result["status"] == "confirmed":
                section = "Sonarr" if item["type"] == "show" else "Radarr"
                list_id = config.get(section, "mdblist_list_id", fallback="").strip()
                if not list_id.isdigit():
                    result["status"] = "missing_list_id"
                else:
                    add_confirmed(session, base, int(list_id), result, timeout)
            report["items"].append(result)
            destination.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"{result['status']}: {item['title']}", flush=True)
            if result["status"] in ("api_error", "add_api_error"):
                print("Stopped after API error; see report. No remaining titles classified.")
                return 1
    print(f"Report: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
