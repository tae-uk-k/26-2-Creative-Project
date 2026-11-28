const page=await figma.getNodeByIdAsync('12:2');await figma.setCurrentPageAsync(page);
const section=await figma.getNodeByIdAsync('562:189');
if(section.children.some(n=>n.name==='04 · 자동정비'))return{alreadyExists:true,createdNodeIds:[],mutatedNodeIds:[]};
const created=[],mutated=new Set(),copyMap=[];
const keep=n=>{created.push(n.id);return n;};
const mutate=n=>{mutated.add(n.id);return n;};
const current=section.findAllWithCriteria({types:['TEXT']});const fontMap=new Map();
for(const t of current)for(const f of t.getStyledTextSegments(['fontName']))fontMap.set(JSON.stringify(f.fontName),f.fontName);
for(const f of fontMap.values())await figma.loadFontAsync(f);
await Promise.all(['Regular','Medium','Bold'].map(style=>figma.loadFontAsync({family:'Noto Sans KR',style})));
await figma.loadFontAsync({family:'Pacifico',style:'Regular'});
const rgb=h=>({r:parseInt(h.slice(1,3),16)/255,g:parseInt(h.slice(3,5),16)/255,b:parseInt(h.slice(5,7),16)/255});
const solid=(h,a=1)=>({type:'SOLID',color:rgb(h),opacity:a});
const palette={white:solid('#ffffff'),ink:solid('#191f28'),body:solid('#333d4b'),secondary:solid('#4e5968'),line:solid('#e5e8eb'),blue:solid('#3182f6'),soft:solid('#f2f4f6')};
const bindIds={white:'VariableID:562:176',ink:'VariableID:562:177',body:'VariableID:562:178',secondary:'VariableID:562:179',line:'VariableID:562:180',blue:'VariableID:562:181',soft:'VariableID:562:182'};
for(const [key,id]of Object.entries(bindIds)){const v=await figma.variables.getVariableByIdAsync(id);palette[key]=figma.variables.setBoundVariableForPaint(palette[key],'color',v);}
function rect(p,name,x,y,w,h,paint=palette.soft,r=0){const n=keep(figma.createRectangle());p.appendChild(n);n.name=name;n.x=x;n.y=y;n.resize(w,h);n.fills=[paint];n.cornerRadius=r;return n;}
function frame(p,name,x,y,w,h,paint=null,r=0){const n=keep(figma.createFrame());p.appendChild(n);n.name=name;n.x=x;n.y=y;n.resize(w,h);n.fills=paint?[paint]:[];n.cornerRadius=r;n.clipsContent=false;return n;}
function stack(p,name,x,y,w,h,dir='VERTICAL',gap=0,pad=0,paint=null,r=0){const n=keep(figma.createAutoLayout(dir));p.appendChild(n);n.name=name;n.resize(w,h);n.primaryAxisSizingMode='FIXED';n.counterAxisSizingMode='FIXED';n.itemSpacing=gap;n.paddingLeft=pad;n.paddingRight=pad;n.paddingTop=pad;n.paddingBottom=pad;n.fills=paint?[paint]:[];n.cornerRadius=r;n.x=x;n.y=y;n.clipsContent=false;return n;}
function text(p,value,w,size=32,weight='Regular',paint=palette.ink,opts={}){const n=keep(figma.createText());p.appendChild(n);n.name=opts.name||value.replace(/\n/g,' ');n.fontName={family:opts.family||'Noto Sans KR',style:weight};n.fontSize=size;n.lineHeight={unit:'PIXELS',value:opts.leading||size*1.5};n.letterSpacing={unit:'PERCENT',value:-1.5};n.fills=[paint];n.resize(w,1);n.characters=value;n.textAlignHorizontal=opts.align||'LEFT';n.textAutoResize='HEIGHT';if(opts.x!==undefined)n.x=opts.x;if(opts.y!==undefined)n.y=opts.y;return n;}
function update(n,value,w,size,weight='Regular',paint=palette.ink,leading=null){mutate(n);n.fontName={family:'Noto Sans KR',style:weight};n.fontSize=size;n.lineHeight={unit:'PIXELS',value:leading||size*1.5};n.fills=[paint];n.resize(w,1);n.characters=value;n.textAutoResize='HEIGHT';return n;}
function range(n,phrase,size,paint=palette.ink){const i=n.characters.indexOf(phrase);if(i<0)throw new Error('Missing emphasis '+phrase);n.setRangeFontName(i,i+phrase.length,{family:'Noto Sans KR',style:'Bold'});n.setRangeFontSize(i,i+phrase.length,size);n.setRangeFills(i,i+phrase.length,[paint]);mutate(n);}
function svg(p,source,name,x,y){const n=figma.createNodeFromSvg(source);created.push(n.id,...n.findAll(()=>true).map(v=>v.id));p.appendChild(n);n.name=name;n.x=x;n.y=y;return n;}
function icon(p,kind,x,y,size=32,color='#3182f6'){
 const paths={check:'<path d="m5 12 5 5L20 6"/>',arrow:'<path d="M5 12h14M12 5l7 7-7 7"/>'};
 return svg(p,'<svg xmlns="http://www.w3.org/2000/svg" width="'+size+'" height="'+size+'" viewBox="0 0 24 24" fill="none" stroke="'+color+'" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+paths[kind]+'</svg>','도식 / '+kind,x,y);
}
const shadow=[{type:'DROP_SHADOW',color:{r:.05,g:.15,b:.3,a:.05},offset:{x:0,y:2},radius:8,visible:true,blendMode:'NORMAL'},{type:'DROP_SHADOW',color:{r:.05,g:.15,b:.3,a:.09},offset:{x:0,y:22},radius:42,visible:true,blendMode:'NORMAL'}];
function gradient(a,b,alpha=1,beta=1){return{type:'GRADIENT_LINEAR',gradientTransform:[[.8,.6,0],[-.6,.8,.3]],gradientStops:[{position:0,color:{...rgb(a),a:alpha}},{position:1,color:{...rgb(b),a:beta}}]};}
function ellipse(p,name,x,y,w,h,paint){const e=keep(figma.createEllipse());p.appendChild(e);e.name=name;e.resize(w,h);e.x=x;e.y=y;e.fills=[paint];return e;}

// 이름은 표지에만. 기존 표지에서 사용자가 지운 내용은 유지한다.
for(const id of ['562:199','562:222','562:275']){const n=await figma.getNodeByIdAsync(id);mutate(n).visible=false;}
for(const id of ['I562:219;562:192','I562:272;562:192']){const n=await figma.getNodeByIdAsync(id);mutate(n).visible=false;}
const coverMeta=await figma.getNodeByIdAsync('I562:196;562:192');mutate(coverMeta);coverMeta.resize(760,1);coverMeta.textAutoResize='HEIGHT';
for(const [id,num]of [['562:201','01'],['562:224','02'],['562:277','03']]){const n=await figma.getNodeByIdAsync(id);update(n,num+' / 04',200,30,'Medium',palette.body,45);}
section.name='seelo · Toss · 4페이지 · 20261103';section.resizeWithoutConstraints(8280,1280);mutate(section);

// 01 — 새로운 카피를 넣지 않고, 기존 제목과 사용자가 남긴 설명의 대비를 조정.
const cover=await figma.getNodeByIdAsync('562:195');
const hero=await figma.getNodeByIdAsync('562:202');mutate(hero);hero.resize(940,510);hero.x=128;hero.y=292;hero.itemSpacing=36;
const deletedLabel=await figma.getNodeByIdAsync('562:203');if(deletedLabel)mutate(deletedLabel).visible=false;
const coverTitle=await figma.getNodeByIdAsync('562:204');update(coverTitle,coverTitle.characters,940,84,'Bold',palette.ink,112);range(coverTitle,'가게 정보를 고칩니다.',84,palette.blue);
const coverBody=await figma.getNodeByIdAsync('562:205');update(coverBody,coverBody.characters,840,34,'Regular',palette.secondary,54);

function shop(p,x,y,isGlass){
 const root=frame(p,isGlass?'유리 가게 · 편집 가능한 입체 도형':'솔리드 가게 · 편집 가능한 입체 도형',x,y,700,700);
 const ground=ellipse(root,'바닥 그림자',70,590,560,42,solid('#15355e',.10));ground.effects=[{type:'LAYER_BLUR',radius:18,visible:true}];
 const orb=ellipse(root,'유리 뒤쪽의 푸른 빛',200,224,360,360,gradient('#3182f6','#e8f3ff',isGlass?.35:.06,isGlass?.10:.02));orb.effects=[{type:'LAYER_BLUR',radius:30,visible:true}];
 const side=svg(root,'<svg xmlns="http://www.w3.org/2000/svg" width="700" height="700" viewBox="0 0 700 700"><path d="M532 260 Q534 249 544 242 L611 197 Q623 190 623 205 L623 516 Q623 530 611 538 L543 583 Q532 590 532 576Z" fill="'+(isGlass?'#a8ceff':'#1764d8')+'" fill-opacity="'+(isGlass?'.3':'1')+'"/></svg>','가게 측면',0,0);
 const wall=rect(root,'가게 정면 · 재질',112,264,424,322,isGlass?gradient('#ffffff','#abd0ff',.50,.20):gradient('#4593fc','#2272eb'),26);wall.effects=shadow;
 if(isGlass){wall.effects=[...shadow,{type:'GLASS',visible:true,lightIntensity:.65,lightAngle:-40,refraction:.13,depth:14,dispersion:0,radius:9}];wall.strokes=[gradient('#ffffff','#b9d7ff',.9,.2)];wall.strokeWeight=1.5;}
 const roof=svg(root,'<svg xmlns="http://www.w3.org/2000/svg" width="700" height="700" viewBox="0 0 700 700"><path d="M84 226 Q80 221 90 215 L167 159 Q177 152 191 152 H617 Q631 152 619 164 L546 219 Q536 226 524 226Z" fill="'+(isGlass?'#a8ceff':'#64a8ff')+'" fill-opacity="'+(isGlass?'.25':'1')+'"/><path d="M534 226 624 160 624 233 Q624 245 614 252 L534 307Z" fill="'+(isGlass?'#b4d7ff':'#1957c2')+'" fill-opacity="'+(isGlass?'.4':'1')+'"/></svg>','차양 윗면 / 입체',0,0);
 const awning=rect(root,'차양',74,218,464,94,isGlass?gradient('#ffffff','#90c2ff',.5,.42):gradient('#64a8ff','#3182f6'),24);
 if(isGlass){awning.strokes=[solid('#ffffff',.65)];awning.strokeWeight=1.5;awning.effects=[{type:'GLASS',visible:true,lightIntensity:.6,lightAngle:-45,refraction:.10,depth:10,dispersion:0,radius:6}];}
 for(let i=0;i<6;i++)rect(root,'차양의 반투명 리듬',91+i*74,231,54,65,isGlass?gradient('#ffffff','#3182f6',.60,.12):solid('#ffffff',i%2?.15:.32),13);
 const sign=rect(root,'간판',210,322,224,46,isGlass?solid('#ffffff',.42):solid('#ffffff',.95),12);
 text(root,'seelo',224,34,'Regular',isGlass?palette.ink:palette.blue,{family:'Pacifico',align:'CENTER',leading:46,x:210,y:322});
 const window=rect(root,'쇼윈도',146,394,190,137,isGlass?gradient('#ffffff','#8cbdff',.32,.14):gradient('#e8f3ff','#c9e2ff'),20);
 if(isGlass){window.effects=[{type:'GLASS',visible:true,lightIntensity:.7,lightAngle:-40,refraction:.20,depth:18,dispersion:0,radius:7}];window.strokes=[gradient('#ffffff','#b8d8ff',.9,.3)];window.strokeWeight=1.5;}
 rect(root,'쇼윈도 세로 프레임',239,404,3,116,solid('#ffffff',.65),1.5);
 const door=rect(root,'출입문',370,387,126,198,isGlass?gradient('#ffffff','#8cbdff',.34,.22):gradient('#e8f3ff','#90c2ff'),19);
 if(isGlass){door.effects=[{type:'GLASS',visible:true,lightIntensity:.7,lightAngle:-40,refraction:.12,depth:12,dispersion:0,radius:6}];door.strokes=[solid('#ffffff',.7)];door.strokeWeight=1.5;}
 rect(root,'문 손잡이',476,475,5,27,isGlass?solid('#ffffff',.9):palette.white,2.5);
 const step=rect(root,'가게 앞 단',92,581,466,22,isGlass?gradient('#ffffff','#c9e2ff',.9,.42):gradient('#e8f3ff','#c9e2ff'),10);step.effects=[shadow[0]];
 return root;
}
shop(cover,1090,188,true);

// 02 — 문장은 의미를 유지하며 조금 줄이고, 원본의 53%만 데이터 그래프로 표현.
const p2=await figma.getNodeByIdAsync('562:218');
const summaries=[['562:228','가게 탐색의\n새 경로가 된 AI',456,40],['562:230','미국 AI 여행계획 이용자\n장소·방문 시기 탐색에 활용',456,30],['562:234','여러 채널 정보를\n직접 점검·수정하기 어렵다.',650,38],['562:259','검색 노출이 비슷해도\nGEO 정보 상태에 따라\nAI 추천 수는 다르다.',564,36],['562:261','정보 상태별 AI 추천 등장률',496,28]];
for(const [id,value,w,size]of summaries){const n=await figma.getNodeByIdAsync(id);copyMap.push({id,before:n.characters,after:value});update(n,value,w,size,id==='562:230'?'Regular':(id==='562:261'?'Medium':'Bold'),id==='562:230'||id==='562:261'?palette.secondary:palette.ink,size*1.5);}
const left=await figma.getNodeByIdAsync('562:226');mutate(left);left.itemSpacing=26;
const index=await figma.getNodeByIdAsync('562:227'),heading=await figma.getNodeByIdAsync('562:228'),number=await figma.getNodeByIdAsync('562:229'),caption=await figma.getNodeByIdAsync('562:230');
const lh=stack(left,'문제 1 제목',0,0,456,118,'HORIZONTAL',16);left.insertChild(0,lh);lh.appendChild(index);update(index,'01',44,30,'Bold',palette.blue,45);lh.appendChild(heading);update(heading,heading.characters,396,38,'Bold',palette.ink,54);
const ring=frame(left,'53% · 조사 수치 시각화',0,0,456,248);left.insertChild(1,ring);
const base=ellipse(ring,'전체 100%',104,0,248,248,palette.line);base.arcData={startingAngle:0,endingAngle:Math.PI*2,innerRadius:.84};
const value=ellipse(ring,'53%',104,0,248,248,palette.blue);value.arcData={startingAngle:-Math.PI/2,endingAngle:-Math.PI/2+Math.PI*2*.53,innerRadius:.84};
ring.appendChild(number);update(number,'53%',456,96,'Bold',palette.ink,120);number.textAlignHorizontal='CENTER';number.x=0;number.y=64;
left.insertChild(2,caption);update(caption,caption.characters,456,30,'Regular',palette.secondary,45);

// 03 — 본문은 보통 굵기, 핵심 구절은 크기·굵기·색을 함께 달리한다.
const p3=await figma.getNodeByIdAsync('562:271');
const ux=await figma.getNodeByIdAsync('562:281');update(ux,ux.characters,544,32,'Regular',palette.secondary,64);range(ux,'영업에 집중하면서도',44);range(ux,'발견되고 싶으며,',46);range(ux,'결과만 쉽게 확인하고 싶다.',40,palette.blue);
const vp=await figma.getNodeByIdAsync('562:284');const vpCopy='seelo는 AI가 우리 가게를 잘 찾고 소개할 수 있도록,\n구글·카카오의 메뉴·가격·영업시간 등을\n대신 고쳐주고\nAI 추천의 변화까지 확인해주는 서비스다.';update(vp,vpCopy,992,32,'Regular',palette.secondary,64);range(vp,'메뉴·가격·영업시간',46);range(vp,'대신 고쳐주고',50,palette.blue);range(vp,'AI 추천의 변화까지',44);
const diag=await figma.getNodeByIdAsync('562:285');mutate(diag);diag.resize(992,150);
for(const c of diag.children){mutate(c);c.resize(c.width,150);c.paddingTop=20;c.paddingBottom=20;c.itemSpacing=12;for(const t of c.findAllWithCriteria({types:['TEXT']}))update(t,t.characters,t.width,30,'Bold',palette.ink,45);const ic=c.children.find(n=>n.type==='FRAME');if(ic){mutate(ic);ic.rescale(48/ic.width);}}
icon(p3,'arrow',723,559,28,'#3182f6');

// 반복되는 승인 행과 흐름은 지역 컴포넌트로 유지.
const support=await figma.getNodeByIdAsync('562:38');mutate(support);support.resizeWithoutConstraints(6240,700);
const item=keep(figma.createComponent());support.appendChild(item);item.name='seelo / 승인·반영 항목';item.description='사장님 승인 항목 또는 지도 반영 결과를 표시하는 행.';item.x=48;item.y=300;item.resize(744,64);item.layoutMode='HORIZONTAL';item.primaryAxisSizingMode='FIXED';item.counterAxisSizingMode='FIXED';item.primaryAxisAlignItems='SPACE_BETWEEN';item.counterAxisAlignItems='CENTER';item.fills=[];
icon(item,'check',0,0,30);const itemLabel=text(item,'영문 메뉴·가격',490,30,'Medium',palette.ink,{leading:45});const itemState=text(item,'확인·승인',160,28,'Medium',palette.blue,{align:'RIGHT',leading:42});
const lp=item.addComponentProperty('항목','TEXT','영문 메뉴·가격'),sp=item.addComponentProperty('상태','TEXT','확인·승인');itemLabel.componentPropertyReferences={characters:lp};itemState.componentPropertyReferences={characters:sp};
const flow=keep(figma.createComponent());support.appendChild(flow);flow.name='seelo / 서비스 흐름 단계';flow.description='서비스 사용 흐름의 제목과 입력 또는 결과를 보여주는 단계.';flow.x=48;flow.y=430;flow.resize(320,156);flow.layoutMode='VERTICAL';flow.primaryAxisSizingMode='FIXED';flow.counterAxisSizingMode='FIXED';flow.paddingLeft=20;flow.paddingRight=20;flow.paddingTop=20;flow.paddingBottom=20;flow.itemSpacing=8;flow.fills=[palette.soft];flow.cornerRadius=20;
const flowTitle=text(flow,'가게 등록',280,30,'Bold',palette.ink,{leading:45}),flowBody=text(flow,'이름·지도 링크',280,28,'Regular',palette.secondary,{leading:42});const ftp=flow.addComponentProperty('단계','TEXT','가게 등록'),fbp=flow.addComponentProperty('설명','TEXT','이름·지도 링크');flowTitle.componentPropertyReferences={characters:ftp};flowBody.componentPropertyReferences={characters:fbp};

// 04 — 원본 468:42의 자동정비·승인·반영 결과와 5단계 사용자 흐름.
const p4=frame(section,'04 · 자동정비',6200,120,1920,1080,palette.white);p4.clipsContent=true;
const header=(await figma.getNodeByIdAsync('562:272')).clone();created.push(header.id,...header.findAll(()=>true).map(n=>n.id));p4.appendChild(header);header.x=96;header.y=36;
text(p4,'04 / 04',200,30,'Medium',palette.body,{align:'RIGHT',leading:45,x:1624,y:1000});
text(p4,'자동정비',1728,76,'Bold',palette.ink,{leading:96,x:96,y:144});
const subtitle=text(p4,'승인한 항목 반영 · 반영 확인 · 변경 이력 기록',1728,34,'Regular',palette.secondary,{leading:51,x:96,y:250});
function window(p,name,x,title,labels,status){
 const outer=frame(p,name,x,330,840,376,palette.soft,32);text(outer,title,776,34,'Bold',palette.ink,{leading:51,x:32,y:22});
 const white=stack(outer,'항목',24,96,792,256,'VERTICAL',8,24,palette.white,20);
 for(const label of labels){const i=item.createInstance();created.push(i.id,...i.findAll(()=>true).map(n=>n.id));white.appendChild(i);i.setProperties({[lp]:label,[sp]:status});}
 return outer;
}
window(p4,'정비안 확인·승인',96,'정비안 확인·승인',['영문 메뉴·가격','실제 영업시간','영문 가게 소개'],'확인·승인');
window(p4,'정비 진행·반영 결과',984,'정비 진행·반영 결과',['Google · 영문 소개','Google · 영문 메뉴','카카오 · 영업시간'],'완료');
icon(p4,'arrow',949,502,30);
text(p4,'사용 흐름',1728,30,'Bold',palette.ink,{leading:45,x:96,y:730});
const flowRow=stack(p4,'가게 등록부터 결과 확인까지',96,786,1728,156,'HORIZONTAL',0);
const steps=[['가게 등록','이름·지도 링크'],['AI 추천 현황 확인','결과 확인·정비 신청'],['연결·정비안 승인','사장님 확인'],['자동정비','Google·카카오 반영'],['결과 확인','반영 이력·전후 비교']];
for(let i=0;i<5;i++){
 if(i){const cell=frame(flowRow,'다음 단계',0,0,32,156);icon(cell,'arrow',4,64,24,'#4e5968');}
 const n=flow.createInstance();created.push(n.id,...n.findAll(()=>true).map(t=>t.id));flowRow.appendChild(n);n.setProperties({[ftp]:steps[i][0],[fbp]:steps[i][1]});
 if(i===3){n.fills=[palette.blue];for(const t of n.findAllWithCriteria({types:['TEXT']})){t.fills=[palette.white];}}
}
text(p4,'사장님: 실제 정보 확인·승인  /  서비스: 정비안 작성·지도 반영·결과 기록',1510,28,'Regular',palette.secondary,{leading:42,x:96,y:966});

// 표지 2안 비교: 같은 문구, 다른 재질·구성. 본문 1~4장과 별도 배치.
const alts=keep(figma.createSection());page.appendChild(alts);alts.name='seelo · 표지 비교 · 유리 가게 / 솔리드 가게';alts.x=section.x;alts.y=3800;alts.resizeWithoutConstraints(4200,1280);
const a=cover.clone();created.push(a.id,...a.findAll(()=>true).map(t=>t.id));alts.appendChild(a);a.name='A · 글라스 가게';a.x=80;a.y=120;
const b=cover.clone();created.push(b.id,...b.findAll(()=>true).map(t=>t.id));alts.appendChild(b);b.name='B · 솔리드 가게';b.x=2120;b.y=120;
const oldModel=b.children.find(n=>n.name.startsWith('유리 가게'));oldModel.visible=false;
const bHero=b.children.find(n=>n.name==='서비스 소개');bHero.x=128;bHero.y=258;bHero.resize(1040,550);
const bTexts=bHero.findAllWithCriteria({types:['TEXT']});const bt=bTexts.find(t=>t.characters.startsWith('AI 추천을'));update(bt,bt.characters,1040,92,'Bold',palette.ink,122);range(bt,'가게 정보를 고칩니다.',92,palette.blue);
const bb=bTexts.find(t=>t.characters.startsWith('Google'));update(bb,bb.characters,840,34,'Regular',palette.secondary,54);
const bShop=shop(b,1130,276,false);bShop.rescale(.88);

const allFrames=[cover,p2,p3,p4,a,b], audits=[];
function effective(n,root){let p=n;while(p&&p.id!==root.id){if(!p.visible)return false;p=p.parent;}return true;}
for(const f of allFrames){const texts=f.findAllWithCriteria({types:['TEXT']}).filter(t=>effective(t,f)&&t.characters.trim());const box=f.absoluteBoundingBox;const overlaps=[];for(let i=0;i<texts.length;i++)for(let j=i+1;j<texts.length;j++){const a=texts[i].absoluteBoundingBox,b=texts[j].absoluteBoundingBox;if(Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x)>2&&Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y)>2)overlaps.push([texts[i].id,texts[j].id]);}audits.push({id:f.id,name:f.name,w:f.width,h:f.height,visibleTexts:texts.length,missingFonts:texts.filter(t=>t.hasMissingFont).map(t=>t.id),overlaps,outside:texts.filter(t=>{const b=t.absoluteBoundingBox;return b.x<box.x-1||b.y<box.y-1||b.x+b.width>box.x+box.width+1||b.y+b.height>box.y+box.height+1;}).map(t=>({id:t.id,text:t.characters})),names:texts.filter(t=>/김태욱|강가힐/.test(t.characters)).map(t=>t.characters)});}
figma.viewport.scrollAndZoomIntoView([cover,p2,p3,p4]);
return{createdNodeIds:created,mutatedNodeIds:[...mutated],sectionId:section.id,frames:audits,coverAlternatives:alts.id,shortenedCopy:copyMap,glassEffects:cover.findAll(n=>'effects'in n&&n.effects.some(e=>e.type==='GLASS')).map(n=>n.id),sourcePage4:'468:42',sourceUI:['223:1934','223:2021']};

