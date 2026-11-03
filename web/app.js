/* MetaCube Control Center - no third-party dependencies, no external requests. */
'use strict';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const labels = {breath:'呼吸',steady:'常亮',spin:'旋转',off:'关闭'};
const oemNames = {system_mode:'主机性能模式',button_brightness:'按键灯亮度',fans_rpm:'CPU / GPU 风扇',gpu_mode:'GPU 模式',fn_lock:'Fn Lock',touchpad_lock:'触摸板锁定',keyboard_mode:'键盘 RGB 模式',keyboard_brightness:'键盘 RGB 亮度',ac_type:'供电接口',cpu_temperature_raw:'原厂温度读数'};
const M = {token:sessionStorage.getItem('metacube-token')||'', live:null,draft:null,dirty:false,presets:Array(5).fill(null),tab:'dashboard',oem:null,busy:false,online:false,baselineRaw:null,undoAvailable:false};
function advancedRgbLocked(){return Boolean(M.live&&!M.live.rgb_experimental_enabled);}
function draftRequiresExperimental(s){return Boolean(s&&(s.mode==='spin'||s.colors.length!==1||s.speed!==2||s.direction!==0||s.cycle!==0||s.transition!==0));}

async function api(path, method='GET', payload=null){
  const headers={'Authorization':`Bearer ${M.token}`};
  if(method!=='GET') headers['Content-Type']='application/json';
  const opts={method,headers,cache:'no-store'};
  if(method!=='GET') opts.body=JSON.stringify(payload);
  const resp=await fetch(path,opts);
  let data;
  try{ data=await resp.json(); }catch{ throw new Error(`服务器返回异常 (${resp.status})`); }
  if(resp.status===401){ showLogin('令牌无效，请重新登录'); throw new Error('访问令牌无效'); }
  if(!resp.ok) throw new Error(data.error||`请求失败 (${resp.status})`);
  return data;
}
function showLogin(error=''){$('#loginError').textContent=error;const dialog=$('#loginDialog'); if(!dialog.open)dialog.showModal();}
function hideLogin(){if($('#loginDialog').open)$('#loginDialog').close();}
let toastTimer;
function toast(message, isError=false){const el=$('#toast');el.textContent=message;el.classList.toggle('error',isError);el.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('visible'),4400);}
function fmtSize(bytes){if(bytes===null||bytes===undefined)return '—';const unit=bytes>=2**30?'GB':'MB';return (bytes/(unit==='GB'?2**30:2**20)).toFixed(1)+' '+unit;}
function setDot(ok){M.online=ok;$('#deviceDot').classList.toggle('online',ok);$('#deviceStatus').textContent=ok?'WMI 已连接':'硬件未连接';}
function selectTab(name){
  if(!['dashboard','lighting','system','diagnostics'].includes(name))return;
  M.tab=name;
  $$('.nav-item').forEach(btn=>btn.classList.toggle('selected',btn.dataset.view===name));
  $$('.view').forEach(el=>el.classList.toggle('active',el.id==='view-'+name));
  $('#pageBreadcrumb').textContent={dashboard:'设备总览',lighting:'光效工作室',system:'系统设置',diagnostics:'硬件诊断'}[name];
  if(name==='system'){loadSystem();loadOemBasic();}
  if(name==='dashboard')loadSystem();
}
function validateColor(candidate){return /^[A-Fa-f0-9]{6}$/.test(candidate)?candidate.toUpperCase():null;}
function rgbToHsv(hex){
  const rgb=[0,2,4].map(i=>parseInt(hex.slice(i,i+2),16)/255);
  const [r,g,b]=rgb, max=Math.max(...rgb), min=Math.min(...rgb), d=max-min;
  let h=0;
  if(d){
    if(max===r)h=((g-b)/d)%6;
    else if(max===g)h=(b-r)/d+2;
    else h=(r-g)/d+4;
    h=((h*60)%360+360)%360;
  }
  const sat=max===0?0:d/max;
  return [Math.round(h),Math.round(sat*100),Math.round(max*100)];
}
function hsvToRgb(h,s,v){
  s/=100;v/=100;
  const c=v*s, x=c*(1-Math.abs((h/60)%2-1)),m=v-c;
  let rgb;
  if(h<60)rgb=[c,x,0];else if(h<120)rgb=[x,c,0];
  else if(h<180)rgb=[0,c,x];else if(h<240)rgb=[0,x,c];
  else if(h<300)rgb=[x,0,c];else rgb=[c,0,x];
  return rgb.map(n=>Math.round((n+m)*255).toString(16).padStart(2,'0').toUpperCase()).join('');
}
function gradientFor(colors, smooth=true){
  const hex=colors.length?colors:['20232C'];
  if(hex.length===1)return '#'+hex[0];
  if(smooth)return `linear-gradient(90deg,${hex.map(x=>'#'+x).join(',')})`;
  return `linear-gradient(90deg,${hex.map((x,i)=>`#${x} ${100*i/hex.length}% ${100*(i+1)/hex.length}%`).join(',')})`;
}
function applyHeroColor(state){
  if(!state)return;
  const colors=state.colors?.length?state.colors:['000000'];
  const c=colors[0];
  $('#heroLight').style.background=gradientFor(colors,Boolean(state.transition));
  $('#heroLight').style.opacity=state.mode==='off'?'0':String(Math.max(.05,state.brightness/255));
  document.documentElement.style.setProperty('--glow','#'+c);
}
function previewLighting(state){
  const colors=state.colors?.length?state.colors:['000000'];
  const c=colors[0];
  const strip=$('#previewStrip');
  document.documentElement.style.setProperty('--led','#'+c);
  strip.style.opacity=state.mode==='off'?'0':String(Math.max(.04,state.brightness/255));
  strip.style.animation='none';
  strip.style.animationDirection='normal';
  if(state.mode==='spin' && colors.length>1){
    // Simulation only: WMI speed/rotation and LED geometry are OEM defined.
    const loop=colors.concat(colors,colors);
    strip.style.background=gradientFor(loop,Boolean(state.transition));
    strip.style.backgroundSize='300% 100%';
    strip.style.animation=`mc-spin ${(1+((255-state.speed)/255)*7).toFixed(2)}s linear infinite`;
    strip.style.animationDirection=state.direction===1?'reverse':'normal';
  }else{
    strip.style.background=gradientFor(colors,Boolean(state.transition));
    strip.style.backgroundSize='100% 100%';
    if(state.mode==='breath')strip.style.animation='mc-breathe 2.8s ease-in-out infinite';
    if(state.mode==='spin' && colors.length===1)strip.style.animation='mc-breathe 2s ease-in-out infinite';
  }
  $('#previewStage').dataset.mode=state.mode;
}
function cleanLighting(state){
  return {mode:state.mode, colors:[...state.colors],brightness:state.brightness,
    speed:state.speed,direction:state.direction,cycle:state.cycle,transition:state.transition};
}
function discardDraft(){
  if(!M.live)return;
  M.draft=cleanLighting(M.live);
  M.baselineRaw=M.live.raw;
  M.dirty=false;
  createColorEditor();refreshDraft();
}
function refreshDraft(){
  if(!M.draft)return;
  $$('.mode-tile').forEach(el=>el.classList.toggle('active',el.dataset.mode===M.draft.mode));
  for(const key of ['brightness','speed','cycle']){
    $(`#${key}Input`).value=M.draft[key];
    $(`#${key}Value`).textContent=key==='cycle'?`${M.draft[key]} / 11`:String(M.draft[key]);
  }
  const level=M.draft.brightness===0?0:Math.min(10,Math.ceil(M.draft.brightness/26));
  $('#brightnessValue').textContent=`${M.draft.brightness}/255 · 原厂约 ${level}/10`;
  $('#transitionInput').checked=Boolean(M.draft.transition);
  $$('[data-direction]').forEach(el=>el.classList.toggle('active',Number(el.dataset.direction)===M.draft.direction));
  $('#previewModeText').textContent=(labels[M.draft.mode]||'未知')+'模式';
  $('#previewColorText').textContent='#'+(M.draft.colors?.[0]||'000000') + (M.draft.colors.length>1?` +${M.draft.colors.length-1}`:'');
  const conflict=M.dirty && M.live?.raw!==M.baselineRaw;
  const locked=advancedRgbLocked();
  const unsafeDraft=locked&&draftRequiresExperimental(M.draft);
  $('#rgbSafetyNotice').hidden=!locked;
  $('[data-mode="spin"]').disabled=locked;
  for(const id of ['speedInput','cycleInput','transitionInput','nextCycleButton'])$('#'+id).disabled=locked;
  $$('[data-direction]').forEach(btn=>btn.disabled=locked);
  const hint=conflict?'设备已被其他操作修改，请放弃草稿后重新编辑':
    (unsafeDraft?'此配置涉及未经验证的 RGB 高级参数，已禁止写入；请恢复为单色、呼吸/常亮、速度 2 等安全参数':
    (M.dirty?'存在尚未写入固件的改动':'当前草稿与设备同步'));
  $('#unsavedHint').textContent=hint;
  $('#unsavedHint').classList.toggle('dirty',M.dirty || conflict);
  $('#draftStateLabel').textContent=hint;
  $('#draftStateLabel').classList.toggle('conflict',Boolean(conflict));
  $('#applyLightingButton').disabled=!M.online||!M.live?.writable||M.busy||!M.dirty||conflict||unsafeDraft;
  $('#undoLightingButton').disabled=!M.online||!M.live?.writable||M.busy||!M.undoAvailable||M.dirty;
  $('#discardDraftButton').disabled=!M.dirty||M.busy;
  $('#inspectPacketButton').disabled=!M.online||M.busy||conflict;
  $('#addColorButton').disabled=M.draft.colors.length>=6||M.busy||locked;
  previewLighting(M.draft);
}
function createColorEditor(){
  const list=$('#colorEditor');list.replaceChildren();
  if(!M.draft)return;
  M.draft.colors.forEach((hex,index)=>{
    const row=document.createElement('div');row.className='color-row';
    const pick=document.createElement('input');pick.type='color';pick.value='#'+hex;pick.setAttribute('aria-label',`颜色 ${index+1}`);
    const code=document.createElement('input');code.type='text';code.value=hex;code.maxLength=7;code.autocomplete='off';code.spellcheck=false;
    code.setAttribute('aria-label',`颜色 ${index+1} 十六进制`);
    const label=document.createElement('span');label.className='color-label';label.textContent=`颜色 ${index+1}`;
    const spacer=document.createElement('span');spacer.className='spacer';
    const up=document.createElement('button');up.className='icon-button';up.textContent='↑';up.title='前移颜色';up.disabled=index===0||advancedRgbLocked();
    const down=document.createElement('button');down.className='icon-button';down.textContent='↓';down.title='后移颜色';down.disabled=index===M.draft.colors.length-1||advancedRgbLocked();
    const remove=document.createElement('button');remove.className='icon-button';remove.textContent='×';remove.title='移除颜色';remove.disabled=M.draft.colors.length===1;
    const move=(shift)=>{const next=index+shift;[M.draft.colors[index],M.draft.colors[next]]=[M.draft.colors[next],M.draft.colors[index]];M.dirty=true;createColorEditor();refreshDraft();};
    up.addEventListener('click',()=>move(-1));down.addEventListener('click',()=>move(1));
    remove.addEventListener('click',()=>{M.draft.colors.splice(index,1);M.dirty=true;createColorEditor();refreshDraft();});
    row.append(pick,label,code,spacer,up,down,remove);list.append(row);
    const details=document.createElement('details');details.className='hsv-panel';
    const summary=document.createElement('summary');summary.textContent=`颜色 ${index+1} · RGB / HSV 数值微调`;
    details.append(summary);
    const groups={};
    function updateColor(newHex, source){
      M.draft.colors[index]=newHex;
      pick.value='#'+newHex;
      code.value=newHex;
      const rgb=[0,2,4].map(i=>parseInt(newHex.slice(i,i+2),16));
      const hsv=rgbToHsv(newHex);
      for(const kind of ['rgb','hsv']){
        if(kind===source)continue;
        groups[kind].forEach((pair,i)=>{pair.range.value=(kind==='rgb'?rgb:hsv)[i];pair.number.value=pair.range.value;});
      }
      M.dirty=true;refreshDraft();
    }
    for(const [kind,names,limits,values] of [
      ['rgb',['R 红','G 绿','B 蓝'],[255,255,255],[0,2,4].map(i=>parseInt(hex.slice(i,i+2),16))],
      ['hsv',['H 色相','S 饱和度','V 明度'],[360,100,100],rgbToHsv(hex)]]){
      const title=document.createElement('div');title.className='color-channel-title';title.textContent=kind.toUpperCase()+' 数值编辑';details.append(title);
      groups[kind]=[];
      names.forEach((name,channel)=>{
        const group=document.createElement('div');group.className='hsv-channel';
        const labelEl=document.createElement('label');labelEl.textContent=name;
        const range=document.createElement('input');range.type='range';range.min='0';range.max=String(limits[channel]);range.step='1';range.value=values[channel];
        range.setAttribute('aria-label',`颜色 ${index+1} ${name} 滑块`);
        const num=document.createElement('input');num.type='number';num.min='0';num.max=String(limits[channel]);num.step='1';num.value=values[channel];
        num.setAttribute('aria-label',`颜色 ${index+1} ${name} 数值`);
        groups[kind].push({range,number:num});
        const process=(newValue)=>{
          const n=Number(newValue);
          if(!Number.isInteger(n)||n<0||n>limits[channel]){
            toast(`${name} 只能输入 0–${limits[channel]} 的整数`,true);num.value=range.value;return;
          }
          range.value=String(n);num.value=String(n);
          const channelVals=groups[kind].map(x=>Number(x.range.value));
          const newHex=kind==='rgb'?channelVals.map(x=>x.toString(16).padStart(2,'0').toUpperCase()).join(''):hsvToRgb(...channelVals);
          updateColor(newHex,kind);
        };
        range.addEventListener('input',()=>process(range.value));
        num.addEventListener('change',()=>process(num.value));
        group.append(labelEl,range,num);details.append(group);
      });
    }
    pick.addEventListener('input',()=>updateColor(pick.value.slice(1).toUpperCase(),null));
    code.addEventListener('change',()=>{
      const c=validateColor(code.value.replace(/^#/,''));
      if(!c){toast('请输入 6 位 RGB 十六进制颜色',true);code.value=M.draft.colors[index];return;}
      updateColor(c,null);
    });
    list.append(details);
  });
}

function displayStatus(state){
  M.live=state;setDot(true);
  applyHeroColor(state);
  if(!M.dirty){
    M.draft=cleanLighting(state);
    M.baselineRaw=state.raw;
    createColorEditor();
  }
  refreshDraft();
  $('#heroMode').textContent=labels[state.mode]||state.mode;
  $('#heroBrightness').textContent=Math.round(state.brightness/255*100)+'%';
  $('#heroColors').textContent=String(state.color_count);
  $('#platformBadge').textContent=state.platform_writable?'已授权':'默认锁定';
  $('#platformBadge').classList.toggle('unlocked',state.platform_writable);
  $$('[data-profile], [data-button-level]').forEach(btn=>btn.disabled=!state.platform_writable);
}
async function loadStatus(){
  try{const data=await api('/api/status');hideLogin();M.undoAvailable=Boolean(data.undo_available);displayStatus(data.lighting);if(data.demo){$('#versionChip').textContent='v2.1 · DEMO';}else{$('#versionChip').textContent='v'+data.version;}}
  catch(e){setDot(false);refreshDraft();if(M.token && !$('#loginDialog').open)toast(e.message,true);}
}
function renderPresets(){
  const list=$('#presetList');list.replaceChildren();
  M.presets.forEach((item,i)=>{
    const slot=i+1;
    const el=document.createElement('div');el.className='preset-item';
    const summary=document.createElement('div');summary.className='preset-summary';
    const dot=document.createElement('i');dot.className='preset-dot';
    if(item?.lighting?.colors?.[0])dot.style.background='#'+item.lighting.colors[0];
    const title=document.createElement('div');title.className='preset-text';
    const strong=document.createElement('strong');strong.textContent=item?.name||`空预设 ${slot}`;
    const sub=document.createElement('small');sub.textContent=item?`${labels[item.lighting.mode]||'光效'} · ${item.lighting.colors.length} 色`:'尚未保存';
    title.append(strong,sub);summary.append(dot,title);
    const controls=document.createElement('div');controls.className='preset-buttons';
    function btn(label,disabled,fn){const b=document.createElement('button');b.textContent=label;b.disabled=disabled;b.addEventListener('click',fn);controls.append(b);}
    btn('保存草稿',!M.draft,()=>savePreset(slot));
    btn('载入编辑器',!item,()=>loadPreset(slot));
    btn('立即应用',!item||!M.live?.writable,()=>applyPreset(slot));
    btn('删除',!item,()=>deletePreset(slot));
    el.append(summary,controls);list.append(el);
  });
}
async function loadPresets(){try{M.presets=(await api('/api/presets')).slots;renderPresets();}catch(e){toast(e.message,true);}}
async function savePreset(slot){
  if(!M.draft)return;
  const name=prompt(`保存编辑器中的 RGB 参数到预设 ${slot}（不会写入设备）：`,M.presets[slot-1]?.name||`我的预设 ${slot}`);
  if(name===null)return;
  try{M.presets=(await api('/api/presets/save','POST',{slot,name:name.slice(0,36),lighting:cleanLighting(M.draft)})).slots;renderPresets();toast(`预设 ${slot} 已保存（未改动设备）`);}catch(e){toast(e.message,true);}
}
function loadPreset(slot){
  if(M.dirty && !confirm('覆盖尚未应用的草稿内容？此操作不会写入设备。'))return;
  M.draft=cleanLighting(M.presets[slot-1].lighting);
  M.dirty=true;
  createColorEditor();refreshDraft();
  selectTab('lighting');
  toast(`预设 ${slot} 已载入编辑器，请确认后点击应用到设备`);
}
async function applyPreset(slot){
  if(M.dirty && !confirm('当前还有未应用的编辑内容。将预设直接写入固件会覆盖这些设置，继续吗？'))return;
  if(!confirm(`将预设 ${slot} 立即写入 MetaCube 固件？`))return;
  M.busy=true;refreshDraft();
  try{
    const result=await api('/api/presets/apply','POST',{slot,expected_raw:M.live.raw});
    M.dirty=false;M.undoAvailable=result.undo_available;
    displayStatus(result.lighting);toast(`预设 ${slot} 已应用到主板（回读验证成功）`);
  }catch(e){toast(e.message,true);}finally{M.busy=false;refreshDraft();}
}
async function deletePreset(slot){
  if(!confirm(`确定删除预设 ${slot} 吗？`))return;
  try{M.presets=(await api('/api/presets/delete','POST',{slot})).slots;renderPresets();toast(`预设 ${slot} 已删除`);}catch(e){toast(e.message,true);}
}
async function exportPresets(){
  try{
    const data=await api('/api/presets/export');
    const payload=new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'});
    const url=URL.createObjectURL(payload);
    const a=document.createElement('a');a.href=url;a.download='metacube-rgb-presets.json';
    a.click();URL.revokeObjectURL(url);toast('5 个 RGB 预设已导出');
  }catch(e){toast(e.message,true);}
}
async function importPresets(file){
  if(!file)return;
  if(file.size>4096){toast('预设 JSON 文件最大 4 KB',true);return;}
  if(!confirm('导入会替换本机全部 5 个预设（不会写入灯光），继续吗？'))return;
  try{
    const json=JSON.parse(await file.text());
    M.presets=(await api('/api/presets/import','POST',json)).slots;
    renderPresets();toast('预设导入成功，灯光保持原状');
  }catch(e){toast('导入失败：'+e.message,true);}
}
async function applyLighting(){
  if(!M.draft || M.busy || !M.dirty)return;
  M.busy=true;refreshDraft();
  try{
    if(advancedRgbLocked()&&draftRequiresExperimental(M.draft))throw new Error('RGB 高级效果已锁定，请先恢复安全配置');
    const result=await api('/api/lighting','POST',{...cleanLighting(M.draft),expected_raw:M.baselineRaw});
    M.dirty=false;M.undoAvailable=result.undo_available;displayStatus(result.lighting);
    toast('光效设置成功 · 固件回读验证通过');
  }catch(e){toast('写入未完成：'+e.message,true);}
  finally{M.busy=false;refreshDraft();}
}
async function undoLighting(){
  if(M.dirty||!M.undoAvailable)return;
  if(!confirm('恢复本次 Web 会话中上一次已应用的 RGB 配置？'))return;
  M.busy=true;refreshDraft();
  try{
    const result=await api('/api/lighting/undo','POST',{});
    M.dirty=false;M.undoAvailable=false;displayStatus(result.lighting);
    toast('已恢复上一次设备灯光配置');
  }catch(e){toast('撤销失败：'+e.message,true);}
  finally{M.busy=false;refreshDraft();}
}
async function inspectPacket(){
  if(!M.draft)return;
  try{
    const result=await api('/api/lighting/plan','POST',{...cleanLighting(M.draft),expected_raw:M.baselineRaw});
    const rows=['WMI SET / 32 字节 / 仅预检',result.set_packet.toUpperCase(),'',`变更项目：${Object.keys(result.changes).join(', ')||'无'}`,`固件写入许可：${result.can_apply?'允许':'已锁定'}`,`高级参数：${result.experimental_reasons.join(', ')||'无'}`];
    $('#packetText').textContent=rows.join('\n');$('#packetCard').hidden=false;
    $('#packetCard').scrollIntoView({block:'nearest',behavior:'smooth'});
  }catch(e){toast('数据包预检失败：'+e.message,true);}
}

function setGauge(name, percent, detail){
  const num=$(`#${name}Metric`), bar=$(`#${name}Bar`), desc=$(`#${name}Detail`);
  num.textContent=Number.isFinite(percent)?String(Math.round(percent*10)/10):'—';
  bar.style.width=Number.isFinite(percent)?`${Math.max(0,Math.min(100,percent))}%`:'0%';
  desc.textContent=detail;
}
function renderSystem(data){
  setGauge('cpu',data.cpu.percent,`${data.cpu.count||'—'} 线程 · ${data.cpu.frequency_ghz??'—'} GHz`);
  setGauge('mem',data.memory.percent,`${fmtSize(data.memory.used)} / ${fmtSize(data.memory.total)}`);
  setGauge('disk',data.disk?.percent,`${fmtSize(data.disk?.used)} / ${fmtSize(data.disk?.total)}`);
  const temps=data.temperatures||[];
  const candidate=temps.find(x=>/Tctl|Tdie|Package|CPU|Core/i.test(x.name))||temps[0];
  setGauge('temp',candidate?.celsius, candidate?.name||'内核暂未提供温度传感器');
  const gpu=data.gpu||{devices:[],percent:null};
  setGauge('gpu',gpu.percent,gpu.devices?.length?`${gpu.devices.length} 个设备 · ${gpu.devices[0].driver||'驱动未知'}`:'DRM 未检测到 GPU（可能已直通）');
  const net=data.network||{};
  const rx=(net.rx_bytes_per_second??0)/1048576;
  const tx=(net.tx_bytes_per_second??0)/1048576;
  setGauge('net',net.percent,net.rx_bytes_per_second===null||net.rx_bytes_per_second===undefined?'正在采样 · 物理 NIC':`↓ ${rx.toFixed(2)} / ↑ ${tx.toFixed(2)} MiB/s`);
  const items=[['设备型号',data.dmi?.product_name],['主板',data.dmi?.board_name],
    ['BIOS 版本',data.dmi?.bios_version],['处理器',data.cpu.model],
    ['Linux 内核',data.kernel],['主机名',data.host],
    ['内存总量',fmtSize(data.memory.total)],['运行时间',`${Math.floor(data.uptime_seconds/86400)} 天 ${Math.floor(data.uptime_seconds%86400/3600)} 小时`],
    ['平均负载',data.cpu.load.join(' / ')],
    ['GPU 设备',data.gpu?.devices?.map(x=>x.device+': '+(x.driver||'无驱动')).join(' / ')||'Linux 未识别 / 已直通'],
    ['物理网卡',data.network?.interfaces?.map(x=>x.interface).join(' / ')||'无']];
  const inf=$('#systemInfo');inf.replaceChildren();
  for(const [label,value] of items){const box=document.createElement('div');box.className='info-item';const small=document.createElement('small');small.textContent=label;const strong=document.createElement('strong');strong.textContent=value||'—';box.append(small,strong);inf.append(box);}
  const sensors=$('#sensorList');sensors.replaceChildren();
  for(const sensor of [...data.temperatures.map(x=>({name:x.name,value:x.celsius+' °C'})),
                        ...data.fans.map(x=>({name:x.name,value:x.rpm+' RPM'}))].slice(0,16)){
    const el=document.createElement('div');el.className='sensor';const small=document.createElement('small');small.textContent=sensor.name;const strong=document.createElement('strong');strong.textContent=sensor.value;el.append(small,strong);sensors.append(el);
  }
  if(!sensors.childNodes.length)sensors.textContent='内核未暴露温度或风扇传感器，请使用 WMI 诊断进一步检查。';
}
async function loadSystem(){
  try{const data=await api('/api/system');renderSystem(data);}catch(e){console.warn(e.message);}
}
function renderOem(data){
  M.oem=data;
  const perf=data.system_mode, btn=data.button_brightness;
  if(perf&&!perf.unsupported){$$('[data-profile]').forEach(x=>x.classList.toggle('active',Number(x.dataset.profile)===perf.value));$('#dashPerf').textContent='当前 '+({0:'狂暴',1:'均衡',2:'静音'}[perf.value]||`状态 ${perf.value}`);}
  if(btn&&!btn.unsupported){$$('[data-button-level]').forEach(x=>x.classList.toggle('active',Number(x.dataset.buttonLevel)===btn.value));$('#buttonValue').textContent=`第 ${btn.value} 级`;}else{$('#buttonValue').textContent='不支持 / 未读取';}
}
async function loadOemBasic(){
  try{renderOem((await api('/api/oem-basic')).functions);}catch(e){console.warn('OEM basic read: '+e.message);}
}
async function probeOem(){
  const button=$('#probeOemButton');button.disabled=true;button.textContent='正在检测...';
  try{
    const items=(await api('/api/oem')).functions;renderOem(items);
    const container=$('#oemList');container.replaceChildren();
    for(const [key,v] of Object.entries(items)){
      const row=document.createElement('div');row.className='diag-item';
      const n=document.createElement('span');n.textContent=oemNames[key]||key;
      const val=document.createElement('strong');
      if(v.unsupported){val.textContent='不可用';val.className='unsupported';val.title=v.reason;}
      else if(key==='fans_rpm')val.textContent=`CPU ${v.cpu} / GPU ${v.gpu} RPM`;
      else val.textContent=`${v.label||v.value} (${v.value})`;
      row.append(n,val);container.append(row);
    }
    toast('原厂 WMI 只读检测完成');
  }catch(e){toast(e.message,true);}finally{button.disabled=false;button.textContent='重新检测 ↗';}
}
async function setPlatform(control,value){
  const title=control==='system_mode'?'系统性能档位':'按键灯亮度';
  if(!confirm(`要修改${title}为 ${value} 吗？\n该功能尚未在本机验证，可能影响设备状态。`))return;
  try{const data=await api('/api/platform','POST',{control,value});toast(title+'已通过固件回读验证');loadOemBasic();}
  catch(e){toast(e.message,true);}
}
function bind(){
  $('#todayText').textContent=new Date().toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'});
  $$('[data-quick-color]').forEach(el=>el.style.setProperty('--swatch','#'+el.dataset.quickColor));
  $$('[data-view]').forEach(el=>el.addEventListener('click',()=>selectTab(el.dataset.view)));
  $$('[data-go]').forEach(el=>el.addEventListener('click',()=>selectTab(el.dataset.go)));
  $('#refreshButton').addEventListener('click',()=>{loadStatus();loadPresets();loadSystem();toast('已请求刷新');});
  $('#loginForm').addEventListener('submit',async evt=>{
    evt.preventDefault();const value=$('#tokenInput').value.trim();
    if(value.length<32){$('#loginError').textContent='令牌长度不正确';return;}
    M.token=value;
    try{const data=await api('/api/status');sessionStorage.setItem('metacube-token',value);hideLogin();M.undoAvailable=Boolean(data.undo_available);displayStatus(data.lighting);loadPresets();loadSystem();toast('成功连接至 MetaCube');}
    catch(e){$('#loginError').textContent=e.message;}
  });
  $$('.mode-tile').forEach(el=>el.addEventListener('click',()=>{if(!M.draft)return;M.draft.mode=el.dataset.mode;M.dirty=true;refreshDraft();}));
  $$('[data-direction]').forEach(el=>el.addEventListener('click',()=>{if(!M.draft)return;M.draft.direction=Number(el.dataset.direction);M.dirty=true;refreshDraft();}));
  for(const key of ['brightness','speed','cycle'])$('#'+key+'Input').addEventListener('input',event=>{if(!M.draft)return;M.draft[key]=Number(event.target.value);M.dirty=true;refreshDraft();});
  $('#transitionInput').addEventListener('change',e=>{if(!M.draft)return;M.draft.transition=e.target.checked?1:0;M.dirty=true;refreshDraft();});
  $('#addColorButton').addEventListener('click',()=>{if(!M.draft||M.draft.colors.length>=6)return;M.draft.colors.push('FFFFFF');M.dirty=true;createColorEditor();refreshDraft();});
  $$('[data-quick-color]').forEach(el=>el.addEventListener('click',()=>{if(!M.draft)return;M.draft.colors[0]=el.dataset.quickColor;M.dirty=true;createColorEditor();refreshDraft();}));
  $('#applyLightingButton').addEventListener('click',applyLighting);
  $('#discardDraftButton').addEventListener('click',()=>{if(M.dirty&&confirm('放弃尚未应用的 RGB 编辑内容？'))discardDraft();});
  $('#undoLightingButton').addEventListener('click',undoLighting);
  $('#inspectPacketButton').addEventListener('click',inspectPacket);
  $('#closePacketButton').addEventListener('click',()=>{$('#packetCard').hidden=true;});
  $('#nextCycleButton').addEventListener('click',()=>{if(!M.draft)return;M.draft.cycle=(M.draft.cycle+1)%12;M.dirty=true;refreshDraft();});
  $('#exportPresetsButton').addEventListener('click',exportPresets);
  $('#importPresetsButton').addEventListener('click',()=>$('#importPresetsFile').click());
  $('#importPresetsFile').addEventListener('change',async e=>{await importPresets(e.target.files?.[0]);e.target.value='';});
  $('#probeOemButton').addEventListener('click',probeOem);
  $$('[data-profile]').forEach(el=>el.addEventListener('click',()=>setPlatform('system_mode',Number(el.dataset.profile))));
  $$('[data-button-level]').forEach(el=>el.addEventListener('click',()=>setPlatform('button_brightness',Number(el.dataset.buttonLevel))));
  $$('[data-profile],[data-button-level]').forEach(el=>el.disabled=true);
  $('#applyLightingButton').disabled=true;
  $('#undoLightingButton').disabled=true;
  $('#addColorButton').disabled=true;
  renderPresets();
}
async function initial(){
  bind();
  if(!M.token){showLogin();return;}
  await loadStatus();
  if(M.live){loadPresets();loadSystem();}
}
initial();
setInterval(()=>{if(M.token&&!$('#loginDialog').open){loadStatus();if(['dashboard','system'].includes(M.tab))loadSystem();}},7000);
