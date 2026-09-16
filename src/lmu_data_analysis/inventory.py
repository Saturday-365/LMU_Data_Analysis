"""Read-only numeric inventory of declared channels; no metadata or personal fields."""
import math
import duckdb
from .reader import quote, digest, numeric
from .models import TelemetryError

DISPLAYED = {'Ground Speed', 'Brake Pos', 'Throttle Pos', 'Steering Pos', 'Gear', 'Lap Dist', 'GPS Latitude', 'GPS Longitude'}
TIMING = {'Lap', 'Lap Time', 'Current Sector', 'Current Sector1', 'Current Sector2', 'Last Sector1', 'Last Sector2'}


def category(name):
    if name in TIMING or name.startswith(('Best ', 'Current Lap')): return '圈速计时'
    if name.startswith(('Tyres', 'Wheel', 'SurfaceTypes')): return '轮胎与车轮'
    if name.startswith(('Brake', 'Brakes')) and 'Pos' not in name: return '刹车系统'
    if name.startswith(('Susp', 'Ride', 'FrontRide', 'RearRide', 'Front3rd', 'Rear3rd')): return '底盘与悬挂'
    if name.startswith(('G Force', 'GPS', 'Path', 'Track Edge', 'Total Dist', 'Ground', 'Lap Dist')): return '运动与位置'
    if name.startswith(('Engine', 'Fuel', 'Turbo', 'Regen', 'SoC', 'Virtual', 'Overheat', 'Clutch RPM')): return '动力与能量'
    if name.startswith(('Ambient', 'Track Temperature', 'Wind', 'Cloud', 'Minimum Path', 'Offpath')): return '环境'
    if name.startswith(('Steering', 'FFB', 'Throttle', 'Brake Pos', 'Clutch Pos')): return '驾驶输入与力反馈'
    return '车辆状态与辅助系统'


def inspect_channels(path, recording):
    before = digest(path)
    if before != recording.source_sha256:
        raise TelemetryError('Stored recording changed since import')
    items = []
    with duckdb.connect(str(path), read_only=True, config={'enable_external_access':'false',
            'autoload_known_extensions':'false', 'autoinstall_known_extensions':'false'}) as c:
        columns = {}
        for table, col in c.execute("SELECT c.table_name,c.column_name FROM information_schema.columns c JOIN information_schema.tables t ON c.table_name=t.table_name AND c.table_schema=t.table_schema AND c.table_catalog=t.table_catalog WHERE c.table_schema='main' AND t.table_type='BASE TABLE'").fetchall():
            columns.setdefault(table, []).append(col)
        for entry in recording.catalog:
            name = entry['source_name']
            item = {**entry, 'category':category(name), 'displayed':name in DISPLAYED,
                    'timing_used':name in TIMING, 'rows':0, 'components':[], 'status':'missing', 'note':'未找到可读数据表'}
            value_columns = sorted(col for col in columns.get(name, []) if col in ('value','value1','value2','value3','value4'))
            if not value_columns:
                items.append(item)
                continue
            rows, first, last = c.execute(f'SELECT count(*),min(rowid),max(rowid) FROM {quote(name)}').fetchone()
            item['rows'] = rows
            for col in value_columns:
                expression = f'TRY_CAST({quote(col)} AS DOUBLE)'
                low, high, count = c.execute(f'SELECT min(v),max(v),count(*) FROM (SELECT {expression} AS v FROM {quote(name)}) WHERE isfinite(v)').fetchone()
                item['components'].append({'name':col, 'min':numeric(low), 'max':numeric(high), 'finite_count':count, 'missing_count':rows-count})
            frequency = entry['frequency_hz']
            clock_frequency = next(e['frequency_hz'] for e in recording.catalog if e['source_name']=='GPS Time')
            timing_ok = entry['kind']=='event' or (isinstance(frequency, int) and frequency>0 and clock_frequency%frequency==0 and rows==math.ceil(len(recording.clock_s)*frequency/clock_frequency) and first==0 and last==rows-1)
            item['timing_compatible'] = timing_ok
            finite = [comp for comp in item['components'] if comp['finite_count']]
            changing = any(comp['min'] != comp['max'] for comp in finite)
            item['changing'] = changing
            if not finite:
                item.update(status='missing', note='没有有限数值，可能是文本 / 枚举或缺失')
            elif not timing_ok:
                item.update(status='timing_review', note='采样频率或数量无法套用已验证的时间重建，需单独核实')
            elif len(value_columns)>1:
                item.update(status='mapping_review', note='多分量数值可视化可行；value1～4 的轮位 / 语义顺序尚未核实')
            elif not changing:
                item.update(status='constant', note='本份样本为常量，适合状态卡，不产生变化曲线')
            elif entry['kind']=='event':
                item.update(status='candidate', note='可做事件时间轴 / 阶梯图；状态枚举需确认，计时字段需按语义解释')
            else:
                item.update(status='candidate', note='可做随圈内时间 / 距离变化的曲线；源采样相位仍未独立核实')
            if name.startswith('GPS ') and name in ('GPS Latitude','GPS Longitude'):
                item['note'] += '；轨迹地图还需校验坐标和赛道方向'
            items.append(item)
    if digest(path) != before:
        raise TelemetryError('Stored recording changed during inventory')
    return {'items':items, 'continuous_count':sum(i['kind']=='continuous' for i in items),
            'event_count':sum(i['kind']=='event' for i in items),
            'note':'数值范围覆盖整份录制（含维修区和残圈）；候选表示数据存在，并非该通道的图表已实现。'}
