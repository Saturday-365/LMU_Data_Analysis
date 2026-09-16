"""Start the local telemetry web application."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lmu_data_analysis.web_app import create_app
import uvicorn


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动 LMU 本地网页端")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("端口范围为 1024～65535")
    uvicorn.run(create_app(args.data_dir), host="127.0.0.1", port=args.port, access_log=False)
