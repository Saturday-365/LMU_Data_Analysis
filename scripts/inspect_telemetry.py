"""Read-only inventory of an LMU DuckDB recording; no app or coaching logic."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import duckdb


SAFE_METADATA = {
    "Version", "RecordingTime", "SessionTime", "SessionType", "TrackName",
    "TrackLayout", "WeatherConditions", "CarName", "CarClass",
}
BOUNDARY_EVENTS = {"Lap", "Lap Time", "Best LapTime", "In Pits"}


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_recording(source: Path, config_path: Path | None = None) -> dict:
    source = source.resolve(strict=True)
    before = sha256(source)
    report = {
        "source_filename": source.name,
        "source_bytes": source.stat().st_size,
        "duckdb_version": duckdb.__version__,
        "sha256_before": before,
        "warnings": [],
    }
    connection = duckdb.connect(
        str(source), read_only=True,
        config={"enable_external_access": "false",
                "autoload_known_extensions": "false",
                "autoinstall_known_extensions": "false"},
    )
    try:
        schema = connection.execute(
            "SELECT table_name, column_name, data_type "
            "FROM information_schema.columns WHERE table_schema='main' "
            "ORDER BY table_name, ordinal_position"
        ).fetchall()
        tables = {}
        for table, column, datatype in schema:
            tables.setdefault(table, []).append({"name": column, "type": datatype})
        required = {
            "metadata": ["key", "value"],
            "channelsList": ["channelName", "frequency", "unit"],
            "eventsList": ["eventName", "unit"],
        }
        for table, columns in required.items():
            actual = {entry["name"] for entry in tables.get(table, [])}
            if not set(columns).issubset(actual):
                raise ValueError(f"Unsupported LMU structure: missing {table} columns")
        report["table_count"] = len(tables)
        report["metadata"] = {
            key: value for key, value in connection.execute(
                "SELECT key, value FROM metadata"
            ).fetchall() if key in SAFE_METADATA
        }
        channels = connection.execute(
            'SELECT "channelName", "frequency", "unit" FROM "channelsList"'
        ).fetchall()
        events = connection.execute(
            'SELECT "eventName", "unit" FROM "eventsList"'
        ).fetchall()
        report["channel_count"] = len(channels)
        report["event_count"] = len(events)
        report["channels"] = []
        report["events"] = []
        for kind, entries in (("channels", channels), ("events", events)):
            for entry in entries:
                name, unit = entry[0], entry[-1]
                item = {"name": name, "unit": unit, "columns": tables.get(name, [])}
                if kind == "channels":
                    item["frequency_hz_declared"] = entry[1]
                report[kind].append(item)
                if name not in tables:
                    report["warnings"].append(f"Listed table missing: {name}")
                    continue
                table_sql = quote_identifier(name)
                item["rows"] = connection.execute(
                    f"SELECT count(*) FROM {table_sql}"
                ).fetchone()[0]
                item["statistics"] = {}
                for column in tables[name]:
                    column_sql = quote_identifier(column["name"])
                    nulls, minimum, maximum = connection.execute(
                        f"SELECT count(*) FILTER (WHERE {column_sql} IS NULL), "
                        f"min({column_sql}), max({column_sql}) FROM {table_sql}"
                    ).fetchone()
                    item["statistics"][column["name"]] = {
                        "nulls": nulls, "min": minimum, "max": maximum,
                    }
                if kind == "events" and name in BOUNDARY_EVENTS:
                    item["boundary_samples"] = connection.execute(
                        f"SELECT ts, value FROM {table_sql} ORDER BY ts"
                    ).fetchall()
        if "GPS Time" in tables:
            first, last, count = connection.execute(
                'SELECT min(value), max(value), count(*) FROM "GPS Time"'
            ).fetchone()
            if count >= 2 and first is not None and last is not None:
                step_min, step_max, nonincreasing = connection.execute(
                    'WITH d AS (SELECT value-lag(value) OVER(ORDER BY rowid) AS dt '
                    'FROM "GPS Time") SELECT min(dt),max(dt), '
                    'count(*) FILTER(WHERE dt<=0) FROM d'
                ).fetchone()
                report["clock"] = {
                    "first_s": first, "last_s": last, "span_s": last-first,
                    "samples": count, "step_min_s": step_min,
                    "step_max_s": step_max, "nonincreasing_steps": nonincreasing,
                }
                # Diagnostic only: this is not a verified per-channel time mapping.
                for item in report["channels"]:
                    frequency = item["frequency_hz_declared"]
                    if frequency and frequency > 0 and "rows" in item:
                        expected = (last-first)*frequency + 1
                        discrepancy = item["rows"] - expected
                        item["nominal_count_difference"] = round(discrepancy, 6)
                        if abs(discrepancy) > 2:
                            report["warnings"].append(
                                f"Nominal sample-count mismatch: {item['name']} "
                                f"({item['rows']} rows, declared {frequency} Hz)"
                            )
        if config_path:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            report["config_comparison"] = {}
            for kind, key, name_field in (
                ("channels", "Channels", "frequency_hz_declared"),
                ("events", "Events", None),
            ):
                declared = {
                    settings.get("Name", name): settings
                    for name, settings in config.get(key, {}).items()
                }
                actual = {item["name"]: item for item in report[kind]}
                report["config_comparison"][kind] = {
                    "only_in_config": sorted(declared.keys()-actual.keys()),
                    "only_in_recording": sorted(actual.keys()-declared.keys()),
                    "frequency_mismatches": [name for name in actual.keys() & declared.keys()
                        if name_field and actual[name][name_field] != declared[name].get("Frequency")],
                }
    finally:
        connection.close()
        after = sha256(source)
        if before != after:
            raise RuntimeError("Source changed during inspection; discard this report")
    report["sha256_after"] = after
    report["source_unchanged"] = True
    return report


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/telemetry-inspection.json"))
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        inputs = {args.source.resolve()}
        if args.config:
            inputs.add(args.config.resolve())
        if output in inputs or output.suffix.lower() != ".json":
            raise ValueError("Output must be a separate .json report, never an input file")
        report = inspect_recording(args.source, args.config)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(json_safe(report), ensure_ascii=False, indent=2,
                                     allow_nan=False)+"\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError, duckdb.Error) as error:
        parser.exit(1, f"Inspection failed: {error}\n")
    print(f"Inspected {report['channel_count']} channels and {report['event_count']} events.")
    print(f"Source unchanged: {report['source_unchanged']}. Report: {output}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")


if __name__ == "__main__":
    main()
