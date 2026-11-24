import {lapTime, typeLabel, vehicleName} from './archive.js';
import {chartHits, growthAxis, growthGroups, minimumGrowthWidth} from './growth-data.js';

const $ = id => document.getElementById(id);
const fullDay = new Intl.DateTimeFormat('zh-CN', {year:'numeric', month:'numeric', day:'numeric'});
const dayAndTime = new Intl.DateTimeFormat('zh-CN', {month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit'});
const yearAndTime = new Intl.DateTimeFormat('zh-CN', {year:'numeric', month:'numeric', day:'numeric',
  hour:'2-digit', minute:'2-digit'});
const clock = new Intl.DateTimeFormat('zh-CN', {hour:'2-digit', minute:'2-digit'});
const exactClock = new Intl.DateTimeFormat('zh-CN', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
const recordedAt = new Intl.DateTimeFormat('zh-CN', {year:'numeric', month:'2-digit', day:'2-digit',
  hour:'2-digit', minute:'2-digit', second:'2-digit'});
const series = [
  {field:'fastest', label:'最快圈', dashed:false},
  {field:'top5', label:'最快 5 圈平均', dashed:true},
];

function drawGrowth(canvas, rows){
  const {width, height} = canvas.getBoundingClientRect();
  if(!rows.length || width < 140) return [];
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.min(16384, Math.round(width * ratio));
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext('2d');
  ctx.scale(canvas.width / width, canvas.height / height);
  const {left, right, position, ticks} = growthAxis(rows.length, width);
  const top = 15, bottom = height - 27;
  const first = rows[0].time, last = rows.at(-1).time;
  let low = Infinity, high = -Infinity;
  for(const row of rows){
    for(const {field} of series){
      if(row[field] == null) continue;
      low = Math.min(low, row[field]);
      high = Math.max(high, row[field]);
    }
  }
  const padding = Math.max(.05, (high - low) * .08);
  low = Math.max(0, low - padding);
  high += padding;
  const y = value => top + (value - low) * (bottom - top) / (high - low);
  ctx.font = '11px "Segoe UI", sans-serif';
  ctx.textAlign = 'right';
  ctx.fillStyle = '#aab8c4';
  ctx.strokeStyle = '#303a42';
  for(let i = 0; i <= 4; i++){
    const value = low + (high - low) * i / 4;
    const tick = y(value);
    ctx.beginPath();
    ctx.moveTo(left, tick);
    ctx.lineTo(right, tick);
    ctx.stroke();
    ctx.fillText(lapTime(value), left - 8, tick + 4);
  }
  const sameDay = fullDay.format(first) === fullDay.format(last);
  const formatter = sameDay ? (last - first < 120000 ? exactClock : clock)
    : new Date(first).getFullYear() === new Date(last).getFullYear() ? dayAndTime : yearAndTime;
  for(const index of ticks){
    ctx.textAlign = rows.length === 1 ? 'center' : index === 0 ? 'left' : index === rows.length - 1 ? 'right' : 'center';
    ctx.fillText(formatter.format(rows[index].time), position(index), height - 8);
  }

  const markers = [];
  const style = getComputedStyle(canvas);
  for(const {field, label, dashed} of series){
    const points = [];
    ctx.beginPath();
    ctx.strokeStyle = ctx.fillStyle = style.getPropertyValue('--growth-' + field).trim();
    ctx.lineWidth = 1.6;
    ctx.setLineDash(dashed ? [5, 4] : []);
    let drawing = false;
    // 缺少最快 5 圈平均的录制在该线留空，仍保留它的最快圈和表格记录。
    for(const [index, row] of rows.entries()){
      const value = row[field];
      if(value == null){drawing = false; continue;}
      const marker = {x:position(index), y:y(value), row, field, label, value};
      ctx[drawing ? 'lineTo' : 'moveTo'](marker.x, marker.y);
      points.push(marker);
      drawing = true;
    }
    ctx.stroke();
    ctx.setLineDash([]);
    for(const marker of points){
      ctx.beginPath();
      ctx.arc(marker.x, marker.y, dashed ? 4.7 : 3.5, 0, Math.PI * 2);
      if(dashed) ctx.stroke();
      else ctx.fill();
      markers.push(marker);
    }
  }
  return markers;
}

function tooltipItem({row:{session, time}, field, label, value}){
  const item = document.createElement('div');
  const title = document.createElement('strong');
  title.className = 'growth-' + field;
  title.textContent = label + ' · ' + lapTime(value);
  const car = document.createElement('div');
  car.textContent = (session.vehicle_model ? '车型 ' : '车辆标识 ') + vehicleName(session);
  const date = document.createElement('time');
  date.dateTime = new Date(time).toISOString();
  date.textContent = recordedAt.format(time) + ' · ' + typeLabel(session.metadata.SessionType);
  item.append(title, car, date);
  return item;
}

export class DriverGrowth {
  constructor(onOpen){
    this.onOpen = onOpen;
    this.groups = [];
    this.rows = [];
    this.markers = [];
    this.track = $('growth-track');
    this.viewport = $('growth-viewport');
    this.plot = $('growth-plot');
    this.canvas = $('growth-chart');
    this.tooltip = $('growth-tooltip');
    this.track.onchange = () => this.showTrack();
    this.canvas.onpointermove = event => this.showTooltip(event.offsetX, event.offsetY);
    this.canvas.onpointerleave = () => this.hideTooltip();
    this.viewport.onscroll = () => this.hideTooltip();
    new ResizeObserver(() => this.draw()).observe(this.canvas);
  }

  setSessions(sessions){this.groups = growthGroups(sessions);}

  render(){
    const selected = this.track.value;
    this.track.replaceChildren(...this.groups.map(group => new Option(group.label, group.key)));
    if(this.groups.some(group => group.key === selected)) this.track.value = selected;
    this.showTrack();
  }

  showTrack(){
    const group = this.groups[this.track.selectedIndex];
    const changedTrack = group?.key !== this.activeTrack;
    this.activeTrack = group?.key;
    $('growth-filter').hidden = $('growth-content').hidden = !group;
    const rows = group?.rows || [];
    $('growth-count').textContent = rows.length + ' 次录制';
    $('growth-rows').replaceChildren(...rows.map(row => this.createRow(row)));
    const dated = group?.hasLayout ? rows.filter(row => row.time != null) : [];
    const hasChart = dated.some(row => row.fastest != null);
    this.rows = hasChart ? dated : [];
    this.viewport.hidden = $('growth-chart-note').hidden = !hasChart;
    $('growth-chart-empty').hidden = hasChart;
    this.plot.style.minWidth = minimumGrowthWidth(this.rows.length) + 'px';
    if(changedTrack) this.viewport.scrollLeft = this.viewport.scrollWidth;
    this.draw();
  }

  createRow({session, time, fastest, top5}){
    const row = document.createElement('tr');
    row.insertCell().textContent = time == null ? '录制时间未知' : recordedAt.format(time);
    row.insertCell().textContent = vehicleName(session);
    row.insertCell().textContent = typeLabel(session.metadata.SessionType);
    const fastestCell = row.insertCell();
    fastestCell.className = 'growth-fastest';
    fastestCell.textContent = lapTime(fastest);
    if(session.pace.best_ordinal != null){
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'overview-best';
      button.textContent = lapTime(fastest);
      button.title = '打开会话的最快圈';
      button.onclick = () => this.onOpen(session.id, session.pace.best_ordinal, 'telemetry');
      fastestCell.replaceChildren(button);
    }
    const top5Cell = row.insertCell();
    top5Cell.className = 'growth-top5';
    top5Cell.textContent = lapTime(top5);
    row.insertCell().textContent = session.pace.count + ' / ' + session.complete_lap_count;
    return row;
  }

  draw(){
    this.hideTooltip();
    this.markers = drawGrowth(this.canvas, this.rows);
    $('growth-scroll-note').hidden = this.viewport.scrollWidth <= this.viewport.clientWidth;
  }

  hideTooltip(){
    this.tooltip.hidden = true;
    this.hovered = null;
  }

  showTooltip(x, y){
    const hits = chartHits(this.markers, x, y);
    const marker = hits[0];
    if(!marker){this.hideTooltip(); return;}
    if(marker === this.hovered) return;
    this.hovered = marker;
    this.tooltip.replaceChildren(...hits.map(tooltipItem));
    this.tooltip.hidden = false;
    const {offsetWidth:width, offsetHeight:height} = this.tooltip;
    const visibleLeft = this.viewport.scrollLeft;
    const visibleRight = visibleLeft + this.viewport.clientWidth;
    const left = marker.x + width + 14 <= visibleRight ? marker.x + 14 : marker.x - width - 14;
    const top = Math.min(this.canvas.clientHeight - height, marker.y - height / 2);
    this.tooltip.style.left = Math.max(visibleLeft, Math.min(left, visibleRight - width)) + 'px';
    this.tooltip.style.top = Math.max(0, top) + 'px';
  }
}
