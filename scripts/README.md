# 开发辅助工具

## 本地网页

`serve_web.py` 在 `127.0.0.1:8765` 启动网页服务。可通过 `--port` 和 `--data-dir` 调整端口与本地存储位置。安装、启动及操作见 [网页使用说明](../docs/web-usage.md)。根目录 `start-web.cmd` 为 Windows 启动入口。

## 核心读取命令

`read_telemetry.py` 提供会话摘要、圈次识别及任意完整圈 JSON 导出。完整命令、输出结构和兼容限制见 [读取模块说明](../docs/reader-usage.md)。

## 原始样本核验工具

已有 `inspect_telemetry.py`：只读检查 LMU 原生 DuckDB 样本，列出表结构、单位、采样数量、事件范围及圈次边界。它是样本核验工具，不是应用解析器或图表程序。

在项目根目录的 PowerShell 中运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-inspection.txt
.\.venv\Scripts\python.exe scripts/inspect_telemetry.py "samples/LMU_SourseData/Autodromo Nazionale Monza_P_2026-09-16T09_50_59Z.duckdb" --config "samples/LMU_SourseData/config.json"
```

也可以传入其他文件路径，通过 `--output outputs/other-inspection.json` 指定报告位置。该命令针对本次核实的基础表结构，不保证识别未来版本。

报告默认保存在被 Git 忽略的 `outputs/`。不输出 DriverName、SteamID 和完整 CarSetup；检查前后计算 SHA-256，源文件变化时停止。报告包含实际数据统计和圈次事件，应保留在本地。

采样数量偏差只是诊断，不表示已确定错误原因或重建出准确时间轴。
