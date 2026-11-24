import {TelemetryCharts} from './charts.js';
import {SessionInsights} from './insights.js';
import {TrajectoryMap} from './trajectory.js';
import {PracticeConditions} from './conditions.js';
import {SessionPace} from './pace.js';
import {CircuitOverview} from './overview.js';
import {IntervalReview} from './intervals.js';
import {PaceArchive, dateLabel, lapTime, layoutKey, sameGroup, trackName, typeLabel, vehicleName} from './archive.js';

const $ = id => document.getElementById(id);
const state = {
  sessions: [], session: null, reference: null, traces: [], delta: null, axis: 'distance',
  sessionRequest: 0, referenceRequest: 0, traceRequest: 0, importing: false, maxUpload: null,
};
const charts = new TelemetryCharts($('charts'), $('cursor-position'));
const trajectory = new TrajectoryMap($('trajectory-map'), $('trajectory-status'), $('trajectory-position'), $('trajectory-follow'));
const insights = new SessionInsights(api, new SessionPace(api, selectSession));
const conditions = new PracticeConditions(api, notice, trajectory);
const archive = new PaceArchive(selectSession);
const overview = new CircuitOverview(api,selectSession,session => archive.show('detail',session));
const intervals = new IntervalReview(api, focusInterval, value => charts.setCursor(value), {
  prepare: () => {if(charts.axis !== 'distance'){state.axis = 'distance';setAxis();}},
  active: enabled => {charts.setMarking(enabled);trajectory.setMarking(enabled);},
  highlight: bounds => {charts.setSelection(bounds);trajectory.setSelection(bounds);},
});
charts.onCursor = value => trajectory.setCursor(value);
charts.onRangePreview = bounds => intervals.previewMark(bounds);
charts.onRange = bounds => intervals.applyMark(bounds);
charts.onMark = trajectory.onMark = value => intervals.markPoint(value);
trajectory.onCursor = value => charts.setCursor(value);

let noticeTimer;
function notice(message, error = false, persist = false){
  clearTimeout(noticeTimer);
  $('notice').textContent = message;
  $('notice').classList.toggle('error', error);
  $('notice').hidden = false;
  if(!persist) noticeTimer = setTimeout(() => $('notice').hidden = true, error ? 10000 : 4000);
}

async function api(path, options = {}){
  const response = await fetch('/api/v1' + path, options);
  if(response.ok) return response.json();
  const problem = await response.json().catch(() => null);
  const error = Error(typeof problem?.detail === 'string' ? problem.detail : `请求失败（${response.status}）`);
  error.code = problem?.code;
  throw error;
}

function sessionDate(session){
  return session.metadata.RecordingTime ? dateLabel(session.metadata.RecordingTime)
    : `录制时间未知 · 导入于 ${dateLabel(session.created_at)}`;
}

function renderSessions(){
  const list = $('sessions');
  list.replaceChildren();
  $('session-count').textContent = state.sessions.length;
  if(!state.sessions.length){
    const note = document.createElement('p');
    note.className = 'session-empty';
    note.textContent = '还没有会话记录。';
    list.append(note);
  }
  for(const session of state.sessions){
    const button = document.createElement('button');
    button.className = 'session-item';
    if(session.id === state.session?.id){
      button.classList.add('active');
      button.setAttribute('aria-current', 'page');
    }
    const title = document.createElement('strong'), meta = document.createElement('small');
    title.textContent = trackName(session.metadata);
    meta.textContent = `${typeLabel(session.metadata.SessionType)} · ${session.complete_lap_count} 圈 · ${sessionDate(session)}`;
    button.append(title, meta);
    button.title = session.filename;
    button.onclick = () => selectSession(session.id);
    list.append(button);
  }
}

async function refreshSessions(){
  const data = await api('/sessions');
  state.sessions = data.items;
  renderSessions();
  archive.setSessions(state.sessions);
  overview.setData(data.overview,archive.sessions);
}

function showArchive(){
  intervals.clear();
  state.session = null;
  state.reference = null;
  state.sessionRequest++;
  state.referenceRequest++;
  state.traceRequest++;
  insights.setSession(null);
  conditions.setSession(null);
  $('workspace').hidden = true;
  $('archive').hidden = false;
  $('import-report').hidden = !$('import-results').childElementCount;
  $('page-label').textContent = '个人圈速';
  $('open-archive').classList.add('active');
  $('open-archive').setAttribute('aria-current', 'page');
  archive.show('overview');
  renderSessions();
}

function lapOption(lap){
  return new Option(`第 ${lap.ordinal} 圈 · ${lap.display_time || lapTime(lap.lap_time_s)}`, lap.id);
}

function renderSession(session, ordinal){
  $('archive').hidden = true;
  $('workspace').hidden = false;
  $('import-report').hidden = true;
  $('open-archive').classList.remove('active');
  $('open-archive').removeAttribute('aria-current');
  $('page-label').textContent = '会话分析';
  $('track-name').textContent = trackName(session.metadata);
  $('car-name').textContent = [vehicleName(session), session.metadata.CarClass].filter(Boolean).join(' · ');
  $('session-type').textContent = typeLabel(session.metadata.SessionType);
  $('best-lap').textContent = lapTime(session.best_lap_s);
  $('lap-count').textContent = session.complete_lap_count;
  const fragments = session.segments.filter(segment => segment.kind !== 'complete').length;
  $('fragment-count').textContent = `另有 ${fragments} 个不完整片段`;
  $('duration').textContent = `${Math.floor(session.duration_s / 60)}:${String(Math.floor(session.duration_s % 60)).padStart(2, '0')}`;
  $('recorded-date').textContent = dateLabel(session.metadata.RecordingTime);
  $('source-file').textContent = `原始文件：${session.filename}`;
  $('diagnostic-count').textContent = `${session.diagnostics.length} 条读取提示`;
  $('diagnostics').replaceChildren(...session.diagnostics.map(item => {
    const li = document.createElement('li');
    li.textContent = item.message;
    return li;
  }));
  const current = $('lap-select');
  current.replaceChildren(...session.laps.map(lapOption));
  current.disabled = !session.laps.length;
  const requested = session.laps.find(lap => lap.ordinal === ordinal);
  if(requested) current.value = requested.id;

  const layout = layoutKey(session.metadata);
  const others = state.sessions.filter(other => other.id !== session.id && layout
    && layout === layoutKey(other.metadata) && other.complete_lap_count > 0);
  const best = others.filter(other => sameGroup(session, other) && other.pace.best_s != null)
    .sort((a,b) => a.pace.best_s - b.pace.best_s)[0];
  const references = $('reference-session');
  references.replaceChildren(new Option('本次会话', session.id), ...others.filter(other => other !== best).map(other =>
    new Option(`${sessionDate(other)} · ${vehicleName(other)} · ${typeLabel(other.metadata.SessionType)}`, other.id)));
  if(best) references.add(new Option(`历史最快参考 · ${lapTime(best.pace.best_s)} · ${sessionDate(best)}`, best.id), 1);
  references.disabled = !session.laps.length;
  populateReference(session, false);
  renderSessions();
}

function populateReference(session, useBest){
  const laps = $('reference-select');
  laps.replaceChildren(new Option('不叠加参考圈', ''), ...session.laps.map(lapOption));
  const best = session.laps.find(lap => lap.ordinal === session.pace.best_ordinal);
  laps.value = useBest ? (best || session.laps[0])?.id || '' : '';
  laps.disabled = !state.session.laps.length || !session.laps.length;
}

async function selectSession(id, ordinal = null, view = null){
  const generation = ++state.sessionRequest;
  state.referenceRequest++;
  state.traceRequest++;
  clearCharts();
  insights.setSession(null);
  conditions.setSession(null);
  $('charts').classList.add('loading');
  try{
    const session = await api(`/sessions/${encodeURIComponent(id)}`);
    if(generation !== state.sessionRequest) return;
    state.session = state.reference = session;
    renderSession(session, ordinal);
    if(view || ordinal != null) insights.show(view || 'telemetry');
    insights.setSession(session);
    conditions.setSession(session);
    await loadTraces();
  }catch(error){
    if(generation !== state.sessionRequest) return;
    showArchive();
    notice(error.message, true);
  }
}

async function changeReference(){
  const sequence = ++state.referenceRequest;
  state.traceRequest++;
  const current = state.session;
  const id = $('reference-session').value;
  $('reference-select').replaceChildren(new Option('正在读取参考圈…', ''));
  $('reference-select').disabled = true;
  $('charts').classList.add('loading');
  clearCharts();
  try{
    const reference = id === current.id ? current : await api(`/sessions/${encodeURIComponent(id)}`);
    if(sequence !== state.referenceRequest) return;
    state.reference = reference;
    populateReference(reference, id !== current.id);
    await loadTraces();
  }catch(error){
    if(sequence !== state.referenceRequest) return;
    state.reference = current;
    $('reference-session').value = current.id;
    populateReference(current, false);
    await loadTraces();
    notice(error.message, true);
  }
}

function clearCharts(){
  state.traces = [];
  state.delta = null;
  intervals.clear();
  $('axis-distance').disabled = true;
  trajectory.setData([], state.axis);
  charts.setData([], state.axis, null);
}

async function loadTraces(){
  const current = state.session;
  if(!current) return;
  const generation = ++state.traceRequest;
  const reference = state.reference;
  const lap = $('lap-select').value;
  const refLap = $('reference-select').value;
  $('charts').classList.add('loading');
  clearCharts();

  const chosen = lap ? [{session: current.id, lap}] : [];
  if(lap && refLap) chosen.push({session: reference.id, lap: refLap});
  conditions.loadLaps(chosen);
  $('selection-note').textContent = !lap ? '未找到可展示的完整圈' : refLap
    ? (current.id === reference.id ? '同会话双圈' : '跨会话双圈') : '单圈查看';
  try{
    if(!lap) return;
    const path = `/sessions/${current.id}/laps/${lap}`;
    let traces, delta;
    if(refLap){
      const query = new URLSearchParams({reference_session_id: reference.id, reference_lap_id: refLap});
      ({traces, delta} = await api(`${path}/comparison?${query}`));
    }else{
      traces = [await api(path + '/trace')];
    }
    if(generation !== state.traceRequest) return;
    state.traces = traces;
    state.delta = delta || null;
    setAxis();
    intervals.setComparison(current, traces, state.delta);
  }catch(error){
    if(generation === state.traceRequest) notice(error.message, true);
  }finally{
    if(generation === state.traceRequest) $('charts').classList.remove('loading');
  }
}

function setAxis(){
  const distanceAvailable = state.traces.length && state.traces.every(trace => trace.distance_available)
    && state.delta?.comparable !== false;
  $('axis-distance').disabled = !distanceAvailable;
  const axis = distanceAvailable && state.axis === 'distance' ? 'distance' : 'time';
  $('axis-distance').setAttribute('aria-pressed', String(axis === 'distance'));
  $('axis-time').setAttribute('aria-pressed', String(axis === 'time'));
  $('axis-note').textContent = axis === 'distance' ? '横轴：赛道距离（m）'
    : `横轴：圈内时间（s）${distanceAvailable ? '' : ' · 缺少可比距离'}`;
  trajectory.setData(state.traces, axis);
  charts.setData(state.traces, axis, state.delta);
}

function focusInterval(start,end){
  state.axis = 'distance';
  setAxis();
  charts.setRange(start, end);
  charts.setCursor(end);
}

async function importFiles(input){
  const files = Array.from(input);
  if(!files.length || state.importing) return;
  state.importing = true;
  document.body.classList.add('busy');
  $('file-input').disabled = true;
  $('empty-import').disabled = true;
  $('import-report').hidden = false;
  $('import-report').open = false;
  $('import-results').replaceChildren();
  let imported = 0, duplicates = 0, filtered = 0, failures = 0;
  try{
    for(const [index, file] of files.entries()){
      $('import-summary').textContent = `正在处理 ${index + 1} / ${files.length}：${file.name}`;
      const result = document.createElement('li');
      try{
        if(!file.name.toLowerCase().endsWith('.duckdb')) throw Error('请选择 LMU 原生 .duckdb 文件。');
        if(state.maxUpload && file.size > state.maxUpload) throw Error('文件超过单个导入上限。');
        const outcome = await api('/sessions', {
          method: 'POST', body: file,
          headers: {'Content-Type':'application/octet-stream', 'X-Filename':encodeURIComponent(file.name), 'X-LMU-Client':'web'},
        });
        imported++;
        result.textContent = `${file.name} · 已导入 · ${outcome.session.complete_lap_count} 个完整圈`;
      }catch(error){
        if(error.code === 'duplicate') duplicates++;
        else if(error.code === 'recording_too_short' || error.code === 'no_complete_lap') filtered++;
        else failures++;
        result.className = 'import-failure';
        result.textContent = `${file.name} · ${error.message}`;
      }
      $('import-results').append(result);
    }
    $('import-summary').textContent = `已导入 ${imported} 份 · 重复拒绝 ${duplicates} 份 · 已过滤 ${filtered} 份 · 失败 ${failures} 份`;
    $('import-report').open = duplicates + filtered + failures > 0;
    if(imported) await refreshSessions();
    showArchive();
  }catch(error){
    notice(`已完成文件处理，刷新档案时出错：${error.message}`, true);
  }finally{
    state.importing = false;
    document.body.classList.remove('busy');
    $('file-input').disabled = false;
    $('empty-import').disabled = false;
    $('file-input').value = '';
  }
}

$('open-archive').onclick = async () => {
  showArchive();
  try{await refreshSessions();}catch(error){notice(error.message, true);}
};
$('trajectory-plus').onclick = () => {trajectory.disableFollow(); trajectory.zoom(1.5);};
$('trajectory-minus').onclick = () => {trajectory.disableFollow(); trajectory.zoom(1 / 1.5);};
$('trajectory-fit').onclick = () => {trajectory.disableFollow(); trajectory.fit();};
$('lap-select').onchange = loadTraces;
$('reference-select').onchange = loadTraces;
$('reference-session').onchange = changeReference;
$('axis-distance').onclick = () => {state.axis = 'distance'; setAxis();};
$('axis-time').onclick = () => {intervals.cancelMarking();state.axis = 'time';setAxis();};
$('reset-zoom').onclick = () => charts.reset();
$('file-input').onchange = event => importFiles(event.target.files);
$('empty-import').onclick = () => $('file-input').click();
for(const event of ['dragenter','dragover']) $('dropzone').addEventListener(event, e => {
  e.preventDefault();
  $('dropzone').classList.add('dragover');
});
for(const event of ['dragleave','drop']) $('dropzone').addEventListener(event, e => {
  e.preventDefault();
  $('dropzone').classList.remove('dragover');
  if(event === 'drop') importFiles(e.dataTransfer.files);
});
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', e => e.preventDefault());

async function start(){
  try{
    const me = await api('/me');
    $('driver-name').textContent = me.display_name;
    state.maxUpload = me.max_upload_bytes;
    $('import-limit').textContent = `单个文件最大 ${state.maxUpload / 1024**2} MiB`;
    await refreshSessions();
  }catch(error){
    $('archive-loading').textContent = '读取本地档案失败。';
    notice(`无法连接本地服务：${error.message}`, true);
  }
}
start();
