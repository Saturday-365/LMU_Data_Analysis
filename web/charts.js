const CHANNELS = [['speed','速度','km/h'],['brake','刹车','%'],['throttle','油门','%'],['steering','转向','%'],['gear','挡位','挡']];
const LABELS = {sample:'采样',interpolated:'插值',held:'保持',missing:'缺失'};
const finite = v => typeof v === 'number' && Number.isFinite(v);
export class TelemetryCharts {
  constructor(root, position) {
    this.root=root; this.position=position; this.rows=[]; this.traces=[]; this.axis='distance'; this.range=[0,1]; this.full=[0,1]; this.cursor=null;
    for(const [key,label,unit] of CHANNELS){
      const row=document.createElement('div'); row.className='chart-row';
      row.innerHTML='<div class="chart-label"><h3></h3><span class="unit"></span><div class="chart-values"><span>—</span><span>—</span></div><div class="provenance"></div></div><div class="plot"><canvas></canvas><canvas></canvas></div>';
      row.querySelector('h3').textContent=label;row.querySelector('.unit').textContent=unit;root.append(row);
      const plot=row.querySelector('.plot'), canvases=plot.querySelectorAll('canvas');
      this.rows.push({key,plot,base:canvases[0],overlay:canvases[1],values:row.querySelectorAll('.chart-values span'),provenance:row.querySelector('.provenance')});
      plot.addEventListener('pointermove',e=>this.move(e,plot));
      plot.addEventListener('pointerdown',e=>{if(!this.traces.length || e.button!==0)return;this.drag={x:e.clientX,range:[...this.range]};plot.setPointerCapture(e.pointerId);});
      const end=()=>{this.drag=null;};plot.addEventListener('pointerup',end);plot.addEventListener('pointercancel',end);plot.addEventListener('lostpointercapture',end);
      plot.addEventListener('pointerleave',()=>{if(!this.drag){this.cursor=null;this.hover();}});
      plot.addEventListener('dblclick',()=>this.reset());
      plot.addEventListener('wheel',e=>{if(!this.traces.length)return;e.preventDefault();const fraction=this.fraction(e,plot);const [lo,hi]=this.range;const anchor=lo+(hi-lo)*fraction;const span=Math.min(this.full[1]-this.full[0],Math.max(this.axis==='distance'?10:.25,(hi-lo)*Math.exp(Math.sign(e.deltaY)*.18)));this.setRange(anchor-span*fraction,anchor+span*(1-fraction));},{passive:false});
    }
    new ResizeObserver(()=>this.draw()).observe(root);
    root.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key)||!this.traces.length)return;e.preventDefault();const [lo,hi]=this.range;this.cursor=Math.min(hi,Math.max(lo,(this.cursor??lo)+(hi-lo)/200*(e.key==='ArrowRight'?1:-1)));this.hover();});
  }
  setData(traces,axis){this.traces=traces.filter(Boolean);this.axis=axis;let min=Infinity,max=-Infinity;for(const trace of this.traces){for(const x of this.xs(trace)||[]){if(finite(x)){min=Math.min(min,x);max=Math.max(max,x);}}}this.full=finite(min)&&max>min?[min,max]:[0,1];this.range=[...this.full];this.cursor=null;this.draw();}
  xs(trace){return this.axis==='distance'?trace.distance_m:trace.time_s;}
  fraction(e,plot){const box=plot.getBoundingClientRect();return Math.min(1,Math.max(0,(e.clientX-box.left-45)/Math.max(1,box.width-62)));}
  move(e,plot){const fraction=this.fraction(e,plot);if(this.drag){const shift=(e.clientX-this.drag.x)/Math.max(1,plot.clientWidth-62)*(this.drag.range[1]-this.drag.range[0]);this.setRange(this.drag.range[0]-shift,this.drag.range[1]-shift);}this.cursor=this.range[0]+fraction*(this.range[1]-this.range[0]);this.hover();}
  setRange(lo,hi){const [start,end]=this.full;if(lo<start){hi+=start-lo;lo=start;}if(hi>end){lo-=hi-end;hi=end;}this.range=[Math.max(start,lo),Math.min(end,hi)];this.draw();}
  reset(){this.range=[...this.full];this.cursor=null;this.draw();}
  context(canvas){const box=canvas.parentElement.getBoundingClientRect(),ratio=window.devicePixelRatio||1;const w=Math.max(1,Math.round(box.width)),h=Math.max(1,Math.round(box.height));if(canvas.width!==Math.round(w*ratio)||canvas.height!==Math.round(h*ratio)){canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);}const c=canvas.getContext('2d');c.setTransform(ratio,0,0,ratio,0,0);c.clearRect(0,0,w,h);return {c,w,h};}
  yRange(key){if(key==='steering')return [-100,100];if(key==='gear')return [-1,8];if(key!=='speed')return [0,100];let top=200;for(const t of this.traces)for(const v of t.channels[key]?.values||[])if(finite(v))top=Math.max(top,v);return [0,Math.ceil(top/50)*50];}
  draw(){for(const row of this.rows){const {c,w,h}=this.context(row.base);const left=45,right=w-17,top=12,bottom=h-25;const [lo,hi]=this.range,[ymin,ymax]=this.yRange(row.key);row.geometry={left,right,top,bottom,w,h};const px=x=>left+(x-lo)/(hi-lo)*(right-left),py=y=>bottom-(y-ymin)/(ymax-ymin)*(bottom-top);
      c.font='9px Segoe UI';c.lineWidth=1;c.textAlign='right';c.fillStyle='#63717c';
      for(let i=0;i<=2;i++){const y=top+(bottom-top)*i/2;c.strokeStyle='#252c32';c.beginPath();c.moveTo(left,y);c.lineTo(right,y);c.stroke();c.fillText(String(Math.round(ymax-(ymax-ymin)*i/2)),left-9,y+3);}
      c.textAlign='center';for(let i=0;i<=6;i++){const x=left+(right-left)*i/6;c.strokeStyle='#22282d';c.beginPath();c.moveTo(x,top);c.lineTo(x,bottom);c.stroke();const v=lo+(hi-lo)*i/6;c.fillText(v.toFixed(this.axis==='distance'?0:1),x,h-8);}
      c.save();c.beginPath();c.rect(left,top,right-left,bottom-top);c.clip();
      // Every aligned sample is rendered; missing samples break the path.
      this.traces.forEach((trace,index)=>{const xs=this.xs(trace),ys=trace.channels[row.key]?.values;if(!xs||!ys)return;c.strokeStyle=index?'#6ecbd5':'#ff804d';c.lineWidth=index?1.3:1.6;c.setLineDash(index?[5,3]:[]);c.beginPath();let previous=null;for(let i=0;i<xs.length;i++){const x=xs[i],y=ys[i];if(!finite(x)||!finite(y)){previous=null;continue;}if(x<lo){previous={x,y};continue;}if(x>hi){if(previous){if(row.key==='gear')c.lineTo(px(x),py(previous.y));c.lineTo(px(x),py(y));}break;}if(previous){if(previous.x<lo)c.moveTo(px(previous.x),py(previous.y));if(row.key==='gear')c.lineTo(px(x),py(previous.y));c.lineTo(px(x),py(y));}else c.moveTo(px(x),py(y));previous={x,y};}c.stroke();});c.restore();
      if(!this.traces.some(t=>t.channels[row.key])){c.fillStyle='#63717c';c.textAlign='center';c.fillText('暂无可用数据',(left+right)/2,h/2);}
    }this.hover();}
  nearest(trace,x){const xs=this.xs(trace);if(!xs?.length)return -1;let start=0,end=xs.length-1;while(start<=end&&!finite(xs[start]))start++;while(end>=start&&!finite(xs[end]))end--;if(start>end||x<xs[start]||x>xs[end])return -1;let lo=start,hi=end;while(lo<hi){const mid=Math.floor((lo+hi)/2);let valid=mid;while(valid<=hi&&!finite(xs[valid]))valid++;if(valid>hi){hi=mid;continue;}if(xs[valid]<x)lo=valid+1;else hi=mid;}let best=-1,diff=Infinity;for(let i=Math.max(start,lo-12);i<=Math.min(end,lo+12);i++){if(finite(xs[i])&&Math.abs(xs[i]-x)<diff){best=i;diff=Math.abs(xs[i]-x);}}if(best<0)return -1;const tolerance=this.axis==='distance'?15:.03;return diff<=tolerance?best:-1;}
  hover(){this.position.textContent=this.cursor===null?'移动鼠标查看数据':`${this.axis==='distance'?'赛道距离':'圈内时间'}  ${this.cursor.toFixed(this.axis==='distance'?1:3)} ${this.axis==='distance'?'m':'s'}`;const indices=this.traces.map(t=>this.cursor===null?-1:this.nearest(t,this.cursor));for(const row of this.rows){const {c}=this.context(row.overlay);const geo=row.geometry;if(geo&&this.cursor!==null){const x=geo.left+(this.cursor-this.range[0])/(this.range[1]-this.range[0])*(geo.right-geo.left);c.strokeStyle='#cbd4dc77';c.setLineDash([3,3]);c.beginPath();c.moveTo(x,geo.top);c.lineTo(x,geo.bottom);c.stroke();}const states=[];row.values.forEach((element,j)=>{const channel=this.traces[j]?.channels[row.key],i=indices[j]??-1;const value=i>=0?channel?.values[i]:null;element.textContent=finite(value)?(row.key==='gear'?(value===-1?'R':value===0?'N':String(value)):value.toFixed(1)):'—';if(this.traces[j])states.push(i>=0&&finite(value)?LABELS[channel?.provenance?.[i]]||'采样':'缺失');});row.provenance.textContent=this.cursor===null?'':states.join(' / ');}}
}
