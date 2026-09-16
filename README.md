# LMU Data Analysis

面向 Le Mans Ultimate（LMU）车手的本地遥测数据查看与圈速复盘工具。

**当前状态：本地网页预览已实现，支持导入、持久保存、选圈、五类联动曲线、双圈叠加、圈速 / 分段统计及原始数据目录。38 项自动化检查通过，完整 V0.1 尚未正式发布。**

## 启动网页

双击根目录 `start-web.cmd`，再打开 **http://127.0.0.1:8765**。首次安装和操作说明见 [网页使用说明](docs/web-usage.md)。

数据保存在本机 `data/`，重启后可继续读取。接口、车手 / 练习 / 圈次编号以及存储层已分开设计，为以后服务器部署和云存储预留替换位置；当前没有云端同步或账号登录。

## V0.1 目标

导入 LMU 原生 `.duckdb` 遥测文件，展示其中可用的会话、圈次和驾驶通道，让车手自行查看与分析。

- 查看文件信息、数据通道、单位、时间范围与缺失情况。
- 选择圈次，查看速度、油门、刹车、转向及挡位等可用数据。
- 使用同步图表、游标、缩放和平移查看同一位置的数据。
- 在数据支持时，切换圈内时间 / 赛道距离横轴，并叠加两圈数据。
- 保留原始文件；遇到缺失、未知或不支持的数据，清楚说明原因。

V0.1 不包含 AI、自动驾驶建议、逐弯原因判断、自动损失排名、实时覆盖层、云服务或车手社区。

## 项目结构

```text
LMU_Data_Analysis/
├── .github/                 问题与 PR 模板
├── docs/
│   ├── scope-v0.1.md        范围与验收标准
│   ├── architecture.md      模块职责与数据流
│   ├── data-contract.md     内部数据约定草案
│   ├── ui-plan.md           数据展示规划
│   ├── roadmap.md           分阶段工作清单
│   ├── references.md        接口与参考项目
│   ├── sample-verification.md 首份真实样本核验
│   └── reader-usage.md      读取命令、输出结构与验收
├── src/
│   └── lmu_data_analysis/
│       ├── reader.py       只读读取、结构检查和分圈
│       ├── models.py       会话、片段、通道模型
│       ├── alignment.py    单圈提取及时间对齐
│       └── cli.py          命令行入口
├── tests/                  合成边界测试与真实样本验收
├── samples/                样本说明及本地数据目录
├── scripts/                读取命令与样本核验工具
├── requirements.txt        锁定读取依赖
├── requirements-inspection.txt 样本核验依赖入口
├── .editorconfig
├── .gitattributes
├── .gitignore
└── CONTRIBUTING.md
```

## 阅读顺序

1. [V0.1 范围](docs/scope-v0.1.md)
2. [展示规划](docs/ui-plan.md)
3. [模块与数据流](docs/architecture.md)
4. [数据约定](docs/data-contract.md)
5. [开发路线](docs/roadmap.md)
6. [首份样本核验](docs/sample-verification.md)
7. [读取模块使用说明](docs/reader-usage.md)

## 开发状态与技术选择

Python 3.12 + DuckDB 1.5.5 已实现最小读取模块，运行方式见 [使用说明](docs/reader-usage.md)。入口为 `scripts/read_telemetry.py`，可选择完整圈并输出 JSON。原始样本以只读方式打开，连续通道时间重建及缺失值都有明确标记。

当前样本已通过 4 个圈时及核心数据验收。连续通道的精确源采样相位与官方有效性仍未知。网页采用 FastAPI + 原生 JavaScript / Canvas，无需前端构建；新增模块为 `web/`、`web_app.py`、`web_service.py`、`storage.py` 和 `scripts/serve_web.py`。Windows EXE 打包暂未实现。

## 数据管理

“圈速总览”展示每圈与三个分段、平均圈速、理论最快圈及组合来源。“数据目录”评估原始文件中更多可视化通道，详细结论见 [扩展数据与分段核验](docs/telemetry-opportunities.md)。

真实遥测放入 `samples/local/`，该目录内容默认被 Git 忽略。当前用户提供的 `samples/LMU_SourseData/` 与 `samples/RacingLabPicture/` 也整体忽略，保留原路径。常见遥测、日志与 `outputs/` 检查报告默认不提交；提交前仍应检查文件列表。

## 参考与许可

见 [参考资料](docs/references.md)。当前仓库尚未选择开源许可证；未复制 TinyPedal 或其他参考项目的实现代码。后续引入第三方代码时，单独记录来源和许可。
