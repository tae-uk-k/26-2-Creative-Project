
const page=await figma.getNodeByIdAsync('12:2');await figma.setCurrentPageAsync(page);
const original=await figma.getNodeByIdAsync('562:189'),current=await figma.getNodeByIdAsync('613:53');
const restoreName='seelo · C · 처음 노란색 복원 · 9장';
if(page.children.some(n=>n.name===restoreName))throw new Error('복원안이 이미 존재함');
const fonts=new Map();for(const root of [original,current])for(const t of root.findAllWithCriteria({types:['TEXT']}))for(const s of t.getStyledTextSegments(['fontName']))fonts.set(JSON.stringify(s.fontName),s.fontName);await Promise.all([...fonts.values()].map(f=>figma.loadFontAsync(f)));
const created=[],mutated=new Set();const R=original.clone();R.name=restoreName;
let x=current.x+current.width+320,y=current.y;
const overlaps=(x,y,w,h,n)=>Math.min(x+w,n.x+n.width)-Math.max(x,n.x)>0&&Math.min(y+h,n.y+n.height)-Math.max(y,n.y)>0;
while(page.children.some(n=>n.id!==R.id&&typeof n.x==='number'&&overlaps(x,y,R.width,R.height,n)))x+=R.width+320;
R.x=x;R.y=y;created.push(R.id,...R.findAll(()=>true).map(n=>n.id));
const rgb=h=>({r:parseInt(h.slice(0,2),16)/255,g:parseInt(h.slice(2,4),16)/255,b:parseInt(h.slice(4,6),16)/255});
const C={key:rgb('FFC54F'),ink:rgb('26231D'),gold:rgb('C88C12'),soft:rgb('FFF2D5'),paper:rgb('FAF9F6')};
const solid=(c,o=1)=>[{type:'SOLID',color:c,opacity:o}];
function native(n,root){let q=n;while(q&&q.id!==root.id){if(q.name.startsWith('원본 화면 /'))return true;q=q.parent;}return false;}
function shown(n,root){let q=n;while(q&&q.id!==root.id){if(!q.visible)return false;q=q.parent;}return true;}
function isBlue(c,strict=false){if(!c)return false;const mx=Math.max(c.r,c.g,c.b),mn=Math.min(c.r,c.g,c.b),l=(mx+mn)/2,s=mx===mn?0:(mx-mn)/(1-Math.abs(2*l-1));return c.b>c.r+(strict?.18:.025)&&c.b>c.g+.005&&(strict||s>.25);}
function warm(c){const l=(Math.max(c.r,c.g,c.b)+Math.min(c.r,c.g,c.b))/2,a=.72*Math.min(l,1-l);const f=n=>{const k=(n+42/30)%12;return l-a*Math.max(-1,Math.min(k-3,9-k,1));};return{r:f(0),g:f(8),b:f(4)};}
function mapPaint(p,kind,isCover){const q=JSON.parse(JSON.stringify(p));let hit=false;if(q.type==='SOLID'&&isBlue(q.color,kind==='TEXT')){const l=(Math.max(q.color.r,q.color.g,q.color.b)+Math.min(q.color.r,q.color.g,q.color.b))/2;q.color=kind==='TEXT'?C.ink:kind==='RULE'?C.key:isCover&&l>.7?warm(q.color):C.gold;hit=true;}else if(q.type.startsWith('GRADIENT'))q.gradientStops=q.gradientStops.map(s=>{if(!isBlue(s.color))return s;hit=true;return{...s,color:{...warm(s.color),a:s.color.a}};});if(hit&&q.boundVariables){delete q.boundVariables.color;if(!Object.keys(q.boundVariables).length)delete q.boundVariables;}return{p:q,hit};}
function isGray(n){return n.type==='FRAME'&&Array.isArray(n.fills)&&n.fills.some(p=>p.type==='SOLID'&&Math.abs(p.color.r-242/255)<.004&&Math.abs(p.color.g-244/255)<.004);}
const frames=R.children.filter(n=>n.type==='FRAME'),cover=frames.find(n=>n.name.startsWith('01'));
function inCover(n){let q=n;while(q&&q.id!==R.id){if(q.id===cover.id)return true;q=q.parent;}return false;}
for(const n of R.findAll(()=>true)){
 if(!shown(n,R)||native(n,R))continue;
 if(n.type==='TEXT'){for(const s of n.getStyledTextSegments(['fills'])){const out=s.fills.map(p=>mapPaint(p,'TEXT',inCover(n)));if(out.some(x=>x.hit))n.setRangeFills(s.start,s.end,out.map(x=>x.p));}continue;}
 for(const field of ['fills','strokes'])if(field in n&&Array.isArray(n[field])){const out=n[field].map(p=>mapPaint(p,n.type==='VECTOR'&&n.width>1200?'RULE':'SHAPE',inCover(n)));if(out.some(x=>x.hit))n[field]=out.map(x=>x.p);}
 if(isGray(n))n.fills=solid(C.paper);
 if(n.type==='FRAME'&&n.name.startsWith('내비게이션 /')&&n.fills.length){n.fills=solid(C.key);for(const t of n.findAllWithCriteria({types:['TEXT']}))t.fills=solid(C.ink);}
}
const primaryNames=['문제 1 · AI 탐색','가치제안','핵심 기능 · 지도 정보 대신 수정','베타 범위','ERD / measurement_runs'];
for(const f of frames)for(const n of f.findAll(n=>n.type==='FRAME'&&primaryNames.includes(n.name)&&shown(n,R)&&!native(n,R)))n.fills=solid(C.soft);
const hero=cover.children.find(n=>n.type==='FRAME'&&n.name==='서비스 소개');
const band=figma.createRectangle();hero.insertChild(0,band);created.push(band.id);band.name='브랜드 옐로 / 제목 강조';band.x=0;band.y=194;band.resize(736,22);band.cornerRadius=7;band.fills=solid(C.key,.88);band.strokes=[];

// 복원본을 기존 노란색 레이어 ID로 정규화해 첫 시안의 저장된 서명과 대조.
const oldIds=new Map();
function match(r,a){if(r.type!==a.type||r.name!==a.name)throw new Error('복원 구조 불일치 '+r.id);oldIds.set(r.id,a.id);if('children'in r){if(r.children.length!==a.children.length)throw new Error('복원 자식 수 불일치');for(let i=0;i<r.children.length;i++)match(r.children[i],a.children[i]);}}
oldIds.set(R.id,current.id);for(let i=0;i<R.children.length;i++)match(R.children[i],current.children[i]);
function sig(n,normalized=false){let out={id:normalized?oldIds.get(n.id):n.id,name:normalized&&n.id===R.id?current.name:n.name,type:n.type,visible:n.visible,x:normalized&&n.id===R.id?current.x:n.x,y:normalized&&n.id===R.id?current.y:n.y,w:n.width,h:n.height};for(const k of ['fills','strokes','effects','opacity','cornerRadius','layoutMode'])if(k in n)out[k]=n[k];if(n.type==='TEXT'){out.text=n.characters;out.font=n.fontName;out.size=n.fontSize;out.ranges=n.getStyledTextSegments(['fontName','fills','fontSize']);}return out;}
function hash(root,normalized=false){const value=JSON.stringify([root,...root.findAll(()=>true)].map(n=>sig(n,normalized)));let h=2166136261;for(let i=0;i<value.length;i++){h^=value.charCodeAt(i);h=Math.imul(h,16777619);}return(h>>>0).toString(16);}
const restoredNormalizedSignature=hash(R,true);

// 현재 안의 어두운 노랑만 선명한 앰버로 치환.
const old=rgb('DFA61D'),bright=rgb('FFB300');
const same=c=>Math.abs(c.r-old.r)<.0001&&Math.abs(c.g-old.g)<.0001&&Math.abs(c.b-old.b)<.0001;
function vivid(p){const q=JSON.parse(JSON.stringify(p));let hit=false;if(q.type==='SOLID'&&same(q.color)){q.color=bright;hit=true;}else if(q.type.startsWith('GRADIENT'))q.gradientStops=q.gradientStops.map(s=>{if(!same(s.color))return s;hit=true;return{...s,color:{...bright,a:s.color.a}};});if(hit&&q.boundVariables){delete q.boundVariables.color;if(!Object.keys(q.boundVariables).length)delete q.boundVariables;}return{p:q,hit};}
for(const n of current.findAll(()=>true)){
 if(native(n,current))continue;
 if(n.type==='TEXT'){for(const s of n.getStyledTextSegments(['fills'])){const out=s.fills.map(vivid);if(out.some(x=>x.hit)){n.setRangeFills(s.start,s.end,out.map(x=>x.p));mutated.add(n.id);}}}
 else for(const field of ['fills','strokes'])if(field in n&&Array.isArray(n[field])){const out=n[field].map(vivid);if(out.some(x=>x.hit)){n[field]=out.map(x=>x.p);mutated.add(n.id);}}
}
const all=R.findAll(()=>true),texts=all.filter(n=>n.type==='TEXT');
return{createdNodeIds:created,mutatedNodeIds:[...mutated],restored:{id:R.id,name:R.name,x:R.x,y:R.y,frames:frames.map(n=>({id:n.id,name:n.name})),normalizedSignature:restoredNormalizedSignature,firstVersionSignature:'c23b6fe0',exactFirstVersionMatch:restoredNormalizedSignature==='c23b6fe0'},current:{id:current.id,from:'#DFA61D',to:'#FFB300',changedNodes:mutated.size},referenceHashes:{original:hash(original),gray:hash(await figma.getNodeByIdAsync('613:926'))},restoredAudit:{autoLayout:all.filter(n=>'layoutMode'in n&&n.layoutMode!=='NONE').length,hugOrFill:all.filter(n=>['HUG','FILL'].includes(n.layoutSizingHorizontal)||['HUG','FILL'].includes(n.layoutSizingVertical)).length,instances:all.filter(n=>n.type==='INSTANCE').length,missingFonts:texts.filter(n=>n.hasMissingFont).map(n=>n.id)}};

