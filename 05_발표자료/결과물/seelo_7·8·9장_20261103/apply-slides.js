
const page=await figma.getNodeByIdAsync('12:2');await figma.setCurrentPageAsync(page);
const section=await figma.getNodeByIdAsync('562:189');
const titleRef=await figma.getNodeByIdAsync('562:278'),numRef=await figma.getNodeByIdAsync('562:277'),navRef=await figma.getNodeByIdAsync('602:82'),lineRef=await figma.getNodeByIdAsync('591:54'),panelRef=await figma.getNodeByIdAsync('562:279'),inkRef=await figma.getNodeByIdAsync('562:281'),blueRef=await figma.getNodeByIdAsync('562:280');
const sourceIds=['365:1924','521:1705','521:1782'];
const sources=await Promise.all(sourceIds.map(id=>figma.getNodeByIdAsync(id)));
const originals=section.children.filter(n=>n.type==='FRAME');
const fonts=new Map();for(const root of [...sources,...originals])for(const tx of root.findAllWithCriteria({types:['TEXT']}))for(const s of tx.getStyledTextSegments(['fontName']))fonts.set(JSON.stringify(s.fontName),s.fontName);
await Promise.all([...fonts.values(),{family:'IBM Plex Sans KR',style:'Regular'},{family:'IBM Plex Sans KR',style:'SemiBold'},{family:'IBM Plex Sans KR',style:'Medium'}].map(f=>figma.loadFontAsync(f)));
const created=new Set(),mutated=new Set();const mark=n=>{mutated.add(n.id);return n;};
function addId(n){created.add(n.id);if('findAll'in n)for(const c of n.findAll(()=>true))created.add(c.id);return n;}
function clone(ref,parent,name){const n=ref.clone();parent.appendChild(n);n.name=name;return addId(n);}
const ink=inkRef.fills,blue=blueRef.fills,gray=panelRef.fills,white=[{type:'SOLID',color:{r:1,g:1,b:1}}];
const faint=[{type:'SOLID',color:{r:0.89,g:0.91,b:0.93}}],slate=[{type:'SOLID',color:{r:.42,g:.46,b:.51}}];
function frame(parent,name,x,y,w,h,fills=gray,radius=24){const n=figma.createFrame();parent.appendChild(n);created.add(n.id);n.name=name;n.x=x;n.y=y;n.resize(w,h);n.layoutMode='NONE';n.fills=fills;n.cornerRadius=radius;n.clipsContent=false;return n;}
function tx(parent,name,value,x,y,w,h,size=30,style='Regular',fills=ink){const n=figma.createText();parent.appendChild(n);created.add(n.id);n.name=name;n.fontName={family:'IBM Plex Sans KR',style};n.fontSize=size;n.lineHeight={unit:'PIXELS',value:Math.round(size*1.45)};n.letterSpacing={unit:'PERCENT',value:-1};n.characters=value;n.textAutoResize='NONE';n.resize(w,h);n.x=x;n.y=y;n.fills=fills;return n;}
function slide(name,title,number,x,y){if(section.children.some(n=>n.name===name))throw new Error('이미 있는 새 장: '+name);const n=frame(section,name,x,y,1920,1080,white,0);const heading=clone(titleRef,n,'페이지 제목');heading.characters=title;const num=clone(numRef,n,'페이지 번호');num.characters=number;clone(lineRef,n,'공통 형식 / 하단선');clone(navRef,n,'공통 내비게이션 / 수동 편집');return n;}
const s7=slide('07 · UI/UX 설계 · 프로토타입','UI/UX 설계 · 프로토타입','07',4160,1330);
const s8=slide('08 · 데이터베이스 설계','데이터베이스 설계','08',6200,1330);
const s9=slide('09 · 개발 계획 · 역할 분담','개발 계획 · 역할 분담','09',80,2540);

// 화면은 원본 레이어를 복제해 핵심 영역만 뷰포트로 보여준다.
const screenSelections=[
 {source:sources[0],type:'와이어프레임',label:'가게 등록',x:96,crop:{x:132,y:120,w:852,h:960}},
 {source:sources[1],type:'프로토타입',label:'정비안 승인',x:684,crop:{x:294,y:1012,w:852,h:984}},
 {source:sources[2],type:'프로토타입',label:'전후 비교',x:1272,crop:{x:294,y:112,w:852,h:960}}
];
for(const cfg of screenSelections){tx(s7,'화면 유형',cfg.type,cfg.x,298,552,44,28,'Medium',blue);tx(s7,'화면 이름',cfg.label,cfg.x,350,552,54,36,'SemiBold');
 const browser=frame(s7,'화면 / '+cfg.label,cfg.x,424,552,524,gray,18);browser.clipsContent=true;
 const chrome=frame(browser,'창 상단',0,0,552,34,gray,0);
 for(let i=0;i<3;i++){const dot=figma.createEllipse();chrome.appendChild(dot);created.add(dot.id);dot.resize(7,7);dot.x=18+i*14;dot.y=13.5;dot.fills=faint;}
 const vp=frame(browser,'화면 뷰포트 / 원본 편집 가능',0,34,552,490,cfg.source.fills,0);vp.clipsContent=true;
 const native=clone(cfg.source,vp,'원본 화면 / '+cfg.source.id);
 const scale=Math.min(552/cfg.crop.w,490/cfg.crop.h);native.rescale(scale);native.x=(552-cfg.crop.w*scale)/2-cfg.crop.x*scale;native.y=-cfg.crop.y*scale;
}

// 원본 ERD에서 핵심 테이블 8개와 실제 FK 관계만 선택한다.
tx(s8,'그룹 / 가게·측정','가게·질문·측정',96,286,900,44,28,'Medium',blue);
tx(s8,'그룹 / 정비·이력','정비·이력',96,632,180,44,28,'Medium',blue);
function relation(parent,name,x1,y1,x2,y2,label,vertical=false){
 const v=figma.createVector();parent.appendChild(v);created.add(v.id);v.name='관계 / '+name;v.x=x1;v.y=y1;
 const dx=x2-x1,dy=y2-y1;v.vectorPaths=[{windingRule:'NONE',data:'M 0 0 L '+dx+' '+dy}];v.strokes=slate;v.strokeWeight=2;
 if(vertical)tx(parent,'관계 수 / '+name,label,x1+16,(y1+y2)/2-16,88,34,22,'Medium',ink);
 else {const a=tx(parent,'관계 수 / '+name,label,x1-5,y1-39,dx+10,34,label==='1:0..1'?19:22,'Medium',ink);a.textAlignHorizontal='CENTER';}
}
for(let i=0;i<3;i++){relation(s8,['가게-질문','질문-측정','측정-비교'][i],480+448*i,462,544+448*i,462,'1:N');relation(s8,['신청-정비안','정비안-항목','항목-기록'][i],480+448*i,808,544+448*i,808,i===2?'1:0..1':'1:N');}
relation(s8,'가게-정비신청',288,582,288,692,'1:N',true);
const entities=[
 ['가게','stores','PK  id\nFK  owner_id',96,346],
 ['질문 세트','question_sets','PK  id\nFK  store_id',544,346],
 ['측정 실행','measurement_runs','PK  id\nFK  store_id · question_set_id\nkind · status',992,346],
 ['비교 보고서','comparison_reports','PK  id\nFK  base_run_id\nFK  after_run_id',1440,346],
 ['정비 신청','fix_requests','PK  id\nFK  store_id · base_run_id',96,692],
 ['정비안','fix_plans','PK  id\nFK  fix_request_id',544,692],
 ['정비 항목','fix_plan_items','PK  id\nFK  fix_plan_id\n현재 값 · 승인 값',992,692],
 ['반영 기록','fix_logs','PK  id\nFK  fix_plan_item_id\n수정 전 값 · 적용 값',1440,692]
];
for(const [label,table,fields,x,y]of entities){const card=frame(s8,'ERD / '+table,x,y,384,236,gray,22);tx(card,'엔티티',label,24,20,336,50,34,'SemiBold');tx(card,'테이블',table,24,73,336,36,23,'Medium',blue);tx(card,'핵심 키',fields,24,122,336,102,22,'Regular');}

// 9장: 백지 구성의 원문 범위에서 역할, 순서, 문제 대응을 편집한다.
const roles=[['김태욱 · 개발·데이터','DB / API / 수집 / AI / 정비 / 배포'],['강가힐 · 기획·UI/UX','사용자 흐름 / 화면 / 평가 / 발표']];
for(let i=0;i<roles.length;i++){const card=frame(s9,'역할 / '+roles[i][0],96+i*880,306,848,154);tx(card,'담당',roles[i][0],28,24,792,54,34,'SemiBold');tx(card,'범위',roles[i][1],28,88,792,44,28,'Regular');}
tx(s9,'구현 순서','구현·검증 순서',96,498,1728,48,30,'SemiBold');
const steps=[['01','등록·진단 연결','진행 / 결과 / 실패 경로'],['02','연결·정비 처리','승인 항목 수정 / 반영 확인'],['03','재측정·보고서','동일 질문 / 변경 이력 대조']];
for(let i=0;i<steps.length;i++){const c=frame(s9,'구현 순서 / '+steps[i][0],96+588*i,562,552,178);tx(c,'순번',steps[i][0],24,22,64,52,34,'SemiBold',blue);tx(c,'단계',steps[i][1],96,24,432,50,32,'SemiBold');tx(c,'검증',steps[i][2],24,104,504,44,27,'Regular');}
tx(s9,'기술 대응','기술 문제·대응',96,782,1728,44,30,'SemiBold');
const risks=[['AI 지연','작업 큐·재시도'],['값 오류','근거·승인·변경 이력'],['자동화 중단','관리자 수동 처리']];
for(let i=0;i<risks.length;i++){const c=frame(s9,'기술 대응 / '+risks[i][0],96+588*i,848,552,92);tx(c,'문제',risks[i][0],24,25,180,42,27,'SemiBold');tx(c,'대응',risks[i][1],208,26,320,40,25,'Regular');}

// 사용자 지정 순번에 맞춰 기존 시스템 구조 장을 6장으로 정리한다.
const architecture=await figma.getNodeByIdAsync('580:210');mark(architecture).name='06 · 시스템 아키텍처 · 데이터 흐름';mark(await figma.getNodeByIdAsync('580:214')).characters='06';

// 9장 메뉴로 통일. 기존 내비게이션을 재사용해 수동 편집을 유지한다.
const menu=[['서비스 소개',152],['문제 정의',132],['인사이트',132],['핵심 기능',132],['개발 범위',132],['시스템 구조',152],['화면 설계',132],['데이터 설계',152],['개발 계획',132]];
const frames=[...originals,s7,s8,s9];
const activeById={'562:195':'서비스 소개','562:218':'문제 정의','562:271':'인사이트','575:63':'핵심 기능','580:179':'개발 범위','580:210':'시스템 구조',[s7.id]:'화면 설계',[s8.id]:'데이터 설계',[s9.id]:'개발 계획'};
const inactiveRef=navRef.children.find(c=>c.name==='내비게이션 / 문제 정의'),activeRef=navRef.children.find(c=>c.name==='내비게이션 / 인사이트');
for(const root of frames){const nav=root.children.find(n=>n.name==='공통 내비게이션 / 수동 편집');let x=240;
 for(const [label,w]of menu){let tab=nav.children.find(n=>n.name==='내비게이션 / '+label);if(!tab)tab=clone(inactiveRef,nav,'내비게이션 / '+label);mark(tab);tab.x=x;tab.y=10;tab.resize(w,64);tab.fills=label===activeById[root.id]?activeRef.fills:[];const t=tab.findOne(n=>n.type==='TEXT');mark(t);t.characters=label;t.fontName={family:'IBM Plex Sans KR',style:label===activeById[root.id]?'SemiBold':'Medium'};t.fills=label===activeById[root.id]?blue:ink;t.textAutoResize='NONE';t.resize(w,42);t.x=0;t.y=11;x+=w+16;}
}
mark(section);section.name='seelo · Toss · 1–9페이지 · 20261103';section.resizeWithoutConstraints(8280,3710);
function visible(n,root){let x=n;while(x&&x.id!==root.id){if(!x.visible)return false;x=x.parent;}return true;}
function inSource(n){let x=n;while(x){if(x.name.startsWith('원본 화면 /'))return true;x=x.parent;}return false;}
const audit=frames.map(root=>{const all=root.findAll(()=>true),texts=all.filter(n=>n.type==='TEXT'&&visible(n,root)&&!inSource(n)&&n.characters.trim()),bb=root.absoluteBoundingBox,overlaps=[];for(let i=0;i<texts.length;i++)for(let j=i+1;j<texts.length;j++){const a=texts[i].absoluteBoundingBox,b=texts[j].absoluteBoundingBox;if(Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x)>2&&Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y)>2)overlaps.push([texts[i].id,texts[j].id]);}return{id:root.id,name:root.name,overlaps,missingFonts:all.filter(n=>n.type==='TEXT'&&n.hasMissingFont).map(n=>n.id),outside:texts.filter(t=>{const b=t.absoluteBoundingBox;return b.x<bb.x-1||b.y<bb.y-1||b.x+b.width>bb.x+bb.width+1||b.y+b.height>bb.y+bb.height+1;}).map(n=>n.id),autoLayout:all.filter(n=>'layoutMode'in n&&n.layoutMode!=='NONE').length,hugOrFill:all.filter(n=>['HUG','FILL'].includes(n.layoutSizingHorizontal)||['HUG','FILL'].includes(n.layoutSizingVertical)).length,instances:all.filter(n=>n.type==='INSTANCE').length};});
return{createdNodeIds:[...created],mutatedNodeIds:[...mutated],newSlides:[{id:s7.id,name:s7.name},{id:s8.id,name:s8.name},{id:s9.id,name:s9.name}],audit,selectedSources:sourceIds,erdTables:entities.map(e=>e[1]),planSource:'468:192',sectionId:section.id};

