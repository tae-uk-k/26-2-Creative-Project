
const p=await figma.getNodeByIdAsync('12:2');await figma.setCurrentPageAsync(p);
const navRef=await figma.getNodeByIdAsync('591:100');
const titleRef=await figma.getNodeByIdAsync('591:73');
const targets=[
 {id:'562:195',active:'서비스 소개',header:'585:79',title:null,positions:{}},
 {id:'562:218',active:'문제 정의',header:'585:85',title:'562:225',positions:{'562:226':306,'562:231':306,'562:256':610,'562:270':936}},
 {id:'562:271',active:'인사이트',header:'585:91',title:'562:278',positions:{'562:279':306,'562:282':306}},
 {id:'575:63',active:'핵심 기능',header:'585:97',title:'580:138',positions:{'580:139':306,'580:149':664,'580:150':728,'580:178':922}},
 {id:'580:179',active:'개발 범위',header:'585:194',title:'580:184',positions:{'580:185':306,'580:188':410,'580:198':772,'580:199':838}},
 {id:'580:210',active:'시스템 구조',header:'585:197',title:'580:215',positions:{'580:216':306,'580:243':744,'580:266':856,'580:269':932}}
];
const roots=await Promise.all(targets.map(t=>figma.getNodeByIdAsync(t.id)));
const fonts=new Map();for(const root of [...roots,navRef]){for(const tx of root.findAllWithCriteria({types:['TEXT']})){for(const s of tx.getStyledTextSegments(['fontName']))fonts.set(JSON.stringify(s.fontName),s.fontName);}}
for(const s of titleRef.getStyledTextSegments(['fontName']))fonts.set(JSON.stringify(s.fontName),s.fontName);
await Promise.all([...fonts.values()].map(f=>figma.loadFontAsync(f)));
const created=new Set(),mutated=new Set();
function mark(n){mutated.add(n.id);return n;}
function clone(ref,parent,name){let n=parent.children.find(c=>c.name===name);if(!n){n=ref.clone();parent.appendChild(n);created.add(n.id);for(const c of n.findAll(()=>true))created.add(c.id);n.name=name;}else mark(n);return n;}
const refActive=navRef.children.find(n=>n.name==='내비게이션 / 인사이트');
const refInactive=navRef.children.find(n=>n.name==='내비게이션 / 문제 정의');
const activeTx=refActive.findOne(n=>n.type==='TEXT'),inactiveTx=refInactive.findOne(n=>n.type==='TEXT');
for(let i=0;i<targets.length;i++){
 const cfg=targets[i],root=roots[i];
 const header=await figma.getNodeByIdAsync(cfg.header);mark(header).visible=false;
 for(const n of root.children){if(n.name==='공통 형식 / 상단선'||n.name==='공통 형식 / 하단 로고'||(n.type==='TEXT'&&n.characters==='seelo'))mark(n).visible=false;}
 if(cfg.id==='562:218')mark(await figma.getNodeByIdAsync('587:842')).visible=false;
 if(cfg.title){const t=await figma.getNodeByIdAsync(cfg.title);mark(t);t.fontName=titleRef.fontName;t.fontSize=titleRef.fontSize;t.lineHeight=titleRef.lineHeight;t.letterSpacing=titleRef.letterSpacing;t.fills=titleRef.fills;t.textAutoResize='NONE';t.resize(titleRef.width,titleRef.height);t.x=titleRef.x;t.y=titleRef.y;}
 for(const [id,y]of Object.entries(cfg.positions)){const n=await figma.getNodeByIdAsync(id);mark(n).y=y;}
 const nav=clone(navRef,root,'공통 내비게이션 / 수동 편집');mark(nav);nav.x=navRef.x;nav.y=navRef.y;nav.visible=true;
 for(const tab of nav.children.filter(n=>n.type==='FRAME')){const tx=tab.findOne(n=>n.type==='TEXT');const selected=tx.characters===cfg.active;mark(tab);tab.fills=selected?refActive.fills:refInactive.fills;mark(tx);tx.fontName=selected?activeTx.fontName:inactiveTx.fontName;tx.fills=selected?activeTx.fills:inactiveTx.fills;}
 if(cfg.id==='562:195'){
   const source=await figma.getNodeByIdAsync('585:81');let author=root.children.find(n=>n.name==='발표 정보 / 표지 하단');
   if(!author){author=source.clone();root.appendChild(author);created.add(author.id);author.name='발표 정보 / 표지 하단';}
   mark(author);author.x=114;author.y=1000;author.resize(1250,44);author.textAutoResize='NONE';author.visible=true;
 }
}
mark(await figma.getNodeByIdAsync('582:837')).visible=false;
function isVisible(n,root){let cur=n;while(cur&&cur.id!==root.id){if(!cur.visible)return false;cur=cur.parent;}return true;}
const audit=[];
for(let i=0;i<roots.length;i++){
 const root=roots[i],all=root.findAll(()=>true),shown=all.filter(n=>isVisible(n,root)),texts=shown.filter(n=>n.type==='TEXT'&&n.characters.trim()),bb=root.absoluteBoundingBox,overlaps=[];
 for(let a=0;a<texts.length;a++)for(let b=a+1;b<texts.length;b++){const x=texts[a].absoluteBoundingBox,y=texts[b].absoluteBoundingBox;if(Math.min(x.x+x.width,y.x+y.width)-Math.max(x.x,y.x)>2&&Math.min(x.y+x.height,y.y+y.height)-Math.max(x.y,y.y)>2)overlaps.push([texts[a].id,texts[b].id]);}
 const nav=root.children.find(n=>n.name==='공통 내비게이션 / 수동 편집');
 audit.push({id:root.id,name:root.name,navId:nav.id,activeMenu:targets[i].active,overlaps,missingFonts:texts.filter(t=>t.hasMissingFont).map(n=>n.id),outside:texts.filter(t=>{const b=t.absoluteBoundingBox;return b.x<bb.x-1||b.y<bb.y-1||b.x+b.width>bb.x+bb.width+1||b.y+b.height>bb.y+bb.height+1;}).map(n=>n.id),autoLayout:all.filter(n=>'layoutMode'in n&&n.layoutMode!=='NONE').length,hugOrFill:all.filter(n=>['HUG','FILL'].includes(n.layoutSizingHorizontal)||['HUG','FILL'].includes(n.layoutSizingVertical)).length,instances:all.filter(n=>n.type==='INSTANCE').length});
}
return {createdNodeIds:[...created],mutatedNodeIds:[...mutated],audit,sourceNavigation:'591:100',frames:targets.map(t=>({id:t.id,active:t.active})),comparisonPreserved:'591:66'};

