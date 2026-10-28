/* An original architectural exhibit, drawn with Three.js r180. No remote models. */
(()=>{
  const stage=document.querySelector('.gallery-stage');
  const canvas=document.querySelector('#gallery-canvas');
  const pauseButton=document.querySelector('#pause-scene');
  const status=document.querySelector('#scene-status');
  const reducedMotion=matchMedia('(prefers-reduced-motion:reduce)');
  let renderer;
  function fallback(){document.querySelector('.stage-fallback').hidden=false;stage.dataset.renderState='unavailable';canvas.hidden=true;document.querySelector('.scene-controls').hidden=true;document.querySelector('.scene-legend').hidden=true;document.querySelector('.stage-tabs').hidden=true;document.querySelector('.scene-instruction').textContent='현재 환경에서는 3D 모형 대신 설명을 표시합니다.';status.textContent='이 환경에서는 3D를 사용할 수 없습니다. 아래에서 서비스와 진단 예시를 확인할 수 있습니다.';}
  if(!window.THREE){fallback();return;}
  try{renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:false,powerPreference:'low-power'});}catch(error){fallback();return;}
  const scene=new THREE.Scene();
  scene.background=new THREE.Color('#eeede7');
  scene.fog=new THREE.Fog('#eeede7',20,40);
  const camera=new THREE.PerspectiveCamera(35,1,.1,80);
  renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));
  renderer.shadowMap.enabled=true;
  renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure=1.28;
  scene.add(new THREE.HemisphereLight('#fff9e9','#b8b6aa',2.5));
  const sun=new THREE.DirectionalLight('#fff5df',4.1);
  sun.position.set(-5,10,6);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);
  Object.assign(sun.shadow.camera,{left:-8,right:8,top:8,bottom:-8,near:.1,far:35});
  sun.shadow.normalBias=.035;sun.shadow.bias=-.00015;sun.shadow.radius=4;
  scene.add(sun);
  const fill=new THREE.DirectionalLight('#dce8ee',1.5);fill.position.set(6,5,-5);scene.add(fill);
  const spot=new THREE.SpotLight('#ffe1b2',35,19,.36,.9,1);
  spot.position.set(1,8,4);spot.target.position.set(0,1,1);scene.add(spot,spot.target);
  const exhibit=new THREE.Group();scene.add(exhibit);
  const materials={
    stone:new THREE.MeshStandardMaterial({color:'#dedcd1',roughness:.92}),
    pale:new THREE.MeshStandardMaterial({color:'#f3f1e7',roughness:.83}),
    white:new THREE.MeshStandardMaterial({color:'#fffdf4',roughness:.7}),
    street:new THREE.MeshStandardMaterial({color:'#c5c5ba',roughness:1}),
    bronze:new THREE.MeshStandardMaterial({color:'#926343',roughness:.58,metalness:.3}),
    roof:new THREE.MeshStandardMaterial({color:'#afb8ad',roughness:.9}),
    glass:new THREE.MeshStandardMaterial({color:'#667b77',roughness:.28,metalness:.15}),
    window:new THREE.MeshStandardMaterial({color:'#e4c994',emissive:'#d7a95e',emissiveIntensity:.13,roughness:.55}),
    ink:new THREE.MeshStandardMaterial({color:'#3a4e43',roughness:.85}),
    foliage:new THREE.MeshStandardMaterial({color:'#8b9579',roughness:1})
  };
  function box(w,h,d,x,y,z,material,parent=exhibit,shadow=true){const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),material);m.position.set(x,y,z);m.castShadow=shadow;m.receiveShadow=true;parent.add(m);return m;}
  // A gallery floor and one low, architectural plinth.
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(120,120),materials.pale);floor.rotation.x=-Math.PI/2;floor.position.y=-.48;floor.receiveShadow=true;scene.add(floor);
  box(7.5,.28,6.6,0,-.22,0,materials.pale);
  box(7.3,.07,6.4,0,-.045,0,materials.white);
  box(7.15,.025,1.1,0,.005,.6,materials.street,exhibit,false);
  box(1.1,.025,6.3,-.4,.01,0,materials.street,exhibit,false);
  // Restrained surrounding buildings. Their facade details remain subordinate.
  function building(x,z,w,d,h,style=0){
    const group=new THREE.Group();group.position.set(x,0,z);exhibit.add(group);
    box(w,h,d,0,h/2+.03,0,style?materials.stone:materials.pale,group);
    box(w+.1,.07,d+.1,0,h+.08,0,materials.white,group);
    box(w-.16,.1,d-.16,0,h+.13,0,materials.stone,group);
    const cols=Math.max(2,Math.floor(w/.32));const rows=Math.max(2,Math.floor(h/.44));
    for(let row=0;row<rows;row++)for(let col=0;col<cols;col++){
      const wx=-w/2+(col+.5)*w/cols;
      box(.12,.2,.025,wx,.36+row*.41,d/2+.016,materials.roof,group,false);
    }
    return group;
  }
  const neighbors=[building(-2.65,-1.6,1.1,1.25,2.3),building(-1.25,-2.05,1.1,1.15,1.9,1),building(.5,-2.12,1.3,1.1,2.7),building(2.4,-1.7,1.3,1.1,1.7,1),building(-2.65,.45,1.15,1.3,1.55,1),building(2.55,.65,1.1,1.4,2.05),building(-2.4,2.15,1.25,.9,.9),building(2.4,2.25,1.35,.8,1.05,1)];
  // The store: a small local building, not an abstract floating object.
  const store=new THREE.Group();store.position.set(.15,.03,.65);exhibit.add(store);
  box(1.65,1.7,1.55,0,.85,0,materials.white,store);
  box(1.77,.12,1.67,0,1.75,0,materials.stone,store);
  box(1.4,.07,1.3,0,1.86,0,materials.roof,store);
  box(1.42,1.12,.03,0,.69,.795,materials.glass,store);
  box(.44,.92,.04,.43,.57,.82,materials.ink,store);
  box(.34,.69,.045,.43,.67,.85,materials.window,store);
  box(.77,.74,.04,-.31,.73,.83,materials.window,store);
  [-.73,-.55,-.37,-.19,-.01,.19,.66,.78].forEach(x=>box(.036,1.18,.04,x,.69,.865,materials.bronze,store));
  box(1.85,.08,.58,0,1.42,1.04,materials.bronze,store);
  box(1.8,.15,.04,0,1.35,1.32,materials.bronze,store);
  box(.04,1.29,.04,-.84,.65,1.26,materials.bronze,store);
  box(.04,1.29,.04,.84,.65,1.26,materials.bronze,store);
  box(1.8,.06,.42,0,.06,1.03,materials.stone,store);
  // A high-resolution, locally drawn sign keeps all geometry independent of assets.
  const signCanvas=document.createElement('canvas');signCanvas.width=768;signCanvas.height=160;
  const ctx=signCanvas.getContext('2d');ctx.fillStyle='#eeeade';ctx.fillRect(0,0,768,160);
  ctx.fillStyle='#3a493d';ctx.font='500 62px Pretendard, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText('망 원 밥 상',384,82);
  const texture=new THREE.CanvasTexture(signCanvas);texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=Math.min(renderer.capabilities.getMaxAnisotropy(),4);
  const sign=new THREE.Mesh(new THREE.PlaneGeometry(1.38,.29),new THREE.MeshStandardMaterial({map:texture,roughness:.9}));sign.position.set(0,1.61,.794);store.add(sign);
  // A thin exhibition frame puts the local store in focus, like an architectural study.
  const portal=new THREE.Group();portal.position.set(.15,0,.22);exhibit.add(portal);
  box(.14,3.8,.16,-1.23,1.9,0,materials.bronze,portal);
  box(.14,3.8,.16,1.23,1.9,0,materials.bronze,portal);
  box(2.6,.14,.16,0,3.8,0,materials.bronze,portal);
  // A narrow inlaid path and low planting beds tie the exhibit to the floor.
  for(let i=0;i<5;i++)box(.8,.016,.23,.15,.032,1.98+i*.24,materials.bronze,exhibit,false);
  function planter(x,z){box(.35,.25,.38,x,.14,z,materials.stone);const shrub=new THREE.Mesh(new THREE.IcosahedronGeometry(.21,1),materials.foliage);shrub.position.set(x,.46,z);shrub.scale.set(.85,1.15,.85);shrub.castShadow=true;exhibit.add(shrub);}
  planter(-1.04,1.4);planter(1.3,1.4);
  // Three gallery states use the same object: found, understood, prepared.
  const stateInfo=[['우리 가게, 발견의 시작.','AI의 시선으로 현재의 노출을 살펴봅니다.'],['흩어진 정보에, 하나의 기준.','지도와 온라인 채널의 정보를 함께 살펴봅니다.'],['다음에 고칠 것을, 선명하게.','진단 뒤에는 구체적인 수정 방향을 준비합니다.']];
  let angle=.63,targetAngle=.63,pointerX=0,pointerY=0,mode=0,visible=true,paused=reducedMotion.matches,dragging=false,lastX=0,lastFrame=0,active=true;
  let radius=12.9,targetRadius=12.9;
  const focus=new THREE.Vector3(0,1.22,.1);
  const stateColor=[new THREE.Color('#926343'),new THREE.Color('#5c7970'),new THREE.Color('#8c734d')];
  function size(){const rect=stage.getBoundingClientRect();renderer.setSize(rect.width,rect.height,false);camera.aspect=rect.width/rect.height;camera.updateProjectionMatrix();}
  const resizeObserver=new ResizeObserver(size);resizeObserver.observe(stage);size();
  function render(time){if(!active)return;requestAnimationFrame(render);if(!visible||document.hidden||time-lastFrame<32)return;lastFrame=time;
    const moving=!paused&&!reducedMotion.matches;
    const drift=moving?Math.sin(time*.00018)*.035:0;
    angle+=(targetAngle+pointerX*.09+drift-angle)*.055;
    radius+=(targetRadius-radius)*.045;
    camera.position.set(Math.sin(angle)*radius,8.15+pointerY*.18,Math.cos(angle)*radius);
    camera.lookAt(focus);
    materials.bronze.color.lerp(stateColor[mode],.035);
    spot.intensity+=((mode===1?25:42)-spot.intensity)*.04;
    renderer.render(scene,camera);
  }
  render(0);stage.dataset.renderState='ready';document.querySelector('.stage-fallback').hidden=true;stage.dataset.scene='0';stage.dataset.angle='0';
  const intersection=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;},{rootMargin:'80px'});intersection.observe(stage);
  function setPaused(value){paused=value;pauseButton.setAttribute('aria-pressed',String(paused));pauseButton.textContent=paused?'움직임 재생':'움직임 멈춤';stage.dataset.paused=String(paused);}
  setPaused(paused);pauseButton.addEventListener('click',()=>setPaused(!paused));reducedMotion.addEventListener('change',()=>setPaused(reducedMotion.matches));
  const rotate=direction=>{targetAngle+=direction*.3;stage.dataset.angle=String(Number(stage.dataset.angle)+direction);status.textContent=direction>0?'모형을 오른쪽으로 회전합니다.':'모형을 왼쪽으로 회전합니다.';};
  document.querySelector('#rotate-left').addEventListener('click',()=>rotate(-1));document.querySelector('#rotate-right').addEventListener('click',()=>rotate(1));
  canvas.addEventListener('pointerdown',event=>{dragging=true;lastX=event.clientX;canvas.setPointerCapture(event.pointerId);});
  canvas.addEventListener('pointermove',event=>{const r=canvas.getBoundingClientRect();if(dragging){targetAngle+=(event.clientX-lastX)*.008;lastX=event.clientX;}else{pointerX=(event.clientX-r.left)/r.width-.5;pointerY=(event.clientY-r.top)/r.height-.5;}});
  const release=()=>{dragging=false;};canvas.addEventListener('pointerup',release);canvas.addEventListener('pointercancel',release);canvas.addEventListener('pointerleave',()=>{pointerX=0;pointerY=0;});
  document.querySelectorAll('[data-scene]').forEach(button=>button.addEventListener('click',()=>{mode=Number(button.dataset.scene);targetAngle=[.63,.12,-.48][mode];targetRadius=[12.9,11.9,12.8][mode];document.querySelectorAll('[data-scene]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));document.querySelector('#scene-title').textContent=stateInfo[mode][0];document.querySelector('#scene-caption').textContent=stateInfo[mode][1];stage.dataset.scene=String(mode);status.textContent=stateInfo[mode].join(' ');}));
  canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();active=false;fallback();});
  window.addEventListener('pagehide',()=>{active=false;resizeObserver.disconnect();intersection.disconnect();scene.traverse(object=>{object.geometry?.dispose();if(object.material){for(const material of Array.isArray(object.material)?object.material:[object.material])material.dispose();}});texture.dispose();renderer.dispose();});
})();
