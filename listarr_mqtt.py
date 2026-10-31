#!/usr/bin/env python3
"""Run each Listarr target separately and retain MQTT/HA job results."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from datetime import datetime
from zoneinfo import ZoneInfo


def now():
    return datetime.now(ZoneInfo("Europe/Oslo")).isoformat(timespec="seconds")


def publish(target, state):
    import paho.mqtt.client as mqtt

    root = os.getenv("MQTT_BASE_TOPIC", "scripts/listarr").strip("/")
    topic = f"{root}/{target}/state"
    prefix = os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant").strip("/")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect_timeout = 10
    connected = threading.Event()
    connection_errors = []

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            connection_errors.append(str(reason_code))
        connected.set()

    client.on_connect = on_connect
    client.connect(os.getenv("MQTT_HOST", "mqtt.home.kinberg.com"),
                   int(os.getenv("MQTT_PORT", "1883")), keepalive=30)
    client.loop_start()
    try:
        if not connected.wait(15) or connection_errors:
            raise RuntimeError(f"MQTT connection failed: {connection_errors}")
        messages = []
        for key, label in (("status", "Status"), ("last_run", "Siste kjøring"),
                           ("last_success", "Siste vellykkede kjøring")):
            uid = f"listarr_{target}_{key}"
            discovery = {
                "name": f"{target.title()} MDBList {label}",
                "unique_id": uid,
                "state_topic": topic,
                "value_template": "{{ value_json." + key + " }}",
                "device": {"identifiers": [f"listarr_{target}"],
                           "name": f"Listarr {target.title()}",
                           "manufacturer": "Listarr", "model": "Script status"},
            }
            if key in ("last_run", "last_success"):
                discovery["device_class"] = "timestamp"
            else:
                discovery["json_attributes_topic"] = topic
            messages.append((f"{prefix}/sensor/{uid}/config", discovery))
        messages.append((topic, state))
        for destination, payload in messages:
            result = client.publish(destination, json.dumps(payload), qos=1, retain=True)
            result.wait_for_publish(timeout=15)
            if result.rc != mqtt.MQTT_ERR_SUCCESS or not result.is_published():
                raise RuntimeError(f"MQTT publish failed: {destination}")
    finally:
        client.disconnect()
        client.loop_stop()


def outcome(returncode, output, dry_run):
    if returncode:
        return "error"
    if dry_run:
        return "dry_run"
    # A zero exit code can still mean that MDBList rejected some IDs.
    if re.search(r"Not found:\s*[1-9]\d*", output, re.IGNORECASE):
        return "partial"
    # Require Listarr's confirmed real-sync marker before advancing last_success.
    return "ok" if "SYNCED" in output else "unconfirmed"


def run_target(target, args, extra):
    directory = Path(os.getenv("LISTARR_STATE_DIR", "/state"))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{target}.json"
    previous = json.loads(path.read_text()) if path.exists() else {}
    state = {"status": "running", "last_success": previous.get("last_success"),
             "last_run": previous.get("last_run") or previous.get("finished_at"),
             "started_at": now(), "finished_at": None, "exit_code": None}
    mqtt_failed = False

    def save_and_publish():
        nonlocal mqtt_failed
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temp.replace(path)
        try:
            publish(target, state)
        except Exception as exc:
            mqtt_failed = True
            print(f"[MQTT ERROR] {target}: {exc}", file=sys.stderr)

    save_and_publish()
    command = ["listarr", "--config", args.config, f"--{target}", *extra]
    if args.dry_run:
        command.append("--dry-run")
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                timeout=int(os.getenv("LISTARR_TIMEOUT", "3600")))
        output = result.stdout
        print(output, end="", flush=True)
        state["exit_code"] = result.returncode
        state["status"] = outcome(result.returncode, output, args.dry_run)
    except subprocess.TimeoutExpired:
        state["status"] = "timeout"
        print(f"[ERROR] {target}: run exceeded timeout", file=sys.stderr)
    except OSError as exc:
        state["status"] = "error"
        print(f"[ERROR] {target}: {exc}", file=sys.stderr)
    state["finished_at"] = now()
    state["last_run"] = state["finished_at"]
    if state["status"] == "ok":
        state["last_success"] = state["finished_at"]
    save_and_publish()
    print(f"[{target}] {state['status']}; last_run={state['last_run']}; last_success={state['last_success']}")
    return state["status"] not in ("ok", "dry_run") or mqtt_failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    for target in ("all", "sonarr", "radarr"):
        group.add_argument(f"--{target}", action="store_true")
    parser.add_argument("--config", default="/config/listarr.conf")
    parser.add_argument("--dry-run", action="store_true")
    args, extra = parser.parse_known_args()
    targets = ("sonarr", "radarr") if args.all else (("sonarr",) if args.sonarr else ("radarr",))
    failed = False
    for target in targets:
        try:
            failed = run_target(target, args, extra) or failed
        except Exception as exc:
            print(f"[ERROR] {target}: {exc}", file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
