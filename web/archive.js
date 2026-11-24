const $ = id => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat('zh-CN', {dateStyle:'short', timeStyle:'short'});
const dayFormat = new Intl.DateTimeFormat('zh-CN', {month:'numeric', day:'numeric'});

export function lapTime(seconds){
  if(seconds == null) return '—';
  const ms = Math.round(seconds * 1000);
  return `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
}

export function dateLabel(value){
  const time = dateValue(value);
  return time == null ? '录制时间未知' : dateFormat.format(time);
}

function dateValue(value){
  if(!value) return null;
  const time = Date.parse(value.replace(/T(\d{2})_(\d{2})_(\d{2})Z$/, 'T$1:$2:$3Z'));
  return Number.isFinite(time) ? time : null;
}

function timestamp(session){return dateValue(session.metadata.RecordingTime);}
function norm(value){return (value || '').trim().toLowerCase();}
export function layoutKey(meta){
  if(!norm(meta.TrackName) || !norm(meta.TrackLayout)) return null;
  return JSON.stringify([norm(meta.TrackName), norm(meta.TrackLayout)]);
}
export function trackName(meta){
  const {TrackName: name, TrackLayout: layout} = meta;
  return name && layout && norm(name) !== norm(layout) ? `${name} · ${layout}` : layout || name || '未知赛道布局';
}
export function typeLabel(value){
  return {practice:'练习',qualify:'排位',qualifying:'排位',race:'正赛',warmup:'热身'}[norm(value)] || value || '未知类型';
}
export function vehicleName(session){
  return session.vehicle_model || session.metadata.CarName || '未知车辆';
}
function vehicleKey(session){
  const category = norm(session.metadata.CarClass);
  if(session.vehicle_model) return JSON.stringify(['model', norm(session.vehicle_model), category]);
  if(session.metadata.CarName) return JSON.stringify(['entry', norm(session.metadata.CarName), category]);
  return session.id;
}
function typeKey(session){return norm(session.metadata.SessionType) || session.id;}
function archiveLayout(session){return layoutKey(session.metadata) || session.id;}
export function sameGroup(a,b){
  return archiveLayout(a) === archiveLayout(b) && vehicleKey(a) === vehicleKey(b) && typeKey(a) === typeKey(b);
}

function options(select, sessions, key, label){
  const current = select.value;
  const unique = new Map();
  for(const session of sessions) if(!unique.has(key(session))) unique.set(key(session), label(session));
  select.replaceChildren(...Array.from(unique, ([value, title]) => new Option(title, value)));
  if(unique.has(current)) select.value = current;
}

export class PaceArchive {
  constructor(onOpen){
    this.onOpen = onOpen;
    this.sessions = [];
    this.visible = [];
    this.layout = $('archive-layout');
    this.car = $('archive-car');
    this.type = $('archive-type');
    this.canvas = $('pace-trend');
    for(const input of [this.layout, this.car, this.type]) input.addEventListener('change', () => this.render());
    new ResizeObserver(() => this.draw()).observe(this.canvas);
  }

  setSessions(sessions){
    this.sessions = [...sessions].sort((a,b) => (timestamp(b) ?? -Infinity) - (timestamp(a) ?? -Infinity)
      || b.created_at.localeCompare(a.created_at));
    this.render();
  }

  render(){
    $('archive-loading').hidden = true;
    $('archive-empty').hidden = this.sessions.length > 0;
    $('archive-content').hidden = !this.sessions.length;
    if(!this.sessions.length) return;

    options(this.layout, this.sessions, archiveLayout, session => trackName(session.metadata));
    const byLayout = this.sessions.filter(session => archiveLayout(session) === this.layout.value);
    options(this.car, byLayout, vehicleKey, session => vehicleName(session));
    const byCar = byLayout.filter(session => vehicleKey(session) === this.car.value);
    options(this.type, byCar, typeKey, session => typeLabel(session.metadata.SessionType));
    this.visible = byCar.filter(session => typeKey(session) === this.type.value);

    const best = this.visible.reduce((winner, session) => session.pace.best_s != null
      && (winner == null || session.pace.best_s < winner.pace.best_s) ? session : winner, null);
    const bestButton = $('archive-best');
    bestButton.textContent = lapTime(best?.pace.best_s);
    bestButton.disabled = !best;
    bestButton.onclick = best ? () => this.onOpen(best.id, best.pace.best_ordinal) : null;
    $('archive-best-source').textContent = best ? `${dateLabel(best.metadata.RecordingTime)} · 第 ${best.pace.best_ordinal} 圈` : '暂无可统计圈次';
    const latest = this.visible.find(session => timestamp(session) != null);
    $('archive-median').textContent = lapTime(latest?.pace.median_s);
    $('archive-median-source').textContent = latest ? dateLabel(latest.metadata.RecordingTime) : '录制时间未知';
    $('archive-count').textContent = this.visible.reduce((count, session) => count + session.pace.count, 0);
    $('archive-session-count').textContent = `${this.visible.length} 次录制`;
    $('archive-rows').replaceChildren(...this.visible.map(session => this.row(session)));
    const points = this.visible.filter(session => timestamp(session) != null && session.pace.best_s != null);
    this.points = points.reverse();
    this.canvas.hidden = !points.length;
    $('trend-empty').hidden = points.length > 0;
    $('trend-empty').textContent = points.length ? '' : '暂无同时包含录制日期和可统计圈时的会话。';
    this.draw();
  }

  row(session){
    const row = document.createElement('tr');
    const pace = session.pace;
    for(const value of [dateLabel(session.metadata.RecordingTime), lapTime(pace.best_s), lapTime(pace.median_s),
      pace.stddev_s == null ? '—' : `${pace.stddev_s.toFixed(3)} s`, `${pace.count} / ${session.complete_lap_count}`]){
      row.insertCell().textContent = value;
    }
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'archive-link';
    button.textContent = pace.best_ordinal ? '查看最快圈' : '打开会话';
    button.title = session.filename;
    button.onclick = () => this.onOpen(session.id, pace.best_ordinal);
    row.insertCell().append(button);
    return row;
  }

  draw(){
    const rows = this.points || [];
    const {width, height} = this.canvas.getBoundingClientRect();
    if(!rows.length || width < 160 || height < 100) return;
    const ratio = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(width * ratio);
    this.canvas.height = Math.round(height * ratio);
    const ctx = this.canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const left = 75, right = width - 28, top = 16, bottom = height - 33;
    const first = timestamp(rows[0]), last = timestamp(rows.at(-1));
    const times = rows.flatMap(({pace}) => [pace.best_s, pace.median_s]);
    const padding = Math.max(.05, (Math.max(...times) - Math.min(...times)) * .1);
    const low = Math.min(...times) - padding, high = Math.max(...times) + padding;
    const x = session => first === last ? (left + right) / 2 : left + (timestamp(session) - first) * (right - left) / (last - first);
    const y = value => top + (value - low) * (bottom - top) / (high - low);
    ctx.font = '11px Segoe UI';
    ctx.textAlign = 'right';
    ctx.fillStyle = '#a5b0bb';
    ctx.strokeStyle = '#303841';
    for(let i = 0; i <= 4; i++){
      const value = low + (high - low) * i / 4, tick = y(value);
      ctx.beginPath();
      ctx.moveTo(left, tick);
      ctx.lineTo(right, tick);
      ctx.stroke();
      ctx.fillText(lapTime(value), left - 10, tick + 4);
    }
    ctx.textAlign = 'center';
    for(const session of first === last ? [rows[0]] : [rows[0], rows.at(-1)]){
      ctx.fillText(dayFormat.format(timestamp(session)), x(session), height - 9);
    }
    for(const [field, color] of [['median_s', '#6ecbd5'], ['best_s', '#ff804d']]){
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      rows.forEach((session, index) => ctx[index ? 'lineTo' : 'moveTo'](x(session), y(session.pace[field])));
      ctx.stroke();
      for(const session of rows){
        ctx.beginPath();
        ctx.arc(x(session), y(session.pace[field]), 3, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
}
