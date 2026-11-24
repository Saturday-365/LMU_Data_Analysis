import {dateLabel, lapTime, timestamp, trackName, typeLabel} from './archive.js';

const $ = id => document.getElementById(id);
const RACE_LENGTHS = [['short','20 分钟内'],['medium','20–40 分钟'],
  ['long','40–60 分钟'],['endurance','60 分钟及以上']];
const COLORS = ['#79cfd6','#ffb48b','#bea5e8','#9ccd90'];
const BOUNDARIES = {pit_entry:'进站',pit_exit:'出站',recording_start:'录制起点',recording_end:'录制结束',first_observation:'首次观测'};

function node(tag,text,className){
  const element = document.createElement(tag);
  if(text != null) element.textContent = text;
  if(className) element.className = className;
  return element;
}

function button(text,onClick,className){
  const element = node('button',text,className);
  element.type = 'button';
  element.onclick = onClick;
  return element;
}

function clock(seconds){
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded/60)}:${String(rounded%60).padStart(2,'0')}`;
}

function addCells(row,values){
  for(const value of values){
    const cell = row.insertCell();
    if(value instanceof HTMLElement) cell.append(value);
    else cell.textContent = value;
  }
}

export class CircuitOverview {
  constructor(api,openSession,openGroup){
    this.api = api;
    this.openSession = openSession;
    this.openGroup = openGroup;
    this.chart = $('latest-chart');
    this.graphRows = [];
    this.latestId = null;
    $('overview-track').onchange = event => {
      $(event.target.value)?.scrollIntoView({block:'start'});
    };
    new ResizeObserver(() => this.drawSpread()).observe(this.chart);
  }

  setData(overview,sessions){
    const {totals,layouts} = overview;
    this.byId = new Map(sessions.map(session=>[session.id,session]));
    for(const [field,value] of Object.entries(totals)){
      $(`overview-${field.replace('_','-')}`).textContent = value.toLocaleString('zh-CN');
    }
    this.renderTracks(layouts);
    $('recent-recordings').replaceChildren(...sessions.slice(0,6).map(session=>this.recentCard(session)));
    const races = sessions.filter(session=>session.metadata.SessionType?.trim().toLowerCase()==='race');
    const latest = races[0] || sessions[0];
    $('overview-latest').hidden = !latest;
    if(latest) this.renderLatest(latest,races.length > 0);
  }

  recentCard(session){
    const {metadata,pace} = session;
    const item = button(null,()=>this.openSession(session.id),'recent-card');
    const time = timestamp(session) == null ? '录制时间未知' : dateLabel(metadata.RecordingTime);
    const info = node('span',null,'recent-card-label');
    info.append(node('strong',trackName(metadata)),node('small',
      [typeLabel(metadata.SessionType),session.vehicle_brand || '未识别品牌',time].join(' · ')));
    const facts = node('span',null,'recent-card-facts');
    facts.append(node('strong',lapTime(pace.best_s)),node('small',`${session.complete_lap_count} 个完整圈`));
    item.append(info,facts);
    return item;
  }

  showFacts(session,pits){
    const {pace,complete_lap_count:complete} = session;
    const facts = [['最快圈',lapTime(pace.best_s)],['中位圈',lapTime(pace.median_s)],
      ['统计 / 完整圈',`${pace.count} / ${complete}`],
      ['进出站耗时',pits?.length ? `${pits.reduce((sum,pit)=>sum+pit.duration_s,0).toFixed(1)} s` : '—']];
    $('latest-facts').replaceChildren(...facts.map(([label,value])=>{
      const group = node('div');
      group.append(node('dt',label),node('dd',value));
      return group;
    }));
  }

  async renderLatest(session,hasRace){
    const {id,metadata} = session;
    $('latest-title').textContent = hasRace ? '最近一场正赛' : '最近会话';
    $('latest-track').textContent = trackName(metadata);
    $('latest-context').textContent = [typeLabel(metadata.SessionType), session.vehicle_brand || '未识别品牌',
      metadata.CarClass,dateLabel(metadata.RecordingTime)].filter(Boolean).join(' · ');
    $('latest-open').onclick = () => this.openSession(id,null,'pace');
    if(this.latestId === id) return;
    this.latestId = id;
    this.showFacts(session);
    this.graphRows = [];
    $('latest-stints').hidden = $('latest-spread').hidden = true;
    $('latest-status').textContent = '正在读取驾驶段…';
    try{
      const data = await this.api(`/sessions/${id}/pace`);
      if(this.latestId !== id) return;
      const completePits = data.pit_visits.filter(pit=>pit.start_kind==='pit_entry'&&pit.end_kind==='pit_exit');
      this.showFacts(session,completePits);
      $('latest-status').textContent = data.stint_reason || (data.stints.length ? '' : '这份录制未观测到赛道驾驶区间。');
      this.renderStints(session,data);
    }catch(error){
      if(this.latestId === id) $('latest-status').textContent = `驾驶段读取失败：${error.message}`;
    }
  }

  renderStints(session,data){
    const {stints,pit_visits:pits,duration_s:duration,statistics} = data;
    const timeline = $('latest-timeline');
    timeline.replaceChildren();
    const parts = [...stints.map(stint=>({...stint,label:`驾驶段 ${stint.number}`,color:COLORS[(stint.number-1)%COLORS.length]})),
      ...pits.map(pit=>({...pit,label:'已观测进站',color:'#97a2ad'}))].sort((a,b)=>a.start_s-b.start_s);
    const timelineLabels = [];
    for(const part of parts){
      const text = `${part.label} ${clock(part.start_s)}–${clock(part.end_s)}`;
      const segment = node('span');
      segment.title = text;
      segment.style.left = `${100 * part.start_s / duration}%`;
      segment.style.width = `${100 * (part.end_s - part.start_s) / duration}%`;
      segment.style.backgroundColor = part.color;
      timelineLabels.push(text);
      timeline.append(segment);
    }
    timeline.setAttribute('aria-label',`录制时间线，${timelineLabels.join('；')}`);
    const body = $('latest-stint-rows');
    body.replaceChildren();
    for(const stint of stints){
      const stats = stint.statistics;
      const label = node('span',`第 ${stint.number} 段`);
      label.title = `${BOUNDARIES[stint.start_kind]} ${clock(stint.start_s)}`;
      const best = stats.best_ordinal
        ? button(lapTime(stats.best_s),()=>this.openSession(session.id,stats.best_ordinal),'overview-best') : '—';
      addCells(body.insertRow(),[label,stats.count,best,lapTime(stats.median_s),BOUNDARIES[stint.end_kind]]);
    }
    $('latest-stints').hidden = !stints.length;
    this.graphRows = stints.filter(stint=>stint.statistics.count).map(stint=>({
      title:`第 ${stint.number} 段`,stats:stint.statistics,color:COLORS[(stint.number-1)%COLORS.length],
    }));
    if(!this.graphRows.length && statistics.count){
      this.graphRows = [{title:'整场',stats:statistics,color:COLORS[0]}];
    }
    this.chart.setAttribute('aria-label',this.graphRows.map(({title,stats})=>
      `${title}最快 ${lapTime(stats.best_s)}，中位 ${lapTime(stats.median_s)}，最慢 ${lapTime(stats.slowest_s)}`).join('；'));
    this.chart.style.height = `${Math.min(280, 34 + 28 * this.graphRows.length)}px`;
    $('latest-spread').hidden = !this.graphRows.length;
    this.drawSpread();
  }

  drawSpread(){
    const rows = this.graphRows;
    const {width,height} = this.chart.getBoundingClientRect();
    if(!rows.length || width < 150 || height < 40) return;
    const ratio = window.devicePixelRatio || 1;
    this.chart.width = Math.round(width*ratio);
    this.chart.height = Math.round(height*ratio);
    const ctx = this.chart.getContext('2d');
    ctx.setTransform(ratio,0,0,ratio,0,0);
    const best = Math.min(...rows.map(row=>row.stats.best_s));
    const slowest = Math.max(...rows.map(row=>row.stats.slowest_s));
    const margin = Math.max(.05,(slowest-best)*.07);
    const lo = Math.max(0,best-margin),hi = slowest+margin;
    const left = 53,right = width-42, axis = height-18;
    const x = value => left+(right-left)*(value-lo)/(hi-lo);
    ctx.font = '11px Segoe UI';
    ctx.textAlign = 'center';
    ctx.strokeStyle = '#33414c';
    ctx.fillStyle = '#a7b2bc';
    for(let i=0;i<=4;i++){
      const value = lo+(hi-lo)*i/4, px = x(value);
      ctx.beginPath();
      ctx.moveTo(px,5);ctx.lineTo(px,axis-4);ctx.stroke();
      ctx.fillText(lapTime(value),px,height-4);
    }
    ctx.textAlign = 'left';
    rows.forEach(({title,stats,color},index)=>{
      const y = 7+(axis-10)*(index+.5)/rows.length;
      ctx.strokeStyle = ctx.fillStyle = color;
      ctx.fillText(title,0,y+4);
      const fastest = x(stats.best_s), slow = x(stats.slowest_s), median = x(stats.median_s);
      ctx.beginPath();ctx.moveTo(fastest,y);ctx.lineTo(slow,y);ctx.stroke();
      if(stats.p10_s != null && stats.p90_s != null){
        ctx.globalAlpha = .45;
        const start = x(stats.p10_s);
        ctx.fillRect(start,y-5,Math.max(1,x(stats.p90_s)-start),10);
        ctx.globalAlpha = 1;
      }
      ctx.fillRect(fastest-1,y-3,2,6);
      ctx.fillRect(slow-1,y-3,2,6);
      ctx.fillRect(median-1,y-7,2,14);
    });
  }

  renderTracks(layouts){
    const jump = $('overview-track');
    jump.replaceChildren(new Option('选择赛道',''),...layouts.map((layout,index)=>new Option(trackName(layout.metadata),`circuit-${index}`)));
    $('overview-tracks').replaceChildren(...layouts.map((layout,index)=>this.trackCard(layout,index)));
  }

  trackCard(layout,index){
    const card = node('article',null,'track-overview overview-circuit');
    card.id = `circuit-${index}`;
    const header = node('header');
    header.append(node('h3',trackName(layout.metadata)),
      node('p',`${layout.sessions} 次录制 · ${layout.complete_laps} 个完整圈 · ${layout.pace_laps} 圈计入节奏`),
      node('small',layout.latest_at ? `最近录制 ${dateLabel(layout.latest_at)}` : '录制时间未知'));
    card.append(header);
    const body = node('div',null,'circuit-results');
    const qualifications = layout.groups.filter(group=>group.kind==='qualify');
    const races = layout.groups.filter(group=>group.kind==='race');
    const others = layout.groups.filter(group=>group.kind!=='race'&&group.kind!=='qualify');
    if(qualifications.length){
      const section = node('section',null,'qualify-card');
      section.append(node('h4','排位成绩'),this.groupTable(qualifications,'qualify'));
      body.append(section);
    }
    if(races.length){
      const section = node('section',null,'race-card');
      const heading = node('div',null,'race-header');
      heading.append(node('h4','正赛节奏'));
      const table = node('div');
      const filters = Object.keys(layout.race_durations || {}).length
        ? [['','全时长'],...RACE_LENGTHS.filter(([key])=>layout.race_durations[key])] : [];
      if(filters.length){
        const tabs = node('div',null,'race-lengths');
        tabs.setAttribute('aria-label','遥测录制时长');
        for(const [key,text] of filters){
          const tab = button(text,()=>{
            for(const sibling of tabs.children) sibling.setAttribute('aria-pressed',String(sibling===tab));
            table.replaceChildren(this.groupTable(key ? layout.race_durations[key] : races,'race'));
          });
          tab.setAttribute('aria-pressed',String(!key));
          tabs.append(tab);
        }
        heading.append(tabs);
      }
      table.append(this.groupTable(races,'race'));
      section.append(heading,table);
      body.append(section);
    }
    if(others.length){
      const section = node('details',null,'circuit-other');
      section.open = !qualifications.length && !races.length;
      section.append(node('summary','练习及其他录制'),this.groupTable(others,'other'));
      body.append(section);
    }
    card.append(body);
    return card;
  }

  groupTable(groups,mode){
    const wrap = node('div',null,'table-scroll');
    const table = node('table',null,`overview-table overview-${mode}`);
    const head = table.createTHead().insertRow();
    const headers = [...(mode==='other' ? ['类型'] : []),'品牌','组别',
      ...(mode==='qualify' ? ['最快圈','统计圈','录制']
        : ['中位圈','最快圈','P10–P90','统计圈','录制'])];
    for(const label of headers){
      const cell = node('th',label);
      cell.scope = 'col';
      head.append(cell);
    }
    const body = table.createTBody();
    for(const group of groups){
      const brand = button(group.brand || '未识别品牌',()=>this.openGroup(this.byId.get(group.session_id)),'overview-brand');
      brand.title = '打开同品牌与会话类型的历史趋势';
      const best = group.best_session
        ? button(lapTime(group.pace.best_s),()=>this.openSession(group.best_session,group.best_ordinal),'overview-best') : '—';
      const range = group.pace.p10_s == null ? '—' : `${lapTime(group.pace.p10_s)}–${lapTime(group.pace.p90_s)}`;
      const row = body.insertRow();
      addCells(row,[...(mode==='other' ? [typeLabel(group.kind)] : []),brand,group.class || '—',
        ...(mode==='qualify' ? [best] : [lapTime(group.pace.median_s),best,range]),group.pace_laps,group.sessions]);
      row.title = `${group.complete_laps} 个完整圈，${group.pace_laps} 圈纳入统计`;
    }
    wrap.append(table);
    return wrap;
  }
}
