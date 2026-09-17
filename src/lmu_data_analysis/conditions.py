"""Conservative practice context extraction; user entries never modify telemetry."""
import duckdb
from .reader import digest, ordered_values, numeric
from .models import TelemetryError


def field(label, group, kind='text', unit='', varying=False, **extra):
    return dict(label=label, group=group, kind=kind, unit=unit, varying=varying, **extra)


FIELDS = {
    'car': field('车辆标识（不等同标准车型）', '车辆', metadata='CarName'),
    'model': field('车型', '车辆'),
    'class': field('组别', '车辆', metadata='CarClass'),
    'game_version': field('游戏版本', '车辆'),
    'track': field('赛道', '练习', metadata='TrackName'),
    'layout': field('布局', '练习', metadata='TrackLayout'),
    'recorded_at': field('录制时间（原始时区）', '练习', metadata='RecordingTime'),
    'session_type': field('练习类型', '练习', metadata='SessionType'),
    'notes': field('练习备注', '练习'),
    'ambient': field('气温', '环境', 'number', 'C', True, channel='Ambient Temperature', minimum=-100, maximum=100),
    'track_temp': field('赛道温度', '环境', 'number', 'C', True, channel='Track Temperature', minimum=-100, maximum=150),
    'wind_speed': field('风速', '环境', 'number', 'm/s', True, channel='Wind Speed', minimum=0, maximum=150),
    'wind_heading': field('风向原始角值（方向约定待核实）', '环境', 'number', 'deg', True, channel='Wind Heading', minimum=-360, maximum=360),
    'weather': field('天气 / 降雨说明', '环境', varying=True, metadata='WeatherConditions'),
    'track_state': field('干湿 / 积水 / 抓地说明', '环境', varying=True),
    'fuel': field('燃油', '车况', 'number', 'L', True, channel='Fuel Level', minimum=0, maximum=1000),
    'tyres': field('轮胎配方 / 胎龄 / 状态', '车况', varying=True),
    'damage': field('损伤说明', '车况', varying=True),
    'assists': field('辅助设置', '车况', varying=True),
    'setup_kind': field('调教类型', '调教', 'choice', varying=True, choices=['默认', '自定义', '未知']),
    'setup_name': field('调教名称', '调教', varying=True),
    'setup_source': field('调教来源', '调教', varying=True),
    'setup_notes': field('已知参数及单位 / 调教备注', '调教', varying=True),
}
STATES = {'known', 'unknown', 'not_recorded', 'not_applicable'}


def extract_context(path, recording):
    if digest(path) != recording.source_sha256:
        raise TelemetryError('Stored recording changed since import')
    result = {}
    with duckdb.connect(str(path), read_only=True, config={'enable_external_access': 'false',
            'autoload_known_extensions': 'false', 'autoinstall_known_extensions': 'false'}) as c:
        clock_rate = next(e['frequency_hz'] for e in recording.catalog if e['source_name'] == 'GPS Time')
        for key, spec in FIELDS.items():
            if 'channel' not in spec:
                continue
            entry = next((e for e in recording.catalog if e['source_name'] == spec['channel'] and e['kind'] == 'continuous'), None)
            item = dict(state='not_recorded', samples=[], reason='文件未提供该通道', frequency_hz=None)
            result[key] = item
            if not entry or not entry['table_present']:
                continue
            rate = entry['frequency_hz']
            item.update(state='unknown', unit=entry['unit'], frequency_hz=rate)
            if entry['unit'] != spec['unit'] or not isinstance(rate, int) or rate <= 0 or clock_rate % rate:
                item['reason'] = '单位或采样频率未通过核验'
                continue
            try:
                values = ordered_values(c, spec['channel'])
            except (duckdb.Error, TelemetryError):
                item['reason'] = '通道结构或采样行不连续'
                continue
            times = recording.clock_s[::clock_rate // rate]
            if len(times) != len(values):
                item['reason'] = '采样数量与时间轴不符'
                continue
            item.update(state='known', reason='按 GPS 时钟和声明频率重建；采样相位未独立核实',
                        samples=list(zip(times, [numeric(v) for v in values])))
        meta = dict(c.execute("SELECT key,value FROM metadata WHERE key IN ('CarSetup','WeatherConditions')").fetchall())
    if digest(path) != recording.source_sha256:
        raise TelemetryError('Stored recording changed during reading')
    return result, {'setup_present': bool(meta.get('CarSetup')),
                    'weather_raw': meta.get('WeatherConditions')}


def validate_changes(payload, scope):
    if not isinstance(payload, dict) or set(payload) != {'changes'} or not isinstance(payload['changes'], dict):
        raise ValueError('需要 changes 字段对象')
    for key, item in payload['changes'].items():
        if key not in FIELDS:
            raise ValueError('不支持的练习信息字段')
        spec = FIELDS[key]
        if scope != 'session' and not spec['varying']:
            raise ValueError('固定信息只能按整场练习编辑')
        if item is None:
            continue
        if not isinstance(item, dict) or set(item) != {'state', 'value'} or not isinstance(item['state'], str) or item['state'] not in STATES:
            raise ValueError('字段需包含有效 state 和 value')
        value = item['value']
        if item['state'] != 'known':
            if value is not None:
                raise ValueError('未知、不适用和未记录状态必须使用空值')
        elif spec['kind'] == 'number':
            if numeric(value) is None or not spec['minimum'] <= value <= spec['maximum']:
                raise ValueError(f"{spec['label']} 数值超出允许范围或不是有限数")
        elif not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError('文字字段需为 1～2000 字符')
        elif spec['kind'] == 'choice' and value not in spec['choices']:
            raise ValueError('调教类型不受支持')
    return payload['changes']


def context_document(session, recording, extracted, annotations, lap_id=None):
    scope = lap_id or 'session'
    lap = next((lap for lap in session['laps'] if lap['id'] == lap_id), None) if lap_id else None
    if lap_id and lap is None:
        raise LookupError('圈次不存在')
    segment = recording.complete_laps[lap['ordinal']-1] if lap else None
    start, end = (segment.start_s, segment.end_s) if segment else (recording.clock_s[0], recording.clock_s[-1])
    channels, metadata_notes = extracted
    rows = {(a['scope'], a['field']): a for a in annotations}
    fields = []
    for key, spec in FIELDS.items():
        original = dict(value=None, state='not_recorded', source='telemetry', unit=spec['unit'],
                        source_field=spec.get('channel', spec.get('metadata')), reason='文件未提供可核实的值',
                        valid_range=({'start_s': start, 'end_s': end, 'lap_id': lap_id} if spec['varying'] else {'scope': 'session'}), updated_at=None)
        if 'metadata' in spec:
            value = recording.metadata.get(spec['metadata'])
            if value:
                original.update(value=value, state='known', reason='文件元数据原值',
                                valid_range={'scope': 'session'})
        if key == 'weather' and metadata_notes['weather_raw']:
            original.update(value=None if lap else metadata_notes['weather_raw'], state='unknown' if lap else 'known',
                            reason='天气元数据快照；生效时刻未知，不能代表所有圈次',
                            valid_range={'scope': 'metadata_snapshot'}, raw_value=metadata_notes['weather_raw'])
        unverified = {'tyres': {'TyresCompound'}, 'assists': {'ABSLevel', 'TCLevel'},
                      'damage': {'WheelsDetached', 'LastImpactMagnitude'},
                      'track_state': {'Minimum Path Wetness', 'OffpathWetness'}}
        present = unverified.get(key, set()) & {e['source_name'] for e in recording.catalog if e['table_present']}
        if present:
            original.update(state='unknown', source_field=', '.join(sorted(present)),
                            reason='文件含相关原始字段，但枚举或完整状态尚未核实')
        if key.startswith('setup_') and metadata_notes['setup_present']:
            original.update(state='unknown', source_field='CarSetup', reason='文件含调教快照；参数含义、单位及生效时段未核实')
        if key in channels:
            data = channels[key]
            original.update(state=data['state'], reason=data['reason'], frequency_hz=data['frequency_hz'],
                            raw_unit=data.get('unit'), time_basis='reconstructed_gps_stride')
            samples = [(t,v) for t,v in data['samples'] if start <= t and (t < end if lap else t <= end)]
            values = [v for _,v in samples if v is not None]
            if data['state'] == 'known':
                original.update(state='known' if values else 'unknown', sample_count=len(values),
                                missing_count=len(samples)-len(values),
                                value={'min': min(values), 'max': max(values), 'first': values[0], 'last': values[-1]} if values else None)
        own = rows.get((scope, key))
        override = own or rows.get(('session', key))
        effective = original.copy()
        if override:
            effective.update(override['data'], source='user', updated_at=override['updated_at'],
                             valid_range={'scope': override['scope']}, reason='用户填写；原始遥测保留')
        fields.append(dict(key=key, **spec, automatic=original, effective=effective,
                           own_override=bool(own), inherited_override=bool(override and not own)))
    return dict(session_id=session['id'], scope=scope, fields=fields,
                notes=['天气元数据原始快照：' + str(metadata_notes['weather_raw']) + '；生效时间未记录，不自动用于各圈。'] if metadata_notes['weather_raw'] else [],
                setup_note='文件含 CarSetup，但参数含义、单位和生效时间尚未核实；暂不自动解释。' if metadata_notes['setup_present'] else '文件未提供已核实的完整调教；可手工记录已知参数和单位。')
