import assert from 'node:assert/strict';
import test from 'node:test';
import {intervalDelta, intervalMetrics} from '../web/interval-metrics.js';

function trace(){
  const speed = [120,118,110,104,98,94,80,82,98,107,110,111,112];
  return {distance_m:speed.map((_, i) => i * 10), time_s:speed.map((_, i) => i * .05),
    channels:{
      speed:{values:speed},
      brake:{values:[0,0,8,0,10,20,20,18,10,0,0,0,0]},
      throttle:{values:[0,0,0,0,0,0,0,40,60,70,80,90,100]},
    }};
}

test('uses the first sustained crossing and compares throttle after minimum speed', () => {
  const {brake,speed,throttle} = intervalMetrics(trace(),5,115);
  assert.equal(brake.distance,35);
  assert.equal(speed.value,80);
  assert.equal(speed.distance,60);
  assert.equal(throttle.distance,65);
});

test('leaves uncertain events unset for gaps, pre-existing pressure and short windows', () => {
  const missing = trace();
  missing.channels.speed.values[5] = null;
  assert.equal(intervalMetrics(missing,5,115).throttle.reason,'最低速度点未知');
  assert.equal(intervalMetrics(trace(),45,105).brake.reason,'区间起点已在刹车');
  assert.equal(intervalMetrics(trace(),5,43).brake.reason,'未检测到持续动作');
  const stationary = trace();
  stationary.distance_m[5] = stationary.distance_m[4];
  assert.equal(intervalMetrics(stationary,0,115).brake.reason,'区间内缺少连续数据');
});

test('calculates interval gain without crossing missing samples', () => {
  const delta = {distance_m:[0,10,20,30,40], values:[0,.5,null,-.25,-.5]};
  assert.equal(intervalDelta(delta,0,40),null);
  assert.equal(intervalDelta(delta,2,8),.30000000000000004);
  assert.equal(intervalDelta(delta,30,40),-.25);
});
