const page=await figma.getNodeByIdAsync('12:2');await figma.setCurrentPageAsync(page);
const roots=await Promise.all(['562:189','575:138'].map(id=>figma.getNodeByIdAsync(id)));
const created=new Set(),mutated=new Set(),detached=[],changedFonts=[],heightChanges=[];
const fontMap=new Map();
for(const root of roots)for(const t of root.findAllWithCriteria({types:['TEXT']}))for(const s of t.getStyledTextSegments(['fontName']))fontMap.set(JSON.stringify(s.fontName),s.fontName);
await Promise.all([...fontMap.values(),...['Regular','Medium','SemiBold','Bold'].map(style=>({family:'IBM Plex Sans KR',style})),...['Medium','SemiBold','Bold'].map(style=>({family:'Plus Jakarta Sans',style}))].map(f=>figma.loadFontAsync(f)));
function instanceParent(n,root){let p=n.parent;while(p&&p.id!==root.id){if(p.type==='INSTANCE')return true;p=p.parent;}return false;}

for(const root of roots){
  // 연결 인스턴스를 일반 프레임으로 바꾼 뒤, 새 ID를 다시 조회한다.
  while(true){
    const instances=root.findAllWithCriteria({types:['INSTANCE']});if(!instances.length)break;
    const n=instances.find(n=>!instanceParent(n,root));if(!n)throw new Error('Instance tree did not resolve');
    const id=n.id,name=n.name,f=n.detachInstance();detached.push({oldId:id,newId:f.id,name});created.add(f.id);for(const d of f.findAll(()=>true))created.add(d.id);
  }
  const all=root.findAll(()=>true);
  const original=all.map(n=>({node:n,id:n.id,x:n.x,y:n.y,w:n.width,h:n.height,transform:n.relativeTransform,text:n.type==='TEXT'?n.characters:null}));
  // 모든 오토레이아웃을 먼저 해제하고, 그 전의 배치와 크기를 되돌린다.
  for(const n of all)if('layoutMode'in n&&n.layoutMode!=='NONE'){n.layoutMode='NONE';mutated.add(n.id);}
  for(const s of original){const n=s.node;if(n.type==='TEXT')n.textAutoResize='NONE';if('resize'in n&&n.type!=='VECTOR'&&n.type!=='LINE')n.resize(s.w,s.h);if('constraints'in n)n.constraints={horizontal:'MIN',vertical:'MIN'};if('minWidth'in n){n.minWidth=null;n.maxWidth=null;n.minHeight=null;n.maxHeight=null;}mutated.add(n.id);}
  for(const s of original)s.node.relativeTransform=s.transform;
  const shifted=original.filter(s=>Math.abs(s.node.x-s.x)>.02||Math.abs(s.node.y-s.y)>.02||Math.abs(s.node.width-s.w)>.02||Math.abs(s.node.height-s.h)>.02).map(s=>s.id);
  if(shifted.length)throw new Error('Layout drift before font conversion: '+shifted.join(','));

  for(const s of original){
    const t=s.node;if(t.type!=='TEXT')continue;
    const segments=t.getStyledTextSegments(['fontName','fontSize']);
    const numeric=/^[\d\s.,_%+:/–→×\-]+$/.test(t.characters)&&/\d|_/.test(t.characters);
    for(const seg of segments){
      if(seg.fontName.family==='Pacifico')continue;
      const family=numeric?'Plus Jakarta Sans':'IBM Plex Sans KR';
      const oldStyle=seg.fontName.style;
      const style=/Bold|Black|Heavy/i.test(oldStyle)?(seg.fontSize>=60?'Bold':'SemiBold'):/Medium/i.test(oldStyle)?'Medium':'Regular';
      t.setRangeFontName(seg.start,seg.end,{family,style});changedFonts.push({id:t.id,start:seg.start,end:seg.end,from:seg.fontName.family,to:family,style});
    }
    if(!segments.length&&t.fontName.family!=='Pacifico')t.fontName={family:'IBM Plex Sans KR',style:'Regular'};
    // 새 서체의 필요한 높이를 확인한 뒤 고정 텍스트 박스로 전환한다.
    t.textAutoResize='HEIGHT';const required=t.height;
    t.textAutoResize='NONE';t.resize(s.w,Math.max(s.h,required));t.x=s.x;t.y=s.y;
    if(required>s.h+.5)heightChanges.push({id:t.id,oldHeight:s.h,newHeight:required,text:t.characters});
    if(t.characters!==s.text)throw new Error('Text changed: '+t.id);
    mutated.add(t.id);
  }
}
function visible(n,root){while(n&&n.id!==root.id){if(!n.visible)return false;n=n.parent;}return true;}
const audit=[];
for(const root of roots){
  const nodes=root.findAll(()=>true),texts=nodes.filter(n=>n.type==='TEXT');
  const fs=root.children.filter(n=>n.type==='FRAME');
  const frames=[];for(const f of fs){const ts=f.findAllWithCriteria({types:['TEXT']}).filter(t=>visible(t,f)&&t.characters.trim()),overlap=[];for(let a=0;a<ts.length;a++)for(let b=a+1;b<ts.length;b++){const aa=ts[a].absoluteBoundingBox,bb=ts[b].absoluteBoundingBox;if(Math.min(aa.x+aa.width,bb.x+bb.width)-Math.max(aa.x,bb.x)>2&&Math.min(aa.y+aa.height,bb.y+bb.height)-Math.max(aa.y,bb.y)>2)overlap.push([ts[a].id,ts[b].id]);}const box=f.absoluteBoundingBox;frames.push({id:f.id,name:f.name,overlap,outside:ts.filter(t=>{const b=t.absoluteBoundingBox;return b.x<box.x-1||b.y<box.y-1||b.x+b.width>box.x+box.width+1||b.y+b.height>box.y+box.height+1;}).map(t=>({id:t.id,text:t.characters}))});}
  audit.push({id:root.id,name:root.name,autoLayout:nodes.filter(n=>'layoutMode'in n&&n.layoutMode!=='NONE').map(n=>n.id),instances:nodes.filter(n=>n.type==='INSTANCE').map(n=>n.id),hugOrFill:nodes.filter(n=>['HUG','FILL'].includes(n.layoutSizingHorizontal)||['HUG','FILL'].includes(n.layoutSizingVertical)).map(n=>n.id),autoText:texts.filter(n=>n.textAutoResize!=='NONE').map(n=>n.id),missingFonts:texts.filter(n=>n.hasMissingFont).map(n=>n.id),families:[...new Set(texts.flatMap(t=>t.getStyledTextSegments(['fontName']).map(s=>s.fontName.family)))],frames});
}
return{createdNodeIds:[...created],mutatedNodeIds:[...mutated],detached,changedFontCount:changedFonts.length,heightChanges,audit,bodyFont:'IBM Plex Sans KR',numericFont:'Plus Jakarta Sans',wordmarkFont:'Pacifico',unchangedText:true};
