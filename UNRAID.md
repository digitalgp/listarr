# Unraid with MQTT status

Build the local image from this repository's Dockerfile and wrapper:

```bash
cd /mnt/user/appdata/listarr
docker build --no-cache -t listarr:local .
```

Place `listarr.conf` in that directory, using `example-listarr.conf` as a
starting point. Use the Unraid IP and published Sonarr/Radarr ports rather
than localhost.

Copy `my-listarr.xml` to
`/boot/config/plugins/dockerMan/templates-user/my-listarr.xml`, then select
listarr in Docker > Add Container. For an existing installation, rebuild the
image, add the `/state` read/write mapping to
`/mnt/user/appdata/listarr/state`, and Apply the container settings to recreate
it with the new image. Configuration remains mounted read-only at `/config`.

The default arguments `--all --dry-run` test both applications independently.
Check the logs, then remove `--dry-run` for real synchronization. Use
`--sonarr` or `--radarr` instead of `--all` to select one application.

Schedule this command with Unraid User Scripts:

```bash
#!/bin/bash
docker start -a listarr
```

The container exits after each run. Keep it rather than using `--rm`, so the
local image remains referenced. Disable container autostart if runs should
only occur on your chosen schedule. Updates require rebuilding the image and
recreating the container; it is a locally built image, not a registry image.

## MQTT and Home Assistant

Defaults: broker `mqtt.home.kinberg.com`, port `1883`, no authentication.
Override with `MQTT_HOST`, `MQTT_PORT`, `MQTT_BASE_TOPIC` (default
`scripts/listarr`) and `MQTT_DISCOVERY_PREFIX` (default `homeassistant`).

Retained QoS 1 JSON messages are published to:

* `scripts/listarr/sonarr/state`
* `scripts/listarr/radarr/state`

Other jobs can share the hierarchy as `scripts/<script-name>/...`.
Each payload contains `status`, `started_at`, `finished_at`, `exit_code` and
`last_success`. Timestamps use ISO 8601 with the Europe/Oslo offset.
Home Assistant discovery creates status and last-success timestamp sensors
for each application. There is no availability expiry: these are retained
job results, not a continuously running service.

Statuses: `running`, `ok`, `error`, `partial`, `timeout`, `dry_run`,
`unconfirmed`. Only a real run with exit code zero, the `SYNCED` confirmation
and no reported not-found IDs advances `last_success`. Errors, partial syncs
and dry runs preserve the previous successful timestamp. Before the first
success the timestamp is null. Status recognition uses Listarr's text output;
unknown output is reported as `unconfirmed` rather than success.

State files persist under `/state`. Do not run concurrent wrappers against
the same state directory. If the process or host is killed, MQTT may retain
`running`; compare timestamps to detect stale runs. MQTT failures are logged
and make the wrapper exit nonzero without preventing the other sync. Local
state is saved even if MQTT is unavailable; it is republished next run.
The per-application timeout defaults to 3600 seconds (`LISTARR_TIMEOUT`).

Run the wrapper's isolated tests with:

```bash
python -m unittest -v test_listarr_mqtt.py
```
