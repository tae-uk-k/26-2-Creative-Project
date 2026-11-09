const page=await figma.getNodeByIdAsync('12:2');await figma.setCurrentPageAsync(page);
const sec=await figma.getNodeByIdAsync('562:189');
if(sec.children.some(n=>n.name==='07 · 시스템 아키텍처 · 데이터 흐름'))return{alreadyExists:true,createdNodeIds:[],mutatedNodeIds:[]};
const created=[],mutated=new Set(),mapping=[];
const add=n=>{created.push(n.id);return n;},touch=n=>{mutated.add(n.id);return n;};
const existing=sec.findAllWithCriteria({types:['TEXT']});const fm=new Map();for(const t of existing)for(const s of t.getStyledTextSegments(['fontName']))fm.set(JSON.stringify(s.fontName),s.fontName);
for(const f of fm.values())await figma.loadFontAsync(f);
await Promise.all(['Regular','Medium','Bold'].map(style=>figma.loadFontAsync({family:'Noto Sans KR',style})));
await figma.loadFontAsync({family:'Pacifico',style:'Regular'});
const rgb=h=>({r:parseInt(h.slice(1,3),16)/255,g:parseInt(h.slice(3,5),16)/255,b:parseInt(h.slice(5,7),16)/255});
const colors={white:'#ffffff',ink:'#191f28',body:'#333d4b',secondary:'#4e5968',line:'#e5e8eb',blue:'#3182f6',soft:'#f2f4f6'};
const binds={white:'562:176',ink:'562:177',body:'562:178',secondary:'562:179',line:'562:180',blue:'562:181',soft:'562:182'},paint={};
for(const[k,h]of Object.entries(colors)){const v=await figma.variables.getVariableByIdAsync('VariableID:'+binds[k]);paint[k]=figma.variables.setBoundVariableForPaint({type:'SOLID',color:rgb(h)},'color',v);}
function frame(p,name,x,y,w,h,fill=null,r=0){const n=add(figma.createFrame());p.appendChild(n);n.name=name;n.resize(w,h);n.x=x;n.y=y;n.fills=fill?[paint[fill]]:[];n.cornerRadius=r;n.clipsContent=false;return n;}
function stack(p,name,x,y,w,h,dir='VERTICAL',gap=0,pad=0,fill=null,r=0){const n=add(figma.createAutoLayout(dir));p.appendChild(n);n.name=name;n.resize(w,h);n.primaryAxisSizingMode='FIXED';n.counterAxisSizingMode='FIXED';n.itemSpacing=gap;n.paddingLeft=pad;n.paddingRight=pad;n.paddingTop=pad;n.paddingBottom=pad;n.fills=fill?[paint[fill]]:[];n.cornerRadius=r;n.x=x;n.y=y;n.clipsContent=false;return n;}
function text(p,value,w,size=32,weight='Regular',color='ink',o={}){const n=add(figma.createText());p.appendChild(n);n.name=o.name||value.replace(/\n/g,' ');n.fontName={family:o.family||'Noto Sans KR',style:weight};n.fontSize=size;n.lineHeight={unit:'PIXELS',value:o.lh||size*1.5};n.letterSpacing={unit:'PERCENT',value:-1.5};n.fills=[paint[color]];n.resize(w,1);n.characters=value;n.textAutoResize='HEIGHT';n.textAlignHorizontal=o.align||'LEFT';if(o.x!==undefined)n.x=o.x;if(o.y!==undefined)n.y=o.y;return n;}
function setText(n,value,w,size=32,weight='Regular',color='ink',lh=null){touch(n);n.fontName={family:'Noto Sans KR',style:weight};n.fontSize=size;n.lineHeight={unit:'PIXELS',value:lh||size*1.5};n.fills=[paint[color]];n.resize(w,1);n.characters=value;n.textAutoResize='HEIGHT';return n;}
async function source(p,id,w,size=32,weight='Regular',color='ink',o={}){const n=await figma.getNodeByIdAsync(id);const value=o.copy||n.characters;const t=text(p,value,w,size,weight,color,o);mapping.push({sourceId:id,id:t.id,sourceText:n.characters,text:value});return t;}
function emph(n,s,color='blue'){const i=n.characters.indexOf(s);if(i>=0)n.setRangeFills(i,i+s.length,[paint[color]]);}
function svg(p,data,name,x,y,w,h){const n=figma.createNodeFromSvg('<svg xmlns="http://www.w3.org/2000/svg" width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" fill="none">'+data+'</svg>');created.push(n.id,...n.findAll(()=>true).map(v=>v.id));p.appendChild(n);n.name=name;n.x=x;n.y=y;return n;}
function arrow(p,x,y,w=32,h=156){return svg(p,'<path d="M4 '+h/2+' H'+(w-6)+' m-7 -6 7 6-7 6" stroke="#4e5968" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>','다음 단계',x,y,w,h);}
function captureClone(n,parent,name,x,y){const clone=n.clone();created.push(clone.id,...clone.findAll(()=>true).map(c=>c.id));parent.appendChild(clone);clone.name=name;clone.x=x;clone.y=y;return clone;}

// 잘못된 4장 전체는 보관하고, 같은 프레임 ID 안을 재구성한다.
const old4=await figma.getNodeByIdAsync('575:63'),archive=await figma.getNodeByIdAsync('542:2');
const saved=captureClone(old4,archive,'보관 · 자동정비를 단독 주제로 구성했던 4장',80,Math.max(...archive.children.map(n=>n.y+n.height))+160);
touch(archive);archive.resizeWithoutConstraints(Math.max(archive.width,2080),saved.y+saved.height+100);
for(const n of old4.children)if(!['575:64','575:67'].includes(n.id))touch(n).visible=false;
old4.name='04 · 서비스 개념과 핵심 기능';touch(old4);

// 2장: 축약한 설명은 유지하되, 원형 그래프는 기존의 큰 숫자로 복원.
const left=await figma.getNodeByIdAsync('562:226');touch(left);left.itemSpacing=22;
const tIndex=await figma.getNodeByIdAsync('562:227'),tHeading=await figma.getNodeByIdAsync('562:228'),tNumber=await figma.getNodeByIdAsync('562:229'),tCaption=await figma.getNodeByIdAsync('562:230');
for(const n of[tIndex,tHeading,tNumber,tCaption]){left.appendChild(n);touch(n);}
for(const id of['575:49','575:50']){const n=await figma.getNodeByIdAsync(id);if(n)touch(n).visible=false;}
setText(tIndex,'01',456,30,'Bold','blue',45);setText(tHeading,tHeading.characters,456,40,'Bold','ink',54);setText(tNumber,'53%',456,174,'Bold','blue',192);tNumber.textAlignHorizontal='LEFT';setText(tCaption,tCaption.characters,456,30,'Regular','secondary',45);

// 3장: 변경 전 토스 버전의 문장·글자 크기·굵기·강조 구간·도식을 복원.
const ux=await figma.getNodeByIdAsync('562:281');setText(ux,'사장님은 영업에 집중하면서도\nAI로 가게를 찾는 관광객에게\n발견되고 싶으며,\n복잡한 노출 관리는 맡기고\n결과만 쉽게 확인하고 싶다.',544,38,'Bold','ink',60);emph(ux,'결과만 쉽게 확인하고 싶다.');
const vp=await figma.getNodeByIdAsync('562:284');setText(vp,'seelo는 AI가 우리 가게를 잘 찾고 소개할 수 있도록,\n구글·카카오의 메뉴·가격·영업시간 등을 대신 고쳐주고\nAI 추천의 변화까지 확인해주는 서비스다.',992,40,'Bold','ink',62);emph(vp,'대신 고쳐주고');
const diag=await figma.getNodeByIdAsync('562:285');touch(diag);diag.resize(992,170);
for(const tile of diag.children){touch(tile);tile.resize(tile.width,170);tile.paddingTop=24;tile.paddingBottom=24;tile.itemSpacing=20;const ic=tile.children.find(n=>n.type==='FRAME');if(ic){touch(ic);ic.rescale(56/ic.width);}for(const t of tile.findAllWithCriteria({types:['TEXT']}))setText(t,t.characters,t.width,32,'Bold','ink',48);}
const extra=await figma.getNodeByIdAsync('575:53');if(extra)touch(extra).visible=false;

// 현재 발표자료 구역을 두 줄로 정리. 새 5·7장은 둘째 줄에 배치한다.
touch(sec);sec.name='seelo · Toss · 1–5·7페이지 · 20261103';sec.resizeWithoutConstraints(8280,2500);
const support=await figma.getNodeByIdAsync('562:38');touch(support);support.y=4110;
const alternatives=await figma.getNodeByIdAsync('575:138');touch(alternatives);alternatives.y=5030;
const header=await figma.getNodeByIdAsync('562:272');
function makeSlide(num,title,x,y){const f=frame(sec,String(num).padStart(2,'0')+' · '+title,x,y,1920,1080,'white');f.clipsContent=true;captureClone(header,f,'seelo / 발표 머리말',96,36);text(f,String(num).padStart(2,'0'),200,30,'Medium','body',{align:'RIGHT',x:1624,y:1000,lh:45});text(f,title,1728,72,'Bold','ink',{x:96,y:156,lh:90});return f;}
for(const[id,value]of[['562:201','01'],['562:224','02'],['562:277','03'],['575:67','04']]){const n=await figma.getNodeByIdAsync(id);setText(n,value,200,30,'Medium','body',45);}

// 4장: 핵심 기능은 짧게. 승인·반영 설명은 작은 두 행으로 줄인다.
text(old4,'서비스 개념과 핵심 기능',1728,72,'Bold','ink',{x:96,y:156,lh:90});
const feature=frame(old4,'핵심 기능 · 지도 정보 대신 수정',96,294,1728,326,'soft',32);
const fc=stack(feature,'무엇을 해주는가',40,32,1136,262,'VERTICAL',16);
text(fc,'핵심 기능',1136,30,'Bold','blue',{lh:45});
text(fc,'구글·카카오의 메뉴·가격·영업시간 등을\n대신 고쳐주기',1136,46,'Bold','ink',{lh:64});
text(fc,'승인한 정보를 반영하고, 반영 결과와 변경 이력을 남깁니다.',1136,30,'Regular','secondary',{lh:45});
const compact=stack(feature,'확인·승인과 결과 확인',1232,70,456,186,'VERTICAL',18);
for(const title of['정비안 확인·승인','지도 반영·변경 이력']){const row=stack(compact,title,0,0,456,84,'HORIZONTAL',0,24,'white',20);row.counterAxisAlignItems='CENTER';text(row,title,408,30,'Medium','body',{lh:45});}
await source(old4,'524:44',1728,32,'Bold','ink',{x:96,y:662,lh:48});
const flowBase=await figma.getNodeByIdAsync('575:60');const defs=flowBase.componentPropertyDefinitions;const propTitle=Object.keys(defs).find(k=>k.startsWith('단계#')),propBody=Object.keys(defs).find(k=>k.startsWith('설명#'));
const usage=stack(old4,'가게 등록부터 결과 확인까지',96,730,1728,156,'HORIZONTAL');
const flowSteps=[['가게 등록','이름·지도 링크'],['AI 추천 현황 확인','결과 확인·정비 신청'],['연결·정비안 승인','사장님 확인'],['정보 대신 수정','Google·카카오 반영'],['결과 확인','반영 이력·전후 비교']];
for(let i=0;i<flowSteps.length;i++){if(i){const a=frame(usage,'다음 단계',0,0,32,156);arrow(a,0,0);}const n=flowBase.createInstance();created.push(n.id,...n.findAll(()=>true).map(v=>v.id));usage.appendChild(n);n.setProperties({[propTitle]:flowSteps[i][0],[propBody]:flowSteps[i][1]});}
await source(old4,'524:69',1728,28,'Regular','secondary',{x:96,y:934,lh:42});

// 5장: 원본 468:100의 범위와 후속 계획을 빠짐없이 배치.
const p5=makeSlide(5,'개발 범위 · 후속 개발',80,1330);
const beta=stack(p5,'베타 범위',96,274,1728,72,'HORIZONTAL',24,16,'soft',20);beta.counterAxisAlignItems='CENTER';
await source(beta,'482:55',180,30,'Bold','blue',{lh:45});await source(beta,'482:56',1448,30,'Medium','body',{lh:45});
const scope=stack(p5,'구현 범위',96,378,1728,330,'HORIZONTAL',36);
const columns=[['482:46','482:47'],['482:49','482:50'],['482:52','482:53']];
for(let i=0;i<3;i++){const c=stack(scope,'범위 '+(i+1),0,0,552,330,'VERTICAL',22,32,'soft',24);const title=i===1?'구글·카카오 정보 수정':(await figma.getNodeByIdAsync(columns[i][0])).characters;await source(c,columns[i][0],488,36,'Bold','ink',{copy:title,lh:54});await source(c,columns[i][1],488,30,'Regular','body',{lh:46});}
await source(p5,'482:57',1728,32,'Bold','ink',{x:96,y:740,lh:48});
const future=stack(p5,'후속 개발안',96,806,1728,148,'HORIZONTAL',36);
for(const[ti,bi]of[['482:60','482:61'],['482:63','482:64'],['482:66','482:67']]){const c=stack(future,'후속 개발',0,0,552,148,'VERTICAL',10);await source(c,ti,552,32,'Bold','ink',{lh:48});await source(c,bi,552,28,'Regular','secondary',{lh:42});}
await source(p5,'482:68',1500,24,'Regular','secondary',{x:96,y:978,lh:36});

// 7장: 원본의 5개 모듈과 4개 연결을 같은 의미·방향으로 시각화.
const p7=makeSlide(7,'시스템 아키텍처 · 데이터 흐름',2120,1330);
const arch=frame(p7,'시스템 구성',96,294,1728,418);
function archLink(path){return svg(arch,'<path d="'+path+'" stroke="#8b95a1" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>','시스템 연결',0,0,1728,418);}
archLink('M320 70H488m-10 -7 10 7-10 7');
archLink('M848 70H1048m-10 -7 10 7-10 7');
archLink('M1388 140V190H668V238m-7 -10 7 10 7-10');
archLink('M848 328H1048m-10 -7 10 7-10 7');
const modules=[['479:84','479:85',0,0,320,140],['479:87','479:88',488,0,360,140],['479:90','479:91',1048,0,680,140],['479:93','479:94',488,238,360,180],['479:96','479:97',1048,210,680,208]];
for(const[ti,bi,x,y,w,h]of modules){const external=ti==='479:96',pad=external?18:24;const c=stack(arch,'모듈',x,y,w,h,'VERTICAL',external?8:10,pad,'soft',24);await source(c,ti,w-pad*2,36,'Bold','ink',{lh:external?48:54});await source(c,bi,w-pad*2,28,'Regular','body',{lh:external?38:42});}
await source(arch,'479:98',168,26,'Medium','secondary',{x:320,y:12,lh:39,align:'CENTER'});
await source(arch,'479:99',200,26,'Medium','secondary',{x:848,y:12,lh:39,align:'CENTER'});
await source(arch,'479:100',360,26,'Medium','secondary',{x:770,y:145,lh:39,align:'CENTER'});
const dataFlow=stack(p7,'데이터 흐름',96,752,1728,90,'HORIZONTAL');
for(let i=0;i<5;i++){if(i){const c=frame(dataFlow,'다음',0,0,32,90);arrow(c,0,0,32,90);}const c=stack(dataFlow,'데이터 처리',0,0,320,90,'VERTICAL',0,20,'soft',20);c.primaryAxisAlignItems='CENTER';await source(c,['479:103','479:107','479:111','479:115','479:119'][i],280,30,'Bold','ink',{lh:45});}
const facts=stack(p7,'측정 조건과 진행 처리',96,876,1728,64,'HORIZONTAL',48);
await source(facts,'479:122',840,30,'Bold','blue',{lh:45});await source(facts,'479:124',840,28,'Medium','body',{lh:42});
await source(p7,'479:125',1510,24,'Regular','secondary',{x:96,y:978,lh:36});

function vis(n,root){while(n&&n.id!==root.id){if(!n.visible)return false;n=n.parent;}return true;}
const frames=[];for(const root of[await figma.getNodeByIdAsync('562:218'),await figma.getNodeByIdAsync('562:271'),old4,p5,p7]){const ns=root.findAll(()=>true).filter(n=>vis(n,root)),ts=ns.filter(n=>n.type==='TEXT'&&n.characters.trim());const counts={};for(const n of ns)counts[n.type]=(counts[n.type]||0)+1;const overlaps=[];for(let i=0;i<ts.length;i++)for(let j=i+1;j<ts.length;j++){const a=ts[i].absoluteBoundingBox,b=ts[j].absoluteBoundingBox;if(Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x)>2&&Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y)>2)overlaps.push([ts[i].id,ts[j].id]);}const box=root.absoluteBoundingBox;frames.push({id:root.id,name:root.name,w:root.width,h:root.height,counts,overlaps,missingFonts:ts.filter(t=>t.hasMissingFont).map(t=>t.id),authors:ts.filter(t=>/김태욱|강가힐/.test(t.characters)).map(t=>t.id),outside:ts.filter(t=>{const b=t.absoluteBoundingBox;return b.x<box.x-1||b.y<box.y-1||b.x+b.width>box.x+box.width+1||b.y+b.height>box.y+box.height+1;}).map(t=>t.id),automatedLabel:ts.filter(t=>/자동\s*정비/.test(t.characters)).map(t=>({id:t.id,text:t.characters}))});}
figma.viewport.scrollAndZoomIntoView([old4,p5,p7]);
return{createdNodeIds:created,mutatedNodeIds:[...mutated],sectionId:sec.id,frames,sourceMapping:mapping,archiveId:saved.id,sourceFrames:['468:42','468:100','468:127'],wireframes:['213:917','214:544','214:634','215:285','213:805'],page5:p5.id,page7:p7.id};
