# 最小读取模块：使用与验收

状态：已实现命令行读取与完整圈 JSON 导出；图表界面另见 [网页说明](web-usage.md)。

## 环境

已在 Windows、Python 3.12、DuckDB 1.5.5 下验证。依赖锁定在 `requirements.txt`；测试使用 Python 自带 unittest，无需 pytest。

在项目根目录打开 PowerShell。已有 `.venv` 时无需重复创建：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 查看会话和圈次

```powershell
.\.venv\Scripts\python.exe scripts/read_telemetry.py "samples/LMU_SourseData/Autodromo Nazionale Monza_P_2026-09-16T09_50_59Z.duckdb"
```

输出赛道、车辆、完整圈数量、圈时、可读取的核心通道和诊断提示。可附加 `--output outputs/session-summary.json` 保存摘要及全部通道目录。

## 提取一个完整圈

```powershell
.\.venv\Scripts\python.exe scripts/read_telemetry.py "samples/LMU_SourseData/Autodromo Nazionale Monza_P_2026-09-16T09_50_59Z.duckdb" --lap 1 --output outputs/my-lap-1.json
```

`--lap 1` 指第 1 个完整计时圈，不是第 1 个记录片段，也不是从数据库的 Lap 计数直接取值。当前样本可以选择 1～4。不存在的圈号会报错且不生成报告；已有输出文件不覆盖，重复运行请换文件名。

源文件始终只读打开，读取前后核对 SHA-256。不接受原文件作为输出路径。建议将输出放在已被 Git 忽略的 `outputs/`。

## 输出结构

| 字段 | 内容 |
| --- | --- |
| metadata | 白名单元数据：赛道、车名、会话等；不导出 DriverName、SteamID 或 CarSetup |
| source_sha256 / source_unchanged | 源文件摘要与本次读取前后的一致性 |
| catalog | 数据库目录中的 56 个连续通道、42 个事件；并非全部已经支持解码 |
| segments | 包括首尾片段在内的分段，包含 source_lap、开始 / 结束时间、分类和维修区状态 |
| complete_laps | 两端圈次边界完整的计时区间，保留游戏圈时与边界间隔，validity 为 unknown |
| distance_boundary_checks | 距离回绕是否包围对应圈次事件 |
| diagnostics | 缺失通道、单位不支持、时间重建等明确提示 |
| selected_lap.native | 所选圈各通道的原始数值、样本时间和频率；连续通道的时间是重建值 |
| selected_lap.aligned | 按该圈 GPS Time 网格对齐的值及 provenance；供后续图表使用 |

通道内部名称为 speed、throttle、brake、steering、distance、gear。速度单位 km/h；油门 / 刹车 / 转向为 %；距离为 m；挡位是离散编码。转向不是角度。

provenance 的含义：`sample` 原值、`interpolated` 连续值插值、`held` 沿用最近事件状态、`missing` 无法提供数据。`sample` 表示数值未插值，不代表连续通道有独立记录的源时间戳。缺失值写为 JSON null。

## 时间和分圈策略

- 明确使用表的 rowid 顺序读取连续样本；不依赖未排序 SQL 查询的偶然顺序。
- GPS Time 必须有有效秒单位、正频率和至少两个有限值，其采样间隔必须均匀。
- 连续核心通道的频率须能整除时钟频率，并且样本数与相应时钟步进完全相符；否则跳过该通道并提示。
- 对本样本使用 100 Hz 时钟，每 1 / 2 / 10 点分别映射 100 / 50 / 10 Hz 数据。
- 连续时间轴标记为 `reconstructed_gps_stride`、`phase_verified=false`。真实样本的 5 个距离回绕均与 Lap 事件在一个 0.1 秒区间内相符；这不证明所有通道的物理采样相位精确一致。
- 起始 Lap 行是初始状态，不视作已观测到的起终点。只有两个已观测到且连续递增的边界之间才列为完整计时区间。
- 官方圈时保留 Lap Time 原值；缺少时保持空值，边界间隔单独提供。不把完整圈自动标为有效圈。
- 事件时间必须严格递增，挡位按最近已发生事件保持，绝不线性插值成小数。
- 连续数据仅在该圈内部的相邻有效样本之间插值；首尾没有支撑数据时保留 null，不跨圈补值。
- 圈内距离不跨大幅回绕或倒退插值。距离回绕与圈次事件不符时关闭距离对齐，仍可使用时间轴和其他通道。

## 当前兼容边界

仅验证本次 format Version=1 样本和合成边界案例。游戏版本仍按用户确认的“2026-09-16 当日最新版”记录，不猜测具体 Build ID。

暂停或丢样导致 GPS Time 非均匀、事件时间重复 / 回退、源行号缺口和未知格式时明确拒绝。个别核心通道缺失、单位未知或样本数量不匹配时，提供其他可用通道及诊断。

暂不解码四轮、温度和能量等非核心通道，7 Hz 温度问题仍保留在样本核验记录中。网页已实现双圈独立曲线叠加；地图、距离域双圈重采样和实时采集尚未实现。其他车辆 / 游戏更新的兼容性需要更多样本验证。

## 测试

合成样本测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

额外启用本次 Monza 样本验收：

```powershell
$env:LMU_SAMPLE_PATH = (Get-ChildItem samples/LMU_SourseData -Filter *.duckdb | Select-Object -First 1).FullName
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

真实样本测试针对用户已经核实的 4 个圈时，不能任意替换成其他记录后仍期待同一结果。测试临时数据仅在 `outputs/reader-test-*` 中生成，清理前验证绝对路径。

2026-09-16：18 项合成测试 + 1 项真实样本验收通过。验收覆盖原文件哈希不变、4 圈圈时、5 次距离回绕、6 个核心通道，以及每圈对齐后的数组长度和挡位离散性。沙箱首次运行阻止测试临时目录访问，获准在沙箱外运行后全部通过。

已生成本地示例 `outputs/lap-1-reader.json`，后续图表可以直接以其 native / aligned 结构作为接入参考。
