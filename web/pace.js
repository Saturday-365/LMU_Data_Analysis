import {dateLabel, lapTime, sameGroup, typeLabel} from './archive.js';

const $ = id => document.getElementById(id);
const colors = ['#ff955f', '#72cdd4', '#c3a5ec', '#a5d28c'];
const starts = {recording_start:'录制起点', first_observation:'首次观测', pit_exit:'出站'};
const ends = {recording_end:'录制结束', pit_entry:'进站'};
const number = new Intl.NumberFormat('zh-CN', {maximumFractionDigits:2});

function seconds(value){
  return value == null ? '—' : `${value.toFixed(3)} s`;
}

function signed(value){
  return value == null ? '—' : (value > 0 ? '+' : '') + seconds(value);
}

function band(stats){
  return stats.p10_s == null ? '—' : `${lapTime(stats.p10_s)} – ${lapTime(stats.p90_s)}`;
}

function clock(seconds){
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

function canvasContext(canvas){
  const {width, height} = canvas.getBoundingClientRect();
  if(width < 160 || height < 70) return null;
  const r = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * r);
  canvas.height = Math.round(height * r);
  const context = canvas.getContext('2d');
  context.setTransform(r, 0, 0, r, 0, 0);
  context.font = '11px Segoe UI';
  return {context, width, height};
}

function line(ctx,x1,y1,x2,y2){
  ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
}

function point(ctx,x,y,radius){
  ctx.beginPath(); ctx.arc(x,y,radius,0,2*Math.PI); ctx.fill();
}

function setupText(setups){
  const labels = setups.names.map(({name, count}) => `${name}（${count} 圈）`);
  if(setups.unknown_count) labels.push(`未标注 ${setups.unknown_count} 圈`);
  return labels.join(' · ') || '暂无纳入统计的圈';
}

function contextText(conditions){
  return conditions.map(({key,label,effective}) => {
    if(effective.state !== 'known') return `${label}未知`;
    const {value, unit, source} = effective;
    const formatted = typeof value === 'object'
      ? [value.min, value.max].filter((item,index,values) => index === 0 || item !== values[0])
        .map(item => number.format(item)).join('–')
      : value;
    const title = key === 'tyres' ? '轮胎' : label;
    return `${title} ${formatted}${unit ? ' ' + unit : ''}${source === 'user' ? '（补录）' : ''}`;
  }).join(' · ');
}

function refillScopes(select, data){
  select.replaceChildren(new Option('整场', ''), ...data.stints.map(stint =>
    new Option(`驾驶段 ${stint.number} · ${stint.statistics.count} 圈`, String(stint.number))));
  select.disabled = false;
}

export class SessionPace {
  constructor(api, openLap){
    this.api = api;
    this.openLap = openLap;
    this.request = this.referenceRequest = 0;
    this.timeline = $('pace-laps');
    this.comparison = $('pace-compare');
    this.sessionB = $('pace-b-session');
    this.scopeA = $('pace-a-scope');
    this.scopeB = $('pace-b-scope');
    this.scopeA.onchange = this.scopeB.onchange = () => this.renderComparison();
    this.sessionB.onchange = () => this.loadReference();
    this.timeline.onclick = event => {
      const bounds = this.timeline.getBoundingClientRect();
      const lap = this.timelinePoints?.find(p => Math.hypot(event.clientX - bounds.left - p.x, event.clientY - bounds.top - p.y) <= 9);
      if(lap) this.openLap(this.session.id, lap.ordinal);
    };
    new ResizeObserver(() => this.drawTimeline()).observe(this.timeline);
    new ResizeObserver(() => this.drawComparison()).observe(this.comparison);
  }

  setSession(session){
    this.request++;
    this.referenceRequest++;
    this.session = session;
    this.a = this.b = this.compared = null;
    this.timelinePoints = [];
    $('pace-content').hidden = true;
    $('pace-status').textContent = '';
  }

  async load(){
    if(!this.session) return;
    const generation = ++this.request;
    this.referenceRequest++;
    const id = this.session.id;
    $('pace-content').hidden = true;
    $('pace-status').textContent = '正在核对进出站记录和圈速…';
    try{
      const [data, catalog] = await Promise.all([this.api(`/sessions/${id}/pace`), this.api('/sessions')]);
      if(generation !== this.request) return;
      this.a = data;
      this.b = this.compared = null;
      this.renderTimeline();
      this.renderStints();
      refillScopes(this.scopeA, data);
      const current = catalog.items.find(item => item.id === id);
      const candidates = catalog.items.filter(item => item.id !== id && current && sameGroup(current, item)
        && item.pace.count > 0);
      if(data.stints.filter(stint => stint.statistics.count).length >= 2) candidates.unshift(current || this.session);
      this.sessionB.replaceChildren(new Option('选择参考会话', ''), ...candidates.map(item =>
        new Option(item.id === id ? '同会话的另一驾驶段'
          : `${dateLabel(item.metadata.RecordingTime)} · ${typeLabel(item.metadata.SessionType)} · ${lapTime(item.pace.best_s)}`, item.id)));
      this.sessionB.disabled = !candidates.length;
      this.scopeB.replaceChildren(new Option('—', ''));
      this.scopeB.disabled = true;
      this.renderComparison();
      $('pace-status').textContent = '';
      $('pace-content').hidden = false;
    }catch(error){
      if(generation === this.request) $('pace-status').textContent = `读取失败：${error.message}。点击本页标签重试。`;
    }
  }

  async loadReference(){
    const sequence = ++this.referenceRequest;
    this.b = this.compared = null;
    this.scopeB.disabled = true;
    this.scopeB.replaceChildren(new Option('—', ''));
    this.renderComparison();
    const id = this.sessionB.value;
    if(!id) return;
    $('pace-ab-status').textContent = '正在读取参考会话…';
    try{
      const data = id === this.session.id ? this.a : await this.api(`/sessions/${id}/pace`);
      if(sequence !== this.referenceRequest) return;
      this.b = data;
      refillScopes(this.scopeB, data);
      if(id === this.session.id){
        const measured = data.stints.filter(stint => stint.statistics.count);
        if(!this.scopeA.value) this.scopeA.value = String(measured[0].number);
        this.scopeB.value = String(measured.find(stint => String(stint.number) !== this.scopeA.value).number);
      }
      this.renderComparison();
    }catch(error){
      if(sequence === this.referenceRequest) $('pace-ab-status').textContent = `读取参考会话失败：${error.message}`;
    }
  }

  renderTimeline(){
    const data = this.a;
    const count = data.statistics.count;
    $('pace-summary').textContent = `${count} 圈参与统计 · ${data.excluded_count} 个完整圈被排除`;
    this.timeline.hidden = !count;
    $('pace-track-note').textContent = count
      ? '横轴为录制经过时间。彩色背景对应驾驶段，灰色为已观测维修区。点击圈速点查看该圈。'
      : '此会话没有可统计的完整圈。';
    this.drawTimeline();
  }

  drawTimeline(){
    if(!this.a || this.timeline.hidden) return;
    const surface = canvasContext(this.timeline);
    if(!surface) return;
    const {context:ctx,width,height} = surface, data = this.a;
    const left = 76, right = width - 28, top = 17, bottom = height - 36;
    const stats = data.statistics;
    const padding = Math.max(.1, (stats.slowest_s - stats.best_s) * .07);
    const low = Math.max(0, stats.best_s - padding), high = stats.slowest_s + padding;
    const x = value => left + value * (right - left) / data.duration_s;
    const y = value => top + (value - low) * (bottom - top) / (high - low);
    for(const stint of data.stints){
      ctx.globalAlpha = .1;
      ctx.fillStyle = colors[(stint.number - 1) % colors.length];
      ctx.fillRect(x(stint.start_s),top,x(stint.end_s) - x(stint.start_s),bottom - top);
    }
    ctx.globalAlpha = .22;
    ctx.fillStyle = '#8d99a5';
    for(const visit of data.pit_visits) ctx.fillRect(x(visit.start_s),top,x(visit.end_s) - x(visit.start_s),bottom - top);
    ctx.globalAlpha = 1;
    ctx.fillStyle = '#a8b2bd';
    ctx.strokeStyle = '#38424c';
    ctx.textAlign = 'right';
    for(let index = 0; index <= 4; index++){
      const time = low + (high - low) * index / 4;
      line(ctx,left,y(time),right,y(time));
      ctx.fillText(lapTime(time),left - 9,y(time) + 4);
    }
    ctx.textAlign = 'center';
    for(let index = 0; index <= 5; index++){
      const elapsed = data.duration_s * index / 5;
      ctx.fillText(clock(elapsed),x(elapsed),height - 12);
    }
    this.timelinePoints = [];
    for(const lap of data.laps.filter(lap => lap.eligible)){
      const px = x(lap.end_s), py = y(lap.time_s);
      ctx.fillStyle = lap.stint ? colors[(lap.stint - 1) % colors.length] : '#aab5c0';
      point(ctx,px,py,4);
      this.timelinePoints.push({x:px,y:py,ordinal:lap.ordinal});
    }
  }

  renderStints(){
    const {stints, pit_visits:visits, stint_reason:reason, unassigned_count:unassigned} = this.a;
    $('pace-stint-table').hidden = !stints.length;
    const rows = $('pace-stints');
    rows.replaceChildren();
    for(const stint of stints){
      const row = rows.insertRow();
      const detail = document.createElement('small');
      detail.textContent = `${clock(stint.start_s)}–${clock(stint.end_s)} · ${starts[stint.start_kind]} → ${ends[stint.end_kind]}`;
      row.insertCell().append(`第 ${stint.number} 段`, detail);
      const stats = stint.statistics;
      row.insertCell().textContent = stats.count;
      const cell = row.insertCell();
      if(stats.best_ordinal){
        const link = document.createElement('button');
        link.className = 'archive-link';
        link.textContent = lapTime(stats.best_s);
        link.title = `查看第 ${stats.best_ordinal} 圈`;
        link.onclick = () => this.openLap(this.session.id, stats.best_ordinal);
        cell.append(link);
      }else cell.textContent = '—';
      for(const metric of [lapTime(stats.median_s),band(stats),seconds(stats.stddev_s),signed(stats.last_vs_first_s)]){
        row.insertCell().textContent = metric;
      }
    }
    const closed = visits.filter(visit => visit.end_kind === 'pit_exit').length;
    const notes = [reason || (stints.length ? `观测到 ${stints.length} 个驾驶段，${closed} 次记录完整的进出站。`
      : '该录制未观测到赛道驾驶区间。')];
    if(unassigned) notes.push(`${unassigned} 个可统计圈无法归入已观测驾驶段。`);
    if(visits.length > closed) notes.push('末次进站延续至录制结束。');
    if(stints.length) notes.push('P10–P90 至少需要 5 圈。前后节奏差比较末 3 圈与首 3 圈的中位数。');
    $('pace-stint-note').textContent = notes.join(' ');
  }

  renderComparison(){
    const status = $('pace-ab-status'), content = $('pace-ab-content');
    this.compared = null;
    content.hidden = true;
    if(!this.b){
      status.textContent = this.sessionB.disabled ? '需要同布局、车辆和会话类型的录制，或本场至少两个有圈速的驾驶段。'
        : '选择 B 会话或本场的另一驾驶段。可在「练习信息」为整场或单圈补录调教名称。';
      return;
    }
    if(this.sessionB.value === this.session.id && (!this.scopeA.value || !this.scopeB.value || this.scopeA.value === this.scopeB.value)){
      status.textContent = '对照同一会话时，请选择两个不同的驾驶段。';
      return;
    }
    const a = this.a.stints.find(stint => String(stint.number) === this.scopeA.value) || this.a;
    const b = this.b.stints.find(stint => String(stint.number) === this.scopeB.value) || this.b;
    if(!a.statistics.count || !b.statistics.count){
      status.textContent = '至少一侧没有可统计的圈，请更换对照范围。';
      return;
    }
    status.textContent = '';
    $('pace-a-title').textContent = 'A · ' + setupText(a.setups);
    $('pace-b-title').textContent = 'B · ' + setupText(b.setups);
    $('pace-a-conditions').textContent = contextText(this.a.conditions);
    $('pace-b-conditions').textContent = contextText(this.b.conditions);
    const aa = a.statistics, bb = b.statistics;
    const rows = $('pace-ab-rows');
    rows.replaceChildren();
    for(const [label,key,formatter] of [['纳入统计圈次','count',String],['最快圈','best_s',lapTime],
      ['中位圈','median_s',lapTime],['圈速标准差','stddev_s',seconds],['P10–P90 圈速',null,band]]){
      const row = rows.insertRow();
      const diff = key && key !== 'count' && aa[key] != null && bb[key] != null ? bb[key] - aa[key] : null;
      for(const text of [label,formatter(key ? aa[key] : aa),formatter(key ? bb[key] : bb),signed(diff)]){
        row.insertCell().textContent = text;
      }
    }
    this.compared = [aa,bb];
    content.hidden = false;
    this.drawComparison();
  }

  drawComparison(){
    if(!this.compared) return;
    const surface = canvasContext(this.comparison);
    if(!surface) return;
    const {context:ctx,width,height} = surface;
    const left = 40, right = width - 43;
    const best = Math.min(...this.compared.map(stat => stat.best_s));
    const slowest = Math.max(...this.compared.map(stat => stat.slowest_s));
    const padding = Math.max(.05,(slowest - best) * .05), low = Math.max(0,best - padding), high = slowest + padding;
    const x = value => left + (value - low) * (right - left) / (high - low);
    ctx.textAlign = 'center';
    ctx.fillStyle = '#a8b2bd';
    ctx.strokeStyle = '#374047';
    for(let index = 0; index <= 4; index++){
      const time = low + (high - low) * index / 4;
      line(ctx,x(time),15,x(time),height-29);
      ctx.fillText(lapTime(time),x(time),height-10);
    }
    this.compared.forEach((stats,index) => {
      const y = 37 + index * 33;
      ctx.fillStyle = ctx.strokeStyle = colors[index];
      ctx.lineWidth = 1.5;
      ctx.fillText(index ? 'B' : 'A',17,y+4);
      line(ctx,x(stats.best_s),y,x(stats.slowest_s),y);
      if(stats.p10_s != null){
        ctx.globalAlpha = .55;
        ctx.fillRect(x(stats.p10_s),y-9,Math.max(1,x(stats.p90_s)-x(stats.p10_s)),18);
        ctx.globalAlpha = 1;
      }
      line(ctx,x(stats.median_s),y-12,x(stats.median_s),y+12);
      point(ctx,x(stats.best_s),y,3);
      point(ctx,x(stats.slowest_s),y,3);
    });
  }
}
