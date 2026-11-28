
const page=await figma.getNodeByIdAsync('12:2');await figma.setCurrentPageAsync(page);
const A=await figma.getNodeByIdAsync('613:53'),B=await figma.getNodeByIdAsync('613:926');
const pairs=[];
function pair(b,a){if(b.type!==a.type||b.name!==a.name)throw new Error('레이어 불일치 '+b.id+' / '+a.id);if(b.type==='TEXT'&&b.characters!==a.characters)throw new Error('문구가 다른 레이어 '+b.id+' / '+a.id);pairs.push([b,a]);if('children'in b){const ac=a.children.filter(n=>n.name!=='브랜드 옐로 / 제목 강조');if(ac.length!==b.children.length)throw new Error('자식 수 불일치');for(let i=0;i<ac.length;i++)pair(b.children[i],ac[i]);}}
for(let i=0;i<B.children.length;i++)pair(B.children[i],A.children[i]);
const fontMap=new Map();for(const [,a]of pairs)if(a.type==='TEXT')for(const s of a.getStyledTextSegments(['fontName']))fontMap.set(JSON.stringify(s.fontName),s.fontName);await Promise.all([...fontMap.values()].map(f=>figma.loadFontAsync(f)));
const changed=new Set(),grayCards=[],colorNodes=[];
const clone=x=>JSON.parse(JSON.stringify(x));
const rgb=hex=>({r:parseInt(hex.slice(0,2),16)/255,g:parseInt(hex.slice(2,4),16)/255,b:parseInt(hex.slice(4,6),16)/255});
const key=rgb('FFC54F'),deep=rgb('DFA61D');
function isNative(n){let x=n;while(x&&x.id!==B.id){if(x.name.startsWith('원본 화면 /'))return true;x=x.parent;}return false;}
function isBlue(c){if(!c)return false;const mx=Math.max(c.r,c.g,c.b),mn=Math.min(c.r,c.g,c.b),l=(mx+mn)/2;const s=mx===mn?0:(mx-mn)/(1-Math.abs(2*l-1));return c.b>c.r+.025&&c.b>c.g+.005&&s>.30;}
function yellowTone(c){
 const max=Math.max(c.r,c.g,c.b),min=Math.min(c.r,c.g,c.b),l=(max+min)/2;
 if(l<.53)return deep;
 if(l<.72)return key;
 const sat=(max-min)/(1-Math.abs(2*l-1)),a=sat*Math.min(l,1-l),h=40.2;
 const f=n=>{const k=(n+h/30)%12;return l-a*Math.max(-1,Math.min(k-3,9-k,1));};
 return {r:f(0),g:f(8),b:f(4)};
}
function replacePaint(p){const q=clone(p);let hit=false;if(q.type==='SOLID'&&isBlue(q.color)){q.color=yellowTone(q.color);hit=true;}else if(q.type.startsWith('GRADIENT'))q.gradientStops=q.gradientStops.map(s=>{if(!isBlue(s.color))return s;hit=true;const out={...s,color:{...yellowTone(s.color),a:s.color.a}};delete out.boundVariables;return out;});if(hit&&q.boundVariables){delete q.boundVariables.color;if(!Object.keys(q.boundVariables).length)delete q.boundVariables;}return{paint:q,hit};}
function grayCard(b){return b.type==='FRAME'&&Array.isArray(b.effects)&&b.effects.some(e=>e.type==='DROP_SHADOW'&&Math.abs(e.color.a-.035)<.002)&&Array.isArray(b.fills)&&b.fills.some(f=>f.type==='GRADIENT_LINEAR');}
for(const[b,a]of pairs){
 if(isNative(b))continue;
 changed.add(a.id);
 if(b.type==='TEXT'){
  for(const seg of b.getStyledTextSegments(['fills'])){const out=seg.fills.map(replacePaint);a.setRangeFills(seg.start,seg.end,out.map(x=>x.paint));if(out.some(x=>x.hit))colorNodes.push(a.id);}
  continue;
 }
 const card=grayCard(b);
 for(const field of ['fills','strokes'])if(field in b&&Array.isArray(b[field])){
  if(card)a[field]=clone(b[field]);
  else {const out=b[field].map(replacePaint);a[field]=out.map(x=>x.paint);if(out.some(x=>x.hit))colorNodes.push(a.id);}
 }
 if('effects'in b)a.effects=clone(b.effects);
 if('strokeWeight'in b&&typeof b.strokeWeight==='number')a.strokeWeight=b.strokeWeight;
 if('strokeAlign'in b)a.strokeAlign=b.strokeAlign;
 if('cornerRadius'in b){if(typeof b.cornerRadius==='number')a.cornerRadius=b.cornerRadius;else for(const k of ['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius'])a[k]=b[k];}
 if(card)grayCards.push({reference:b.id,target:a.id});
}
const band=A.findOne(n=>n.name==='브랜드 옐로 / 제목 강조');if(band){band.visible=false;changed.add(band.id);}
const cardDifferences=[];
for(const{reference,target}of grayCards){const b=await figma.getNodeByIdAsync(reference),a=await figma.getNodeByIdAsync(target);for(const key of ['fills','strokes','effects','cornerRadius','strokeWeight'])if(JSON.stringify(b[key])!==JSON.stringify(a[key]))cardDifferences.push({id:a.id,field:key});}
return{createdNodeIds:[],mutatedNodeIds:[...changed],yellowSection:A.id,grayReference:B.id,matchedGrayCards:grayCards.length,cardDifferences,colorNodeCount:[...new Set(colorNodes)].length,palette:{key:'#FFC54F',deep:'#DFA61D',pale:'원본 파란색 명도와 투명도를 따라 옅은 노란색으로 변환'},extraHighlightHidden:band?.id,unchangedReferences:['562:189','613:926']};

