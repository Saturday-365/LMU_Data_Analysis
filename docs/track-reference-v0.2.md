# V0.2 赛道来源调查与接入约定

2026-09-17。结论：尚未取得同时满足授权、LMU Monza 布局版本及坐标精度要求的赛道几何文件。本版本交付接入、验证与降级能力，不含已验证的 Monza 边界或路肩底图。

## 来源调查

| 来源 | 可确认内容 | 接入结论 |
| --- | --- | --- |
| [Monza 官方赛道介绍](https://www.monzanet.it/en/circuit/) | 赛道布局与介绍 | 不能据此证明与 LMU 游戏几何一致，亦未取得可配准的精确边界数据和再分发许可 |
| [Studio 397 Track AI Tutorial](https://docs.studio-397.com/display/DG/Track%2BAI%2BTutorial) | AIW 的 Main / Collision / Cut corridors 有不同语义 | 格式说明不等于 LMU Monza 资产；合法行驶走廊、护栏、赛道限制不能混作物理路肩 |
| [LMU 官方录制说明](https://guide.lemansultimate.com/hc/en-gb/articles/14524956311695-Telemetry-Recording) | 原生 DuckDB 与通道配置 | 现有遥测可支撑局部轨迹，Path Lateral / Track Edge 标量未核实，不足以生成完整左右边界 |

未从游戏包提取或再分发资产，未复制 Track Titan 资产，未用车辆轨迹估计值冒充原始边界。公开地图轮廓不能作为几何精度证明。

## 资源格式（schema_version = 1）

资源为本机 UTF-8 JSON，最多 10 MB。以下字段均必需：

| 字段 | 约定 |
| --- | --- |
| `source`, `license` | 来源和允许本地使用的授权依据；文字声明需要人工查证，不代表程序自动核实了许可 |
| `track`, `layout`, `version` | 赛道、布局精确匹配原始元数据，另记录资产版本；用户补录的赛道显示名称不改变匹配 |
| `coordinate_system`, `unit` | 说明输入坐标系、方向、原点及高程处理；输入二维坐标单位固定为 `m` |
| `recording_sha256` | 已实际核验录制的哈希；不能把一份录制的配准直接推广到其他录制 |
| `frame` | 与轨迹接口一致的 `{projection: "local_equirectangular", origin_deg: [latitude, longitude]}` |
| `transform` | `{scale, rotation_rad, translation_m: [x,y]}`；正比例缩放、旋转和平移；不支持未经验证的镜像或非刚性拟合 |
| `layers` | 非空数组，最多 5 类；每项 `{kind, paths}`。`kind` 为 `centerline`, `left_boundary`, `right_boundary`, `kerb`, `pit_lane`；仅列实际拥有的几何 |
| `paths` | 多条独立折线，每条是至少两个 `[x,y]` 坐标；缺口必须分成独立折线，不自动补线或闭合；总点数不超过 100000 |
| `validation` | 下述人工核验记录 |

`validation` 必须包含：

- `threshold_m`、`threshold_basis`：正有限误差阈值，以及依据数据精度、用途制定该阈值的理由。没有真实资源前不预设 Monza 的合格阈值。
- `threshold_set_at`、`checked_at`：含时区的 ISO 时间；阈值必须先于或等于独立核验时间。
- `reviewer`：核验人。
- `fit_points`：至少 3 个不共线配准点。
- `check_points`：至少 6 个独立验证点，覆盖圈内四个四分之一区间。
- 每个点包含 `{id, source: [x,y], target: [x,y]}`；验证点另含 `lap_fraction`（0 ≤ 值 < 1）。编号全部唯一，不与配准点复用源位置。人工负责核对位置对应、全赛道分布和方向。

程序按同一个转换计算所有控制点误差，所有配准点与验证点必须不超过阈值；返回独立验证点的最大误差与 RMS。坐标转换后的点必须在局部 ±100 km 范围内。程序验证记录一致性，不能替代人工对地标、数据真实性和授权的核验。

## 接入方式

准备资源后，在项目根目录运行：

```powershell
.venv/Scripts/python.exe scripts/install_track_reference.py <练习编号> <已核验资源.json>
```

脚本先验证资源，成功后保存到 `data/track-resources/` 并关联现有练习。默认只操作本地车手，可用 `--data-dir` 指定验收目录。资源和关联存于被 Git 忽略的本地数据目录。版本更换时重新验证并接入，新关联替换旧关联，旧资源文件保留。

`GET /api/v1/sessions/{id}/track-reference` 每次重新核验资源，返回 `available`、`reason`、`layers`、坐标转换、来源和验证结果。错误布局、错误录制、错误原点、缺授权说明、缺独立验证或超限误差均返回不可用，现有走线仍可使用。

## 已验证与未验证

合成资源用于自动化测试及独立浏览器验收，明确标注 Synthetic，不作为真实赛道数据发布。真实 Monza 的独立地标验证和准确边界效果尚未完成；需要合格来源后按上述流程进行。
