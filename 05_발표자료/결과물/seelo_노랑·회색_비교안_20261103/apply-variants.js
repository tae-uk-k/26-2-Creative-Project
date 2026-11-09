
const page=await figma.getNodeByIdAsync('12:2');await figma.setCurrentPageAsync(page);
const source=await figma.getNodeByIdAsync('562:189');
const names=['seelo · A · FFC54F 브랜드 컬러 · 9장','seelo · B · 회색 카드 미세조정 · 9장'];
for(const name of names)if(page.children.some(n=>n.name===name))throw new Error('동일 이름의 비교안이 이미 있습니다: '+name);
const fontMap=new Map();for(const t of source.findAllWithCriteria({types:['TEXT']}))for(const s of t.getStyledTextSegments(['fontName']))fontMap.set(JSON.stringify(s.fontName),s.fontName);
await Promise.all([...fontMap.values()].map(f=>figma.loadFontAsync(f)));
const created=[],changedA=[],changedB=[];
const A=source.clone();A.name=names[0];A.x=source.x+source.width+320;A.y=source.y;
const B=source.clone();B.name=names[1];B.x=A.x+A.width+320;B.y=source.y;
for(const n of [A,...A.findAll(()=>true),B,...B.findAll(()=>true)])created.push(n.id);
function rgb(hex){return{r:parseInt(hex.slice(0,2),16)/255,g:parseInt(hex.slice(2,4),16)/255,b:parseInt(hex.slice(4,6),16)/255};}
const C={key:rgb('FFC54F'),ink:rgb('26231D'),amber:rgb('8C6415'),gold:rgb('C88C12'),soft:rgb('FFF2D5'),paper:rgb('FAF9F6')};
const paint=(color,opacity=1)=>[{type:'SOLID',color,opacity}];
function native(n,root){let x=n;while(x&&x.id!==root.id){if(x.name.startsWith('원본 화면 /'))return true;x=x.parent;}return false;}
function shown(n,root){let x=n;while(x&&x.id!==root.id){if(!x.visible)return false;x=x.parent;}return true;}
function blue(c,strict=false){if(!c)return false;const mx=Math.max(c.r,c.g,c.b),mn=Math.min(c.r,c.g,c.b),l=(mx+mn)/2,s=mx===mn?0:(mx-mn)/(1-Math.abs(2*l-1));return c.b>c.r+(strict?.18:.025)&&c.b>c.g+.005&&(strict||s>.25);}
function warm(c){const mx=Math.max(c.r,c.g,c.b),mn=Math.min(c.r,c.g,c.b),l=(mx+mn)/2,s=.72;const a=s*Math.min(l,1-l);const f=n=>{const k=(n+42/30)%12;return l-a*Math.max(-1,Math.min(k-3,9-k,1));};return{r:f(0),g:f(8),b:f(4)};}
function grayPanel(n){if(n.type!=='FRAME'||!Array.isArray(n.fills))return false;return n.fills.some(p=>p.type==='SOLID'&&Math.abs(p.color.r-242/255)<.004&&Math.abs(p.color.g-244/255)<.004&&Math.abs(p.color.b-246/255)<.004);}
function recolorPaint(p,kind){let q=JSON.parse(JSON.stringify(p));let changed=false;if(q.type==='SOLID'&&blue(q.color,kind==='TEXT')){q.color=kind==='TEXT'?C.ink:kind==='RULE'?C.key:C.gold;changed=true;}else if(q.type.startsWith('GRADIENT')){q.gradientStops=q.gradientStops.map(s=>{if(!blue(s.color))return s;changed=true;return{...s,color:{...warm(s.color),a:s.color.a}};});}if(changed&&q.boundVariables){delete q.boundVariables.color;if(!Object.keys(q.boundVariables).length)delete q.boundVariables;}return{p:q,changed};}

// A: 컬러만으로 읽기 위계를 만드는 브랜드 컬러 버전.
for(const n of A.findAll(()=>true)){
 if(!shown(n,A)||native(n,A))continue;
 if(n.type==='TEXT'){let hit=false;const segments=n.getStyledTextSegments(['fills']);for(const s of segments){const out=s.fills.map(p=>recolorPaint(p,'TEXT'));if(out.some(x=>x.changed)){n.setRangeFills(s.start,s.end,out.map(x=>x.p));hit=true;}}if(hit)changedA.push(n.id);continue;}
 let hit=false;
 for(const field of ['fills','strokes']){if(!(field in n)||!Array.isArray(n[field]))continue;const out=n[field].map(p=>recolorPaint(p,n.type==='VECTOR'&&n.width>1200?'RULE':'SHAPE'));if(out.some(x=>x.changed)){n[field]=out.map(x=>x.p);hit=true;}}
 if(grayPanel(n)){n.fills=paint(C.paper);hit=true;}
 if(n.type==='FRAME'&&n.name.startsWith('내비게이션 /')&&n.fills.length){n.fills=paint(C.key);for(const t of n.findAllWithCriteria({types:['TEXT']})){t.fills=paint(C.ink);changedA.push(t.id);}hit=true;}
 if(hit)changedA.push(n.id);
}
const aFrames=A.children.filter(n=>n.type==='FRAME'),bFrames=B.children.filter(n=>n.type==='FRAME');
const primaryNames=['문제 1 · AI 탐색','가치제안','핵심 기능 · 지도 정보 대신 수정','베타 범위','ERD / measurement_runs'];
for(const f of aFrames)for(const n of f.findAll(x=>x.type==='FRAME'&&primaryNames.includes(x.name)&&shown(x,A)&&!native(x,A))){n.fills=paint(C.soft);changedA.push(n.id);}
const cover=aFrames.find(f=>f.name.startsWith('01'));
const hero=cover.children.find(n=>n.type==='FRAME'&&n.name==='서비스 소개');
if(hero){const band=figma.createRectangle();hero.insertChild(0,band);created.push(band.id);band.name='브랜드 옐로 / 제목 강조';band.x=0;band.y=194;band.resize(842,22);band.cornerRadius=7;band.fills=paint(C.key,.88);band.strokes=[];}

// B: 기존 색·내용·배치를 유지하고 회색 카드의 표면만 정돈한다.
for(const n of B.findAll(()=>true)){
 if(!shown(n,B)||native(n,B)||!grayPanel(n)||n.name.startsWith('내비게이션 /')||n.height<70||n.width<250)continue;
 n.fills=[{type:'GRADIENT_LINEAR',gradientTransform:[[0,1,0],[-1,0,1]],gradientStops:[{position:0,color:{...rgb('F9FAFC'),a:1}},{position:1,color:{...rgb('F2F4F7'),a:1}}],opacity:1}];
 n.cornerRadius=Math.min(n.cornerRadius===figma.mixed?24:n.cornerRadius,24);
 n.strokes=[{type:'SOLID',color:rgb('E4E9EF'),opacity:.72}];n.strokeWeight=1;n.strokeAlign='INSIDE';
 n.effects=[{type:'DROP_SHADOW',color:{r:.13,g:.17,b:.23,a:.035},offset:{x:0,y:5},radius:18,spread:0,visible:true,blendMode:'NORMAL'}];
 changedB.push(n.id);
}
function sig(n){let out={id:n.id,name:n.name,type:n.type,visible:n.visible,x:n.x,y:n.y,w:n.width,h:n.height};for(const k of ['fills','strokes','effects','opacity','cornerRadius','layoutMode'])if(k in n)out[k]=n[k];if(n.type==='TEXT'){out.text=n.characters;out.font=n.fontName;out.size=n.fontSize;out.ranges=n.getStyledTextSegments(['fontName','fills','fontSize']);}return out;}
function hash(root){const value=JSON.stringify([root,...root.findAll(()=>true)].map(sig));let h=2166136261;for(let i=0;i<value.length;i++){h^=value.charCodeAt(i);h=Math.imul(h,16777619);}return(h>>>0).toString(16);}
const originals=source.children.filter(n=>n.type==='FRAME');
const audits=[];
for(const [label,root,frames]of [['A',A,aFrames],['B',B,bFrames]]){
 for(let i=0;i<frames.length;i++){
  const f=frames[i],all=f.findAll(()=>true),oTexts=originals[i].findAllWithCriteria({types:['TEXT']}),texts=f.findAllWithCriteria({types:['TEXT']});
  const copyPreserved=oTexts.length===texts.length&&oTexts.every((t,j)=>t.characters===texts[j].characters);
  audits.push({variant:label,id:f.id,name:f.name,copyPreserved,autoLayout:all.filter(n=>'layoutMode'in n&&n.layoutMode!=='NONE').length,hugOrFill:all.filter(n=>['HUG','FILL'].includes(n.layoutSizingHorizontal)||['HUG','FILL'].includes(n.layoutSizingVertical)).length,instances:all.filter(n=>n.type==='INSTANCE').length,missingFonts:texts.filter(t=>t.hasMissingFont).map(t=>t.id)});
 }
}
return{createdNodeIds:created,mutatedOriginalNodeIds:[],originalSignature:hash(source),originalNodeCount:1+source.findAll(()=>true).length,versions:[{variant:'A',id:A.id,name:A.name,x:A.x,y:A.y,frames:aFrames.map(f=>({id:f.id,name:f.name})),styledNodes:changedA.length},{variant:'B',id:B.id,name:B.name,x:B.x,y:B.y,frames:bFrames.map(f=>({id:f.id,name:f.name})),styledNodes:changedB.length}],audit:audits};

