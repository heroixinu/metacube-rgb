/* MetaCube Control Center - no third-party dependencies, no external requests. */
'use strict';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const labels = {breath:'呼吸',steady:'常亮',spin:'旋转',off:'关闭'};
const oemNames = {system_mode:'主机性能模式',button_brightness:'按键灯亮度',fans_rpm:'CPU / GPU 风扇',gpu_mode:'GPU 模式',fn_lock:'Fn Lock',touchpad_lock:'触摸板锁定',keyboard_mode:'键盘 RGB 模式',keyboard_brightness:'键盘 RGB 亮度',ac_type:'供电接口',cpu_temperature_raw:'原厂温度读数'};
const M = {token:sessionStorage.getItem('metacube-token')||'', live:null,draft:null,dirty:false,presets:Array(5).fill(null),tab:'dashboard',oem:null,busy:false};

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
function setDot(ok){$('#deviceDot').classList.toggle('online',ok);$('#deviceStatus').textContent=ok?'WMI 已连接':'硬件未连接';}
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
function applyDisplayColor(state){
  const colors=state?.colors?.length?state.colors:['50DCFA'];
  const c=colors[0];
  document.documentElement.style.setProperty('--led','#'+c);
  document.documentElement.style.setProperty('--glow','#'+c);
  const grad=colors.length>1?`linear-gradient(90deg,${colors.map(x=>'#'+x).join(',')})`:'#'+c;
  $('#previewStrip').style.background=grad;
  $('#heroLight').style.background=grad;
}
function refreshDraft(){
  if(!M.draft)return;
  $$('.mode-tile').forEach(el=>el.classList.toggle('active',el.dataset.mode===M.draft.mode));
  for(const key of ['brightness','speed','cycle']){
    $(`#${key}Input`).value=M.draft[key];
    $(`#${key}Value`).textContent=key==='cycle'?`${M.draft[key]} / 11`:String(M.draft[key]);
  }
  $('#transitionInput').checked=Boolean(M.draft.transition);
  $$('[data-direction]').forEach(el=>el.classList.toggle('active',Number(el.dataset.direction)===M.draft.direction));
  $('#previewModeText').textContent=(labels[M.draft.mode]||'未知')+'模式';
  $('#previewColorText').textContent='#'+(M.draft.colors?.[0]||'000000') + (M.draft.colors.length>1?` +${M.draft.colors.length-1}`:'');
  $('#unsavedHint').textContent=M.dirty?'存在尚未写入固件的改动':'修改不会自动写入主板固件';
  $('#unsavedHint').classList.toggle('dirty',M.dirty);
  $('#applyLightingButton').disabled=!M.live?.writable||M.busy;
  $('#addColorButton').disabled=M.draft.colors.length>=6;
  applyDisplayColor(M.draft);
}
function createColorEditor(){
  const list=$('#colorEditor');list.replaceChildren();
  if(!M.draft)return;
  M.draft.colors.forEach((hex,index)=>{
    const row=document.createElement('div');row.className='color-row';
    const input=document.createElement('input');input.type='color';input.value='#'+hex;input.setAttribute('aria-label',`颜色 ${index+1}`);
    const text=document.createElement('input');text.type='text';text.value=hex;text.maxLength=7;text.autocomplete='off';text.spellcheck=false;
    const label=document.createElement('span');label.className='color-label';label.textContent=`颜色 ${index+1}`;
    const spacer=document.createElement('span');spacer.className='spacer';
    const remove=document.createElement('button');remove.className='icon-button';remove.textContent='×';remove.title='移除颜色';remove.disabled=M.draft.colors.length===1;
    input.addEventListener('input',()=>{M.draft.colors[index]=input.value.slice(1).toUpperCase();text.value=M.draft.colors[index];M.dirty=true;refreshDraft();});
    text.addEventListener('change',()=>{
      const c=validateColor(text.value.replace(/^#/,''));
      if(!c){toast('请输入 6 位 RGB 十六进制颜色',true);text.value=M.draft.colors[index];return;}
      M.draft.colors[index]=c;M.dirty=true;createColorEditor();refreshDraft();
    });
    remove.addEventListener('click',()=>{M.draft.colors.splice(index,1);M.dirty=true;createColorEditor();refreshDraft();});
    row.append(input,label,text,spacer,remove);list.append(row);
    const details=document.createElement('details');details.className='hsv-panel';
    const summary=document.createElement('summary');summary.textContent=`颜色 ${index+1} · HSV 精细调节`;
    details.append(summary);
    const hsvValues=rgbToHsv(hex);
    const names=['色相 H','饱和度 S','明度 V'];
    for(let channel=0;channel<3;channel++){
      const group=document.createElement('div');group.className='hsv-channel';
      const labelEl=document.createElement('label');labelEl.textContent=names[channel];
      const slider=document.createElement('input');slider.type='range';slider.min='0';
      slider.max=channel===0?'360':'100';slider.step='1';slider.value=hsvValues[channel];
      slider.setAttribute('aria-label',`颜色 ${index+1} ${names[channel]}`);
      const output=document.createElement('output');output.textContent=String(hsvValues[channel]);
      slider.addEventListener('input',()=>{
        hsvValues[channel]=Number(slider.value);
        M.draft.colors[index]=hsvToRgb(...hsvValues);
        input.value='#'+M.draft.colors[index];text.value=M.draft.colors[index];
        output.textContent=String(hsvValues[channel]);M.dirty=true;refreshDraft();
      });
      group.append(labelEl,slider,output);details.append(group);
    }
    list.append(details);
  });
}
function displayStatus(state){
  M.live=state;setDot(true);
  if(!M.dirty){
    M.draft={mode:state.mode,colors:[...state.colors],brightness:state.brightness,
      speed:state.speed,direction:state.direction,cycle:state.cycle,transition:state.transition};
    createColorEditor();refreshDraft();
  }
  $('#heroMode').textContent=labels[state.mode]||state.mode;
  $('#heroBrightness').textContent=Math.round(state.brightness/255*100)+'%';
  $('#heroColors').textContent=String(state.color_count);
  $('#platformBadge').textContent=state.platform_writable?'已授权':'默认锁定';
  $('#platformBadge').classList.toggle('unlocked',state.platform_writable);
  $$('[data-profile], [data-button-level]').forEach(btn=>btn.disabled=!state.platform_writable);
}
async function loadStatus(){
  try{const data=await api('/api/status');hideLogin();displayStatus(data.lighting);if(data.demo){$('#versionChip').textContent='v2.0 · DEMO';}else{$('#versionChip').textContent='v'+data.version;}}
  catch(e){setDot(false);if(M.token && !$('#loginDialog').open)toast(e.message,true);}
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
    btn('保存',!M.live?.writable,()=>savePreset(slot));
    btn('加载',!item||!M.live?.writable,()=>applyPreset(slot));
    btn('×',!item,()=>deletePreset(slot));
    el.append(summary,controls);list.append(el);
  });
}
async function loadPresets(){try{M.presets=(await api('/api/presets')).slots;renderPresets();}catch(e){toast(e.message,true);}}
async function savePreset(slot){
  const name=prompt(`将当前已应用的灯效保存到预设 ${slot}：`,M.presets[slot-1]?.name||`我的预设 ${slot}`);
  if(name===null)return;
  try{M.presets=(await api('/api/presets/save','POST',{slot,name:name.slice(0,36)})).slots;renderPresets();toast(`已保存预设 ${slot}`);}catch(e){toast(e.message,true);}
}
async function applyPreset(slot){
  if(M.dirty && !confirm('当前还有未应用的编辑内容，加载预设会覆盖。继续吗？'))return;
  try{const result=await api('/api/presets/apply','POST',{slot});M.dirty=false;displayStatus(result.lighting);toast(`预设 ${slot} 已应用到主板`);}catch(e){toast(e.message,true);}
}
async function deletePreset(slot){
  if(!confirm(`确定删除预设 ${slot} 吗？`))return;
  try{M.presets=(await api('/api/presets/delete','POST',{slot})).slots;renderPresets();toast(`预设 ${slot} 已删除`);}catch(e){toast(e.message,true);}
}
async function applyLighting(){
  if(!M.draft || M.busy)return;
  M.busy=true;refreshDraft();
  try{const result=await api('/api/lighting','POST',M.draft);M.dirty=false;displayStatus(result.lighting);toast('光效设置成功 · 已通过固件回读验证');}
  catch(e){toast('写入失败：'+e.message,true);}finally{M.busy=false;refreshDraft();}
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
    try{const data=await api('/api/status');sessionStorage.setItem('metacube-token',value);hideLogin();displayStatus(data.lighting);loadPresets();loadSystem();toast('成功连接至 MetaCube');}
    catch(e){$('#loginError').textContent=e.message;}
  });
  $$('.mode-tile').forEach(el=>el.addEventListener('click',()=>{if(!M.draft)return;M.draft.mode=el.dataset.mode;M.dirty=true;refreshDraft();}));
  $$('[data-direction]').forEach(el=>el.addEventListener('click',()=>{if(!M.draft)return;M.draft.direction=Number(el.dataset.direction);M.dirty=true;refreshDraft();}));
  for(const key of ['brightness','speed','cycle'])$('#'+key+'Input').addEventListener('input',event=>{if(!M.draft)return;M.draft[key]=Number(event.target.value);M.dirty=true;refreshDraft();});
  $('#transitionInput').addEventListener('change',e=>{if(!M.draft)return;M.draft.transition=e.target.checked?1:0;M.dirty=true;refreshDraft();});
  $('#addColorButton').addEventListener('click',()=>{if(!M.draft||M.draft.colors.length>=6)return;M.draft.colors.push('FFFFFF');M.dirty=true;createColorEditor();refreshDraft();});
  $$('[data-quick-color]').forEach(el=>el.addEventListener('click',()=>{if(!M.draft)return;M.draft.colors[0]=el.dataset.quickColor;M.dirty=true;createColorEditor();refreshDraft();}));
  $('#applyLightingButton').addEventListener('click',applyLighting);
  $('#probeOemButton').addEventListener('click',probeOem);
  $$('[data-profile]').forEach(el=>el.addEventListener('click',()=>setPlatform('system_mode',Number(el.dataset.profile))));
  $$('[data-button-level]').forEach(el=>el.addEventListener('click',()=>setPlatform('button_brightness',Number(el.dataset.buttonLevel))));
  $$('[data-profile],[data-button-level]').forEach(el=>el.disabled=true);
  $('#applyLightingButton').disabled=true;
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
