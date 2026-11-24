import assert from 'node:assert/strict';
import test from 'node:test';
import {chartHits, growthAxis, growthGroups, minimumGrowthWidth} from '../web/growth-data.js';

function session(id, date, options = {}){
  const {model, layout = 'Grand Prix', name = 'Monza', type = 'Race', best = 110, top5 = 111} = options;
  return {id, vehicle_model:model, metadata:{TrackName:name, TrackLayout:layout, SessionType:type,
    RecordingTime:date}, pace:{best_s:best, top5_mean_s:top5}};
}

test('groups different models and session types by track layout and sorts by recorded time', () => {
  const first = '2026-11-21T12_23_11Z', latest = '2026-11-21T15_38_03Z';
  const groups = growthGroups([
    session('later', latest, {model:'Ferrari 296 GT3', top5:null}),
    session('earlier', first, {model:'BMW M4 GT3', type:'Practice'}),
    session('short', latest, {layout:'Junior'}),
    session('untimed', null, {best:null, top5:null}),
    session('missing-layout', first, {layout:''}), session('missing-track', first, {name:''})
  ]);
  const grouped = groups.map(({label, rows}) => [label, rows.map(({session}) => session.id)]);
  assert.deepEqual(grouped.slice(0, 2), [
    ['Monza · Grand Prix', ['earlier','later','untimed']], ['Monza · Junior', ['short']]
  ]);
  assert.deepEqual(Object.fromEntries(grouped.slice(2)), {'Monza · 布局未知':['missing-layout'], '未识别赛道':['missing-track']});
  assert.equal(groups[0].rows[1].top5, null);
  assert.equal(groups[0].rows[2].time, null);
  assert.equal(groups[0].rows[2].fastest, null);
  assert.ok(groups.slice(2).every(group => !group.hasLayout));
});

test('finds the nearest point and shows overlapping values from either series', () => {
  const fastest = {x:24, y:32}, top5 = {x:24, y:34}, separate = {x:25, y:47};
  const points = [fastest, top5, separate];
  assert.deepEqual(chartHits(points, 24, 33.8), [top5, fastest]);
  assert.deepEqual(chartHits(points, 25, 47), [separate]);
  assert.deepEqual(chartHits(points, 38, 33), []);
});

test('spreads 59 recordings with readable gaps and selects real recording indices for ticks', () => {
  const count = 59;
  const width = minimumGrowthWidth(count);
  const {position, ticks, left, right} = growthAxis(count, width);
  assert.equal(position(0), left);
  assert.equal(position(58), right);
  assert.equal(position(58) - position(57), 16);
  assert.equal(position(1) - position(0), 16);
  assert.equal(ticks[0], 0);
  assert.equal(ticks.at(-1), 58);
  assert.ok(ticks.every((index, i) => i === 0 || position(index) - position(ticks[i-1]) >= 140));
  assert.ok(growthAxis(count, 1460).ticks.length > ticks.length);
});

test('centers one recording and draws endpoints for two recordings', () => {
  const single = growthAxis(1, 300);
  assert.deepEqual(single.ticks, [0]);
  assert.equal(single.position(0), (single.left + single.right) / 2);
  assert.deepEqual(growthAxis(2, 1460).ticks, [0, 1]);
});
