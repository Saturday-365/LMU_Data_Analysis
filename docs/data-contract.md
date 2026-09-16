# 内部数据约定

下表描述已实现的最小读取模型，不是 LMU 原始数据库表结构。JSON 字段见 [读取模块说明](reader-usage.md)，源结构见 [核验记录](sample-verification.md)。

## 模型

| 对象 | 最小信息 | 规则 |
| --- | --- | --- |
| Recording | 文件名、SHA-256、metadata、clock_s、catalog、series、segments、diagnostics | 会话元数据采用白名单，不导出身份字段 |
| Segment | segment_id、source_lap、kind、start_s、end_s、lap_time_s、validity、contains_pit_state | 首尾片段与完整圈分开；官方有效性保持 unknown |
| catalog 条目 | source_name、kind、unit、frequency_hz、table_present | 目录存在不代表非核心通道已解码 |
| Series | key、source_name、unit、kind、times_s、values、frequency_hz、time_basis、phase_verified | 连续时钟明确标记 reconstructed；事件保留源 ts；缺值为 None |
| Diagnostic | code、message、channel | 区分缺失、异常与时钟假设；无法安全解释的文件抛出 TelemetryError |

## 已支持的核心通道

| 通道 | 源表与单位 | 当前处理 |
| --- | --- | --- |
| speed | Ground Speed，km/h | 保留源值，连续插值 |
| throttle / brake | Throttle Pos / Brake Pos，% | 保留 0～100 源值；当前读取过滤版本 |
| steering | Steering Pos，% | 保留有符号输入比例，不推测角度 |
| gear | Gear，离散编码 | 最近事件保持，不做小数插值 |
| distance | Lap Dist，m | 检查回绕与圈边界；不跨回绕或倒退插值 |
| 时间 | GPS Time / 事件 ts，s | 会话时间和相对圈内时间分开，非现实 UTC 时间 |

未知单位不猜测转换，跳过该核心通道并诊断；非核心通道仅列入目录。完整圈按 1 起始的顺序索引选择，并保留 source_lap 以追溯源计数。

## 异常及对齐约定

- 真实零值不等同于无数据；无法读取时使用缺失标记。
- 异常时间戳、重复时间、时间回退需要诊断；不静默重排并掩盖记录问题。
- 不跨长时间缺口插值。允许插值的间隔阈值应由通道与实测采样特征确定。
- 离散值展示采用保持前值或原始事件语义，不进行线性插值。
- 距离回绕、倒车、出站与传送回维修区需要在圈次识别中单独处理。
- 有效性信息缺失时显示“未知”，不能仅凭圈时或未检测到异常标记为有效。
- 对比资格至少核对赛道布局和车辆；油量、轮胎、环境等已知条件可显示，未知条件明确标记。

## 获取样本后的待办

已实现核心整数分频通道的 GPS 时钟步进映射，并保留 time_basis / phase_verified。后续仍需核实源采样相位、7 Hz 通道数量偏差、游戏版本、圈有效性和更多事件编码。单圈 JSON 的 provenance 标明 sample / interpolated / held / missing，不伪装成每个原始通道都有独立时间戳。
