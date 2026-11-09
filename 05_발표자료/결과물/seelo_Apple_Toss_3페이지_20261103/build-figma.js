const page = await figma.getNodeByIdAsync('12:2');
await figma.setCurrentPageAsync(page);
const sectionNames = ['seelo · Apple · 3페이지 · 20261103', 'seelo · Toss · 3페이지 · 20261103'];
const existing = page.children.filter(n => sectionNames.includes(n.name));
if (existing.length) return { alreadyExists: existing.map(n => ({ id:n.id, name:n.name })), createdNodeIds:[], mutatedNodeIds:[] };

const fonts = [
  {family:'Noto Sans KR',style:'Regular'}, {family:'Noto Sans KR',style:'Medium'},
  {family:'Noto Sans KR',style:'Bold'}, {family:'Pacifico',style:'Regular'},
  {family:'SF Pro',style:'Regular'}, {family:'SF Pro',style:'Medium'},
  {family:'SF Pro',style:'Semibold'}, {family:'SF Pro',style:'Bold'}
];
await Promise.all(fonts.map(f => figma.loadFontAsync(f)));
const ids=[], mappings=[], frames=[], variables=[], styles=[];
const register=n=>{ids.push(n.id);return n;};
const rgb=hex=>({r:parseInt(hex.slice(1,3),16)/255,g:parseInt(hex.slice(3,5),16)/255,b:parseInt(hex.slice(5,7),16)/255});
const sourceIds=['554:25','554:26','554:27','554:31','554:34','554:37','508:4','508:5','508:7','508:8','508:11','508:12','508:15','508:16','508:18','508:21','508:22','508:24','508:26','508:27','508:28','534:3','534:4','534:6','534:7'];
const source={};
for(const id of sourceIds){const n=await figma.getNodeByIdAsync(id);source[id]=n.characters;}
const norm=s=>s.replace(/\s+/g,'');
const x0=Math.max(...page.children.map(n=>n.x+n.width))+400;
const support=register(figma.createSection());support.name='seelo · 시안 공통 요소 · 20261103';support.x=x0;support.y=2850;support.resizeWithoutConstraints(6240,450);

function shape(parent,name,x,y,w,h,fill,radius=0){
  const n=register(figma.createRectangle());n.name=name;parent.appendChild(n);n.x=x;n.y=y;n.resize(w,h);n.cornerRadius=radius;n.fills=[fill];return n;
}
function frame(parent,name,x,y,w,h,fill,radius=0){
  const n=register(figma.createFrame());n.name=name;parent.appendChild(n);n.x=x;n.y=y;n.resize(w,h);n.fills=fill?[fill]:[];n.cornerRadius=radius;n.clipsContent=false;return n;
}
function stack(parent,name,x,y,w,h,dir='VERTICAL',gap=0,pad=0,fill=null,radius=0){
  const n=register(figma.createAutoLayout(dir));n.name=name;parent.appendChild(n);n.resize(w,h);n.primaryAxisSizingMode='FIXED';n.counterAxisSizingMode='FIXED';n.itemSpacing=gap;n.paddingLeft=pad;n.paddingRight=pad;n.paddingTop=pad;n.paddingBottom=pad;n.fills=fill?[fill]:[];n.cornerRadius=radius;n.clipsContent=false;n.x=x;n.y=y;return n;
}

for(let ti=0;ti<2;ti++){
  const isApple=ti===0;
  const theme=isApple?'Apple':'Toss';
  const hex=isApple?{bg:'#f5f5f7',surface:'#ffffff',ink:'#1d1d1f',body:'#424245',secondary:'#6e6e73',line:'#e8e8ed',accent:'#0071e3',soft:'#f5f5f7'}:{bg:'#ffffff',surface:'#ffffff',ink:'#191f28',body:'#333d4b',secondary:'#4e5968',line:'#e5e8eb',accent:'#3182f6',soft:'#f2f4f6'};
  const collection=figma.variables.createVariableCollection('seelo / '+theme+' / 발표 20261103');
  variables.push(collection.id);
  const paints={};
  for(const [k,v]of Object.entries(hex)){
    const variable=figma.variables.createVariable(k,collection,'COLOR');variable.scopes=['FRAME_FILL','SHAPE_FILL','TEXT_FILL','STROKE_COLOR'];variable.setValueForMode(collection.modes[0].modeId,{...rgb(v),a:1});variables.push(variable.id);
    paints[k]=figma.variables.setBoundVariableForPaint({type:'SOLID',color:rgb(v)},'color',variable);
  }
  const ink=k=>paints[k];
  const localStyles={};
  for(const [role,size,style,leading] of [['display',104,'Bold',1.20],['title',72,'Bold',1.25],['heading',40,'Bold',1.40],['body',36,'Regular',1.55],['label',30,'Medium',1.45],['meta',28,'Regular',1.45]]){
    const s=figma.createTextStyle();s.name='seelo / '+theme+' / '+role;s.fontName={family:'Noto Sans KR',style};s.fontSize=size;s.lineHeight={unit:'PIXELS',value:size*leading};s.letterSpacing={unit:'PERCENT',value:isApple?-2:-1.5};styles.push(s.id);localStyles[role]=s;
  }
  function text(parent,value,w,size=36,weight='Regular',color='ink',opts={}){
    const n=register(figma.createText());n.name=opts.name||value.replace(/\n/g,' ').slice(0,100);parent.appendChild(n);
    const family=opts.family==='SF Pro'?'Noto Sans KR':(opts.family||'Noto Sans KR');
    const style=family==='Noto Sans KR'&&weight==='Semibold'?'Bold':weight;
    n.textStyleId=localStyles[opts.role||'body'].id;n.fontName={family,style};n.fontSize=size;n.lineHeight={unit:'PIXELS',value:opts.leading||size*(size>=60?1.20:1.5)};n.letterSpacing={unit:'PERCENT',value:opts.tracking===undefined?(isApple?-2:-1.5):opts.tracking};n.fills=[ink(color)];n.resize(w,1);n.characters=value;n.textAlignHorizontal=opts.align||'LEFT';n.textAutoResize='HEIGHT';
    if(opts.x!==undefined)n.x=opts.x;if(opts.y!==undefined)n.y=opts.y;
    return n;
  }
  function sourceText(parent,id,w,size=36,weight='Regular',color='ink',opts={}){
    const value=opts.reflow||source[id];if(norm(value)!==norm(source[id]))throw new Error('Source mismatch: '+id);
    const n=text(parent,value,w,size,weight,color,opts);mappings.push({theme,sourceId:id,createdId:n.id,text:value});return n;
  }
  function accentPhrase(n,phrase){const a=n.characters.indexOf(phrase);if(a>=0)n.setRangeFills(a,a+phrase.length,[ink('accent')]);}
  function icon(parent,kind,x,y,size=44,color='body'){
    const paths={search:'<circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35"/>',home:'<path d="m3 10.5 9-7.5 9 7.5"/><path d="M5 9.5V21h14V9.5"/>',check:'<path d="m5 12 5 5L20 6"/>',user:'<circle cx="12" cy="8" r="4"/><path d="M4 20a8 8 0 0 1 16 0"/>',arrow:'<path d="M5 12h14M12 5l7 7-7 7"/>',edit:'<path d="m16 3 5 5-11 11-7 2 2-7L16 3Z"/><path d="m14 5 5 5"/>',compare:'<path d="M3 8h17M16 4l4 4-4 4M21 16H4M8 12l-4 4 4 4"/>'};
    const svg='<svg xmlns="http://www.w3.org/2000/svg" width="'+size+'" height="'+size+'" viewBox="0 0 24 24" fill="none" stroke="'+hex[color]+'" stroke-width="'+(isApple?1.5:1.5)+'" stroke-linecap="round" stroke-linejoin="round">'+paths[kind]+'</svg>';
    const n=figma.createNodeFromSvg(svg);ids.push(n.id,...n.findAll(()=>true).map(c=>c.id));parent.appendChild(n);n.name='도식 / '+kind;n.x=x;n.y=y;return n;
  }
  const sec=register(figma.createSection());sec.name=sectionNames[ti];sec.resizeWithoutConstraints(6240,1280);sec.x=x0;sec.y=ti*1410;
  const head=register(figma.createComponent());support.appendChild(head);head.name='seelo / '+theme+' / Header';head.description='발표자료 공통 머리말. 제품 로고와 중간점검 날짜.';head.x=48+ti*3080;head.y=60;head.resize(1728,72);head.fills=[];head.layoutMode='HORIZONTAL';head.primaryAxisSizingMode='FIXED';head.counterAxisSizingMode='FIXED';head.primaryAxisAlignItems='SPACE_BETWEEN';head.counterAxisAlignItems='CENTER';
  text(head,'seelo',210,44,'Regular','ink',{family:'Pacifico',leading:66});
  text(head,'중간점검  ·  2026.11',420,28,'Medium','body',{align:'RIGHT'});
  const foot=register(figma.createComponent());support.appendChild(foot);foot.name='seelo / '+theme+' / Footer';foot.description='발표자료 공통 꼬리말. 발표자와 페이지 번호.';foot.x=48+ti*3080;foot.y=180;foot.resize(1728,44);foot.fills=[];foot.layoutMode='HORIZONTAL';foot.primaryAxisSizingMode='FIXED';foot.counterAxisSizingMode='FIXED';foot.primaryAxisAlignItems='SPACE_BETWEEN';foot.counterAxisAlignItems='CENTER';
  text(foot,'김태욱 · 강가힐',500,28,'Regular','body');
  function makeSlide(index,title){
    const n=frame(sec,String(index).padStart(2,'0')+' · '+title,80+(index-1)*2040,120,1920,1080,ink('bg'));n.clipsContent=true;
    const hi=head.createInstance();ids.push(hi.id,...hi.findAll(()=>true).map(c=>c.id));n.appendChild(hi);hi.x=96;hi.y=36;
    const fi=foot.createInstance();ids.push(fi.id,...fi.findAll(()=>true).map(c=>c.id));n.appendChild(fi);fi.x=96;fi.y=996;
    text(n,String(index).padStart(2,'0')+' / 03',200,30,'Medium','body',{align:'RIGHT',x:1624,y:1000});
    frames.push({theme,index,id:n.id,name:n.name,w:n.width,h:n.height});return n;
  }
  function processStrip(parent,x,y,w,h,withIcons=false){
    const row=stack(parent,'진단 → 정보 정비 → 전후 비교',x,y,w,h,'HORIZONTAL',0,0,isApple?ink('surface'):ink('soft'),isApple?22:24);
    const cellW=(w-2)/3;
    for(let i=0;i<3;i++){
      if(i>0){const d=shape(row,'구분선',0,0,1,h-56,ink('line'));d.layoutAlign='CENTER';}
      const cell=stack(row,'단계 '+(i+1),0,0,cellW,h,'HORIZONTAL',20,32,null);cell.counterAxisAlignItems='CENTER';
      if(withIcons)icon(cell,['search','edit','compare'][i],0,0,48,'body');else text(cell,'0'+(i+1),64,30,'Medium','accent',{family:'SF Pro'});
      sourceText(cell,['554:31','554:34','554:37'][i],cellW-160,34,'Bold');
    }
    return row;
  }
  function documentDiagram(parent,x,y,w,h){
    const root=frame(parent,'여러 채널의 정보를 점검하는 작업 · 도식',x,y,w,h,null);
    const scale=Math.min(w/474,h/272), ox=(w-474*scale)/2;
    const positions=[[18,54],[161,14],[306,70]];
    for(let i=0;i<3;i++){
      const dx=positions[i][0]*scale+ox,dy=positions[i][1]*scale;shape(root,'채널별 정보',dx,dy,150*scale,190*scale,ink('surface'),isApple?18:24).strokes=[ink('line')];
      shape(root,'정보 항목',dx+24*scale,dy+38*scale,84*scale,10*scale,ink('line'),5);shape(root,'정보 항목',dx+24*scale,dy+70*scale,102*scale,10*scale,ink('line'),5);shape(root,'정보 항목',dx+24*scale,dy+102*scale,70*scale,10*scale,ink('line'),5);
      icon(root,i===1?'check':'search',dx+96*scale,dy+142*scale,30*scale,i===1?'accent':'body');
    }
    return root;
  }
  function compare(parent,x,y,w,h){
    const col=stack(parent,'GEO 정보 상태에 따른 비교',x,y,w,h,'VERTICAL',20,0,null);
    sourceText(col,'508:18',w,28,'Medium','body',{leading:42});
    const row=stack(col,'집단 간 비교',0,0,w,h-62,'HORIZONTAL',16,0,null);row.counterAxisAlignItems='CENTER';
    const cw=(w-80)/2;
    for(let i=0;i<2;i++){
      if(i===1)sourceText(row,'508:24',48,28,'Medium','body',{family:'SF Pro',align:'CENTER'});
      const c=stack(row,'GEO 집단 '+i,0,0,cw,h-62,'VERTICAL',8,14,isApple?ink('soft'):ink('surface'),isApple?18:20);
      sourceText(c,i?'508:26':'508:21',cw-28,28,'Medium','body',{leading:36});
      sourceText(c,i?'508:27':'508:22',cw-28,60,'Semibold',i?'accent':'ink',{family:'SF Pro',leading:72});
    }
  }

  // 01 — 승인된 기존 표지의 내용. 이미지 없이 타이포그래피와 흐름만 배치.
  const cover=makeSlide(1,'서비스 소개');
  if(isApple){
    const hero=stack(cover,'서비스 소개',180,218,1560,528,'VERTICAL',30,0,null);hero.counterAxisAlignItems='CENTER';
    sourceText(hero,'554:25',1400,30,'Medium','accent',{align:'CENTER'});
    const headline=sourceText(hero,'554:26',1560,104,'Bold','ink',{align:'CENTER',leading:126});accentPhrase(headline,'가게 정보를 고칩니다.');
    sourceText(hero,'554:27',1300,36,'Regular','body',{align:'CENTER',leading:54});
    processStrip(cover,288,812,1344,112);
  }else{
    const hero=stack(cover,'서비스 소개',128,218,1664,502,'VERTICAL',32,0,null);
    sourceText(hero,'554:25',1500,32,'Bold','accent');
    const headline=sourceText(hero,'554:26',1664,108,'Bold','ink',{leading:132});accentPhrase(headline,'가게 정보를 고칩니다.');
    sourceText(hero,'554:27',1500,38,'Regular','body',{leading:57,reflow:'Google·카카오 정보 정비부터 2주 뒤 AI 추천 변화 확인까지.'});
    processStrip(cover,128,780,1664,156);
  }

  // 02 — 백지 PPT의 문제 정의 3개를 그대로 시각화. 미기입 수치의 막대·높이는 그리지 않음.
  const problem=makeSlide(2,'문제 정의');
  text(problem,'문제 정의',1728,72,'Bold','ink',{x:96,y:156,leading:90,role:'title'});
  if(isApple){
    const panel=stack(problem,'문제 정의 · 단일 패널',96,294,1728,624,'HORIZONTAL',36,40,ink('surface'),22);
    panel.effects=[{type:'DROP_SHADOW',color:{r:0,g:0,b:0,a:.03},offset:{x:0,y:1},radius:3,visible:true,blendMode:'NORMAL'},{type:'DROP_SHADOW',color:{r:0,g:0,b:0,a:.035},offset:{x:0,y:14},radius:40,visible:true,blendMode:'NORMAL'}];
    const widths=[500,474,528];
    const cols=[];
    for(let i=0;i<3;i++){
      if(i){shape(panel,'구분선',0,0,1,544,ink('line'));}
      const c=stack(panel,'문제 '+(i+1),0,0,widths[i],544,'VERTICAL',26,0,null);cols.push(c);
    }
    const c1=cols[0];const h1=stack(c1,'문제 1 제목',0,0,500,130,'HORIZONTAL',18);sourceText(h1,'508:4',42,30,'Medium','accent',{family:'SF Pro'});sourceText(h1,'508:5',440,38,'Bold','ink',{leading:54});
    sourceText(c1,'508:7',500,174,'Bold','accent',{family:'SF Pro',leading:192,tracking:-4});
    sourceText(c1,'508:8',500,30,'Regular','body',{leading:45});
    const c2=cols[1];const h2=stack(c2,'문제 2 제목',0,0,474,216,'HORIZONTAL',18);sourceText(h2,'508:11',42,30,'Medium','accent',{family:'SF Pro'});sourceText(h2,'508:12',414,36,'Bold','ink',{leading:54,reflow:'사장님은 여러 채널의\n정보를 직접 점검하고\n수정하기 어렵다.'});
    documentDiagram(c2,0,0,474,272);
    const c3=cols[2];const h3=stack(c3,'문제 3 제목',0,0,528,216,'HORIZONTAL',18);sourceText(h3,'508:15',42,30,'Medium','accent',{family:'SF Pro'});sourceText(h3,'508:16',468,36,'Bold','ink',{leading:54,reflow:'검색 노출이 비슷한 가게도\nGEO 정보 상태에 따른\nAI 추천 수 차이가 존재한다.'});
    compare(c3,0,0,528,260);
  }else{
    const left=stack(problem,'문제 1 · AI 탐색',96,294,528,620,'VERTICAL',22,36,ink('soft'),32);
    sourceText(left,'508:4',456,30,'Bold','accent',{family:'SF Pro'});
    sourceText(left,'508:5',456,40,'Bold','ink',{leading:54});
    sourceText(left,'508:7',456,174,'Bold','accent',{family:'SF Pro',leading:192,tracking:-4});
    sourceText(left,'508:8',456,30,'Regular','body',{leading:45});
    const upper=stack(problem,'문제 2 · 채널 관리',656,294,1168,272,'HORIZONTAL',28,36,ink('soft'),32);
    const uc=stack(upper,'문제 2 설명',0,0,650,200,'VERTICAL',20);sourceText(uc,'508:11',650,30,'Bold','accent',{family:'SF Pro'});sourceText(uc,'508:12',650,38,'Bold','ink',{leading:56});documentDiagram(upper,0,0,390,200);
    const lower=stack(problem,'문제 3 · GEO 차이',656,598,1168,316,'HORIZONTAL',36,36,ink('soft'),32);
    const lc=stack(lower,'문제 3 설명',0,0,564,244,'VERTICAL',16);sourceText(lc,'508:15',564,30,'Bold','accent',{family:'SF Pro'});sourceText(lc,'508:16',564,36,'Bold','ink',{leading:54});compare(lower,0,0,496,244);
  }
  sourceText(problem,'508:28',1728,28,'Regular','body',{x:96,y:946,leading:40});

  // 03 — 원본 인사이트와 가치제안의 문장을 보존하고, 앞 장의 3단계 구조로 연결.
  const insight=makeSlide(3,'UX 인사이트 · 가치제안');
  text(insight,'UX 인사이트 · 가치제안',1728,72,'Bold','ink',{x:96,y:156,leading:90,role:'title'});
  if(isApple){
    const panel=frame(insight,'인사이트와 가치제안 · 단일 패널',96,294,1728,624,ink('surface'),22);
    const row=stack(panel,'사용자 요구와 제공 가치',48,42,1632,400,'HORIZONTAL',64);
    const a=stack(row,'사용자 요구',0,0,752,400,'VERTICAL',30);sourceText(a,'534:3',752,30,'Bold','accent');const at=sourceText(a,'534:4',752,38,'Medium','ink',{leading:62,reflow:'사장님은 영업에 집중하면서도\nAI로 가게를 찾는 관광객에게\n발견되고 싶으며,\n복잡한 노출 관리는 맡기고\n결과만 쉽게 확인하고 싶다.'});accentPhrase(at,'결과만 쉽게 확인하고 싶다.');
    const b=stack(row,'제공 가치',0,0,816,400,'VERTICAL',30);sourceText(b,'534:6',816,30,'Bold','accent');const bt=sourceText(b,'534:7',816,38,'Medium','ink',{leading:62,reflow:'seelo는 AI가 우리 가게를 잘 찾고\n소개할 수 있도록,\n구글·카카오의 메뉴·가격·영업시간 등을\n대신 고쳐주고 AI 추천의 변화까지\n확인해주는 서비스다.'});accentPhrase(bt,'대신 고쳐주고');
    shape(panel,'구분선',48,466,1632,1,ink('line'));
    processStrip(panel,48,490,1632,100,true);
  }else{
    const a=stack(insight,'UX 인사이트',96,294,624,624,'VERTICAL',30,40,ink('soft'),32);
    sourceText(a,'534:3',544,30,'Bold','accent');
    const at=sourceText(a,'534:4',544,38,'Bold','ink',{leading:60,reflow:'사장님은 영업에 집중하면서도\nAI로 가게를 찾는 관광객에게\n발견되고 싶으며,\n복잡한 노출 관리는 맡기고\n결과만 쉽게 확인하고 싶다.'});accentPhrase(at,'결과만 쉽게 확인하고 싶다.');
    const b=stack(insight,'가치제안',752,294,1072,624,'VERTICAL',30,40,ink('soft'),32);
    sourceText(b,'534:6',992,30,'Bold','accent');
    const bt=sourceText(b,'534:7',992,40,'Bold','ink',{leading:62,reflow:'seelo는 AI가 우리 가게를 잘 찾고 소개할 수 있도록,\n구글·카카오의 메뉴·가격·영업시간 등을 대신 고쳐주고\nAI 추천의 변화까지 확인해주는 서비스다.'});accentPhrase(bt,'대신 고쳐주고');
    const diagram=stack(b,'서비스의 세 단계',0,0,992,170,'HORIZONTAL',24,0);
    for(let i=0;i<3;i++){
      const tile=stack(diagram,'단계 '+(i+1),0,0,(992-48)/3,170,'VERTICAL',20,24,ink('surface'),24);tile.counterAxisAlignItems='CENTER';icon(tile,['search','edit','compare'][i],0,0,56,'accent');sourceText(tile,['554:31','554:34','554:37'][i],(992-48)/3-48,32,'Bold','ink',{align:'CENTER',leading:48});
    }
  }
  sec.placeholder=false;
}

const audits=[];
for(const f of frames){
  const n=await figma.getNodeByIdAsync(f.id);const descendants=n.findAll(()=>true);const counts={};for(const d of descendants)counts[d.type]=(counts[d.type]||0)+1;
  const texts=n.findAllWithCriteria({types:['TEXT']});const fb=n.absoluteBoundingBox;
  const overflow=texts.filter(t=>{const b=t.absoluteBoundingBox;return b.x<fb.x-1||b.y<fb.y-1||b.x+b.width>fb.x+fb.width+1||b.y+b.height>fb.y+fb.height+1;}).map(t=>({id:t.id,text:t.characters}));
  audits.push({...f,descendants:descendants.length,counts,minText:Math.min(...texts.map(t=>t.fontSize)),fonts:[...new Set(texts.map(t=>t.fontName.family))],overflow,imageNodes:descendants.filter(d=>'fills'in d&&Array.isArray(d.fills)&&d.fills.some(p=>p.type==='IMAGE')).map(d=>({id:d.id,name:d.name,type:d.type,w:d.width,h:d.height}))});
}
figma.viewport.scrollAndZoomIntoView(await Promise.all(frames.map(f=>figma.getNodeByIdAsync(f.id))));
return {sections:page.children.filter(n=>sectionNames.includes(n.name)).map(n=>({id:n.id,name:n.name,x:n.x,y:n.y,w:n.width,h:n.height})),supportId:support.id,frames:audits,sourceMapping:mappings,createdNodeIds:ids,mutatedNodeIds:[],variableIds:variables,textStyleIds:styles,libraryFallback:'Apple macOS 26 asset import not permitted; installed skill tokens applied as scoped local variables and styles.'};
