# 源码模块

`lmu_data_analysis/` 为可运行的核心读取包，通过 `scripts/read_telemetry.py` 使用。

- `reader.py`：只读文件检查、源格式适配、圈次切分。
- `models.py`：会话、片段、通道和诊断模型。
- `alignment.py`：单圈数据提取、连续通道插值和事件状态保持。
- `cli.py`：命令行摘要和 JSON 导出。

- `storage.py`：存储接口、本地 SQLite 和原始文件副本管理。
- `web_service.py`：导入、去重、归属检查和圈轨迹服务。
- `web_app.py`：FastAPI HTTP 接口及本地身份适配。

网页代码位于根目录 `web/`，通过 `scripts/serve_web.py` 启动。核心读取模块仍不依赖界面框架；时间重建的假设与限制随输出提供。
