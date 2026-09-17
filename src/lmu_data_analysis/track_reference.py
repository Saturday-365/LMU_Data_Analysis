"""Fail-closed, recording-bound geometry adapter. No bundled unverified track map."""
from datetime import datetime
import json
import math
import re
from .trajectory import valid_coordinate


def unavailable(reason):
    return dict(available=False, reason=reason, layers=[], validation_status='unavailable')


def validate_resource(resource, recording):
    def require(ok, reason):
        if not ok:
            raise ValueError(reason)

    def point(p):
        return isinstance(p, list) and len(p) == 2 and all(
            isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in p)

    require(resource['schema_version'] == 1, '赛道资源格式版本不支持')
    for key in ('source', 'license', 'track', 'layout', 'version', 'coordinate_system'):
        require(isinstance(resource[key], str) and bool(resource[key].strip()), '缺少赛道来源、授权或版本说明')
    require(resource['unit'] == 'm', '赛道资源须显式转换为米')
    require(resource['track'] == recording.metadata.get('TrackName') and
            resource['layout'] == recording.metadata.get('TrackLayout'), '赛道或布局不匹配')
    require(resource['recording_sha256'] == recording.source_sha256, '配准未在本份录制上核验')
    latitude = recording.position_series.get('latitude')
    longitude = recording.position_series.get('longitude')
    require(latitude is not None and longitude is not None, '录制缺少可核验的坐标')
    origin = next(([a,b] for a,b in zip(latitude.values, longitude.values) if valid_coordinate(a,b)), None)
    require(resource['frame'] == {'projection': 'local_equirectangular', 'origin_deg': origin}, '配准坐标原点不匹配')
    transform = resource['transform']
    scale, angle, offset = transform['scale'], transform['rotation_rad'], transform['translation_m']
    require(point([scale, angle]) and scale > 0 and point(offset), '坐标转换参数无效')

    def convert(p):
        return [scale*(math.cos(angle)*p[0]-math.sin(angle)*p[1])+offset[0],
                scale*(math.sin(angle)*p[0]+math.cos(angle)*p[1])+offset[1]]

    validation = resource['validation']
    threshold = validation['threshold_m']
    require(isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and
            math.isfinite(threshold) and threshold > 0, '误差阈值无效')
    require(bool(validation['threshold_basis'].strip()) and bool(validation['reviewer'].strip()), '缺少阈值依据或核验人')
    approved = datetime.fromisoformat(validation['threshold_set_at'])
    checked = datetime.fromisoformat(validation['checked_at'])
    require(approved.tzinfo is not None and checked.tzinfo is not None and approved <= checked,
            '必须先确定阈值，再进行独立核验；时间须含时区')
    fit, checks = validation['fit_points'], validation['check_points']
    require(3 <= len(fit) <= 64 and 6 <= len(checks) <= 1024, '需要 3～64 个配准点及 6～1024 个独立验证点')
    ids = set()
    for p in fit + checks:
        require(isinstance(p['id'], str) and p['id'] and p['id'] not in ids, '配准点与验证点须独立且编号唯一')
        ids.add(p['id'])
        require(point(p['source']) and point(p['target']), '控制点坐标无效')
    require(not ({tuple(p['source']) for p in fit} & {tuple(p['source']) for p in checks}), '验证点不能复用配准位置')
    require(len({tuple(p['source']) for p in checks}) == len(checks) and
            len({tuple(p['target']) for p in checks}) == len(checks), '验证点不能重复位置')
    # Reject collinear fitting landmarks, and demand checkpoints around the whole lap.
    a = fit[0]['source']
    require(any(abs((b['source'][0]-a[0])*(c['source'][1]-a[1])-(b['source'][1]-a[1])*(c['source'][0]-a[0])) > 1e-6
                for b in fit[1:] for c in fit[2:]), '配准点不能全部共线')
    fractions = [p['lap_fraction'] for p in checks]
    require(all(isinstance(f, (int, float)) and not isinstance(f, bool) and math.isfinite(f) and 0 <= f < 1 for f in fractions), '验证位置需为有效圈内比例')
    require({int(f*4) for f in fractions} == {0,1,2,3}, '独立验证点未覆盖全赛道四个区间')
    errors = [math.dist(convert(p['source']), p['target']) for p in checks]
    fit_errors = [math.dist(convert(p['source']), p['target']) for p in fit]
    require(max(errors + fit_errors) <= threshold, '配准误差超过已确定阈值')
    layers, seen, count = [], set(), 0
    require(0 < len(resource['layers']) <= 5, '图层数量无效')
    for layer in resource['layers']:
        kind = layer['kind']
        require(kind in {'centerline','left_boundary','right_boundary','kerb','pit_lane'} and kind not in seen, '图层类型无效或重复')
        seen.add(kind)
        paths = []
        require(bool(layer['paths']), '图层没有几何数据')
        for path in layer['paths']:
            count += len(path)
            require(2 <= len(path) and count <= 100000 and all(point(p) for p in path), '几何点无效或数量过大')
            converted = [convert(p) for p in path]
            require(all(point(p) and max(map(abs, p)) <= 100000 for p in converted), '转换后的几何超出局部范围')
            paths.append([dict(x_m=p[0], y_m=p[1]) for p in converted])
        layers.append(dict(kind=kind, paths=paths))
    return dict(available=True, reason='', layers=layers, frame=resource['frame'], transform=transform,
                source=resource['source'], license=resource['license'], version=resource['version'],
                validation_status='verified', validation={k: validation[k] for k in
                    ('threshold_m','threshold_basis','reviewer','checked_at')},
                max_error_m=max(errors), rms_error_m=math.sqrt(sum(e*e for e in errors)/len(errors)))


def load_reference(root, key, recording):
    if key is None:
        return unavailable('尚无经核验的本布局赛道数据；继续显示双圈走线。')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', key):
        return unavailable('赛道资源标识无效')
    path = root / (key + '.json')
    try:
        if path.resolve().parent != root.resolve() or path.stat().st_size > 10*1024*1024:
            return unavailable('赛道资源路径或大小无效')
        return validate_resource(json.loads(path.read_text(encoding='utf-8')), recording)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        return unavailable('赛道参照未通过核验：' + (str(error) if isinstance(error, ValueError) else '资源缺失或结构不完整'))
