# 读取模块测试

已有 `test_reader.py`，使用 Python 自带 unittest 和 DuckDB 合成数据库，覆盖：

- 文件识别及只读读取。
- 源数据与模型数值、单位一致。
- 圈次边界、残圈与有效性未知状态。
- 不同采样频率、缺失区间及离散通道的处理。
- 圈内插值、挡位事件保持、首尾缺值、输出覆盖保护及身份元数据排除。

在项目根目录安装 `requirements-dev.txt`，然后运行检查。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/test_interval_metrics.mjs tests/test_growth.mjs
```

设置 `LMU_SAMPLE_PATH` 为已核实的 Monza 文件绝对路径，可额外执行真实样本检查。其余检查使用合成数据。

`test_trajectory.py` 验证固定坐标原点、圈间偏移不被抹平、投影尺度、经度换日线、GPS 配对、缺失 / 跳变断线、圈界及距离缺失回退，真实样本核验轨迹长度和投影速度。API 检查还验证 GPS 错误单位不阻碍原有驾驶曲线。

`test_timing.py` 检查累计第二段含义、分段来源、当前字段回退、旧值不串圈、字段冲突、缺失分段、维修区 / 残圈排除、空统计和真实样本清点。`test_web.py` 另检查新接口的车手归属、旧记录重启后重读和异常分段单位。

`test_web.py` 验证导入、稳定编号、重启恢复、去重、非法输入、文件路径隔离、写入失败回滚和跨车手隔离（包括缓存）。测试数据生成于项目 outputs 临时子目录，不提交真实遥测，不硬编码个人电脑绝对路径。浏览器人工检查记录见 [网页使用说明](../docs/web-usage.md)。

`test_auto_import.py` 验证目录设置、启动扫描、按更新时间导入、跨重启跳过未变更文件及等待读写结束后的重试。

`test_growth.mjs` 验证成长页按录制时间排序，隔离不同车辆和赛道布局，以及正确处理单场基准、同一时刻和毫秒级并列圈速。
