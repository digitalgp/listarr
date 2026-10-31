# Diagnose rejected MDBList IDs on Unraid

The tool reads rejected title/ID lines from a Listarr log. It queries each
supplied ID separately using MDBList's media-info endpoint. It does not need
Sonarr/Radarr API access. Use your existing `listarr.conf` with its MDBList key;
never put the key in the command line or report.

Copy `diagnose_ids.py` and the updated `Dockerfile` beside `listarr_mqtt.py`
under `/mnt/user/appdata/listarr`, then rebuild:

```bash
cd /mnt/user/appdata/listarr
docker build --no-cache -t listarr:local .
mkdir -p /mnt/user/appdata/listarr/state
docker logs listarr > /mnt/user/appdata/listarr/state/listarr.log 2>&1
```

Use a log from the latest completed run (avoid old logs from different
libraries/filters). The existing container keeps the local image referenced.
The following temporary diagnostic container uses the rebuilt image directly:

```bash
docker run --rm --entrypoint python \
  -v /mnt/user/appdata/listarr:/config:ro \
  -v /mnt/user/appdata/listarr/state:/state \
  listarr:local /app/diagnose_ids.py \
  --log /state/listarr.log
```

Inspect `/mnt/user/appdata/listarr/state/id-report.json`. It contains each
original ID, the returned title/year/IDs and the result of each lookup.
Statuses:

* `confirmed`: lookup confirms the exact requested ID, media type and title;
  a year in the original title must also match. No supplied or independently
  returned IDs may conflict. Eligible for a single-ID retry.
* `id_conflict`: returned IDs disagree. Correct the source metadata or review
  manually; the tool never adds these entries.
* `title_needs_review`: an ID resolves but title/year does not match. This
  can include translated titles, not only wrong matches. No automatic add.
* `missing_for_supplied_ids`: every supplied ID returned HTTP 404. This is
  not proof the title is absent under other IDs. Investigate on MDBList or
  report the missing mappings to MDBList support.
* `unresolved`: the response did not provide enough metadata to confirm a match.
* `api_error`: authentication, rate limits, connection errors or malformed
  responses. The run stops; remaining entries are not classified as missing.

To retry confirmed entries, configure concrete `mdblist_list_id` values for
Sonarr/Radarr in `listarr.conf`, then run:

```bash
docker run --rm --entrypoint python \
  -v /mnt/user/appdata/listarr:/config:ro \
  -v /mnt/user/appdata/listarr/state:/state \
  listarr:local /app/diagnose_ids.py \
  --log /state/listarr.log --apply
```

This repeats lookups and tries confirmed IDs separately. It stops trying an
item after an accepted addition or an already-present response. It never
removes items or changes Sonarr/Radarr metadata. The report records the add
attempts and distinguishes `added`, `already_present`,
`found_but_add_rejected`, `add_unconfirmed`, `add_api_error`, `missing_list_id`.
An add API error stops the run to avoid repeated requests with a bad key or
exhausted quota. A report is saved after every item.

This is an explicit recovery tool, not automatic fallback during scheduled
sync. Run a normal sync afterwards to verify the recovered IDs are recognized.
An item without any IDs shared with the source may still require a metadata
mapping fix. Keep `partial` visible until that is resolved.

Tests use mocked API responses; live diagnosis must run on your server with
its API key. Each title uses one lookup per supplied ID, plus optional
single-ID add attempts, so MDBList daily API limits apply.
