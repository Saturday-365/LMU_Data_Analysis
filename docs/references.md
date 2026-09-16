# 参考资料

查阅日期：2026-09-16。接口与文档可能随游戏版本变化；实际兼容性以本地样本核验为准。

| 来源 | 用途 | 已确认的边界 |
| --- | --- | --- |
| [LMU 官方遥测录制说明](https://guide.lemansultimate.com/hc/en-gb/articles/14524956311695-Telemetry-Recording) | 原生 DuckDB 录制、通道配置 | 示例配置不等于已核实的数据库 schema |
| [TinyPedal](https://github.com/TinyPedal/TinyPedal) | 遥测展示和接口使用参考 | 主程序 GPL-3.0-or-later；本仓库未复制其代码 |
| [pyLMUSharedMemory](https://github.com/TinyPedal/pyLMUSharedMemory) | 后续实时读取参考 | MIT；V0.1 不接入共享内存 |
| [MOZA Racing Lab](https://support.mozaracing.com/en/support/solutions/articles/70000683725-what-is-racing-lab-how-do-i-use-it-) | 数据对比交互参考 | 不集成其 AI、不假设可复用其数据或资源 |

当前没有引入任何参考项目作为依赖。后续引入时应记录具体版本、许可和使用范围。
