const $ = id => document.getElementById(id);
const PATH = '/settings/auto-import';

export class ImportSettings {
  constructor(api, onImported){
    this.api = api;
    this.onImported = onImported;
    this.input = $('telemetry-directory');
    this.save = $('save-import-settings');
    this.scan = $('scan-telemetry-directory');
    this.browse = $('browse-telemetry-directory');
    this.message = $('import-settings-status');
    this.request = 0;
    this.input.oninput = () => this.updateControls();
    $('auto-import-form').onsubmit = event => {
      event.preventDefault();
      if(!this.save.disabled) this.submit(false);
    };
    this.scan.onclick = () => this.submit(true);
    this.browse.onclick = async () => {
      this.browse.disabled = true;
      this.message.textContent = '';
      try{
        const path = await window.pywebview.api.choose_telemetry_directory();
        if(path) this.input.value = path;
      }catch(error){
        this.message.textContent = `无法打开文件夹选择窗口。 ${error.message}`;
      }finally{
        this.updateControls();
      }
    };
    const showPicker = () => {
      this.browse.hidden = typeof window.pywebview?.api?.choose_telemetry_directory !== 'function';
    };
    window.addEventListener('pywebviewready', showPicker);
    showPicker();
  }

  updateControls(){
    const changed = this.input.value.trim() !== this.directory;
    this.input.disabled = this.browse.disabled = Boolean(this.busy);
    this.save.disabled = Boolean(this.busy) || this.directory === undefined || !changed;
    this.scan.disabled = Boolean(this.busy) || !this.directory || changed || this.lastScan?.state === 'running';
  }

  async refresh(){
    if(this.busy) return;
    const request = ++this.request;
    try{
      const result = await this.api(PATH);
      if(request === this.request) this.render(result);
    }catch(error){
      if(request !== this.request) return;
      this.message.textContent = `设置读取失败。 ${error.message}`;
      if(this.lastScan?.state === 'running') this.poll();
    }
  }

  async submit(scan){
    clearTimeout(this.timer);
    this.request++;
    this.busy = true;
    this.updateControls();
    this.message.textContent = scan ? '' : '正在保存目录…';
    try{
      const result = await this.api(scan ? PATH + '/scan' : PATH, {
        method: scan ? 'POST' : 'PUT',
        headers: {'Content-Type':'application/json','X-LMU-Client':'web'},
        ...(scan ? {} : {body: JSON.stringify({directory: this.input.value.trim() || null})}),
      });
      this.render(result, !scan);
      if(!scan) this.message.textContent = result.directory ? '目录已保存。' : '已关闭启动时导入。';
    }catch(error){
      this.message.textContent = error.message;
      if(this.lastScan?.state === 'running') this.poll();
    }finally{
      this.busy = false;
      this.updateControls();
    }
  }

  poll(){
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.refresh(), 900);
  }

  render({directory, scan}, fillInput = false){
    if(this.directory === undefined || fillInput) this.input.value = directory || '';
    this.directory = directory || '';
    this.lastScan = scan;
    this.updateControls();
    const banner = $('auto-import-banner');
    const details = $('directory-scan-issues');
    details.replaceChildren(...scan.issues.map(item => {
      const element = document.createElement('li');
      element.textContent = `${item.filename} · ${item.message}`;
      return element;
    }));
    clearTimeout(this.timer);
    let message = scan.error || (directory ? '下次启动时将自动扫描，也可立即扫描。' : '尚未配置遥测目录。');
    if(scan.state === 'running'){
      message = scan.total ? `正在自动导入 ${scan.done} / ${scan.total}${scan.current ? ' · ' + scan.current : ''}`
        : '正在扫描遥测目录…';
      this.poll();
    }
    if(scan.state === 'finished'){
      const totals = `新增 ${scan.imported} · 已处理 ${scan.unchanged} · 重复 ${scan.duplicate} · 过滤 ${scan.filtered} · 待重试 ${scan.deferred} · 失败 ${scan.failed}`;
      message = scan.error ? `${scan.error} ${totals}` : `扫描完成。 ${totals}`;
      if(scan.id !== this.completedScan){
        this.completedScan = scan.id;
        if(scan.imported) this.onImported();
      }
    }
    $('directory-scan-status').textContent = scan.directory && scan.directory !== directory
      ? `${scan.directory} · ${message}` : message;
    banner.hidden = scan.state === 'idle' && !scan.error;
    banner.textContent = message;
  }
}
