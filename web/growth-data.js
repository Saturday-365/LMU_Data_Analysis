import {layoutKey, timestamp, trackName} from './archive.js';

const axisLeft = 65;
const axisRight = 17;

export function minimumGrowthWidth(count){
  return axisLeft + axisRight + Math.max(0, count - 1) * 16;
}

export function growthAxis(count, width){
  const left = axisLeft, right = width - axisRight;
  const span = Math.max(0, count - 1);
  const position = index => span ? left + (right - left) * index / span : (left + right) / 2;
  const intervals = Math.min(span, Math.max(1, Math.floor((right - left) / 150)));
  const ticks = Array.from({length:intervals + 1}, (_, index) => intervals ? Math.round(index * span / intervals) : 0);
  return {left, right, position, ticks};
}

export function growthGroups(sessions){
  const groups = new Map();
  for(const session of sessions){
    const {metadata, pace} = session;
    const name = metadata.TrackName?.trim();
    const layout = layoutKey(metadata);
    const key = layout || JSON.stringify([name?.toLowerCase() || '', null]);
    if(!groups.has(key)){
      const label = layout ? trackName(metadata) : name ? name + ' · 布局未知' : '未识别赛道';
      groups.set(key, {key, label, hasLayout:Boolean(layout), rows:[], latest:-Infinity});
    }
    const group = groups.get(key);
    const time = timestamp(session);
    group.rows.push({session, time, fastest:pace.best_s, top5:pace.top5_mean_s ?? null});
    if(time != null) group.latest = Math.max(group.latest, time);
  }
  for(const group of groups.values()){
    // 不用导入时间补录制时间，缺日期的文件保留在表格末尾。
    group.rows.sort((a,b) => (a.time ?? Infinity) - (b.time ?? Infinity) || a.session.id.localeCompare(b.session.id));
  }
  return [...groups.values()].sort((a,b) => Number(b.hasLayout) - Number(a.hasLayout)
    || b.latest - a.latest || a.label.localeCompare(b.label, 'zh-CN'));
}

export function chartHits(markers, x, y){
  const radius = 9;
  let nearest = null;
  let distance = radius;
  for(const marker of markers){
    const gap = Math.hypot(marker.x - x, marker.y - y);
    if(gap < distance){
      nearest = marker;
      distance = gap;
    }
  }
  if(!nearest) return [];
  // 同一位置可能有多条录制，或者两项圈速相等，提示中一起显示。
  return [nearest, ...markers.filter(marker => marker !== nearest
    && Math.hypot(marker.x - nearest.x, marker.y - nearest.y) <= 4)];
}
