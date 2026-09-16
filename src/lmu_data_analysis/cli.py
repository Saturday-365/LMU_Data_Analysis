from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .alignment import extract_lap
from .models import TelemetryError, format_lap_time
from .reader import read_recording


def summary(recording):
    laps = []
    for number, lap in enumerate(recording.complete_laps, 1):
        laps.append({"complete_lap_number": number, **asdict(lap),
                     "boundary_duration_s": lap.duration_s,
                     "recorded_lap_time_display": format_lap_time(lap.lap_time_s)})
    return {"reader_format": "lmu-format-1-core-reader", "source_filename": recording.source_filename,
            "source_sha256": recording.source_sha256, "source_unchanged": True,
            "metadata": recording.metadata,
            "recording_start_s": recording.clock_s[0], "recording_end_s": recording.clock_s[-1],
            "complete_laps": laps, "segments": [asdict(s) for s in recording.segments],
            "available_core_channels": list(recording.series), "catalog": recording.catalog,
            "distance_boundary_checks": recording.distance_boundary_checks,
            "diagnostics": [asdict(d) for d in recording.diagnostics]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="LMU 遥测核心数据读取（本地、只读）")
    parser.add_argument("source", type=Path, help="LMU .duckdb 遥测文件")
    parser.add_argument("--lap", type=int, help="导出第 N 个完整圈，从 1 开始")
    parser.add_argument("--output", type=Path, help="新建 JSON 输出路径，已有文件不覆盖")
    args = parser.parse_args(argv)
    try:
        if args.lap is not None and args.output is None:
            raise TelemetryError("--lap 必须搭配 --output 指定数据输出文件")
        if args.output:
            output = args.output.resolve()
            if output == args.source.resolve() or output.suffix.lower() != ".json":
                raise TelemetryError("输出必须是独立的 .json 文件，不能覆盖原始遥测")
            if output.exists():
                raise TelemetryError("输出文件已存在，请使用新文件名")
        recording = read_recording(args.source)
        result = summary(recording)
        if args.lap is not None:
            result["selected_lap"] = extract_lap(recording, args.lap)
        if args.output:
            output.parent.mkdir(parents=True, exist_ok=True)
            # Serialize first; x-mode avoids accidentally replacing an existing artifact.
            content = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n"
            with output.open("x", encoding="utf-8") as stream:
                stream.write(content)
        print(f"赛道：{recording.metadata.get('TrackLayout', '未知')}")
        print(f"车辆：{recording.metadata.get('CarName', '未知')}")
        print(f"完整圈：{len(recording.complete_laps)}；总片段：{len(recording.segments)}")
        for lap in result["complete_laps"]:
            display = lap['recorded_lap_time_display'] or '圈时未记录'
            print(f"  第 {lap['complete_lap_number']} 个完整圈：{display}（有效性未知）")
        print("核心通道："+", ".join(recording.series))
        for diagnostic in recording.diagnostics:
            print(f"提示 [{diagnostic.code}] {diagnostic.message}")
        if args.output:
            print(f"已保存：{output}")
        return 0
    except (TelemetryError, OSError, ValueError) as error:
        print(f"读取失败：{error}")
        return 1
