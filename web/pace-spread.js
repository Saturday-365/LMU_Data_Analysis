import {lapTime} from './archive.js';

const STINT_COLORS = ['#79cfd6', '#ffb48b', '#bea5e8', '#9ccd90'];

export function stintColor(number){
  return STINT_COLORS[(number - 1) % STINT_COLORS.length];
}

export function stintSpreadRows(stints){
  return stints.filter(stint => stint.statistics.count).map(stint => ({
    label: `第 ${stint.number} 段`,
    stats: stint.statistics,
    color: stintColor(stint.number),
  }));
}

export class PaceSpread {
  constructor(canvas){
    this.canvas = canvas;
    this.rows = [];
    new ResizeObserver(() => this.draw()).observe(canvas);
  }

  setRows(rows){
    this.rows = rows.filter(row => row.stats.count);
    this.canvas.hidden = !this.rows.length;
    this.canvas.style.height = `${28 + 27 * this.rows.length}px`;
    this.canvas.setAttribute('aria-label', this.rows.map(({label, stats}) => {
      const range = stats.p10_s == null ? ''
        : `，P10–P90 ${lapTime(stats.p10_s)} 至 ${lapTime(stats.p90_s)}`;
      return `${label}，${stats.count} 圈，最快 ${lapTime(stats.best_s)}，中位 ${lapTime(stats.median_s)}，最慢 ${lapTime(stats.slowest_s)}${range}`;
    }).join('；'));
    this.draw();
  }

  draw(){
    const {width, height} = this.canvas.getBoundingClientRect();
    if(!this.rows.length || width < 150 || height < 40) return;
    const ratio = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(width * ratio);
    this.canvas.height = Math.round(height * ratio);
    const ctx = this.canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.font = '11px Segoe UI';
    const left = Math.max(43, ...this.rows.map(row => ctx.measureText(row.label).width + 14));
    const right = width - 39;
    const axis = height - 20;
    const best = Math.min(...this.rows.map(row => row.stats.best_s));
    const slowest = Math.max(...this.rows.map(row => row.stats.slowest_s));
    const padding = Math.max(.05, (slowest - best) * .07);
    const low = Math.max(0, best - padding), high = slowest + padding;
    const x = time => left + (right - left) * (time - low) / (high - low);

    ctx.textAlign = 'center';
    ctx.strokeStyle = '#33414c';
    ctx.fillStyle = '#a7b2bc';
    const ticks = Math.max(1, Math.min(4, Math.floor((right - left) / 63)));
    for(let index = 0; index <= ticks; index++){
      const time = low + (high - low) * index / ticks;
      const px = x(time);
      ctx.beginPath();
      ctx.moveTo(px, 5);
      ctx.lineTo(px, axis - 4);
      ctx.stroke();
      ctx.fillText(lapTime(time), px, height - 4);
    }
    ctx.textAlign = 'left';
    for(const [index, {label, stats, color}] of this.rows.entries()){
      const y = 7 + (axis - 10) * (index + .5) / this.rows.length;
      ctx.fillStyle = ctx.strokeStyle = color;
      ctx.fillText(label, 0, y + 4);
      const first = x(stats.best_s), last = x(stats.slowest_s);
      ctx.beginPath();
      ctx.moveTo(first, y);
      ctx.lineTo(last, y);
      ctx.stroke();
      // 少于五圈时后端不返回分位数，仍可画出实测范围和中位圈。
      if(stats.p10_s != null && stats.p90_s != null){
        const start = x(stats.p10_s);
        ctx.globalAlpha = .45;
        ctx.fillRect(start, y - 5, Math.max(1, x(stats.p90_s) - start), 10);
        ctx.globalAlpha = 1;
      }
      ctx.fillRect(first - 1, y - 3, 2, 6);
      ctx.fillRect(last - 1, y - 3, 2, 6);
      ctx.fillRect(x(stats.median_s) - 1, y - 7, 2, 14);
    }
  }
}
