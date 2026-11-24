import {layoutKey, norm, timestamp, typeKey, vehicleKey} from './archive.js';

export function timeChange(current, baseline){
  return Math.round(current * 1000) - Math.round(baseline * 1000);
}

export function hasPace(pace){
  return pace.count >= 3 && Number.isFinite(pace.median_s) && Number.isFinite(pace.stddev_s);
}

export function growthGroups(sessions){
  const groups = new Map();
  for(const session of sessions){
    const {metadata, pace} = session;
    const track = layoutKey(metadata);
    const time = timestamp(session);
    if(!track || time == null || !norm(metadata.CarClass) || !norm(metadata.SessionType)
      || !(norm(session.vehicle_model) || norm(metadata.CarName))
      || !Number.isFinite(pace.best_s) || pace.best_s <= 0) continue;
    // 有车型就按车型归组，旧录制使用完整车辆条目，避免把同品牌的不同车混在一起。
    const key = JSON.stringify([track, vehicleKey(session), typeKey(session)]);
    if(!groups.has(key)) groups.set(key, []);
    groups.get(key).push({session, time, pace});
  }
  return [...groups].map(([key, points]) => {
    // 同一录制时刻先处理最快记录，不把同一时刻的两个文件计作连续破纪录。
    points.sort((a,b) => a.time - b.time || a.pace.best_s - b.pace.best_s || a.session.id.localeCompare(b.session.id));
    return {key, points};
  }).sort((a,b) => b.points.at(-1).time - a.points.at(-1).time);
}

export function growthSummary(points){
  let best = points[0];
  const milestones = [{point: best, change: null}];
  const trend = points.map((point, index) => {
    const change = timeChange(point.pace.best_s, best.pace.best_s);
    const record = index === 0 || change < 0;
    if(change < 0){
      milestones.push({point, change});
      best = point;
    }
    return {point, record, best: best.pace.best_s};
  });
  const pacePoints = points.filter(({pace}) => hasPace(pace));
  return {best, trend, milestones, firstPace: pacePoints[0], recentPace: pacePoints.at(-1)};
}
