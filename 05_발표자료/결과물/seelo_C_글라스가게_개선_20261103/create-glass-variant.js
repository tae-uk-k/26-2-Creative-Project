const p=await figma.getNodeByIdAsync('12:2');await figma.setCurrentPageAsync(p);
const original=await figma.getNodeByIdAsync('620:12');
const fontMap=new Map();for(const t of original.findAllWithCriteria({types:['TEXT']}))for(const s of t.getStyledTextSegments(['fontName']))fontMap.set(JSON.stringify(s.fontName),s.fontName);await Promise.all([...fontMap.values()].map(f=>figma.loadFontAsync(f)));
const created=[],mutated=[];
function rgb(h){return{r:parseInt(h.slice(0,2),16)/255,g:parseInt(h.slice(2,4),16)/255,b:parseInt(h.slice(4,6),16)/255};}
function solid(h,a=1){return{type:'SOLID',color:rgb(h),opacity:a};}
function grad(stops,vertical=false){return{type:'GRADIENT_LINEAR',gradientTransform:vertical?[[0,1,0],[-1,0,1]]:[[.85,.52,-.08],[-.52,.85,.28]],gradientStops:stops.map(([position,h,a])=>({position,color:{...rgb(h),a}}))};}
function shadow(h,a,x,y,r,inner=false){return{type:inner?'INNER_SHADOW':'DROP_SHADOW',color:{...rgb(h),a},offset:{x,y},radius:r,spread:0,visible:true,blendMode:'NORMAL'};}
function glass(depth=20,radius=6,refraction=.17){return{type:'GLASS',visible:true,lightIntensity:.88,lightAngle:-42,refraction,depth,dispersion:.015,radius};}
function layerBlur(radius){return{type:'LAYER_BLUR',visible:true,radius};}
const section=figma.createSection();section.name='시안 C · 1페이지 · 글라스 가게 개선';section.x=54000;section.y=7252;section.resizeWithoutConstraints(2080,1280);section.fills=[solid('444444')];created.push(section.id);
const clone=original.clone();section.appendChild(clone);clone.x=80;clone.y=120;clone.name='01 · 서비스 소개 · 글라스 개선';
const legacy=clone.children.find(n=>n.name==='유리 가게 · 편집 가능한 입체 도형');legacy.visible=false;legacy.name='원본 유리 가게 / 보관';
const g=figma.createFrame();g.name='유리 가게 / 크리스털 · 편집 가능';g.layoutMode='NONE';g.resize(700,700);g.x=legacy.x;g.y=legacy.y;g.fills=[];g.clipsContent=false;clone.insertChild(clone.children.indexOf(legacy)+1,g);created.push(g.id);
function rect(name,x,y,w,h,r,fill,stroke=[],effects=[]){const n=figma.createRectangle();g.appendChild(n);n.name=name;n.resize(w,h);n.x=x;n.y=y;n.cornerRadius=r;n.fills=fill;n.strokes=stroke;n.strokeWeight=stroke.length?1.7:0;n.effects=effects;created.push(n.id);return n;}
function ellipse(name,x,y,w,h,fill,effects=[]){const n=figma.createEllipse();g.appendChild(n);n.name=name;n.resize(w,h);n.x=x;n.y=y;n.fills=fill;n.effects=effects;created.push(n.id);return n;}
function vector(name,data,fill,stroke=[],width=1.5,effects=[]){const n=figma.createVector();g.appendChild(n);n.name=name;n.vectorPaths=[{windingRule:'NONZERO',data}];n.fills=fill;n.strokes=stroke;n.strokeWeight=width;n.strokeCap='ROUND';n.strokeJoin='ROUND';n.effects=effects;created.push(n.id);return n;}
const rim=grad([[0,'FFFFFF',1],[.4,'FFFFFF',.85],[1,'B9C5D2',.35]]);
ellipse('빛 / 후면의 옅은 앰버',175,247,380,323,[grad([[0,'FFE4A5',.42],[1,'FFF9EC',.04]])],[layerBlur(50)]);
ellipse('그림자 / 바닥 접촉',110,602,470,24,[solid('725833',.13)],[layerBlur(14)]);
ellipse('그림자 / 넓은 주변광',82,598,540,46,[solid('85909B',.075)],[layerBlur(25)]);
vector('측면 / 두께가 있는 투명 유리','M 532 261 Q 532 248 543 240 L 610 193 Q 624 184 624 201 L 624 518 Q 624 532 612 541 L 545 587 Q 532 596 532 580 Z',[grad([[0,'FFFFFF',.46],[.55,'D7E1E8',.16],[1,'FFE8AD',.28]])],[rim],2,[glass(26,7,.22)]);
vector('측면 / 후면 모서리 빛','M 618 206 L 618 518 Q 618 528 607 535 L 549 575',[],[grad([[0,'FFFFFF',.9],[1,'E4BE67',.38]])],2);
rect('내부 / 따뜻한 창빛',161,358,153,181,22,[solid('FFD887',.30)],[],[layerBlur(20)]);
rect('내부 / 문 뒤의 빛',385,346,78,237,18,[solid('FFE6AC',.27)],[],[layerBlur(20)]);
rect('내부 / 먼쪽 벽',133,284,381,293,22,[grad([[0,'EAF0F4',.28],[1,'D0D8E1',.19]])]);
rect('정면 / 24mm 유리',112,264,424,322,28,[grad([[0,'FFFFFF',.34],[.52,'DEE5ED',.17],[1,'FFFFFF',.20]])],[rim],[shadow('64758A',.09,0,20,33),shadow('FFFFFF',.76,0,2,4,true),shadow('7E8FA4',.10,0,-3,7,true),glass(26,7,.22)]);
rect('정면 / 안쪽 베벨',118,270,412,310,23,[],[grad([[0,'FFFFFF',.75],[.48,'FFFFFF',.06],[1,'BAC8D8',.30]])]);
vector('정면 / 길게 흐르는 반사광','M 126 290 Q 126 279 137 279 L 227 279 L 145 571 L 129 571 Z',[grad([[0,'FFFFFF',.33],[.65,'FFFFFF',.05],[1,'FFFFFF',0]])]);
vector('차양 / 옆면 유리','M 534 224 L 623 159 L 623 230 Q 623 242 613 250 L 535 304 Z',[grad([[0,'FFF2CC',.55],[.55,'FFE0A0',.22],[1,'FFCA58',.30]])],[grad([[0,'FFFFFF',.95],[1,'E6BD66',.25]])],1.8,[glass(16,4,.12)]);
vector('차양 / 윗면 유리','M 84 220 Q 80 215 91 209 L 166 156 Q 175 150 190 150 L 611 150 Q 629 150 616 163 L 544 215 Q 536 221 522 221 Z',[grad([[0,'FFFFFF',.84],[.48,'FFF1CE',.34],[1,'FFD77E',.30]])],[rim],2,[glass(18,5,.14)]);
vector('차양 / 윗면 반사 선','M 171 155 L 609 155',[],[grad([[0,'FFFFFF',.95],[1,'FFFFFF',.28]])],2.3);
rect('차양 / 프런트 글라스',74,218,464,94,24,[grad([[0,'FFFFFF',.46],[.48,'FFFFFF',.24],[1,'FFF1CE',.24]])],[rim],[shadow('8894A3',.085,0,11,17),shadow('FFFFFF',.8,0,2,3,true),glass(19,5,.19)]);
for(let i=0;i<6;i++){const warm=i%2===0;const stops=warm?[[0,'FFF9E9',.78],[.45,'FFE3A0',.55],[1,'FFC54F',.48]]:[[0,'FFFFFF',.88],[.55,'F5F8FC',.45],[1,'DEE6EE',.36]];const n=rect('차양 / '+(warm?'앰버':'클리어')+' 리브 '+(i+1),88+i*74,230,58,66,15,[grad(stops,true)],[grad([[0,'FFFFFF',.90],[1,'FFFFFF',.12]])],[shadow('FFFFFF',.65,0,1.5,2,true)]);n.strokeWeight=1;}
rect('간판 / 프로스트 플레이트',186,326,274,71,18,[grad([[0,'FFFFFF',.50],[1,'FFFFFF',.24]])],[grad([[0,'FFFFFF',.90],[1,'FFFFFF',.20]])],[glass(12,4,.12)]);
const brand=legacy.findAllWithCriteria({types:['TEXT']}).find(n=>n.characters==='seelo').clone();g.appendChild(brand);brand.name='간판 / seelo';brand.fontSize=75;brand.lineHeight={unit:'PIXELS',value:100};brand.textAutoResize='NONE';brand.resize(270,100);brand.x=188;brand.y=306;brand.textAlignHorizontal='CENTER';brand.textAlignVertical='CENTER';brand.fills=[solid('242C35')];brand.effects=[];created.push(brand.id);
rect('쇼윈도 / 광학 유리',146,411,190,139,22,[grad([[0,'FFFFFF',.26],[.55,'E4ECF4',.10],[1,'FFFFFF',.20]])],[rim],[shadow('FFFFFF',.70,0,1.5,3,true),shadow('6E8299',.09,0,-2,5,true),glass(17,5,.18)]);
rect('쇼윈도 / 세로 몰딩',238,423,3,113,1.5,[solid('FFFFFF',.9)],[],[shadow('8797A8',.08,1,0,2)]);
vector('쇼윈도 / 빛의 사선','M 158 431 L 191 431 L 164 533 L 156 533 Z',[grad([[0,'FFFFFF',.23],[1,'FFFFFF',0]])]);
rect('문 / 광학 유리',370,405,126,181,21,[grad([[0,'FFFFFF',.27],[.5,'E7EDF4',.10],[1,'FFFFFF',.21]])],[rim],[shadow('FFFFFF',.8,0,1.5,3,true),shadow('7C8B9E',.10,0,-2,5,true),glass(19,5,.17)]);
rect('문 / 손잡이',476,482,5,29,2.5,[grad([[0,'FFFFFF',1],[1,'D6E1EA',.8]],true)],[],[shadow('627181',.18,1,1,2)]);
rect('기단 / 두꺼운 유리',92,583,466,22,10,[grad([[0,'FFFFFF',.92],[.5,'F4F7F9',.60],[1,'FFEACA',.43]],true)],[grad([[0,'FFFFFF',1],[1,'CDD7E1',.30]])],[shadow('8C7B61',.10,0,7,9),glass(10,3,.10)]);
vector('기단 / 오른쪽 연장','M 552 584 L 620 538 L 620 551 L 557 599 Z',[grad([[0,'F9FBFE',.75],[1,'EDD3A0',.20]])],[grad([[0,'FFFFFF',.80],[1,'FFFFFF',.05]])],1.2);
created.push(clone.id,...clone.findAll(()=>true).map(n=>n.id));
figma.currentPage.selection=[clone];figma.viewport.scrollAndZoomIntoView([clone]);
return{createdNodeIds:[...new Set(created)],mutatedNodeIds:[],sectionId:section.id,frameId:clone.id,glassShopId:g.id,legacyId:legacy.id,originalId:original.id,bounds:{x:section.x,y:section.y,w:section.width,h:section.height},glassCount:g.findAll(n=>'effects'in n&&n.effects.some(e=>e.type==='GLASS')).length,imageNodes:g.findAll(n=>'fills'in n&&Array.isArray(n.fills)&&n.fills.some(f=>f.type==='IMAGE')).map(n=>n.id),typeCounts:g.findAll(()=>true).reduce((a,n)=>(a[n.type]=(a[n.type]||0)+1,a),{})};
