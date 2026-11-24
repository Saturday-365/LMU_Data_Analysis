import {dateLabel, lapTime, trackName, typeLabel} from './archive.js';
import {growthGroups, growthSummary, hasPace, timeChange} from './growth-data.js';

const $ = id => document.getElementById(id);
const day = new Intl.DateTimeFormat('zh-CN', {month:'numeric', day:'numeric'});
const clock = new Intl.DateTimeFormat('zh-CN', {hour:'2-digit', minute:'2-digit'});
const colors = {fastest:'#ffb58d', pace:'#80ced9', record:'#9fe0be'};

function seconds(ms){return (Math.abs(ms) / 1000).toFixed(3) + ' 秒';}

function setChange(id, text, change = 0){
  const target = $(id);
  target.textContent = text;
  target.dataset.improved = String(change < 0);
}

function changeLabel(change, lower, higher){
  if(change === 0) return '与基准持平';
  return '较基准' + (change < 0 ? lower : higher) + ' ' + seconds(change);
}

function groupLabel(group){
  const {session} = group.points.at(-1);
  const meta = session.metadata;
  return [trackName(meta), typeLabel(meta.SessionType), meta.CarClass, session.vehicle_model || meta.CarName].join(' · ');
}

function milestoneItem({point, change}, onOpen){
  const item = document.createElement('li');
  item.className = 'growth-milestone';
  const icon = document.createElement('span');
  icon.className = 'growth-milestone-icon';
  icon.dataset.icon = change == null ? 'stopwatch' : 'trend';
  icon.setAttribute('aria-hidden', 'true');
  const body = document.createElement('div');
  const heading = document.createElement('h4');
  heading.textContent = change == null ? '建立基准' : '刷新个人最佳';
  const value = document.createElement('p');
  value.textContent = lapTime(point.pace.best_s);
  if(change != null){
    const delta = document.createElement('span');
    delta.textContent = '快 ' + seconds(change);
    value.append(delta);
  }
  const date = document.createElement('time');
  date.dateTime = new Date(point.time).toISOString();
  date.textContent = dateLabel(date.dateTime);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'overview-best';
  button.textContent = '查看最快圈';
  button.setAttribute('aria-label', '查看 ' + date.textContent + ' 的最快圈');
  button.onclick = () => onOpen(point);
  body.append(heading, value, date, button);
  item.append(icon, body);
  return item;
}

function drawGrowth(canvas, trend, selected){
  const {width, height} = canvas.getBoundingClientRect();
  if(!trend.length || width < 140) return null;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext('2d');
  ctx.scale(ratio, ratio);
  const left = 67, right = width - 15, top = 12, bottom = height - 26;
  const last = trend.length - 1;
  const x = index => last ? left + (right - left) * index / last : (left + right) / 2;
  let low = Infinity, high = -Infinity;
  for(const {point:{pace}} of trend){
    const median = hasPace(pace) ? pace.median_s : pace.best_s;
    low = Math.min(low, pace.best_s, median);
    high = Math.max(high, pace.best_s, median);
  }
  const padding = Math.max(.04, (high - low) * .12);
  low = Math.max(0, low - padding);
  high += padding;
  const y = value => top + (value - low) * (bottom - top) / (high - low);
  ctx.font = '11px "Segoe UI", sans-serif';
  ctx.textAlign = 'right';
  ctx.fillStyle = '#aab8c4';
  for(let i = 0; i <= 4; i++){
    const value = low + (high - low) * i / 4;
    const tick = y(value);
    ctx.strokeStyle = '#303a42';
    ctx.beginPath();
    ctx.moveTo(left, tick);
    ctx.lineTo(right, tick);
    ctx.stroke();
    ctx.fillText(lapTime(value), left - 8, tick + 4);
  }
  const firstTime = trend[0].point.time, lastTime = trend[last].point.time;
  const dates = day.format(firstTime) === day.format(lastTime) ? clock : day;
  ctx.textAlign = last ? 'left' : 'center';
  ctx.fillText(dates.format(firstTime), x(0), height - 7);
  if(last){
    ctx.textAlign = 'right';
    ctx.fillText(dates.format(lastTime), x(last), height - 7);
  }
  ctx.strokeStyle = '#738590';
  ctx.beginPath();
  ctx.moveTo(x(selected), top);
  ctx.lineTo(x(selected), bottom);
  ctx.stroke();

  // 样本不足的中位圈断开绘制，虚线保留截至每次录制的历史最佳。
  for(const [field, color] of Object.entries(colors)){
    ctx.beginPath();
    ctx.strokeStyle = ctx.fillStyle = color;
    ctx.lineWidth = 1.6;
    ctx.setLineDash(field === 'record' ? [5, 4] : []);
    let previous = null;
    const dots = [];
    trend.forEach(({point:{pace}, best, record}, index) => {
      const value = field === 'fastest' ? pace.best_s : field === 'record' ? best : hasPace(pace) ? pace.median_s : null;
      if(value == null){previous = null; return;}
      const pos = x(index);
      const row = y(value);
      if(previous == null) ctx.moveTo(pos, row);
      else {
        if(field === 'record') ctx.lineTo(pos, previous);
        ctx.lineTo(pos, row);
      }
      previous = row;
      if(field !== 'record' || record) dots.push([pos, row, index === selected ? 4.5 : 3]);
    });
    ctx.stroke();
    for(const [pos, row, radius] of dots){
      ctx.beginPath();
      ctx.arc(pos, row, radius, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  return {left, right, top, bottom, last};
}

export class DriverGrowth {
  constructor(onOpen){
    this.onOpen = ({session, pace}) => onOpen(session.id, pace.best_ordinal, 'telemetry');
    this.groups = [];
    this.group = $('growth-group');
    this.recording = $('growth-recording');
    this.canvas = $('growth-chart');
    this.group.onchange = () => this.render();
    this.recording.onchange = () => this.selectRecording();
    $('growth-open-recording').onclick = () => this.onOpen(this.trend[this.recording.selectedIndex].point);
    this.canvas.onclick = event => {
      if(!this.plot) return;
      const {left, right, top, bottom, last} = this.plot;
      if(event.offsetX < left - 6 || event.offsetX > right + 6
        || event.offsetY < top - 6 || event.offsetY > bottom + 6) return;
      const position = (event.offsetX - left) / (right - left);
      this.recording.selectedIndex = Math.max(0, Math.min(last, Math.round(position * last)));
      this.selectRecording();
    };
    new ResizeObserver(() => this.draw()).observe(this.canvas);
  }

  setSessions(sessions){this.groups = growthGroups(sessions);}

  render(){
    const group = this.groups.find(item => item.key === this.group.value)
      || this.groups.find(({points}) => points[0].time < points.at(-1).time) || this.groups[0];
    $('growth-empty').hidden = Boolean(group);
    $('growth-filter').hidden = $('growth-content').hidden = !group;
    if(!group){
      this.trend = [];
      this.group.replaceChildren();
      this.recording.replaceChildren();
      $('growth-period').textContent = '';
      return;
    }
    this.group.replaceChildren(...this.groups.map(item => new Option(groupLabel(item), item.key)));
    this.group.value = group.key;
    this.group.title = groupLabel(group);
    const {points} = group;
    const first = points[0], latest = points.at(-1);
    const date = point => dateLabel(point.session.metadata.RecordingTime);
    $('growth-period').textContent = points.length === 1 ? '1 次录制 · ' + date(first)
      : points.length + ' 次录制 · ' + date(first) + ' 至 ' + date(latest);

    const {best, trend, milestones, firstPace, recentPace} = growthSummary(points);
    this.trend = trend;
    $('growth-best').textContent = lapTime(best.pace.best_s);
    const bestChange = timeChange(best.pace.best_s, first.pace.best_s);
    setChange('growth-best-change', latest.time === first.time ? '已建立起点'
      : changeLabel(bestChange, '快', '慢'), bestChange);
    $('growth-pace').textContent = lapTime(recentPace?.pace.median_s);
    $('growth-spread').textContent = recentPace ? recentPace.pace.stddev_s.toFixed(3) + ' 秒' : '—';
    const comparablePace = Boolean(firstPace && recentPace.time > firstPace.time);
    for(const [id, field, lower, higher] of [
      ['growth-pace-change','median_s','快','慢'], ['growth-spread-change','stddev_s','收窄','扩大']
    ]){
      const change = comparablePace ? timeChange(recentPace.pace[field], firstPace.pace[field]) : 0;
      const source = recentPace && recentPace !== latest ? ' · ' + date(recentPace) : '';
      setChange(id, comparablePace ? changeLabel(change, lower, higher) + source
        : recentPace ? '已建立基准 · ' + date(recentPace) : '每场至少需要 3 个统计圈', change);
      $(id).title = recentPace ? '最近可统计录制 ' + date(recentPace) : '';
    }

    $('growth-record-count').textContent = '已刷新 ' + (milestones.length - 1) + ' 次';
    $('growth-milestone-list').replaceChildren(...milestones.reverse().map(item => milestoneItem(item, this.onOpen)));
    const current = this.recording.value;
    this.recording.replaceChildren(...points.map((point,index) => new Option(
      (index + 1) + ' · ' + date(point), point.session.id)));
    const currentIndex = points.findIndex(({session}) => session.id === current);
    this.recording.selectedIndex = currentIndex < 0 ? points.length - 1 : currentIndex;
    this.selectRecording();
  }

  selectRecording(){
    const {point:{pace, session}, best, record} = this.trend[this.recording.selectedIndex];
    const gap = timeChange(pace.best_s, best);
    const context = record ? (this.recording.selectedIndex === 0 ? '成长基准' : '刷新个人最佳')
      : gap === 0 ? '追平当时的个人最佳' : '距当时个人最佳 ' + seconds(gap);
    const stats = hasPace(pace) ? '中位圈 ' + lapTime(pace.median_s) + ' · 波动 ' + pace.stddev_s.toFixed(3) + ' 秒'
      : '统计圈少于 3 圈';
    $('growth-recording-note').textContent = [
      '最快圈 ' + lapTime(pace.best_s), stats, pace.count + ' / ' + session.complete_lap_count + ' 个统计圈', context
    ].join(' · ');
    this.draw();
  }

  draw(){this.plot = drawGrowth(this.canvas, this.trend || [], this.recording.selectedIndex);}
}
