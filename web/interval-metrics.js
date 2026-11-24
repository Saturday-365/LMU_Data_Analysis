const HOLD_S = .15;
export const BRAKE_THRESHOLD = 5;
export const THROTTLE_THRESHOLD = 20;

function interpolate(a,b,distance){
  const weight = (distance - a.distance) / (b.distance - a.distance);
  return {distance, time:a.time + weight * (b.time - a.time), value:a.value + weight * (b.value - a.value)};
}

function samplesFor(trace,channel,start,end){
  const distances = trace.distance_m, times = trace.time_s, values = trace.channels[channel]?.values;
  if(!distances || !values || !(start < end)) return null;
  const first = distances.findIndex(value => Number.isFinite(value) && value >= start);
  const last = distances.findIndex((value,index) => index >= first && Number.isFinite(value) && value >= end);
  if(first < 0 || last < 0) return null;
  const lower = distances[first] === start ? first : first - 1;
  if(lower < 0) return null;
  const samples = [];
  for(let i = lower; i <= last; i++){
    const distance = distances[i], time = times[i], value = values[i];
    if(![distance, time, value].every(Number.isFinite)) return null;
    const previous = samples.at(-1);
    if(previous && (distance <= previous.distance || time <= previous.time)) return null;
    samples.push({distance,time,value});
  }
  if(distances[first] > start) samples[0] = interpolate(samples[0],samples[1],start);
  if(distances[last] > end) samples[samples.length - 1] = interpolate(samples.at(-2),samples.at(-1),end);
  return samples;
}

function sustainedCrossing(samples, threshold, startsAbove){
  if(!samples) return {reason:'区间内缺少连续数据'};
  let crossing = null;
  for(let i = 1; i < samples.length; i++){
    const before = samples[i - 1], current = samples[i];
    if(current.value < threshold){
      crossing = null;
      continue;
    }
    if(before.value < threshold){
      const ratio = (threshold - before.value) / (current.value - before.value);
      crossing = {distance:before.distance + ratio * (current.distance - before.distance),
                  time:before.time + ratio * (current.time - before.time)};
    }
    // 短脉冲不作为驾驶动作。区间之外的样点不用于证明动作持续。
    if(crossing && current.time - crossing.time + 1e-9 >= HOLD_S){
      return {value:crossing.distance, distance:crossing.distance};
    }
  }
  return {reason:samples[0].value >= threshold ? startsAbove : '未检测到持续动作'};
}

export function intervalMetrics(trace,start,end){
  const brake = sustainedCrossing(samplesFor(trace,'brake',start,end),BRAKE_THRESHOLD,'区间起点已在刹车');
  // 最低速度允许区间边缘插值，不跨通道缺口取最小值。
  const speeds = samplesFor(trace,'speed',start,end);
  if(!speeds){
    return {brake, speed:{reason:'区间内缺少连续数据'}, throttle:{reason:'最低速度点未知'}};
  }
  const minimum = speeds.reduce((lowest,sample)=>sample.value < lowest.value ? sample : lowest);
  const throttle = minimum.distance < end
    ? sustainedCrossing(samplesFor(trace,'throttle',minimum.distance,end),THROTTLE_THRESHOLD,'最低速度点已回油')
    : {reason:'最低速度点在区间终点'};
  return {brake, speed:minimum, throttle};
}

export function intervalDelta(delta,start,end){
  const distances = delta.distance_m, values = delta.values;
  function at(distance){
    const right = distances.findIndex(value => value >= distance);
    if(right < 0 || distance < distances[0]) return null;
    if(distances[right] === distance) return values[right];
    if(values[right - 1] == null || values[right] == null) return null;
    const fraction = (distance - distances[right - 1]) / (distances[right] - distances[right - 1]);
    return values[right - 1] + (values[right] - values[right - 1]) * fraction;
  }
  const first = at(start), last = at(end);
  const gap = distances.some((distance,index)=>distance > start && distance < end && values[index] == null);
  return first == null || last == null || gap ? null : last - first;
}
