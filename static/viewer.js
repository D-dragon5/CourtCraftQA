const csrf=document.querySelector('meta[name="viewer-token"]').content;

const $=id=>document.getElementById(id);

let rows=[],filtered=[],page=0,size=40,current='',selection=0,jsonSelection=0,doc=null,original='',saving=false,loading=false,model=null,sectionIndex=0,qaIndex=0,attachments={images:[],json:[]};
let catalogRootId=null,indexLoading=false,changingRoot=false;

const dirty=()=>!!doc&&$('editor').value!==original;

function editMessage(message,kind=''){
  $('editStatus').textContent=message;
  $('editStatus').className=kind;
  $('editStatus').title=message
}

function updateFullscreenButton(){
  const full=!!document.fullscreenElement,button=$('toggleFullscreen');
  button.textContent=full?'退出全屏（Esc）':'全屏（F11）';
  button.setAttribute('aria-pressed',String(full));
  button.title=full?'退出整个页面的全屏（Esc）':'全屏显示整个核对页面，Esc 退出；F11 为浏览器自带全屏'
}
$('toggleFullscreen').onclick=async()=>{
  try{
    if(document.fullscreenElement)await document.exitFullscreen();
    else if(document.documentElement.requestFullscreen)await document.documentElement.requestFullscreen({navigationUI:'hide'});
    else editMessage('当前浏览器不支持页面全屏，可使用浏览器的 F11。','error')
  }catch{
    editMessage('当前浏览器未允许页面全屏，可在独立浏览器中打开并使用 F11。','error')
  }
};
document.addEventListener('fullscreenchange',()=>{
  updateFullscreenButton();applyPanelLayout();scheduleCompactReview()
});
updateFullscreenButton();

function showPath(){
  $('jsonPath').textContent=doc?`读取：${doc.path}　→　保存：${doc.save_path}（原始文件保留）`:'选择回合后加载 JSON。'
}

async function request(url,options={}){
  if(catalogRootId&&(!options.method||options.method==='GET')&&/^\/api\/(assets|references|json|prepare)\?/.test(url))url+='&root_id='+encodeURIComponent(catalogRootId);
  const r=await fetch(url,{cache:'no-store',...options}),data=await r.json();
  if(!r.ok)throw Error(data.error||'请求失败');
  return data
}

let pinned=false;
let wheelFirstAt=null,wheelLastAt=0,wheelPagingLocked=false;
const wheelHint='列表到底后，连续下滚两次翻页';
function resetWheelPaging(){
  wheelFirstAt=null;
  wheelLastAt=0;
  wheelPagingLocked=false;
  $('listWheelHint').textContent=wheelHint;
}
try{
  pinned=localStorage.getItem('basketball-sidebar-pinned')==='true'
}catch{}

function sidebar(open){
  if(!open)resetWheelPaging();
  document.body.classList.toggle('sidebar-open',open);
  $('sidebar').inert=!(open||pinned);
  $('menu').setAttribute('aria-expanded',String(open||pinned))
}

function pin(value){
  pinned=value;
  document.body.classList.toggle('pinned',pinned);
  $('pin').textContent=pinned?'取消固定':'固定';
  $('pin').setAttribute('aria-pressed',String(pinned));
  try{
    localStorage.setItem('basketball-sidebar-pinned',String(pinned))
  }catch{}
  sidebar(pinned)
}

let menuTimer;
function openMenu(){
  clearTimeout(menuTimer);
  sidebar(true)
}

$('edge').onmouseenter=openMenu;
$('menu').onmouseenter=openMenu;
$('menu').onclick=openMenu;
$('sidebar').onmouseenter=openMenu;
$('sidebar').onmouseleave=()=>{
  resetWheelPaging();
  if(!pinned)menuTimer=setTimeout(()=>{
    sidebar(false);
    if($('sidebar').contains(document.activeElement))document.activeElement.blur()
  },200)
};
$('pin').onclick=()=>pin(!pinned);
$('closeMenu').onclick=()=>{
  pin(false);
  sidebar(false);
  $('menu').focus()
};
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&!pinned){
    sidebar(false);
    $('menu').focus()
  }
});
pin(pinned);

function filter(){
  resetWheelPaging();
  const q=$('search').value.trim().toLowerCase(),g=$('group').value;
  filtered=rows.filter(x=>(!g||x.path.split('/')[0]===g)&&x.path.toLowerCase().includes(q));
  page=0;
  draw()
}

function draw(){
  page=Math.max(0,Math.min(page,Math.max(0,Math.ceil(filtered.length/size)-1)));
  $('items').replaceChildren();
  for(const r of filtered.slice(page*size,(page+1)*size)){
    const b=document.createElement('button');
    b.textContent=r.path;
    b.className=r.path===current?'active':'';
    b.onclick=async()=>{
      if(await play(r.path)){
        if(!pinned){
          sidebar(false);
          $('title').tabIndex=-1;
          $('title').focus()
        }
      }
    };
    $('items').append(b)
  }
  $('page').textContent=`${page+1}/${Math.max(1,Math.ceil(filtered.length/size))}`;
  const folderCount=new Set(rows.map(r=>r.path.includes('/')?r.path.slice(0,r.path.lastIndexOf('/')):'.')).size;
  $('catalogCount').textContent=`${folderCount} 个回合目录 · ${rows.length} 个视频 · 每页 ${size} 个`;
  $('prev').disabled=page===0;
  $('next').disabled=(page+1)*size>=filtered.length;
  $('status').textContent=`找到 ${filtered.length} 个视频（共 ${rows.length} 个）`;
  controls()
}

async function load(force=false){
  if(saving||loading||indexLoading||changingRoot)return;
  indexLoading=true;
  controls();
  resetWheelPaging();
  try{
    const health=await request('/api/root'+(force?'?refresh=1':'')),videoRows=health.videos;
    if(catalogRootId&&health.root_id!==catalogRootId){
      if(dirty()&&!confirm('数据目录已在其他页面切换。重新读取会放弃当前未保存修改，是否继续？'))return;
      clearLoadedRound();
    }
    rows=videoRows;
    catalogRootId=health.root_id;
    $('dataRoot').value=health.data_root;
    $('catalogRoot').textContent='读取目录：'+health.data_root;
    $('catalogRoot').title=health.data_root;
    const old=$('group').value;
    $('group').replaceChildren(new Option('全部回合',''));
    for(const g of [...new Set(rows.map(x=>x.path.split('/')[0]))].sort())$('group').add(new Option(g,g));
    $('group').value=old;
    filter()
  }catch(e){
    $('status').textContent='索引失败：'+e.message
  }finally{
    indexLoading=false;
    controls();
  }
}

function clearLoadedRound(){
  ++selection;
  ++jsonSelection;
  loading=false;
  current='';
  doc=null;
  model=null;
  sourceModel=null;
  referenceData=null;
  referenceError='';
  original='';
  attachments={images:[],json:[]};
  restoreSnapshot=null;
  cleanupContext=null;
  pendingCleanup=false;
  questionEditing=false;
  setAnswerEditing(false,false);
  $('editor').value='';
  $('jsonFiles').replaceChildren();
  $('video').pause();
  $('video').removeAttribute('src');
  $('video').load();
  $('title').textContent='从左侧选择回合';
  showPath();
  renderReview();
}

async function applyDataRoot(){
  if(saving||loading||changingRoot||indexLoading)return;
  const path=$('dataRoot').value.trim().replace(/^"(.*)"$/,'$1');
  if(!path){$('dataRoot').focus();return}
  cleanEditedAnswers();
  if(dirty()&&!confirm('切换目录会放弃当前回合未保存的修改，是否继续？'))return;
  changingRoot=true;
  controls();
  editMessage('正在读取新目录…');
  try{
    const data=await request('/api/root',{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Token':csrf},body:JSON.stringify({data_root:path,root_id:catalogRootId})});
    clearLoadedRound();
    rows=data.videos;
    catalogRootId=data.root_id;
    $('dataRoot').value=data.data_root;
    $('catalogRoot').textContent='读取目录：'+data.data_root;
    $('catalogRoot').title=data.data_root;
    $('group').replaceChildren(new Option('全部回合',''));
    for(const group of [...new Set(rows.map(x=>x.path.split('/')[0]))].sort())$('group').add(new Option(group,group));
    $('search').value='';
    filter();
    editMessage('目录已记住，已读取全部 '+rows.length+' 个视频。请选择回合。','success');
  }catch(e){
    editMessage('目录读取失败：'+e.message+'。当前编辑已保留，可刷新列表核对当前目录。','error');
  }finally{
    changingRoot=false;
    controls();
  }
}
$('applyRoot').onclick=applyDataRoot;
$('dataRoot').addEventListener('keydown',event=>{
  if(event.key==='Enter'&&!event.isComposing){
    event.preventDefault();
    event.stopPropagation();
    applyDataRoot();
  }
});

function turnListPage(delta){
  const target=page+delta;
  if(target<0||target>=Math.ceil(filtered.length/size))return false;
  const list=$('items'),focusInList=list.contains(document.activeElement);
  resetWheelPaging();
  page=target;
  draw();
  list.scrollTop=0;
  if(focusInList)list.focus({preventScroll:true});
  return true;
}

$('items').addEventListener('wheel',event=>{
  const list=$('items'),now=performance.now(),idle=now-wheelLastAt;
  wheelLastAt=now;
  const bottom=list.scrollTop+list.clientHeight>=list.scrollHeight-2;
  const downward=event.deltaY>0&&Math.abs(event.deltaY)>=Math.abs(event.deltaX);
  if(!downward||!bottom||$('next').disabled){
    wheelFirstAt=null;
    $('listWheelHint').textContent=wheelHint;
    return;
  }
  event.preventDefault();
  if(wheelPagingLocked){
    if(idle<250)return;
    wheelPagingLocked=false;
  }
  if(wheelFirstAt===null||now-wheelFirstAt>800){
    wheelFirstAt=now;
    $('listWheelHint').textContent='再向下滚一次，进入下一页';
    return;
  }
  if(now-wheelFirstAt<65)return;
  if(turnListPage(1)){
    wheelPagingLocked=true;
    wheelLastAt=now;
  }
},{passive:false});

function questionRefs(){
  return sections().flatMap((s,i)=>Array.isArray(s.qa)?s.qa.map((_,j)=>({s:i,q:j})):[])
}

function primitiveField(value,path,container){
  if(value!==null&&typeof value==='object'){
    const d=document.createElement('details'),summary=document.createElement('summary');
    summary.textContent=String(path.at(-1))+(Array.isArray(value)?`（${value.length} 项）`:'');
    d.append(summary);
    container.append(d);
    for(const [k,v]of Object.entries(value))primitiveField(v,[...path,k],d);
    return
  }
  const label=document.createElement('label');
  label.textContent=path.join(' / ');
  let input;
  if(typeof value==='boolean'){
    input=document.createElement('select');
    input.add(new Option('true','true'));
    input.add(new Option('false','false'));
    input.value=String(value)
  }else{
    input=document.createElement(typeof value==='string'&&value.length>70?'textarea':'input');
    input.value=value===null?'null':String(value);
    if(typeof value==='number'){
      input.type='number';
      input.step='any'
    }
  }
  input.oninput=()=>{
    let v=input.value;
    if(typeof value==='number'){
      if(!v.trim()||!Number.isFinite(Number(v)))return input.setCustomValidity('请输入有效数字');
      v=Number(v)
    }else if(typeof value==='boolean')v=v==='true';else if(value===null){
      try{
        v=JSON.parse(v)
      }catch{
        return input.setCustomValidity('请输入有效 JSON 值')
      }
    }
    input.setCustomValidity('');
    let target=model;
    for(const k of path.slice(0,-1))target=target[k];
    target[path.at(-1)]=v;
    syncModel()
  };
  label.append(input);
  container.append(label)
}

function imageTimeFor(name,data,preferredIndex){
  const filename=value=>String(value||'').replace(/\\/g,'/').split('/').at(-1).toLowerCase();
  const image=filename(name),stages=Array.isArray(data?.prediction)?data.prediction:[];
  let matches=stages.filter(stage=>stage?.image&&filename(stage.image)===image);
  if(!matches.length){
    const type={action_boxes:'action',tactic_boxes:'tactic',outcome_boxes:'outcome'}[image.replace(/\.[^.]+$/,'')];
    if(type)matches=stages.filter(stage=>!stage?.image&&stage?.type===type);
  }
  const format=stage=>{
    if(typeof stage.cutoff_timestamp==='string'&&stage.cutoff_timestamp.trim())return stage.cutoff_timestamp.trim();
    if(typeof stage.cutoff_seconds!=='number'||!Number.isFinite(stage.cutoff_seconds)||stage.cutoff_seconds<0)return null;
    const total=Math.round(stage.cutoff_seconds*1000),pad=(value,width=2)=>String(value).padStart(width,'0');
    return `${pad(Math.floor(total/3600000))}:${pad(Math.floor(total/60000)%60)}:${pad(Math.floor(total/1000)%60)}.${pad(total%1000,3)}`;
  };
  const current=stages[preferredIndex];
  if(matches.includes(current))return format(current);
  const times=[...new Set(matches.map(format).filter(Boolean))];
  return times.length===1?times[0]:null;
}

function updateImageTime(){
  const name=$('images').dataset.name||'',time=imageTimeFor(name,model,sectionIndex);
  $('imageTime').hidden=!name;
  $('imageTime').textContent=time?'时间 '+time:'时间未提供';
  $('imageTime').title='当前标注图在 JSON 中对应的时间';
  return time;
}

function showImage(name){
  $('images').replaceChildren();
  const item=attachments.images.find(x=>x.name===name)||attachments.images[0];
  $('images').dataset.name=item?.name||'';
  updateImageTime();
  if(!item){
    $('images').textContent='此回合没有图片。';
    return
  }
  const f=document.createElement('figure'),a=document.createElement('a'),img=document.createElement('img'),c=document.createElement('figcaption');
  a.href='/image?path='+encodeURIComponent(item.path)+(catalogRootId?'&root_id='+encodeURIComponent(catalogRootId):'');
  a.title='点击放大标注图';
  a.onclick=e=>{
    e.preventDefault();
    $('previewImage').src=a.href;
    const time=updateImageTime();
    $('imageTitle').textContent=item.name+(time?' · 时间 '+time:' · 时间未提供');
    $('imageDialog').showModal()
  };
  img.src=a.href;
  img.alt=item.name;
  c.textContent=item.name+' · 点击查看原图';
  a.append(img);
  f.append(a,c);
  $('images').append(f);
  for(const b of $('imageTabs').children)b.classList.toggle('active',b.dataset.name===item.name)
}

function imageTabs(){
  $('imageTabs').replaceChildren();
  for(const item of attachments.images){
    const b=document.createElement('button');
    b.textContent=({action_boxes:'动作',tactic_boxes:'战术',outcome_boxes:'结果'}[item.name.replace(/\.[^.]+$/,'')]||item.name);
    b.title=item.name;
    b.dataset.name=item.name;
    b.onclick=()=>showImage(item.name);
    $('imageTabs').append(b)
  }
}

const typeNames={action:'动作',tactic:'战术',outcome:'结果'};

$('jsonFiles').onchange=()=>{
  if(dirty()&&!confirm('是否放弃未保存的修改并切换 JSON？')){
    $('jsonFiles').value=doc.path;
    return
  }
  loadJSON($('jsonFiles').value)
};
$('reload').onclick=()=>{
  if(!dirty()||confirm('是否放弃未保存的修改并重新读取？'))loadJSON(doc.path)
};

$('video').onerror=()=>{
  $('status').textContent='浏览器无法解码此视频，请检查视频格式。'
};
$('speed').onchange=()=>{
  $('video').playbackRate=Number($('speed').value)
};
$('video').onloadedmetadata=$('speed').onchange;
$('search').oninput=filter;
$('group').onchange=filter;
$('refresh').onclick=()=>load(true);
$('prev').onclick=()=>turnListPage(-1);
$('next').onclick=()=>turnListPage(1);
$('prevVideo').onclick=()=>{
  const i=filtered.findIndex(r=>r.path===current);
  if(i>0)play(filtered[i-1].path)
};
$('nextVideo').onclick=()=>{
  const i=filtered.findIndex(r=>r.path===current);
  if(i>=0&&i<filtered.length-1)play(filtered[i+1].path)
};
window.addEventListener('beforeunload',e=>{
  if(dirty()||saving){
    e.preventDefault();
    e.returnValue=''
  }
});

$('openOptions').onclick=()=>$('optionsDialog').showModal();

$('openMetadata').onclick=()=>{
  $('optionsDialog').close();
  $('metadataDialog').showModal()
};

$('openRaw').onclick=()=>{
  $('optionsDialog').close();
  $('rawDialog').showModal()
};

for(const button of document.querySelectorAll('[data-close]'))button.onclick=()=>$(button.dataset.close).close();

for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('click',event=>{
  if(event.target===dialog){
    const r=dialog.getBoundingClientRect();
    if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close()
  }
});

let answerMeasureField=null,compactReviewFrame=0;
/*
 * Locate a JSON value by its structural path, preserving every original byte
 * represented in the JavaScript string (spacing, CRLF and escaping included).
 * start is inclusive and end is exclusive, measured in UTF-16 string offsets.
 * No rendering, HTML insertion, source rewriting or external dependencies.
 */

function findJsonPathRange(text, path) {

  if (typeof text !== 'string' || !Array.isArray(path)) return null;

  try {
    JSON.parse(text);
  } catch {
    return null;
  }

  const length = text.length;

  const whitespace = c => c === ' ' || c === '\t' || c === '\r' || c === '\n';

  function skipWhitespace(index) {

    while (index < length && whitespace(text[index])) index++;

    return index;

  }

  function stringEnd(index) {
    // Input is already validated. An escape consumes its next code unit;
    // the remaining digits of a Unicode escape cannot contain delimiters.

    for (let i = index + 1; i < length; i++) {

      if (text[i] === '\\') i++;
      else if (text[i] === '"') return i + 1;

    }

    return length;

  }

  function valueEnd(index) {

    const first = text[index];

    if (first === '"') return stringEnd(index);

    if (first === '{' || first === '[') {

      let depth = 0;

      for (let i = index; i < length; i++) {

        const character = text[i];

        if (character === '"') i = stringEnd(i) - 1;
        else if (character === '{' || character === '[') depth++;
        else if (character === '}' || character === ']') {

          if (--depth === 0) return i + 1;

        }

      }

      return length;

    }

    let i = index;

    while (i < length && !whitespace(text[i]) && text[i] !== ',' && text[i] !== '}' && text[i] !== ']') i++;

    return i;

  }

  let start = skipWhitespace(0), end = valueEnd(start);

  for (const part of path) {

    const kind = text[start];

    if (kind === '{') {

      if (typeof part !== 'string' && typeof part !== 'number') return null;

      const wanted = String(part);

      let cursor = skipWhitespace(start + 1), found = null;

      while (text[cursor] !== '}') {

        const keyEnd = stringEnd(cursor);

        const key = JSON.parse(text.slice(cursor, keyEnd));

        const colon = skipWhitespace(keyEnd);

        const childStart = skipWhitespace(colon + 1);

        const childEnd = valueEnd(childStart);
        // Scan all siblings so duplicate keys match JSON.parse's last-key
        // semantics, rather than silently selecting an earlier occurrence.

        if (key === wanted) found = {start: childStart, end: childEnd};

        cursor = skipWhitespace(childEnd);

        if (text[cursor] !== ',') break;

        cursor = skipWhitespace(cursor + 1);

      }

      if (!found) return null;

      start = found.start;

      end = found.end;

    } else if (kind === '[') {

      const wanted = typeof part === 'number' ? part
        : typeof part === 'string' && /^(0|[1-9]\d*)$/.test(part) ? Number(part) : NaN;

      if (!Number.isSafeInteger(wanted) || wanted < 0) return null;

      let cursor = skipWhitespace(start + 1), index = 0, found = null;

      while (text[cursor] !== ']') {

        const childEnd = valueEnd(cursor);

        if (index === wanted) {
          found = {start: cursor, end: childEnd};
          break;
        }

        index++;

        cursor = skipWhitespace(childEnd);

        if (text[cursor] !== ',') break;

        cursor = skipWhitespace(cursor + 1);

      }

      if (!found) return null;

      start = found.start;

      end = found.end;

    } else return null;

  }

  return {start, end};

}

if (typeof module !== 'undefined' && module.exports) module.exports = {findJsonPathRange};

let sourceRenderedText=null,sourceRenderedPath=null;
/*
 * Unicode-code-point text diff for a classic browser script or Node.js.
 * Returns merged {type: 'equal' | 'delete' | 'insert', text} segments.
 * Memory is bounded independently of n*m: an exact short-text LCS table is
 * capped at 1,000,000 cells (~2 MiB); larger middles use bounded Myers.
 * If the edit-distance/work cap is exceeded, only the unmatched middle
 * degrades to one deletion plus one insertion. Shared ends stay precise.
 */

function diffText(before, after) {

  if (typeof before !== 'string' || typeof after !== 'string') {

    throw new TypeError('diffText expects two strings');

  }

  if (before === after) return before ? [{type: 'equal', text: before}] : [];

  const left = Array.from(before), right = Array.from(after);

  let prefix = 0;

  while (prefix < left.length && prefix < right.length && left[prefix] === right[prefix]) prefix++;

  let leftEnd = left.length, rightEnd = right.length;

  while (leftEnd > prefix && rightEnd > prefix && left[leftEnd - 1] === right[rightEnd - 1]) {

    leftEnd--;

    rightEnd--;

  }

  const a = left.slice(prefix, leftEnd), b = right.slice(prefix, rightEnd);

  const segments = [];

  function append(type, text) {

    if (!text) return;

    const last = segments[segments.length - 1];

    if (last && last.type === type) last.text += text;
    else segments.push({type, text});

  }

  append('equal', left.slice(0, prefix).join(''));

  if (!a.length) append('insert', b.join(''));
  else if (!b.length) append('delete', a.join(''));
  else {

    const MAX_CELLS = 1000000;

    if ((a.length + 1) * (b.length + 1) <= MAX_CELLS) {
      // The shorter LCS is necessarily below 1,000 with this cell cap,
      // so Uint16 is sufficient, even for a very rectangular table.

      const columns = b.length + 1;

      const table = new Uint16Array((a.length + 1) * columns);

      for (let i = a.length - 1; i >= 0; i--) {

        const row = i * columns, next = row + columns;

        for (let j = b.length - 1; j >= 0; j--) {

          table[row + j] = a[i] === b[j]
            ? table[next + j + 1] + 1
            : Math.max(table[next + j], table[row + j + 1]);

        }

      }
      // Buffer a run rather than concatenating one object per character.

      let runType = null, run = [];

      function emit(type, character) {

        if (runType !== type && run.length) {

          append(runType, run.join(''));

          run = [];

        }

        runType = type;

        run.push(character);

      }

      let i = 0, j = 0;

      while (i < a.length && j < b.length) {

        if (a[i] === b[j]) {
          emit('equal', a[i++]);
          j++;
        }
        else if (table[(i + 1) * columns + j] >= table[i * columns + j + 1]) emit('delete', a[i++]);
        else emit('insert', b[j++]);

      }

      while (i < a.length) emit('delete', a[i++]);

      while (j < b.length) emit('insert', b[j++]);

      if (run.length) append(runType, run.join(''));

    } else {

      const middle = boundedMyers(a, b);

      if (middle) for (const part of middle) append(part.type, part.text);
      else {

        Object.defineProperty(segments,'coarse',{value:true});

        append('delete', a.join(''));

        append('insert', b.join(''));

      }

    }

  }

  append('equal', left.slice(leftEnd).join(''));

  return segments;

  function boundedMyers(a, b) {

    const MAX_DISTANCE = 256, MAX_WORK = 2000000;

    const limit = Math.min(MAX_DISTANCE, a.length + b.length), offset = limit + 1;

    const frontier = new Int32Array(2 * limit + 3);

    frontier.fill(-1);

    frontier[offset + 1] = 0;

    const trace = [];

    let work = 0;

    for (let distance = 0; distance <= limit; distance++) {

      trace.push(frontier.slice());

      for (let k = -distance; k <= distance; k += 2) {

        if (++work > MAX_WORK) return null;

        const index = offset + k;

        let x = k === -distance || (k !== distance && frontier[index - 1] < frontier[index + 1])
          ? frontier[index + 1] : frontier[index - 1] + 1;

        let y = x - k;

        while (x < a.length && y < b.length && a[x] === b[y]) {

          if (++work > MAX_WORK) return null;

          x++;

          y++;

        }

        frontier[index] = x;

        if (x >= a.length && y >= b.length) {
          // Each snake becomes one segment; long equal runs do not allocate
          // one object per code point during reconstruction.

          const backwards = [];

          x = a.length;

          y = b.length;

          for (let d = distance; d >= 0; d--) {

            const previous = trace[d], diagonal = x - y;

            const previousK = diagonal === -d ||
              (diagonal !== d && previous[offset + diagonal - 1] < previous[offset + diagonal + 1])
              ? diagonal + 1 : diagonal - 1;

            const previousX = previous[offset + previousK], previousY = previousX - previousK;

            const snakeEnd = x;

            while (x > previousX && y > previousY) {
              x--;
              y--;
            }

            if (snakeEnd > x) backwards.push({type: 'equal', text: a.slice(x, snakeEnd).join('')});

            if (d === 0) break;

            if (x === previousX) backwards.push({type: 'insert', text: b[--y]});
            else backwards.push({type: 'delete', text: a[--x]});

          }

          return backwards.reverse();

        }

      }

    }

    return null;

  }

}

if (typeof module !== 'undefined' && module.exports) module.exports = {diffText};

let answerEditing=false,shiftTapArmed=false,swallowedSpace=false,activeAnswerId='answer',pairedQuestionEditing=false;
const heldShiftKeys=new Set();

let sourceModel=null,sourcePinned=false,sourceTimer,referenceData=null,referenceError='',referenceTicket=0,questionEditing=false;
let restoreSnapshot=null,cleanupContext=null,pendingCleanup=false;
const dismissedCleanups=new Set();

const sameJSON=(a,b)=>JSON.stringify(a)===JSON.stringify(b);

function sections(){
  const list=Array.isArray(model?.prediction)?model.prediction.map((s,i)=>({...s,__path:['prediction',i]})):[];
  if(Array.isArray(model?.review))list.push({type:'review',qa:model.review,__path:[]});
  return list
}

function currentQA(){
  return sections()[sectionIndex]?.qa?.[qaIndex]
}

function questionPair(section,index){
  return ['action','tactic','outcome'].includes(section?.type)&&section?.qa?.length===6?[index%3,index%3+3]:[index]
}
function visibleQuestionIndices(){return questionPair(sections()[sectionIndex],qaIndex)}
function slotIndex(paired=false){return visibleQuestionIndices()[paired?1:0]}
function slotQA(paired=false){return sections()[sectionIndex]?.qa?.[slotIndex(paired)]}
function slotPath(paired=false){
  return sections()[sectionIndex]?.type==='review'?['review',slotIndex(paired)]:['prediction',sectionIndex,'qa',slotIndex(paired)]
}
function navigationRefs(){
  return sections().flatMap((s,i)=>(s.qa||[]).flatMap((_,q)=>questionPair(s,q)[0]===q?[{s:i,q}]:[]))
}
function activateQuestion(index,fieldId){
  if(!Number.isInteger(index))return;
  qaIndex=index;activeAnswerId=fieldId;
  if(answerEditing)setAnswerEditing(true,false);
  controls();renderSource();renderReferences()
}

function currentPath(){
  const s=sections()[sectionIndex];
  return s?.type==='review'?['review',qaIndex]:['prediction',sectionIndex,'qa',qaIndex]
}

function atPath(object,path){
  return path.reduce((v,k)=>v?.[k],object)
}

function controls(){
  const enabled=!!doc&&!saving&&!loading&&!changingRoot&&!indexLoading;
  $('dataRoot').disabled=saving||loading||changingRoot||indexLoading;
  $('applyRoot').disabled=saving||loading||changingRoot||indexLoading;
  $('refresh').disabled=saving||loading||changingRoot||indexLoading;
  for(const id of ['save','sourceToggle'])$(id).disabled=!enabled;
  $('restoreSource').disabled=!enabled||!sourceModel||(!restoreSnapshot&&!changesBetween(sourceModel,model).length);
  $('restoreSource').textContent=restoreSnapshot?'撤销恢复':'恢复源 JSON';
  const qaChanges=sourceModel&&slotQA()?changesBetween(atPath(sourceModel,slotPath()),slotQA()):[];
  $('currentDiff').hidden=!qaChanges.length;
  $('currentDiff').disabled=!enabled;
  $('currentDiff').textContent=`本题改动 ${qaChanges.length}`;
  for(const id of ['format','reload','editor','applyRaw'])$(id).disabled=!enabled;
  $('jsonFiles').disabled=saving||loading||!$('jsonFiles').options.length;
  for(const el of document.querySelectorAll('#reviewFields textarea,#metadata input,#metadata textarea,#metadata select,#sectionSelect,#choices button,#pairedChoices button,#editQuestion,#pairedEditQuestion'))el.disabled=!enabled;
  const index=filtered.findIndex(r=>r.path===current);
  $('prevVideo').disabled=saving||loading||changingRoot||indexLoading||index<=0;
  $('nextVideo').disabled=saving||loading||changingRoot||indexLoading||index<0||index>=filtered.length-1;
  const all=navigationRefs(),pos=all.findIndex(r=>r.s===sectionIndex&&r.q===visibleQuestionIndices()[0]);
  $('prevQA').disabled=!enabled||pos<=0;
  $('nextQA').disabled=!enabled||pos<0;
  const pairedPage=visibleQuestionIndices().length===2;
  $('prevQA').textContent=pairedPage?'上一组（Q/⌫）':'上一题（Q/⌫）';
  $('nextQA').textContent=pos===all.length-1?'完成核对（Enter）':pairedPage?'下一组（Enter）':'下一题（Enter）';
  $('confirmSave').disabled=!enabled;
  const hasChanges=!sourceModel||changesBetween(sourceModel,model).length>0;
  $('confirmSave').textContent=!hasChanges&&doc?.target_exists?'检查已有新版（+）':(hasChanges?'保存并':'无改动，')+(index>=0&&index<filtered.length-1?'下一回合（+）':'完成（+）');
  $('cleanupDelete').disabled=saving||loading;
  $('keepSaved').disabled=saving||loading;
  const cutoff=sections()[sectionIndex]?.cutoff_seconds;
  for(const id of ['seekBefore','seekCutoff','seekAfter'])$(id).disabled=!enabled||!Number.isFinite(cutoff)||$('video').readyState<1;
  $('openReferences').disabled=!referenceData;
  const lower=slotQA(true),lowerChanges=sourceModel&&lower?changesBetween(atPath(sourceModel,slotPath(true)),lower):[];
  $('pairedCurrentDiff').hidden=!lowerChanges.length;
  $('pairedCurrentDiff').textContent=`本题改动 ${lowerChanges.length}`;
  $('pairedCurrentDiff').disabled=!enabled;
  $('zoomImage').disabled=!enabled||!$('images').querySelector('a img');
  for(const id of ['volumeDown','volumeUp','nudgeBack','nudgeForward'])$(id).disabled=!$('video').getAttribute('src')||$('video').readyState<1
}

function syncModel(){
  restoreSnapshot=null;
  let baseline;
  try{
    baseline=JSON.parse(original)
  }catch{}
  $('editor').value=sameJSON(model,baseline)?original:JSON.stringify(model,null,2)+'\n';
  editMessage(dirty()?'有未保存的修改，将保存为 '+doc.save_path:'内容未修改');
  controls();
  updateImageTime();
  renderSource();
  scheduleReferences();
  scheduleCompactReview()
}

function showMetadata(){
  $('metadata').replaceChildren();
  if(!model||typeof model!=='object')return;
  const s=sections()[sectionIndex];
  if(s&&s.type!=='review')for(const[k,v]of Object.entries(s))if(k!=='qa'&&k!=='__path')primitiveField(v,[...s.__path,k],$('metadata'));
  for(const[k,v]of Object.entries(model))if(k!=='prediction'&&k!=='review')primitiveField(v,[k],$('metadata'))
}

function parseChoices(text){
  if(typeof text!=='string')return null;
  const regex=/(?:^|\n)\s*([A-H])[.．、)）:：]\s*([^]*?)(?=\n\s*[A-H][.．、)）:：]|$)/g;
  const matches=[...text.matchAll(regex)];
  if(matches.length<2||new Set(matches.map(m=>m[1])).size!==matches.length)return null;
  return{stem:text.slice(0,matches[0].index).trim(),options:matches.map(m=>({letter:m[1],text:m[2].trim()}))}
}

function answerLetter(text,options){
  const value=String(text??'').trim(),m=value.match(/^([A-H])(?:[.．、)）:：\s]|$)/);
  if(m&&options.some(o=>o.letter===m[1]))return m[1];
  return options.find(o=>o.text===value)?.letter||null
}

function renderChoices(paired=false){
  const el=id=>$(paired?'paired'+id[0].toUpperCase()+id.slice(1):id);
  const qa=slotQA(paired),parsed=parseChoices(qa?.question),selected=parsed?answerLetter(qa?.answer,parsed.options):null,baseline=atPath(sourceModel,slotPath(paired)),originLetter=parsed?answerLetter(baseline?.answer,parsed.options):null;
  const editing=paired?pairedQuestionEditing:questionEditing;
  el('choices').replaceChildren();
  el('editQuestion').hidden=!parsed;
  el('editQuestion').textContent=editing?'返回选项':'编辑题目';
  el('question').hidden=!!parsed&&!editing;
  el('questionStem').hidden=!parsed||editing;
  el('choices').hidden=!parsed||editing;
  el('questionStem').textContent=parsed?.stem||'';
  el('choiceNote').textContent=parsed?'点选答案；原选项或下一页保留原值':paired?'Shift 编辑答案':visibleQuestionIndices().length===2?'Tab 编辑答案':'Tab / Shift 编辑答案';
  if(!parsed)return;
  for(const option of parsed.options){
    const b=document.createElement('button');
    b.className='choice';b.type='button';
    b.setAttribute('role','radio');b.setAttribute('aria-checked',String(selected===option.letter));
    const label=document.createElement('span');label.textContent=option.letter+'. '+option.text;b.append(label);
    if(option.letter===originLetter){const tag=document.createElement('small');tag.textContent='原答案';b.append(tag)}
    b.onclick=()=>{
      activateQuestion(slotIndex(paired),paired?'pairedAnswer':'answer');
      const qa=slotQA(paired),targetAnswer=option.letter===originLetter?baseline.answer:option.letter+'. '+option.text;
      if(qa.answer===targetAnswer)return;
      qa.answer=targetAnswer;el('answer').value=qa.answer;
      syncModel();cleanEditedAnswers();renderChoices(paired)
    };
    el('choices').append(b)
  }
}

function renderReview(){
  const ss=sections(),refs=questionRefs();
  sectionIndex=Math.min(sectionIndex,Math.max(0,ss.length-1));
  const s=ss[sectionIndex];
  qaIndex=Math.min(qaIndex,Math.max(0,(s?.qa?.length||0)-1));
  $('sectionSelect').replaceChildren();
  ss.forEach((s,i)=>$('sectionSelect').add(new Option(s.type==='review'?'复盘':typeNames[s.type]||s.type||`阶段 ${i+1}`,i)));
  $('sectionSelect').value=String(sectionIndex);
  const qa=s?.qa?.[qaIndex],hasQA=!!qa;
  $('reviewFields').hidden=!hasQA;
  $('reviewEmpty').hidden=hasQA;
  if(!hasQA)$('reviewEmpty').textContent=doc?'当前文件没有可逐题编辑的问答，可通过“更多”查看原始 JSON。':'从左侧选择回合，开始逐题核对。';
  panelLayout.pair=null;
  pairedQuestionEditing=false;
  const indices=visibleQuestionIndices(),paired=indices.length===2;
  activeAnswerId=paired&&qaIndex===indices[1]?'pairedAnswer':'answer';
  $('reviewFields').classList.toggle('paired-view',paired);
  $('pairedQA').hidden=!paired;$('answerSplitter').hidden=!paired;
  const upper=slotQA(),lower=slotQA(true);
  $('question').value=upper?.question??'';$('answer').value=upper?.answer??'';
  $('pairedQuestion').value=lower?.question??'';$('pairedAnswer').value=lower?.answer??'';
  $('questionLabel').textContent='问题 · 第 '+(indices[0]+1)+' 题';
  $('answerLabel').textContent='答案 · 第 '+(indices[0]+1)+(paired?' 题（Tab）':' 题（Tab / Shift）');
  $('pairedQuestionLabel').textContent=paired?'问题 · 第 '+(indices[1]+1)+' 题':'问题';
  $('pairedAnswerLabel').textContent=paired?'答案 · 第 '+(indices[1]+1)+' 题（Shift）':'答案';
  $('answer').setAttribute('aria-keyshortcuts',paired?'Tab':'Tab Shift');
  $('pairedAnswer').setAttribute('aria-keyshortcuts','Shift');
  $('answerLabel').parentElement.title='Tab 进入或退出第一个答案编辑；单题页也可用 Shift';
  $('answerSplitter').setAttribute('aria-label',paired?'上下两组问答高度':'答案和参考区高度');
  $('answerSplitter').title=paired?'拖动调整上下两组问答的高度，双击恢复自动高度':'拖动调整答案和参考区高度，双击恢复自动高度';
  setAnswerEditing(false,false);
  $('position').textContent=paired?`${indices[0]+1}＋${indices[1]+1} / 6`:`${hasQA?qaIndex+1:0} / ${s?.qa?.length||0}`;
  $('totalPosition').textContent=`总进度 ${Math.max(0,refs.findIndex(r=>r.s===sectionIndex&&r.q===qaIndex)+1)} / ${refs.length}`;
  showMetadata();
  showImage(s?.image||(s?.type==='review'?'outcome_boxes.jpg':undefined));
  renderChoices();renderChoices(true);
  renderSource();
  renderReferences();
  controls()
}

async function loadJSON(path){
  const ticket=++jsonSelection;
  loading=true;
  controls();
  editMessage('正在读取 JSON…');
  try{
    const data=await request('/api/json?path='+encodeURIComponent(path));
    if(ticket!==jsonSelection)return;
    doc=data;
    restoreSnapshot=null;
    original=data.text.replace(/\r\n?/g,'\n');
    $('editor').value=original;
    model=JSON.parse(data.text);
    try{
      sourceModel=data.source_available?JSON.parse(data.source_text):null
    }catch{
      sourceModel=null
    }
    questionEditing=false;
    sectionIndex=0;
    qaIndex=0;
    showPath();
    renderReview();
    editMessage('已读取。修改将保存为 '+doc.save_path+'。')
  }catch(e){
    if(ticket!==jsonSelection)return;
    doc=null;
    model=null;
    sourceModel=null;
    $('editor').value='';
    renderReview();
    editMessage('读取失败：'+e.message,'error')
  }finally{
    if(ticket===jsonSelection){
      loading=false;
      controls();
      maybePromptCleanup()
    }
  }
}

async function assets(path,ticket){
  try{
    const data=await request('/api/assets?path='+encodeURIComponent(path));
    if(ticket!==selection)return;
    attachments=data;
    imageTabs();
    $('jsonFiles').replaceChildren();
    data.json.sort((a,b)=>Number(b.name==='qa-new.json')-Number(a.name==='qa-new.json')||Number(b.name==='qa.json')-Number(a.name==='qa.json')||a.name.localeCompare(b.name));
    for(const item of data.json)$('jsonFiles').add(new Option(item.name,item.path));
    if(data.json.length)await loadJSON(data.json[0].path);else{
      showPath();
      renderReview();
      editMessage('此回合没有 JSON 文件。')
    }
  }catch(e){
    if(ticket===selection)editMessage('附件加载失败：'+e.message,'error')
  }finally{
    if(ticket===selection){
      loading=false;
      controls()
    }
  }
}

async function play(path){
  if(saving||loading||changingRoot||indexLoading)return false;
  cleanEditedAnswers();
  if(dirty()&&!confirm('当前回合有未保存的修改，是否放弃并切换？'))return false;
  const ticket=++selection;
  ++jsonSelection;
  current=path;
  doc=null;
  model=null;
  sourceModel=null;
  restoreSnapshot=null;
  cleanupContext=null;
  pendingCleanup=false;
  referenceData=null;
  referenceError='';
  original='';
  attachments={images:[],json:[]};
  questionEditing=false;
  setAnswerEditing(false,false);
  $('editor').value='';
  $('jsonFiles').replaceChildren();
  showPath();
  renderReview();
  draw();
  $('title').textContent=path;
  $('title').title=path;
  $('video').pause();
  $('video').removeAttribute('src');
  $('video').load();
  loading=true;
  controls();
  const assetTask=assets(path,ticket);
  loadReferences(path,ticket);
  try{
    const data=await request('/api/prepare?path='+encodeURIComponent(path));
    if(ticket!==selection)return true;
    $('video').src=data.url;
    $('video').load();
    $('status').textContent='视频已就绪，点击播放'
  }catch(e){
    if(ticket===selection)$('status').textContent='无法打开视频：'+e.message
  }
  await assetTask;
  return true
}

function stepQA(delta){
  cleanEditedAnswers();
  const refs=navigationRefs(),i=refs.findIndex(r=>r.s===sectionIndex&&r.q===visibleQuestionIndices()[0]),r=refs[i+delta];
  if(r){
    sectionIndex=r.s;
    qaIndex=r.q;
    questionEditing=false;
    renderReview()
  }else if(delta>0&&i===refs.length-1)openDiff()
}

function openSource(){
  clearTimeout(sourceTimer);
  document.body.classList.add('source-open');
  $('sourceDrawer').inert=false;
  renderSource({forceLocate:true})
}

function closeSource(force=false){
  if(sourcePinned&&!force)return;
  document.body.classList.remove('source-open');
  $('sourceDrawer').inert=true
}

$('sourceToggle').onmouseenter=openSource;
$('sourceToggle').onclick=openSource;
$('sourceEdge').onmouseenter=openSource;
$('sourceEdge').onclick=openSource;
$('sourceDrawer').onmouseenter=()=>clearTimeout(sourceTimer);
$('sourceDrawer').onmouseleave=()=>sourceTimer=setTimeout(()=>closeSource(),220);
$('sourceToggle').onmouseleave=()=>sourceTimer=setTimeout(()=>closeSource(),220);
$('sourcePin').onclick=()=>{
  sourcePinned=!sourcePinned;
  $('sourcePin').textContent=sourcePinned?'取消固定':'固定';
  $('sourcePin').setAttribute('aria-pressed',String(sourcePinned));
  if(sourcePinned)openSource()
};
$('closeSource').onclick=()=>{
  sourcePinned=false;
  $('sourcePin').textContent='固定';
  $('sourcePin').setAttribute('aria-pressed','false');
  closeSource(true)
};
$('sourceLocate').onclick=()=>renderSource({forceLocate:true});

function changesBetween(before,after,path=[]){
  if(before===after)return[];
  if(before&&after&&typeof before==='object'&&typeof after==='object'&&Array.isArray(before)===Array.isArray(after)){
    return [...new Set([...Object.keys(before),...Object.keys(after)])].flatMap(k=>changesBetween(before[k],after[k],[...path,k]))
  }
  return[{path,before,after}]
}

function pathLabel(path){
  let text=path.join(' / ');
  if(path[0]==='prediction'){
    const s=sourceModel?.prediction?.[Number(path[1])]||model?.prediction?.[Number(path[1])];
    text=(typeNames[s?.type]||`阶段 ${Number(path[1])+1}`)+(path[2]==='qa'?` · 第 ${Number(path[3])+1} 题 · `: ' · ')+path.slice(path[2]==='qa'?4:2).join(' / ')
  }else if(path[0]==='review')text=`复盘 · 第 ${Number(path[1])+1} 题 · `+path.slice(2).join(' / ');
  return text.replace(/question/g,'问题').replace(/answer/g,'答案')
}

function displayValue(value){
  return value===undefined?'（不存在）':typeof value==='string'?value:JSON.stringify(value,null,2)
}

const currentDiffButton=document.createElement('button');
currentDiffButton.id='currentDiff';
currentDiffButton.type='button';
currentDiffButton.hidden=true;
document.querySelector('.question-tools').prepend(currentDiffButton);
currentDiffButton.onclick=()=>{activateQuestion(slotIndex(),'answer');openDiff(slotPath())};

function sourceStateKey(){
  return doc?[doc.root_id,doc.save_path,doc.save_version,doc.source_version].join('|'):''
}

function restoreSource(){
  if(!doc||!sourceModel||saving||loading)return;
  setAnswerEditing(false,false);
  if(restoreSnapshot){
    const snapshot=restoreSnapshot;
    restoreSnapshot=null;
    $('editor').value=snapshot.text;
    try{model=JSON.parse(snapshot.text)}catch{model=snapshot.model}
    sectionIndex=snapshot.section;
    qaIndex=snapshot.question;
    editMessage('已撤销恢复，原有编辑已找回。');
  }else{
    restoreSnapshot={text:$('editor').value,model:structuredClone(model),section:sectionIndex,question:qaIndex};
    $('editor').value=doc.source_text.replace(/\r\n?/g,'\n');
    model=JSON.parse(doc.source_text);
    editMessage('已恢复整个回合的源 JSON，尚未写入磁盘；可点击“撤销恢复”。');
  }
  questionEditing=false;
  renderReview();
}
$('restoreSource').onclick=restoreSource;
$('save').onclick=()=>openDiff();
$('nextQA').onclick=()=>stepQA(1);
$('prevQA').onclick=()=>stepQA(-1);
$('sectionSelect').onchange=()=>{
  cleanEditedAnswers();
  sectionIndex=Number($('sectionSelect').value);
  qaIndex=0;
  questionEditing=false;
  renderReview()
};
$('editQuestion').onclick=()=>{
  activateQuestion(slotIndex(),'answer');
  questionEditing=!questionEditing;
  renderChoices();
  controls();
  scheduleCompactReview()
};

for(const paired of [false,true]){
  const prefix=paired?'paired':'',field=id=>$(paired?prefix+id[0].toUpperCase()+id.slice(1):id);
  field('questionArea').addEventListener('pointerdown',()=>activateQuestion(slotIndex(paired),paired?'pairedAnswer':'answer'));
  field('question').addEventListener('focus',()=>activateQuestion(slotIndex(paired),paired?'pairedAnswer':'answer'));
  field('question').oninput=()=>{slotQA(paired).question=field('question').value;syncModel()};
  field('question').onblur=()=>{if(!(paired?pairedQuestionEditing:questionEditing))renderChoices(paired)};
  field('answer').oninput=()=>{slotQA(paired).answer=field('answer').value;syncModel();renderChoices(paired)};
}
$('pairedEditQuestion').onclick=()=>{
  activateQuestion(slotIndex(true),'pairedAnswer');pairedQuestionEditing=!pairedQuestionEditing;
  renderChoices(true);controls();scheduleCompactReview()
};
$('pairedCurrentDiff').onclick=()=>{activateQuestion(slotIndex(true),'pairedAnswer');openDiff(currentPath())};

function seekOffset(delta){
  const cutoff=sections()[sectionIndex]?.cutoff_seconds,video=$('video');
  if(!Number.isFinite(cutoff)||video.readyState<1)return;
  const end=Number.isFinite(video.duration)?Math.max(0,video.duration-0.05):Infinity;
  video.currentTime=Math.min(end,Math.max(0,cutoff+delta));
  startVideo()
}

$('seekBefore').onclick=()=>seekOffset(-2);
$('seekCutoff').onclick=()=>seekOffset(0);
$('seekAfter').onclick=()=>seekOffset(2);

function normalizeName(text){
  return String(text).normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim().replace(/\s+/g,' ')
}

function matchedPlayers(text,players){
  const normalized=' '+normalizeName(text)+' ',names=players.map(player=>{
    const full=normalizeName(player),parts=full.split(' ');
    while(['jr','sr','ii','iii','iv'].includes(parts.at(-1)))parts.pop();
    return{player,full,surname:parts.length>1?parts.at(-1):null}
  });
  return names.filter(n=>normalized.includes(' '+n.full+' ')||normalized.includes(' '+n.full.replace(/ /g,'')+' ')||(n.surname&&names.filter(x=>x.surname===n.surname).length===1&&normalized.includes(' '+n.surname+' '))).map(n=>n.player)
}

async function loadReferences(path,ticket){
  const number=++referenceTicket;
  try{
    const data=await request('/api/references?path='+encodeURIComponent(path));
    if(ticket!==selection||number!==referenceTicket)return;
    referenceData=data;
    referenceError=data.error||''
  }catch(e){
    if(ticket!==selection||number!==referenceTicket)return;
    referenceError=e.message;
    referenceData=null
  }
  renderReferences();
  controls()
}

let referenceDebounce;
function scheduleReferences(){
  clearTimeout(referenceDebounce);
  referenceDebounce=setTimeout(renderReferences,180)
}

const eventZh={Dribble:'运球',PassBall:'传球','3ptShot':'三分投篮','2ptShot':'两分投篮',Layup:'上篮',Rebound:'篮板',Dunk:'扣篮',Block:'封盖',Steal:'抢断',Screen:'掩护',Turnover:'失误',Hold:'持球',HandOff:'手递手传球',PutBack:'补篮',InboundPass:'界外发球'},resultZh={success:'成功',missed:'未命中',made:'命中',offensive:'进攻篮板',defensive:'防守篮板',turnover:'失误',fouled:'被犯规'};

function referenceNode(record){
  const el=document.createElement('div');
  el.className='reference';
  const name=document.createElement('strong');
  name.textContent=record.player;
  el.append(name,document.createTextNode(' · '+record.time+' · '+(eventZh[record.classification]?`${eventZh[record.classification]} (${record.classification})`:record.classification)+' · '+(resultZh[record.result]||record.result)));
  if(record.caption){
    const caption=document.createElement('div');
    caption.textContent=record.caption;
    el.append(caption)
  }
  const source=document.createElement('div');
  source.className='citation';
  source.textContent=`${referenceData.file} · ${record.sheet} · 第 ${record.row} 行 · 时间为表格原始标记`;
  source.title=JSON.stringify(record.raw,null,2);
  el.append(source);
  return el
}

function renderReferences(){

  if(!$('referenceList'))return;

  const qa=currentQA(),text=visibleQuestionIndices().map(i=>sections()[sectionIndex]?.qa?.[i]).filter(Boolean).map(q=>q.question+'\n'+q.answer).join('\n'),names=referenceData?matchedPlayers(text,referenceData.players||[]):[],records=(referenceData?.records||[]).filter(r=>names.includes(r.player));

  $('referenceList').replaceChildren();
  $('allReferences').replaceChildren();

  const empty=!!referenceData&&!referenceError&&!records.length;

  $('reviewFields').classList.toggle('no-references',!records.length);
  $('reviewFields').classList.toggle('has-references',!!records.length);
  $('refs').classList.toggle('empty-signature',empty);
  $('authorSignature').hidden=!empty;

  $('referenceSource').textContent=(referenceData?.path||referenceData?.file||'')+' · '+(referenceData?.time_note||'');

  if(records.length){
    for(const record of records){
      $('referenceList').append(referenceNode(record));
      $('allReferences').append(referenceNode(record))
    }
  }
  else{
    const message=referenceError?'Excel 参考读取失败：'+referenceError:!referenceData?'正在读取同目录 Excel…':'当前问题与答案未匹配到表内人名。';
    $('referenceList').textContent=message;
    $('allReferences').textContent=message
  }

  controls();
  scheduleCompactReview();

}

$('openReferences').onclick=()=>$('referencesDialog').showModal();

function applyRaw(){
  try{
    model=JSON.parse($('editor').value);
    questionEditing=false;
    renderReview();
    editMessage(dirty()?'有未保存的修改':'内容未修改');
    controls();
    return true
  }catch(e){
    editMessage('JSON 格式错误：'+e.message,'error');
    return false
  }
}

controls();
load();

$('editor').oninput=()=>{
  restoreSnapshot=null;
  try{
    model=JSON.parse($('editor').value);
    questionEditing=false;
    renderReview();
    editMessage(dirty()?'有未保存的修改':'内容未修改')
  }catch(e){
    model=null;
    $('reviewFields').hidden=true;
    $('reviewEmpty').hidden=false;
    $('reviewEmpty').textContent='请先修正 JSON 格式，再继续逐题核对。';
    editMessage('JSON 格式错误：'+e.message,'error')
  }
  controls()
};

$('format').onclick=()=>{
  if(applyRaw())syncModel()
};

$('applyRaw').onclick=()=>{
  if(applyRaw())$('rawDialog').close()
};

$('nextQA').title='Enter 切换下一组问答；最后一页打开改动对照';

$('nextQA').setAttribute('aria-keyshortcuts','Enter');


function syncPlaybackControl(){
  const video=$('video'),button=$('playPause');
  button.textContent=video.paused||video.ended?'播放（空格）':'暂停（空格）';
  button.disabled=!video.getAttribute('src')||!!video.error;
  button.title='空格播放 / 暂停；编辑文本时空格正常输入';
  button.setAttribute('aria-pressed',String(!video.paused&&!video.ended))
}

function startVideo(){
  const video=$('video');
  if(!video.getAttribute('src')||video.error)return;
  const source=video.getAttribute('src');
  try{
    const pending=video.play();
    if(pending)pending.catch(error=>{
      if(error.name!=='AbortError'&&video.getAttribute('src')===source)$('status').textContent='无法开始播放：'+error.message;
      syncPlaybackControl()
    })
  }catch(error){
    $('status').textContent='无法开始播放：'+error.message
  }
  syncPlaybackControl()
}

function toggleVideo(){
  const video=$('video');
  if(video.paused||video.ended)startVideo();else video.pause()
}

$('playPause').onclick=toggleVideo;

for(const eventName of ['play','pause','ended','loadstart','emptied','error'])$('video').addEventListener(eventName,syncPlaybackControl);

$('video').addEventListener('loadedmetadata',()=>{
  syncPlaybackControl();
  controls()
});



syncPlaybackControl();

function openCurrentImage(){
  const link=$('images').querySelector('a');
  if(link&&link.querySelector('img'))link.click()
}

$('zoomImage').onclick=openCurrentImage;

for(const[id,key]of [['prevQA','Q'],['seekCutoff','J'],['seekBefore','A'],['seekAfter','D'],['zoomImage','X']]){

  $(id).setAttribute('aria-keyshortcuts',key);

  $(id).title=({prevQA:'Q 上一题',seekCutoff:'J 跳到当前阶段截断点并播放',seekBefore:'A 跳到截断点前两秒并播放',seekAfter:'D 跳到截断点后两秒并播放',zoomImage:'X 放大当前标注图'})[id];

}

const letterShortcuts={q:'prevQA',j:'seekCutoff',a:'seekBefore',d:'seekAfter',x:'zoomImage'};


$('confirmSave').onclick=async()=>{

  if(saving||!doc)return;

  if(cleanEditedAnswers()){
    if($('diffDialog').open)$('diffDialog').close();
    openDiff();
    return
  }

  try{
    JSON.parse($('editor').value)
  }catch(e){
    editMessage('JSON 格式错误，未保存：'+e.message,'error');
    return
  }

  for(const el of document.querySelectorAll('#metadata input,#metadata textarea'))if(!el.checkValidity()){
    $('diffDialog').close();
    $('metadataDialog').showModal();
    el.reportValidity();
    return
  }

  saving=true;
  controls();
  editMessage('正在核对并处理…');
  let result=null;

  try{

    const data=await request('/api/json',{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Token':csrf},body:JSON.stringify({root_id:doc.root_id,path:doc.path,version:doc.version,save_version:doc.save_version,immutable_source_path:doc.immutable_source_path,source_version:doc.source_version,text:$('editor').value})});

    applyDocumentSnapshot(data);
    result=data;
    $('diffDialog').close();

  }catch(e){
    editMessage('保存失败：'+e.message+'\n当前编辑内容已保留。','error');
    $('diffSummary').textContent='保存失败：'+e.message+'。当前编辑内容已保留，请返回检查。'
  }
  finally{
    saving=false;
    controls()
  }

  if(result){
    if(result.skipped&&result.cleanup_required)showCleanup(true);
    else await completeRound(result.skipped?'与源文件一致，未生成或覆盖新版。':'已保存 '+result.path+'。');
  }

};

function applyDocumentSnapshot(data){
  doc={...doc,...data};
  original=doc.text.replace(/\r\n?/g,'\n');
  $('editor').value=original;
  model=JSON.parse(original);
  restoreSnapshot=null;
  if(doc.source_available)sourceModel=JSON.parse(doc.source_text);
  if(data.deleted){
    for(const option of [...$('jsonFiles').options])if(option.value===data.deleted_path)option.remove();
  }
  if(![...$('jsonFiles').options].some(o=>o.value===doc.path))$('jsonFiles').add(new Option(doc.path.split('/').at(-1),doc.path));
  $('jsonFiles').value=doc.path;
  showPath();
  renderReview();
}

async function completeRound(message){
  const index=filtered.findIndex(r=>r.path===current),next=filtered[index+1];
  if(index>=0&&next&&await play(next.path))editMessage(message+' 已进入下一回合。','success');
  else editMessage(message+' 当前列表核对完成。','success');
}

function maybePromptCleanup(){
  if(dirty()){
    pendingCleanup=false;
    return;
  }
  if(!doc?.source_available||!doc.target_exists||doc.saved_matches_source!==true||dismissedCleanups.has(sourceStateKey()))return;
  if(loading||saving||document.querySelector('dialog[open]')){
    pendingCleanup=true;
    return;
  }
  showCleanup(false);
}

function showCleanup(advance){
  if(!doc?.target_exists||doc.saved_text==null)return;
  pendingCleanup=false;
  const saved=JSON.parse(doc.saved_text),changes=changesBetween(sourceModel,saved);
  cleanupContext={advance,key:sourceStateKey(),differs:changes.length>0};
  $('cleanupError').textContent='';
  $('cleanupSummary').textContent=changes.length?`当前页面与源 JSON 一致，但磁盘已有新版仍有 ${changes.length} 处字段改动。请查看下方旧版差异，选择保留，或备份后删除这些改动。`:'已有 qa-new.json 与源 JSON 内容相同（仅排版不同也视为相同）。可备份后删除这个重复文件。';
  $('cleanupPath').textContent='源文件：'+doc.immutable_source_path+'　｜　已有新版：'+doc.save_path+'。删除前会自动备份，源文件保留。';
  $('cleanupChanges').replaceChildren();
  renderChangeCards($('cleanupChanges'),changes,{navigable:false,after:saved});
  $('cleanupDelete').textContent=changes.length?'备份并删除旧改动（+）':'备份并删除重复新版（+）';
  const index=filtered.findIndex(r=>r.path===current);
  $('keepSaved').textContent=advance?'保留已有新版，'+(filtered[index+1]?'继续下一回合':'完成核对'):'保留已有新版';
  $('cleanupDialog').showModal();
  controls();
}

$('keepSaved').onclick=async()=>{
  if(saving||!cleanupContext)return;
  const {advance,key}=cleanupContext;
  dismissedCleanups.add(key);
  cleanupContext=null;
  $('cleanupDialog').close();
  if(advance)await completeRound('本次无改动；已按选择保留磁盘上的已有新版。');
  else editMessage('已保留已有新版。');
};

$('cleanupDelete').onclick=async()=>{
  if(saving||!doc||!cleanupContext)return;
  const {advance,key,differs}=cleanupContext;
  saving=true;
  controls();
  try{
    const data=await request('/api/json/cleanup',{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Token':csrf},body:JSON.stringify({root_id:doc.root_id,path:doc.path,version:doc.version,save_version:doc.save_version,immutable_source_path:doc.immutable_source_path,source_version:doc.source_version,confirm_delete:true,discard_saved_changes:differs})});
    dismissedCleanups.add(key);
    applyDocumentSnapshot(data);
    cleanupContext=null;
    $('cleanupDialog').close();
    saving=false;
    controls();
    const message='已备份并删除 '+data.deleted_path+'，源文件保留。';
    if(advance)await completeRound(message);
    else editMessage(message,'success');
  }catch(e){
    $('cleanupError').textContent='未删除：'+e.message+'。请返回编辑，重新读取后再核对。';
  }finally{
    saving=false;
    controls();
  }
};

for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('close',()=>{
  if(dialog.id==='cleanupDialog'&&cleanupContext){
    dismissedCleanups.add(cleanupContext.key);
    cleanupContext=null;
  }
  if(pendingCleanup)queueMicrotask(maybePromptCleanup);
});

function adjustVolume(delta){
  const video=$('video');
  if(video.readyState<1)return;
  video.volume=Math.max(0,Math.min(1,Math.round((video.volume+delta)*100)/100));
  if(delta>0)video.muted=false;
  syncFineControls()
}

function nudgeVideo(delta){
  const video=$('video');
  if(video.readyState<1)return;
  const end=Number.isFinite(video.duration)?Math.max(0,video.duration-0.001):Infinity;
  video.currentTime=Math.max(0,Math.min(end,video.currentTime+delta))
}

function syncFineControls(){
  const video=$('video'),percent=Math.round((video.muted?0:video.volume)*100);
  $('volumeUp').title='↑ / 小键盘8：音量增加5%；当前 '+percent+'%';
  $('volumeDown').title='↓ / 小键盘2：音量减少5%；当前 '+percent+'%'
}

$('volumeUp').onclick=()=>adjustVolume(0.05);
$('volumeDown').onclick=()=>adjustVolume(-0.05);
$('nudgeBack').onclick=()=>nudgeVideo(-0.3);
$('nudgeForward').onclick=()=>nudgeVideo(0.3);

for(const[id,key]of [['volumeUp','ArrowUp'],['volumeDown','ArrowDown'],['nudgeBack','ArrowLeft'],['nudgeForward','ArrowRight']])$(id).setAttribute('aria-keyshortcuts',key);

$('nudgeBack').title='← / 小键盘4：相对当前时间后退0.3秒，保持播放/暂停状态';
$('nudgeForward').title='→ / 小键盘6：相对当前时间前进0.3秒，保持播放/暂停状态';

$('video').addEventListener('volumechange',syncFineControls);
syncFineControls();

const directionKeys={ArrowUp:'volumeUp',ArrowDown:'volumeDown',ArrowLeft:'nudgeBack',ArrowRight:'nudgeForward'},numpadDirections={Numpad8:'volumeUp',Numpad2:'volumeDown',Numpad4:'nudgeBack',Numpad6:'nudgeForward'};


function setAnswerEditing(enabled,moveFocus=true){
  if(!enabled)cleanEditedAnswers();
  answerEditing=!!enabled&&!!doc&&!saving&&!loading;
  document.body.classList.toggle('answer-editing',answerEditing);
  for(const paired of [false,true]){
    const id=paired?'pairedAnswer':'answer',editing=answerEditing&&activeAnswerId===id;
    $(id).classList.toggle('is-editing',editing);
    $(paired?'pairedAnswerModeNotice':'answerModeNotice').hidden=!editing;
    $(paired?'pairedChoiceNote':'choiceNote').hidden=editing;
  }
  const field=$(activeAnswerId);
  if(answerEditing&&moveFocus){field.focus({preventScroll:true});const end=field.value.length;field.setSelectionRange(end,end)}
  else if(!answerEditing&&['answer','pairedAnswer'].includes(document.activeElement?.id)){
    document.activeElement.blur();
    if(moveFocus){$('title').tabIndex=-1;$('title').focus({preventScroll:true})}
  }
}
function toggleAnswerSlot(paired){
  const lower=paired&&visibleQuestionIndices().length===2,id=lower?'pairedAnswer':'answer';
  if(!doc||saving||loading||!slotQA(lower))return;
  if(answerEditing&&activeAnswerId===id){setAnswerEditing(false,true);return}
  cleanEditedAnswers();
  activateQuestion(slotIndex(lower),id);
  setAnswerEditing(true,true)
}
for(const paired of [false,true]){
  const id=paired?'pairedAnswer':'answer';
  $(id).addEventListener('focus',()=>{
    activateQuestion(slotIndex(paired),id);setAnswerEditing(true,false)
  })
}

function keyboardAction(event){

  if(event.key==='+'||event.code==='NumpadAdd')return'plus';

  if(event.key===' '||event.code==='Space')return'playPause';

  if(event.key==='Enter')return'nextQA';

  if(event.key==='Backspace')return'prevQA';

  if(['[','【'].includes(event.key)||event.code==='BracketLeft')return'prevVideo';

  if([']','】'].includes(event.key)||event.code==='BracketRight')return'nextVideo';

  return directionKeys[event.key]||numpadDirections[event.code]||letterShortcuts[event.key.toLowerCase()]||null;

}

for(const[id,key,label]of [['prevVideo','[','上一回合（【）'],['nextVideo',']','下一回合（】）']]){
  $(id).textContent=label;
  $(id).setAttribute('aria-keyshortcuts',key);
  $(id).title=label+'；兼容英文方括号'
}

document.addEventListener('keydown',event=>{

  // A focused splitter owns its arrow keys, including while editing an answer.
  if(event.target instanceof Element&&event.target.closest('[role="separator"]'))return;

  if(event.key==='Shift'){
    if(!event.repeat){
      const target=event.target instanceof Element?event.target:null;
      const otherInput=target?.closest('input,select,textarea,[contenteditable="true"],[role="textbox"]')&&!['answer','pairedAnswer'].includes(target?.id);
      shiftTapArmed=heldShiftKeys.size===0&&!otherInput;
      heldShiftKeys.add(event.code)
    }
    return
  }

  shiftTapArmed=false;

  if(event.isComposing||event.ctrlKey||event.altKey||event.metaKey)return;

  if(event.key==='Tab'&&!event.shiftKey&&!document.querySelector('dialog[open]')){
    const target=event.target instanceof Element?event.target:null;
    const otherInput=target?.closest('input,select,textarea,[contenteditable="true"],[role="textbox"]')&&!['answer','pairedAnswer'].includes(target?.id);
    if(doc&&!saving&&!loading&&!otherInput){
      event.preventDefault();event.stopPropagation();
      if(!event.repeat)toggleAnswerSlot(false);
      return
    }
  }

  const action=keyboardAction(event);
  if(!action)return;

  const target=event.target instanceof Element?event.target:null;

  const editable=target?.isContentEditable||target?.closest('textarea,input,select,[contenteditable="true"],[role="textbox"]');

  const inAnswer=target===$('answer')||target===$('pairedAnswer'),dialog=document.querySelector('dialog[open]');

  if(editable&&!(inAnswer&&answerEditing&&event.shiftKey))return;

  if(dialog&&!(action==='plus'&&['diffDialog','cleanupDialog'].includes(dialog.id)))return;

  if(answerEditing&&!event.shiftKey){
    if(!editable){
      event.preventDefault();
      event.stopPropagation();
      if(action==='playPause')swallowedSpace=true
    }
    return
  }

  let button=action==='plus'?(dialog?$(dialog.id==='cleanupDialog'?'cleanupDelete':'confirmSave'):$('save')):$(action);

  if(!button||button.disabled){
    if(event.key==='Backspace'){
      event.preventDefault();
      event.stopPropagation()
    }
    return;
  }
  // Enter on other ordinary buttons keeps their native activation outside answer editing.

  if(action==='nextQA'&&target?.closest('button,a,summary')&&!target.closest('#nextQA,[role="radio"]')&&!answerEditing)return;

  event.preventDefault();
  event.stopPropagation();

  if(action==='playPause')swallowedSpace=true;

  if(event.repeat&&!['volumeUp','volumeDown','nudgeBack','nudgeForward'].includes(action))return;

  button.click();

},true);

document.addEventListener('keyup',event=>{

  if(event.key==='Shift'){

    heldShiftKeys.delete(event.code);
    if(heldShiftKeys.size){
      shiftTapArmed=false;
      return
    }

    const toggle=shiftTapArmed;
    shiftTapArmed=false;

    if(toggle&&!event.isComposing&&!event.ctrlKey&&!event.altKey&&!event.metaKey&&!document.querySelector('dialog[open]')){
      event.preventDefault();
      toggleAnswerSlot(true)
    }

  }

  if((event.key===' '||event.code==='Space')&&swallowedSpace){
    event.preventDefault();
    event.stopPropagation();
    swallowedSpace=false
  }

},true);

document.addEventListener('pointerdown',event=>{
  if(event.shiftKey)shiftTapArmed=false
},true);

window.addEventListener('blur',()=>{
  shiftTapArmed=false;
  swallowedSpace=false;
  heldShiftKeys.clear()
});

document.addEventListener('visibilitychange',()=>{
  if(document.hidden){
    shiftTapArmed=false;
    heldShiftKeys.clear();
    swallowedSpace=false
  }
});

function diffChunks(parts){
  const groups=[];
  let current=null;
  for(const part of parts){
    if(part.type==='equal'){
      current=null;
      continue
    }
    if(!current){
      current={removed:'',added:''};
      groups.push(current)
    }
    current[part.type==='delete'?'removed':'added']+=part.text
  }
  return groups
}

function readableChange(text){
  if(/^[ \t\r\n]+$/.test(text))return [...text.matchAll(/( +|\t+|\r+|\n+)/g)].map(([part])=>({' ':'␠','\t':'⇥','\r':'␍','\n':'↵'}[part[0]])+(part.length>1?' × '+part.length:'')).join(' · ');
  return text.replace(/ /g,'␠').replace(/\t/g,'⇥').replace(/\n/g,'↵\n')
}

function appendDetailedDiff(parent,before,after){

  const parts=diffText(before===undefined?'':displayValue(before),after===undefined?'':displayValue(after));

  const added=parts.filter(p=>p.type==='insert').reduce((n,p)=>n+Array.from(p.text).length,0),removed=parts.filter(p=>p.type==='delete').reduce((n,p)=>n+Array.from(p.text).length,0);

  const count=document.createElement('div');
  count.className='diff-counts';
  count.textContent=`新增 ${added} 字符 · 删除 ${removed} 字符`;
  parent.append(count);

  const text=document.createElement('div');
  text.className='diff-inline';

  for(const part of parts){
    const node=document.createElement(part.type==='delete'?'del':part.type==='insert'?'ins':'span');
    node.textContent=part.type!=='equal'&&/^[ \t\r\n]+$/.test(part.text)?readableChange(part.text):part.text;
    if(part.type!=='equal')node.title=(part.type==='delete'?'删除：':'新增：')+readableChange(part.text);
    text.append(node)
  }
  parent.append(text);

  const list=document.createElement('div');
  list.className='diff-operations';

  for(const group of diffChunks(parts)){

    const line=document.createElement('div');
    line.className='diff-operation';

    const label=document.createElement('strong');
    label.textContent=group.added&&group.removed?'替换':group.removed?'删除':'新增';
    label.className=group.added&&group.removed?'replace-label':group.removed?'delete-label':'insert-label';
    line.append(label);

    if(group.removed){
      const old=document.createElement('del');
      old.textContent=readableChange(group.removed);
      line.append(old)
    }

    if(group.added&&group.removed)line.append(document.createTextNode(' → '));

    if(group.added){
      const added=document.createElement('ins');
      added.textContent=readableChange(group.added);
      line.append(added)
    }
    list.append(line);

  }

  parent.append(list);
  if(parts.coarse){
    const note=document.createElement('small');
    note.className='muted';
    note.textContent='长文本改动过多，未匹配的中段以整段变化显示。';
    parent.append(note)
  }

}

function questionLocation(path){
  if(path[0]==='prediction'&&path[2]==='qa'&&path.length>=4)return{s:Number(path[1]),q:Number(path[3]),path:path.slice(0,4)};
  if(path[0]==='review'&&path.length>=2)return{s:model?.prediction?.length||0,q:Number(path[1]),path:path.slice(0,2)};
  return null;
}

function goToChange(path){
  $('diffDialog').close();
  const location=questionLocation(path);
  questionEditing=false;
  if(location&&sections()[location.s]?.qa?.[location.q]){
    sectionIndex=location.s;
    qaIndex=location.q;
    renderReview();
    if(path.at(-1)==='question'){
      if(activeAnswerId==='pairedAnswer')pairedQuestionEditing=true;else questionEditing=true;
      renderChoices(activeAnswerId==='pairedAnswer');
      $(activeAnswerId==='pairedAnswer'?'pairedQuestion':'question').focus()
    }else setAnswerEditing(true,true);
    editMessage('已定位 '+pathLabel(path)+'；可点“本题改动”再次核对。');
  }else{
    if(location||path.length===0||['prediction','review'].includes(path[0])&&(path.length<3||path.includes('qa'))){
      $('rawDialog').showModal();
      $('editor').focus();
      let parent=path.slice(),range=null;
      while(parent.length&&!range){
        try{range=findJsonPathRange($('editor').value,parent)}catch{}
        if(!range)parent.pop();
      }
      if(range)$('editor').setSelectionRange(range.start,range.end);
      editMessage('此处涉及问题结构变化，已打开 JSON 编辑器并定位相关内容。');
      return;
    }
    if(path[0]==='prediction')sectionIndex=Math.min(Number(path[1]),Math.max(0,sections().length-1));
    renderReview();
    $('metadataDialog').showModal();
  }
}

function renderChangeCards(container,changes,{navigable=true,after=model}={}){
  for(const change of changes){
    const row=document.createElement('article');
    row.className='diff-row';
    const title=document.createElement(navigable?'button':'div');
    title.className='diff-path'+(navigable?' diff-jump':'');
    title.textContent=pathLabel(change.path);
    if(navigable){
      const action=document.createElement('span');
      action.textContent='定位并编辑 →';
      title.append(action);
      title.onclick=()=>goToChange(change.path);
    }
    row.append(title);
    const location=questionLocation(change.path);
    const qa=location&&(atPath(after,location.path)||atPath(sourceModel,location.path));
    if(qa?.question){
      const context=document.createElement('div');
      context.className='diff-question';
      context.textContent=qa.question;
      row.append(context);
    }
    appendDetailedDiff(row,change.before,change.after);
    container.append(row);
  }
}

function openDiff(prefix=null){

  if(!doc||saving||loading)return;
  setAnswerEditing(false,false);
  let after;

  try{
    after=JSON.parse($('editor').value)
  }catch(e){
    editMessage('JSON 格式错误：'+e.message,'error');
    return
  }

  closeSource(true);
  const allChanges=sourceModel?changesBetween(sourceModel,after):[];
  const changes=prefix?allChanges.filter(c=>prefix.every((key,i)=>String(c.path[i])===String(key))):allChanges;
  $('diffChanges').replaceChildren();

  $('diffSummary').textContent=sourceModel?`相对 ${doc.immutable_source_path}：共 ${allChanges.length} 处字段改动${prefix?`，当前显示本题 ${changes.length} 处`:''}。绿色下划线为新增，红色删除线为删除；替换同时标出旧词与新词。点击题目可返回编辑。${allChanges.length?'':'内容与原始文件一致，不会写入新版。'}`:'未找到可用的原始 JSON，无法生成源文件差异。';
  const nav=document.createElement('nav');
  nav.className='diff-overview';
  nav.setAttribute('aria-label','修改题目导航');
  if(prefix){
    const all=document.createElement('button');
    all.textContent=`查看全部 ${allChanges.length} 处改动`;
    all.onclick=()=>openDiff();
    nav.append(all);
  }
  const groups=new Map();
  for(const change of changes){
    const location=questionLocation(change.path),key=JSON.stringify(location?.path||change.path.slice(0,2));
    if(!groups.has(key))groups.set(key,{path:change.path,count:0});
    groups.get(key).count++;
  }
  for(const {path,count} of groups.values()){
    const button=document.createElement('button');
    const location=questionLocation(path);
    button.textContent=(location?pathLabel([...location.path]).replace(/ · $/,''):pathLabel(path))+` · ${count}处 ↗`;
    button.onclick=()=>goToChange(path);
    nav.append(button);
  }
  $('diffChanges').append(nav);
  renderChangeCards($('diffChanges'),changes,{after});
  $('diffTarget').textContent=sourceModel&&!allChanges.length?(doc.target_exists?'无改动；继续后先检查已有 '+doc.save_path:'无改动；不创建 qa-new.json'):'整回合保存到：'+doc.save_path;
  if(!$('diffDialog').open)$('diffDialog').showModal();
  controls();

}

$('prevQA').setAttribute('aria-keyshortcuts','Q Backspace');
$('prevQA').title='Q / Backspace 上一题；答案编辑时按 Shift 加快捷键';

function scrollSourceToCurrent(){

  const code=$('sourceCode'),mark=$('sourceCurrent');

  if(!mark||!document.body.classList.contains('source-open'))return;

  const top=mark.getBoundingClientRect().top-code.getBoundingClientRect().top+code.scrollTop;

  code.scrollTop=Math.max(0,top-Math.min(110,code.clientHeight*.2));

}

function renderSource({forceLocate=false}={}){

  const code=$('sourceCode');
  if(!code)return;

  $('sourcePath').textContent=doc?.immutable_source_path||'未选择文件';

  if(!doc?.source_available){

    code.textContent='未找到对应的原始 JSON 文件。';
    $('sourcePosition').textContent='';
    $('sourceLocate').disabled=true;
    sourceRenderedText=null;
    sourceRenderedPath=null;
    return;

  }

  const text=doc.source_text,path=currentPath(),key=JSON.stringify(path);

  if(text!==sourceRenderedText||key!==sourceRenderedPath){

    let range=null;
    try{
      range=findJsonPathRange(text,path)
    }catch{}

    code.replaceChildren();

    if(range){

      code.append(document.createTextNode(text.slice(0,range.start)));

      const mark=document.createElement('mark');
      mark.id='sourceCurrent';
      mark.textContent=text.slice(range.start,range.end);
      mark.title='当前问题在源文件中的位置';
      code.append(mark,document.createTextNode(text.slice(range.end)));

      const line=text.slice(0,range.start).split('\n').length;

      $('sourcePosition').textContent='当前：'+pathLabel([...path,'question'])+' · 源文件第 '+line+' 行';

    }else{

      code.textContent=text;
      $('sourcePosition').textContent='当前问题在源文件中没有对应位置。';

    }

    $('sourceLocate').disabled=!range;
    sourceRenderedText=text;
    sourceRenderedPath=key;
    forceLocate=true;

  }

  if(forceLocate)requestAnimationFrame(scrollSourceToCurrent);

}

function normalizeEditedAnswers(model,baseline,source){

  let changed=0;

  function visit(value,old,original){

    if(!value||typeof value!=='object')return;

    for(const key of Object.keys(value)){

      if(key==='answer'&&typeof value[key]==='string'){

        if(value[key]===old?.[key]||value[key]===original?.[key])continue;

        // Keep word separators (including player names); flatten pasted line breaks.
        const cleaned=value[key].replace(/\s+/gu,' ').trim();

        if(cleaned!==value[key]){
          value[key]=cleaned;
          changed++
        }

      }else visit(value[key],old?.[key],original?.[key]);

    }

  }

  visit(model,baseline,source);
  return changed;

}

function cleanEditedAnswers(){

  if(!doc||!model)return 0;

  let baseline;
  try{
    baseline=JSON.parse(original)
  }catch{
    return 0
  }

  const changed=normalizeEditedAnswers(model,baseline,sourceModel);

  if(changed){
    for(const paired of [false,true]){const qa=slotQA(paired);if(qa&&typeof qa.answer==='string')$(paired?'pairedAnswer':'answer').value=qa.answer}
    syncModel()
  }

  return changed;

}

for(const id of ['answer','pairedAnswer'])$(id).addEventListener('blur',()=>cleanEditedAnswers());

for(const id of ['answer','pairedAnswer'])$(id).title='结束编辑、切题或查看对照前，去掉首尾空白，将换行、制表符和连续空格合并为一个空格；保留英文词语和人名之间的空格';

function measureTextRows(field,text){

  const width=field.getBoundingClientRect().width;
  if(width<1)return null;

  const style=getComputedStyle(field);

  if(!answerMeasureField){
    answerMeasureField=document.createElement('textarea');
    answerMeasureField.setAttribute('aria-hidden','true');
    answerMeasureField.tabIndex=-1;
    answerMeasureField.readOnly=true;
    answerMeasureField.style.cssText='position:fixed;left:-20000px;top:0;visibility:hidden;pointer-events:none;height:0;min-height:0;max-height:none;overflow:hidden;resize:none;box-sizing:border-box;';
    document.body.append(answerMeasureField)
  }

  for(const key of ['font','lineHeight','letterSpacing','paddingTop','paddingRight','paddingBottom','paddingLeft','borderTopWidth','borderRightWidth','borderBottomWidth','borderLeftWidth','borderStyle','wordBreak','overflowWrap','tabSize','whiteSpace'])answerMeasureField.style[key]=style[key];

  answerMeasureField.style.width=width+'px';
  answerMeasureField.style.height='0px';
  answerMeasureField.value=String(text||' ');

  const lineHeight=parseFloat(style.lineHeight)||24.75,padding=parseFloat(style.paddingTop)+parseFloat(style.paddingBottom),border=parseFloat(style.borderTopWidth)+parseFloat(style.borderBottomWidth);

  const rows=Math.max(1,Math.round((answerMeasureField.scrollHeight-padding)/lineHeight));

  return{rows,lineHeight,padding,border};

}

function scheduleCompactReview(){
  if(compactReviewFrame)return;
  compactReviewFrame=requestAnimationFrame(()=>{
    compactReviewFrame=0;
    resizeCompactReview()
  })
}

function qaContentSize(paired=false){
  const el=id=>$(paired?'paired'+id[0].toUpperCase()+id.slice(1):id);
  const measured=measureTextRows(el('answer'),el('answer').value);
  if(!measured)return {question:48,answer:70,answerBase:43,rows:1};
  let q;
  if(!el('choices').hidden)q=el('questionStem').scrollHeight+el('choices').scrollHeight+6;
  else{const m=measureTextRows(el('question'),el('question').value);q=m?m.rows*m.lineHeight+m.padding+m.border:48}
  return {question:Math.max(32,Math.ceil(q)+2),answer:Math.ceil((measured.rows+2)*measured.lineHeight+measured.padding+measured.border),answerBase:Math.ceil(measured.rows*measured.lineHeight+measured.padding+measured.border),rows:measured.rows}
}
function fitQaContent(room,qDesired,aDesired,manual=null,answerBase=43){
  const qMin=Math.min(32,room*.4),aMin=Math.min(43,room*.4);
  const desired=manual!==null?room*manual:room>=qDesired+answerBase?qDesired:room*qDesired/Math.max(1,qDesired+answerBase);
  const q=Math.max(qMin,Math.min(room-aMin,desired));
  return [q,Math.max(0,room-q)]
}
function resizeCompactReview(){
  const fields=$('reviewFields');
  if(fields.hidden||!fields.clientWidth||!fields.clientHeight)return;
  const paired=!$('pairedQA').hidden,upper=qaContentSize(),lower=paired?qaContentSize(true):null;
  const navHeight=Math.max(30,$('qaNav').scrollHeight);
  const labels=[...fields.children].filter(el=>el.matches('label.field'));
  const labelHeight=labels.reduce((n,el)=>n+Math.max(21,el.scrollHeight),0);
  const refDesired=fields.classList.contains('has-references')?Math.min(96,Math.max(60,fields.clientHeight*.13)):(paired?48:60);
  const fixed=navHeight+labelHeight+(paired?28+8:25);
  const room=Math.max(0,fields.clientHeight-fixed);
  let refs=Math.min(room*.25,refDesired);
  const lowerStyle=getComputedStyle($('pairedQA'));
  const lowerOverhead=paired?[...$('pairedQA').querySelectorAll('label.field')].reduce((n,el)=>n+Math.max(21,el.scrollHeight),0)+3*parseFloat(lowerStyle.rowGap)+parseFloat(lowerStyle.paddingTop)+parseFloat(lowerStyle.paddingBottom)+2:0;
  const baseNeeded=upper.question+upper.answerBase+(lower?lower.question+lower.answerBase:0);
  // Give QA content priority; only the bottom reference area yields first.
  refs=Math.min(refs,Math.max(0,room-lowerOverhead-baseNeeded));
  const available=Math.max(0,room-refs-lowerOverhead);
  const needed=upper.question+upper.answer+(lower?lower.question+lower.answer:0);
  const used=panelLayout.pair!==null?available:Math.min(available,needed);
  let upperRoom=used,lowerRoom=0;
  if(paired){
    const upperBase=upper.question+upper.answerBase,lowerBase=lower.question+lower.answerBase,base=upperBase+lowerBase;
    if(panelLayout.pair!==null)upperRoom=used*boundedPanelFraction(panelLayout.pair,used,76);
    else upperRoom=used>=base?upperBase+(used-base)/2:Math.min(upperBase,Math.max(0,used-32));
    lowerRoom=used-upperRoom
  }
  const [q,a]=fitQaContent(upperRoom,upper.question,upper.answer,null,upper.answerBase);
  let template=`auto auto ${q}px auto ${a}px `;
  if(paired){
    const [lq,la]=fitQaContent(lowerRoom,lower.question,lower.answer,null,lower.answerBase);
    $('pairedQA').style.gridTemplateRows=`auto ${lq}px auto ${la}px`;
    template+=`8px ${lowerRoom+lowerOverhead}px `;
    $('pairedAnswer').dataset.contentRows=String(lower.rows);
  }
  template+='minmax(0,1fr)';
  if(fields.style.gridTemplateRows!==template)fields.style.gridTemplateRows=template;
  $('answer').dataset.contentRows=String(upper.rows);
  $('answer').dataset.extraRows='2';$('pairedAnswer').dataset.extraRows='2';
  updateSplitterValue($('answerSplitter'),room?(paired?upperRoom/Math.max(1,used):used/room):0);
}

window.addEventListener('resize',()=>{applyPanelLayout();scheduleCompactReview()});

const compactReviewObserver=new ResizeObserver(scheduleCompactReview);
compactReviewObserver.observe($('reviewLayout'));

$('answer').addEventListener('input',scheduleCompactReview);
$('question').addEventListener('input',scheduleCompactReview);
$('pairedQuestion').addEventListener('input',scheduleCompactReview);
$('pairedAnswer').addEventListener('input',scheduleCompactReview);

const PANEL_LAYOUT_KEY='basketball-panel-layout-v1';
const DEFAULT_PANEL_LAYOUT={columns:1.12/2.12,media:.575,question:null,answer:null,pairedQuestion:null,pair:null,references:null};
function readPanelLayout(raw){
  const state={...DEFAULT_PANEL_LAYOUT};
  if(!raw||typeof raw!=='object')return state;
  for(const key of ['columns','media']){
    if(Number.isFinite(raw[key]))state[key]=Math.max(.15,Math.min(.85,raw[key]));
  }
  return state
}
let panelLayout={...DEFAULT_PANEL_LAYOUT};
try{panelLayout=readPanelLayout(JSON.parse(localStorage.getItem(PANEL_LAYOUT_KEY)))}catch{}
function persistPanelLayout(){
  try{localStorage.setItem(PANEL_LAYOUT_KEY,JSON.stringify({columns:panelLayout.columns,media:panelLayout.media}))}catch{}
}
function boundedPanelFraction(value,room,minimum){
  const edge=room>0?Math.min(.45,minimum/room):.45;
  return Math.max(edge,Math.min(1-edge,value))
}
function updateSplitterValue(handle,fraction){
  handle.setAttribute('aria-valuemin','0');
  handle.setAttribute('aria-valuemax','100');
  handle.setAttribute('aria-valuenow',String(Math.round(fraction*100)));
  handle.setAttribute('aria-valuetext',Math.round(fraction*100)+'%')
}
function applyPanelLayout(){
  const layout=$('reviewLayout'),media=$('mediaPanels');
  const column=boundedPanelFraction(panelLayout.columns,layout.clientWidth-10,280);
  const row=boundedPanelFraction(panelLayout.media,media.clientHeight-10,105);
  layout.style.gridTemplateColumns=`minmax(0,${column}fr) 10px minmax(0,${1-column}fr)`;
  media.style.gridTemplateRows=`minmax(0,${row}fr) 10px minmax(0,${1-row}fr)`;
  updateSplitterValue($('columnsSplitter'),column);
  updateSplitterValue($('mediaSplitter'),row);
  scheduleCompactReview()
}
function resetPanelAxis(axis){
  if(axis==='columns'||axis==='media')panelLayout[axis]=DEFAULT_PANEL_LAYOUT[axis];
  else panelLayout.pair=null
  persistPanelLayout();applyPanelLayout()
}
function splitterSnapshot(axis){
  if(axis==='columns'){
    const room=$('reviewLayout').clientWidth-10;
    return {room,value:$('mediaPanels').getBoundingClientRect().width,minimum:280}
  }
  if(axis==='media'){
    const room=$('mediaPanels').clientHeight-10;
    return {room,value:$('video').closest('.visual-panel').getBoundingClientRect().height,minimum:105}
  }
  const q=$('questionArea').getBoundingClientRect().height,a=$('answer').getBoundingClientRect().height,r=$('refs').getBoundingClientRect().height;
  const lq=$('pairedQuestionArea').getBoundingClientRect().height,la=$('pairedAnswer').getBoundingClientRect().height;
  return {room:q+a+r+lq+la,q,a,r,lq,la,paired:!$('pairedQA').hidden}
}
function movePanelSplitter(axis,start,delta){
  if(start.room<=0)return;
  if(axis==='columns'||axis==='media'){
    panelLayout[axis]=boundedPanelFraction((start.value+delta)/start.room,start.room,start.minimum);
    applyPanelLayout();return
  }
  const qaRoom=start.q+start.a+start.lq+start.la;
  if(!start.paired||qaRoom<=0)return;
  panelLayout.pair=boundedPanelFraction((start.q+start.a+delta)/qaRoom,qaRoom,76);
  resizeCompactReview()
}

function initializePanelSplitter(id,axis){
  const handle=$(id),vertical=axis==='columns';
  handle.setAttribute('aria-keyshortcuts',vertical?'ArrowLeft ArrowRight Home':'ArrowUp ArrowDown Home');
  let drag=null;
  const position=e=>vertical?e.clientX:e.clientY;
  handle.addEventListener('pointerdown',e=>{
    if(!e.isPrimary||e.button!==0)return;
    e.preventDefault();shiftTapArmed=false;
    handle.focus({preventScroll:true});
    drag={pointer:e.pointerId,position:position(e),start:splitterSnapshot(axis)};
    handle.setPointerCapture(e.pointerId);
    handle.classList.add('dragging');
    document.body.classList.add('resizing-panels');
    document.body.style.cursor=vertical?'col-resize':'row-resize'
  });
  handle.addEventListener('pointermove',e=>{
    if(drag&&e.pointerId===drag.pointer)movePanelSplitter(axis,drag.start,position(e)-drag.position)
  });
  function finish(e){
    if(!drag||(e&&e.pointerId!==undefined&&e.pointerId!==drag.pointer))return;
    const pointer=drag.pointer;drag=null;
    handle.classList.remove('dragging');
    document.body.classList.remove('resizing-panels');
    document.body.style.cursor='';
    if(handle.hasPointerCapture(pointer))handle.releasePointerCapture(pointer);
    persistPanelLayout()
  }
  for(const event of ['pointerup','pointercancel','lostpointercapture'])handle.addEventListener(event,finish);
  window.addEventListener('blur',()=>finish());
  handle.addEventListener('dblclick',()=>resetPanelAxis(axis));
  handle.addEventListener('keydown',e=>{
    shiftTapArmed=false;
    if(e.ctrlKey||e.altKey||e.metaKey)return;
    if(e.key==='Home'){
      e.preventDefault();resetPanelAxis(axis);return
    }
    const minus=vertical?'ArrowLeft':'ArrowUp',plus=vertical?'ArrowRight':'ArrowDown';
    if(e.key!==minus&&e.key!==plus)return;
    e.preventDefault();e.stopPropagation();
    movePanelSplitter(axis,splitterSnapshot(axis),(e.key===minus?-1:1)*(e.shiftKey?30:8));
    persistPanelLayout()
  })
}
for(const [id,axis] of [['columnsSplitter','columns'],['mediaSplitter','media'],['answerSplitter','answer']])initializePanelSplitter(id,axis);
$('resetPanelLayout').onclick=()=>{
  panelLayout={...DEFAULT_PANEL_LAYOUT};persistPanelLayout();applyPanelLayout()
};
const panelLayoutObserver=new ResizeObserver(applyPanelLayout);
panelLayoutObserver.observe($('reviewLayout'));
applyPanelLayout();

scheduleCompactReview();
