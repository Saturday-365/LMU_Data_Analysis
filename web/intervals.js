import {layoutKey} from './archive.js';
import {BRAKE_THRESHOLD, THROTTLE_THRESHOLD, intervalDelta, intervalMetrics} from './interval-metrics.js';

const $ = id => document.getElementById(id);
const METRICS = [
  ['brake', '刹车点（m）'],
  ['speed', '最低速度（km/h）'],
  ['throttle', '回油点（m）'],
];
const WRITE_HEADERS = {'X-LMU-Client':'web', 'Content-Type':'application/json'};

export class IntervalReview {
  constructor(api,focus,placeCursor){
    this.api = api;
    this.focus = focus;
    this.placeCursor = placeCursor;
    this.library = $('interval-presets');
    this.name = $('interval-name');
    this.start = $('interval-start');
    this.end = $('interval-end');
    this.status = $('interval-library-status');
    this.originButton = $('interval-mark-start');
    this.endButton = $('interval-mark-end');
    this.saveButton = $('interval-save');
    this.removeButton = $('interval-delete');
    this.library.onchange = () => this.select(this.library.value);
    this.saveButton.onclick = () => this.save();
    this.removeButton.onclick = () => this.remove();
    this.originButton.onclick = () => this.capture(this.start);
    this.endButton.onclick = () => this.capture(this.end);
    $('interval-form').onsubmit = event => {event.preventDefault(); this.analyze();};
    $('interval-metric-note').textContent =
      `刹车 ≥ ${BRAKE_THRESHOLD}%，回油 ≥ ${THROTTLE_THRESHOLD}% 且在最低速度点之后。动作需持续至少 0.15 秒。`;
    this.clear();
  }

  clear(){
    this.context = null;
    this.lastDistance = null;
    this.presets = [];
    $('comparison-interval').hidden = true;
    this.status.textContent = '';
    $('interval-result').textContent = '';
    $('interval-metrics').hidden = true;
    this.toggleCapture();
  }

  setComparison(session,traces,delta){
    this.clear();
    $('comparison-interval').hidden = !delta;
    $('delta-description').textContent = delta?.reason || '';
    $('interval-form').hidden = !delta?.values;
    $('interval-library').hidden = !delta?.values || !layoutKey(session.metadata);
    if(!delta?.values) return;
    this.context = {traces, delta, url:`/sessions/${session.id}/intervals`, ready:false};
    this.defaultBounds();
    this.library.replaceChildren(new Option('新建区间',''));
    this.name.value = '';
    this.updateButtons(false);
    if(!$('interval-library').hidden) this.refresh(this.context);
  }

  defaultBounds(){
    const distances = this.context.delta.distance_m;
    this.start.value = Math.ceil(distances[0]);
    this.end.value = Math.floor(distances.at(-1));
  }

  recordCursor(value,axis){
    if(axis !== 'distance') this.lastDistance = null;
    else if(this.context && Number.isFinite(value)) this.lastDistance = value;
    this.toggleCapture();
  }

  toggleCapture(){
    this.originButton.disabled = this.endButton.disabled = this.lastDistance == null;
  }

  capture(input){
    if(this.lastDistance == null) return;
    const distances = this.context.delta.distance_m;
    input.value = Math.max(distances[0], Math.min(distances.at(-1), Number(this.lastDistance.toFixed(2))));
  }

  updateButtons(busy){
    this.library.disabled = busy || !this.context?.ready;
    this.name.disabled = this.saveButton.disabled = this.library.disabled;
    this.removeButton.disabled = this.library.disabled || !this.library.value;
  }

  async refresh(context,selected = ''){
    this.updateButtons(true);
    try{
      const result = await this.api(context.url);
      if(this.context !== context) return;
      this.presets = result.items;
      this.library.replaceChildren(new Option('新建区间',''), ...this.presets.map(item => new Option(item.name,item.id)));
      if(this.presets.some(item => item.id === selected)) this.library.value = selected;
      context.ready = true;
    }catch(error){
      if(this.context === context) this.status.textContent = `区间库读取失败：${error.message}`;
    }finally{
      if(this.context === context) this.updateButtons(false);
    }
  }

  select(id){
    const selected = this.presets.find(item => item.id === id);
    this.name.value = selected?.name || '';
    this.status.textContent = '';
    this.updateButtons(false);
    if(selected){
      this.start.value = selected.start_m;
      this.end.value = selected.end_m;
      this.analyze();
    }
  }

  bounds(){
    const start = this.start.valueAsNumber, end = this.end.valueAsNumber;
    const distance = this.context.delta.distance_m;
    return start < end && start >= distance[0] && end <= distance.at(-1) ? [start,end] : null;
  }

  async save(){
    const context = this.context;
    const bounds = this.bounds();
    const name = this.name.value.trim(), id = this.library.value;
    if(!bounds || !name || bounds[0] < 0){
      this.status.textContent = '请输入区间名称，以及共同覆盖范围内有效的起止距离。';
      return;
    }
    this.updateButtons(true);
    this.status.textContent = '';
    try{
      const [start_m,end_m] = bounds;
      const item = await this.api(context.url + (id ? '/' + id : ''), {
        method:id ? 'PUT' : 'POST', headers:WRITE_HEADERS, body:JSON.stringify({name,start_m,end_m}),
      });
      if(this.context !== context) return;
      this.status.textContent = `已保存 ${item.name}`;
      await this.refresh(context,item.id);
    }catch(error){
      if(this.context === context) this.status.textContent = error.message;
    }finally{
      if(this.context === context) this.updateButtons(false);
    }
  }

  async remove(){
    const context = this.context, id = this.library.value;
    const item = this.presets.find(preset => preset.id === id);
    if(!item || !window.confirm(`删除区间「${item.name}」？`)) return;
    this.updateButtons(true);
    this.status.textContent = '';
    try{
      await this.api(context.url + '/' + id, {method:'DELETE',headers:WRITE_HEADERS});
      if(this.context !== context) return;
      this.name.value = '';
      this.status.textContent = '已删除区间。';
      await this.refresh(context);
    }catch(error){
      if(this.context === context) this.status.textContent = error.message;
    }finally{
      if(this.context === context) this.updateButtons(false);
    }
  }

  analyze(){
    if(!this.context) return;
    const bounds = this.bounds(), result = $('interval-result');
    $('interval-metrics').hidden = true;
    if(!bounds){
      result.textContent = '请输入共同覆盖范围内由小到大的距离。';
      return;
    }
    const [start,end] = bounds;
    const difference = intervalDelta(this.context.delta,start,end);
    this.focus(start,end);
    if(difference == null){
      result.textContent = '区间包含未能对齐的样点，无法计算区间得失。';
    }else if(Math.abs(difference) < .0005){
      result.textContent = '该区间两圈节奏相同（精确到毫秒）。';
    }else{
      result.textContent = `当前圈在该区间${difference > 0 ? '丢失' : '追回'} ${Math.abs(difference).toFixed(3)} 秒。`;
    }
    this.renderMetrics(this.context.traces.map(trace=>intervalMetrics(trace,start,end)));
  }

  renderMetrics([current,reference]){
    const rows = $('interval-metric-rows');
    rows.replaceChildren();
    for(const [key,title] of METRICS){
      const row = rows.insertRow();
      const heading = document.createElement('th');
      heading.scope = 'row';
      heading.textContent = title;
      row.append(heading);
      for(const metric of [current[key],reference[key]]){
        const cell = row.insertCell();
        if(metric.value == null){
          const reason = document.createElement('small');
          reason.textContent = metric.reason;
          cell.append(reason);
          continue;
        }
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = metric.value.toFixed(1);
        button.title = `定位于 ${metric.distance.toFixed(1)} m`;
        button.onclick = () => this.placeCursor(metric.distance);
        cell.append(button);
      }
      const [a,b] = [current[key].value,reference[key].value];
      const difference = a == null || b == null ? null : Number((a-b).toFixed(1));
      row.insertCell().textContent = difference == null ? '—' : `${difference > 0 ? '+' : ''}${difference.toFixed(1)}`;
    }
    $('interval-metrics').hidden = false;
  }
}
