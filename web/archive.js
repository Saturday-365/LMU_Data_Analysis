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
  return session.vehicle_model || [session.vehicle_brand,session.metadata.CarName].filter(Boolean).join(' · ') || '未知车辆';
}
function brandKey(session){return norm(session.vehicle_brand);}
function classKey(session){return norm(session.metadata.CarClass);}
function vehicleKey(session){
  const category = norm(session.metadata.CarClass);
  if(session.vehicle_model) return JSON.stringify(['model', norm(session.vehicle_model), category]);
  if(session.metadata.CarName) return JSON.stringify(['entry', norm(session.metadata.CarName), category]);
  return session.id;
}
function typeKey(session){
  const kind=norm(session.metadata.SessionType);
  return kind==='qualifying'?'qualify':kind || session.id;
}
function archiveLayout(session){return layoutKey(session.metadata) || session.id;}
export function sameGroup(a,b){
  return archiveLayout(a) === archiveLayout(b) && vehicleKey(a) === vehicleKey(b) && typeKey(a) === typeKey(b);
}

function options(select, sessions, key, label, desired){
  const current = desired ?? select.value;
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
    this.category = $('archive-class');
    this.type = $('archive-type');
    this.canvas = $('pace-trend');
    for(const input of [this.layout, this.car, this.category, this.type]) input.addEventListener('change', () => this.render());
    $('archive-show-overview').onclick = () => this.show('overview');
    $('archive-show-detail').onclick = () => this.show('detail');
    $('overview-type').onchange = () => this.renderOverview();
    new ResizeObserver(() => this.draw()).observe(this.canvas);
  }

  setSessions(sessions,overview){
    this.sessions = [...sessions].sort((a,b) => (timestamp(b) ?? -Infinity) - (timestamp(a) ?? -Infinity)
      || b.created_at.localeCompare(a.created_at));
    this.overview = overview;
    this.renderOverview();
    this.render();
  }

  show(mode,session){
    for(const name of ['overview','detail']){
      $(`archive-${name}`).hidden = name !== mode;
      $(`archive-show-${name}`).setAttribute('aria-pressed', String(name === mode));
    }
    if(mode === 'detail') this.render(session);
  }

  renderOverview(){
    if(!this.overview) return;
    const {totals,layouts} = this.overview;
    for(const [field,value] of Object.entries(totals)){
      $(`overview-${field.replace('_','-')}`).textContent = value.toLocaleString('zh-CN');
    }
    const kind = $('overview-type').value;
    const root = $('overview-tracks');
    root.replaceChildren();
    for(const layout of layouts){
      const groups = layout.groups.filter(group => !kind || group.kind === kind);
      if(!groups.length) continue;
      const card = document.createElement('article');
      card.className = 'track-overview';
      const header = document.createElement('header');
      const title = document.createElement('h3');
      title.textContent = trackName(layout.metadata);
      const stats = document.createElement('p');
      const displayed = field => groups.reduce((sum,group) => sum + group[field], 0);
      stats.textContent = `${displayed('sessions')} 次录制 · ${displayed('complete_laps')} 个完整圈 · ${displayed('pace_laps')} 圈计入节奏`;
      const date = document.createElement('small');
      date.textContent = layout.latest_at ? `最近录制 ${dateLabel(layout.latest_at)}` : '录制时间未知';
      header.append(title,stats,date);
      card.append(header,this.overviewTable(groups));
      root.append(card);
    }
    if(!root.childElementCount){
      const note = document.createElement('p');
      note.className = 'info-note';
      note.textContent = '没有该会话类型的录制。';
      root.append(note);
    }
  }

  overviewTable(groups){
    const wrap = document.createElement('div');
    wrap.className = 'table-scroll';
    const table = document.createElement('table');
    table.className = 'overview-table';
    const head = table.createTHead().insertRow();
    for(const label of ['类型','品牌','组别','会话','完整圈','统计圈','最快圈','中位圈','P10–P90']){
      const cell = document.createElement('th');
      cell.scope = 'col';
      cell.textContent = label;
      head.append(cell);
    }
    const body = table.createTBody();
    for(const group of groups){
      const row = body.insertRow();
      row.insertCell().textContent = typeLabel(group.kind);
      const brand = document.createElement('button');
      brand.className = 'overview-brand';
      brand.textContent = group.brand || '未识别品牌';
      brand.title = '查看该品牌与会话类型的录制';
      brand.onclick = () => this.show('detail',this.sessions.find(session => session.id === group.session_id));
      row.insertCell().append(brand);
      for(const value of [group.class || '—',group.sessions,group.complete_laps,group.pace_laps]){
        row.insertCell().textContent = value;
      }
      const best = row.insertCell();
      if(group.best_session){
        const link = document.createElement('button');
        link.className = 'overview-best';
        link.textContent = lapTime(group.pace.best_s);
        link.title = '打开最快圈';
        link.onclick = () => this.onOpen(group.best_session,group.best_ordinal);
        best.append(link);
      }else best.textContent = '—';
      row.insertCell().textContent = lapTime(group.pace.median_s);
      row.insertCell().textContent = group.pace.p10_s == null ? '—' : `${lapTime(group.pace.p10_s)} – ${lapTime(group.pace.p90_s)}`;
    }
    wrap.append(table);
    return wrap;
  }

  render(anchor){
    $('archive-loading').hidden = true;
    $('archive-empty').hidden = this.sessions.length > 0;
    $('archive-content').hidden = !this.sessions.length;
    if(!this.sessions.length) return;

    options(this.layout, this.sessions, archiveLayout, session => trackName(session.metadata), anchor && archiveLayout(anchor));
    const byLayout = this.sessions.filter(session => archiveLayout(session) === this.layout.value);
    options(this.car, byLayout, brandKey, session => session.vehicle_brand || '未识别品牌', anchor && brandKey(anchor));
    const byCar = byLayout.filter(session => brandKey(session) === this.car.value);
    options(this.category, byCar, classKey, session => session.metadata.CarClass || '未知组别', anchor && classKey(anchor));
    const byClass = byCar.filter(session => classKey(session) === this.category.value);
    options(this.type, byClass, typeKey, session => typeLabel(session.metadata.SessionType), anchor && typeKey(anchor));
    this.visible = byClass.filter(session => typeKey(session) === this.type.value);

    const comparable = Boolean(this.car.value && this.category.value && this.visible[0]?.metadata.SessionType);
    const trend = comparable ? this.visible : [];
    const best = trend.reduce((winner, session) => session.pace.best_s != null
      && (winner == null || session.pace.best_s < winner.pace.best_s) ? session : winner, null);
    const bestButton = $('archive-best');
    bestButton.textContent = lapTime(best?.pace.best_s);
    bestButton.disabled = !best;
    bestButton.onclick = best ? () => this.onOpen(best.id, best.pace.best_ordinal) : null;
    $('archive-best-source').textContent = best ? `${dateLabel(best.metadata.RecordingTime)} · 第 ${best.pace.best_ordinal} 圈`
      : comparable ? '暂无可统计圈次' : '分组信息缺失';
    const latest = trend.find(session => timestamp(session) != null);
    $('archive-median').textContent = lapTime(latest?.pace.median_s);
    $('archive-median-source').textContent = latest ? dateLabel(latest.metadata.RecordingTime)
      : comparable ? '录制时间未知' : '请检查品牌与组别';
    $('archive-count').textContent = this.visible.reduce((count, session) => count + session.pace.count, 0);
    $('archive-session-count').textContent = `${this.visible.length} 次录制`;
    $('archive-rows').replaceChildren(...this.visible.map(session => this.row(session)));
    const points = trend.filter(session => timestamp(session) != null && session.pace.best_s != null);
    this.points = points.reverse();
    this.canvas.hidden = !points.length;
    $('trend-empty').hidden = points.length > 0;
    $('trend-empty').textContent = points.length ? '' : comparable ? '暂无同时包含录制日期和可统计圈时的会话。'
      : '分组信息缺失，单场圈速可在会话表格查看。';
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
