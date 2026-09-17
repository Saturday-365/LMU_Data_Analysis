const $=id=>document.getElementById(id);
const labels={known:'已知',unknown:'未知',not_recorded:'未记录',not_applicable:'不适用'};
const layers={centerline:'中心线',left_boundary:'左边界',right_boundary:'右边界',kerb:'路肩',pit_lane:'维修区'};
function node(tag,text,cls){const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;}
function valueText(data){if(data.state!=='known')return labels[data.state]||'未知';const v=data.value;const n=x=>new Intl.NumberFormat('zh-CN',{maximumFractionDigits:2}).format(x);return `${v&&typeof v==='object'?(v.min===v.max?n(v.min):`${n(v.min)}～${n(v.max)}`):v}${data.unit?' '+data.unit:''}`;}

export class PracticeConditions {
  constructor(api,notice,map){this.api=api;this.notice=notice;this.map=map;this.generation=0;this.editGeneration=0;this.lapGeneration=0;
    $('condition-scope').addEventListener('change',()=>this.loadEditor());
    $('condition-field').addEventListener('change',()=>this.populate());
    $('condition-state').addEventListener('change',()=>{this.input().disabled=$('condition-state').value!=='known';});
    $('condition-form').addEventListener('submit',e=>{e.preventDefault();this.save(false);});
    $('condition-restore').addEventListener('click',()=>this.save(true));
  }
  input(){return this.field?.kind==='choice'?$('condition-choice'):$('condition-value');}
  async setSession(session){this.session=session;const generation=++this.generation;this.editGeneration++;this.lapGeneration++;this.document=null;this.map.setReference(null);
    $('condition-cards').replaceChildren();$('condition-summary').textContent='';$('lap-conditions').replaceChildren();$('track-layers').replaceChildren();$('track-reference-status').textContent='正在检查赛道参照…';$('condition-form').hidden=true;
    const scopes=$('condition-scope');scopes.replaceChildren(new Option('整场练习（变化信息明确适用于整场）','session'));
    if(!session){$('track-reference-status').textContent='';return;}
    for(const lap of session.laps)scopes.add(new Option(`第 ${lap.ordinal} 圈`,lap.id));
    this.loadEditor();
    try{const ref=await this.api(`/sessions/${session.id}/track-reference`);if(generation!==this.generation)return;this.map.setReference(ref);
      $('track-reference-status').textContent=ref.available?`赛道参照 ${ref.version} · 最大验证误差 ${ref.max_error_m.toFixed(2)} m · 阈值 ${ref.validation.threshold_m} m · 来源：${ref.source} · 授权：${ref.license} · 核验：${ref.validation.reviewer} / ${ref.validation.checked_at}`:ref.reason;
      if(ref.available)for(const layer of ref.layers){const label=node('label'),input=node('input');input.type='checkbox';input.checked=true;input.addEventListener('change',()=>this.map.toggleLayer(layer.kind,input.checked));label.append(input,document.createTextNode(' '+layers[layer.kind]));$('track-layers').append(label);}
    }catch(e){if(generation===this.generation)$('track-reference-status').textContent='赛道参照读取失败：'+e.message;}
  }
  async loadEditor(){if(!this.session)return;const generation=this.generation,edit=++this.editGeneration,id=this.session.id,scope=$('condition-scope').value;
    $('condition-status').textContent='正在读取练习信息…';$('condition-form').hidden=true;
    try{const data=await this.api(`/sessions/${id}/conditions${scope==='session'?'':'?lap_id='+scope}`);if(generation!==this.generation||edit!==this.editGeneration)return;
      this.document=data;this.render();$('condition-status').textContent='';if(scope==='session')this.summary(data);
    }catch(e){if(generation===this.generation&&edit===this.editGeneration){$('condition-status').textContent=e.message;$('condition-cards').replaceChildren();}}
  }
  summary(data){const f=key=>data.fields.find(f=>f.key===key).effective;$('car-name').textContent=[valueText(f(f('model').state==='known'?'model':'car')),valueText(f('class'))].join(' · ');$('track-name').textContent=valueText(f(f('layout').state==='known'?'layout':'track'));$('session-type').textContent=valueText(f('session_type'));const keys=['ambient','track_temp','fuel','recorded_at'];$('condition-summary').textContent=keys.map(key=>{const f=data.fields.find(f=>f.key===key);return `${f.label} ${valueText(f.effective)}${f.effective.source==='user'?'（补录）':''}`;}).join(' · ');}
  render(){const data=this.document;const selected=$('condition-field').value;$('condition-field').replaceChildren();$('condition-cards').replaceChildren();
    for(const group of [...new Set(data.fields.map(f=>f.group))]){const card=node('section',null,'condition-card');card.append(node('h3',group));const list=node('dl');
      for(const f of data.fields.filter(f=>f.group===group)){list.append(node('dt',f.label));const dd=node('dd',valueText(f.effective));const e=f.effective;
        const scope=e.valid_range.scope==='metadata_snapshot'?'元数据快照（生效时间未知）':e.valid_range.scope==='session'?'整场练习':e.valid_range.scope?'指定圈次':`${e.valid_range.start_s?.toFixed(2)}～${e.valid_range.end_s?.toFixed(2)} s（录制时钟）`;
        dd.append(node('small',`${e.source==='user'?'用户填写':'遥测读取'} · ${scope}${e.updated_at?' · '+new Date(e.updated_at).toLocaleString('zh-CN'):''}`));
        if(f.own_override||f.inherited_override)dd.append(node('small',`自动值：${valueText(f.automatic)}${f.inherited_override?' · 当前继承整场补录':''}`));
        const detail=node('details');detail.append(node('summary','来源与有效范围'));detail.append(node('small',`${e.reason}；原始字段：${f.automatic.source_field||'无已核实字段'}${f.automatic.frequency_hz?'；'+f.automatic.frequency_hz+' Hz':''}${f.automatic.sample_count!=null?'；有效样本 '+f.automatic.sample_count+'，缺失 '+f.automatic.missing_count:''}`));dd.append(detail);list.append(dd);
        if(data.scope==='session'||f.varying)$('condition-field').add(new Option(`${f.group} · ${f.label}`,f.key));
      }card.append(list);$('condition-cards').append(card);}
    if([...$('condition-field').options].some(o=>o.value===selected))$('condition-field').value=selected;
    $('condition-notes').textContent=[data.setup_note,...data.notes,'四轮参数、湿度枚举及调教生效时间未核实的内容保持未知。录制时间与导入时间分别保留。'].join(' ');
    $('condition-form').hidden=false;this.populate();
  }
  populate(){this.field=this.document?.fields.find(f=>f.key===$('condition-field').value);if(!this.field)return;const f=this.field,e=f.effective;
    $('condition-state').value=e.state;$('condition-value').hidden=f.kind==='choice';$('condition-choice').hidden=f.kind!=='choice';$('condition-choice').replaceChildren(...(f.choices||[]).map(v=>new Option(v,v)));
    const input=this.input();input.value=typeof e.value==='object'?'':e.value??'';input.disabled=e.state!=='known';$('condition-unit').textContent=f.unit;
    $('condition-value').placeholder=f.kind==='number'?'填写此范围内的已知值；保留自动范围可不编辑':'填写已知信息';
    $('condition-original').textContent=`自动值：${valueText(f.automatic)}。${f.inherited_override?'当前继承整场补录；恢复只移除当前圈的覆盖。':''}`;
    $('condition-restore').disabled=!f.own_override;
  }
  async save(restore){if(!this.document||!this.field)return;const generation=this.generation,edit=this.editGeneration,id=this.session.id,scope=this.document.scope,key=this.field.key;
    let value=this.input().value.trim();const status=$('condition-state').value;if(!restore&&status==='known'&&!value){this.notice('请填写数值或文字，或选择未知状态。',true);return;}
    if(status!=='known')value=null;else if(this.field.kind==='number'){value=Number(value);if(!Number.isFinite(value)){this.notice('请输入有限数值。',true);return;}}
    $('condition-save').disabled=true;$('condition-restore').disabled=true;$('condition-scope').disabled=true;$('condition-field').disabled=true;
    try{const data=await this.api(`/sessions/${id}/conditions${scope==='session'?'':'?lap_id='+scope}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-LMU-Client':'web'},body:JSON.stringify({changes:{[key]:restore?null:{state:status,value}}})});
      if(generation!==this.generation||edit!==this.editGeneration)return;this.document=data;this.render();if(scope==='session')this.summary(data);this.loadLaps(this.lapIds||[]);this.notice(restore?'已移除此范围的补录，恢复继承或自动值。':'练习信息已保存。');
    }catch(e){if(generation===this.generation)this.notice(e.message,true);}finally{$('condition-save').disabled=false;$('condition-scope').disabled=false;$('condition-field').disabled=false;if(generation===this.generation&&edit===this.editGeneration)this.populate();}
  }
  async loadLaps(ids){this.lapIds=ids;const generation=this.generation,request=++this.lapGeneration,id=this.session?.id;$('lap-conditions').replaceChildren();if(!id)return;
    try{const values=await Promise.all(ids.map(lap=>this.api(`/sessions/${id}/conditions?lap_id=${lap}`)));if(generation!==this.generation||request!==this.lapGeneration)return;
      values.forEach((data,i)=>{const p=node('p',`${i?'参考圈':'当前圈'} · `);p.className=i?'reference-conditions':'current-conditions';p.append(document.createTextNode(['ambient','track_temp','fuel','tyres','setup_name'].map(key=>{const f=data.fields.find(f=>f.key===key);return `${f.label}：${valueText(f.effective)}${f.effective.source==='user'?'（补录）':''}`;}).join(' · ')));$('lap-conditions').append(p);});
    }catch(e){if(generation===this.generation&&request===this.lapGeneration)$('lap-conditions').textContent='圈次条件读取失败：'+e.message;}
  }
}
