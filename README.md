# LMU Data Analysis

面向 Le Mans Ultimate（LMU）车手的本地遥测数据查看与圈速复盘工具。

## 使用 V0.7

在另一台电脑上使用时，可以复制 `LMU-Data-Analysis-v0.7-win-x64.zip`，完整解压后运行 `LMU-Data-Analysis-v0.7.exe`。需要 64 位 Windows 和 Microsoft Edge WebView2 Runtime。克隆仓库可获得源码，由构建脚本生成的 `dist/` 发行目录保存在本地。

桌面版默认把档案保存在 `%LOCALAPPDATA%\LMU Data Analysis`。同一 Windows 账号升级时退出旧版，再解压并运行新版。换电脑时，可以在软件退出后复制整个档案目录，随后在新电脑的「设置」确认遥测路径。详细步骤见 [桌面启动、迁移、升级及构建](docs/desktop-v0.7.md)。

V0.7 在「个人圈速」中加入「车手成长」。按同赛道布局、车辆、组别和会话类型查看进步曲线、节奏变化和个人最佳里程碑，可直接打开对应最快圈。已有档案可直接使用。

首页可从右侧选择录制，在左侧预览圈速、驾驶段和分布图，点击「打开会话」进入详情。「设置」中的遥测目录可用于启动时自动导入。

从源码运行本地网页时，安装依赖后双击根目录 `start-web.cmd`，再打开 **http://127.0.0.1:8765**。网页版默认使用项目内的 `data/`。安装和操作见 [网页使用说明](docs/web-usage.md)。

## V0.1 历史范围

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
│   ├── desktop-v0.7.md     桌面运行、成长统计、迁移与构建
│   ├── web-usage.md        网页使用和本地档案说明
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
│       ├── cli.py          命令行入口
│       ├── web_app.py      本地 HTTP 接口
│       ├── storage.py      SQLite 档案及文件副本
│       └── auto_import.py  启动扫描和路径设置
├── web/                    档案、圈速分析及设置界面
├── tests/                  合成边界测试与真实样本验收
├── samples/                样本说明及本地数据目录
├── scripts/                桌面构建、网页启动及遥测工具
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

V0.2 完成了练习信息读取、按整场或圈次补录、恢复和保存，以及赛道资源接入和图层开关。当时的 Monza 样本用双圈走线展示，56 项自动化检查通过。[V0.2 交付记录](docs/release-v0.2.md) · [练习信息约定](docs/practice-fields-v0.2.md) · [赛道资源调查与接入](docs/track-reference-v0.2.md) · [V0.2 任务](docs/scope-v0.2.md) · [V0.1 交付记录](docs/release-v0.1.md)

## 开发状态与技术选择

Python 3.12 + DuckDB 1.5.5 已实现最小读取模块，运行方式见 [使用说明](docs/reader-usage.md)。入口为 `scripts/read_telemetry.py`，可选择完整圈并输出 JSON。原始样本以只读方式打开，连续通道时间重建及缺失值都有明确标记。

当前样本已通过 4 个圈时及核心数据验收。连续通道的精确源采样相位与官方有效性仍未知。网页采用 FastAPI + 原生 JavaScript / Canvas，无需前端构建。桌面版复用同一套本机服务和界面，由 WebView2 提供独立窗口。

## 数据管理

“圈速总览”展示每圈与三个分段、平均圈速、理论最快圈及组合来源。“数据目录”评估原始文件中更多可视化通道，详细结论见 [扩展数据与分段核验](docs/telemetry-opportunities.md)。

本机真实遥测可放在 `Data_Telemetry/` 或 `samples/local/`，也可保存在游戏自己的遥测目录。`Example_web_Photo/` 用于存放界面参考。遥测、参考截图、网页版档案、构建和发行产物均有本地 Git 忽略规则。桌面档案的备份和迁移见 [桌面版说明](docs/desktop-v0.7.md#迁移到另一台电脑)。

## 参考与许可

见 [参考资料](docs/references.md)。当前仓库尚未选择开源许可证；未复制 TinyPedal 或其他参考项目的实现代码。后续引入第三方代码时，单独记录来源和许可。
