import assert from 'node:assert/strict';
import test from 'node:test';
import {growthGroups, growthSummary, timeChange} from '../web/growth-data.js';

function session(id, date, best, options = {}){
  const {count = 5, median = best + 1, spread = .4, model = null, metadata = {}} = options;
  return {id, vehicle_model:model, vehicle_brand:'Ferrari', metadata:{
    TrackName:'Monza', TrackLayout:'Grand Prix', CarClass:'GT3', CarName:'Ferrari #51',
    SessionType:'Race', RecordingTime:date, ...metadata
  }, pace:{count, best_s:best, median_s:median, stddev_s:spread}};
}

test('uses recorded chronology and keeps models, entries, layouts and session types separate', () => {
  const first = '2026-11-21T12_23_11Z', latest = '2026-11-21T15_38_03Z';
  const groups = growthGroups([
    session('later', latest, 110), session('earlier', first, 111),
    session('other-entry', first, 109, {metadata:{CarName:'Ferrari #54'}}),
    session('model-a', first, 109, {model:'Ferrari 296 GT3'}),
    session('model-b', latest, 108, {model:'Ferrari 296 GT3', metadata:{CarName:'Ferrari #54'}}),
    session('other-model', first, 109, {model:'Ferrari 488 GT3'}),
    session('other-group', first, 103, {metadata:{CarClass:'Hypercar'}}),
    session('other-layout', first, 105, {metadata:{TrackLayout:'Junior'}}),
    session('practice', first, 107, {metadata:{SessionType:'Practice'}}),
    session('missing-date', null, 100), session('missing-layout', first, 100, {metadata:{TrackLayout:''}}),
    session('untimed', first, null), session('local-time-unknown', '2026-11-21T15:40:00', 100)
  ]);
  const ids = groups.map(({points}) => points.map(({session}) => session.id));
  assert.deepEqual(ids.slice(0, 2), [['earlier','later'], ['model-a','model-b']]);
  assert.deepEqual(ids.slice(2).flat().sort(), ['other-entry','other-group','other-layout','other-model','practice']);
});

test('records a baseline and only improvements visible at millisecond resolution', () => {
  const [group] = growthGroups([
    session('base', '2026-11-20T18:00:00Z', 111.4214),
    session('faster', '2026-11-21T18:00:00Z', 110.3594, {count:1}),
    session('same-start', '2026-11-21T18:00:00Z', 110.410),
    session('rounded-tie', '2026-11-22T18:00:00Z', 110.3591, {median:112.50, spread:.70}),
    session('slower', '2026-11-23T18:00:00Z', 112.0, {count:2})
  ]);
  const summary = growthSummary(group.points);
  assert.equal(summary.best.session.id, 'faster');
  assert.deepEqual(summary.milestones.map(({point, change}) => [point.session.id, change]), [['base',null], ['faster',-1062]]);
  assert.deepEqual(summary.trend.map(({record}) => record), [true,true,false,false,false]);
  assert.deepEqual(summary.trend.map(({best}) => best), [111.4214,110.3594,110.3594,110.3594,110.3594]);
  assert.equal(summary.firstPace.session.id, 'base');
  assert.equal(summary.recentPace.session.id, 'rounded-tie');
  assert.equal(timeChange(summary.recentPace.pace.stddev_s, summary.firstPace.pace.stddev_s), 300);
});

test('a single record establishes a baseline without a pace claim on too few laps', () => {
  const [group] = growthGroups([session('only', '2026-11-20T18:00:00Z', 110, {count:2})]);
  const summary = growthSummary(group.points);
  assert.equal(summary.firstPace, undefined);
  assert.equal(summary.recentPace, undefined);
  assert.equal(summary.milestones.length, 1);
  assert.equal(summary.milestones[0].change, null);
});
