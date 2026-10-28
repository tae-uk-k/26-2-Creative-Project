(() => {
  'use strict';
  const story = document.querySelector('.shop-story');
  if (!story) return;
  const stage = document.querySelector('.shop-stage');
  const canvas = document.querySelector('#shop-canvas');
  const panels = [...document.querySelectorAll('.satellite')];
  const pager = [...document.querySelectorAll('.story-pager a')];
  const motionButton = document.querySelector('.motion-toggle');
  const bar = document.querySelector('[data-orbit-bar]');
  const beforeBar = document.querySelector('[data-orbit-before]');
  const intro = document.querySelector('.shop-intro');
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  const narrow = matchMedia('(max-width:760px)');
  const clamp = x => Math.max(0, Math.min(1, x));
  const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
  let manualStatic = false, unavailable = false, renderer, scene, camera, store, frame = 0, magnet;
  let scrollDirty = true, resizeDirty = true, target = 0, current = 0, lastTime = 0, lastP = -1, needsRender = true;
  let width = 1, height = 1, sun, shopWindowMaterial, storyTop = 0, storyTravel = 1, storyBottom = 1;
  const resources = new Set();
  const keep = resource => { resources.add(resource); return resource; };
  const isStatic = () => manualStatic || preference.matches || unavailable;

  function requestFrame() { if (!frame && !document.hidden) frame = requestAnimationFrame(tick); }
  function configureMotion() {
    const staticMode = isStatic();
    document.body.classList.toggle('static-story', staticMode);
    motionButton.setAttribute('aria-pressed', String(staticMode));
    motionButton.textContent = staticMode ? '전체 내용 보기 중' : '움직임 줄이기';
    if (manualStatic && !preference.matches && !unavailable) motionButton.textContent = '스크롤 모션 켜기';
    motionButton.disabled = preference.matches || unavailable;
    panels.forEach(panel => { panel.inert = false; panel.setAttribute('aria-hidden', 'false'); });
    resizeDirty = scrollDirty = needsRender = true;
    magnet?.refresh();
    requestFrame();
  }
  motionButton.addEventListener('click', () => { manualStatic = !manualStatic; configureMotion(); });
  preference.addEventListener('change', configureMotion);
  function fallback() {
    unavailable = true; canvas.hidden = true;
    document.querySelector('.shop-fallback').hidden = false;
    story.dataset.renderState = 'fallback';
    configureMotion();
  }

  function build() {
    const T = window.THREE;
    if (!T) throw new Error('Three.js unavailable');
    renderer = new T.WebGLRenderer({canvas, alpha:true, antialias:true, powerPreference:'default'});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.25));
    renderer.setClearColor(0x000000, 0);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = T.PCFSoftShadowMap;
    renderer.shadowMap.autoUpdate = false;
    renderer.shadowMap.needsUpdate = true;
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    scene = new T.Scene();
    camera = new T.OrthographicCamera(-5,5,5,-5,.1,60);
    store = new T.Group(); scene.add(store);
    const color = (hex, extra = {}) => keep(new T.MeshStandardMaterial({color:hex,roughness:.82,metalness:0,...extra}));
    const cream=color('#eeeee5'), trim=color('#fafbf3'), sage=color('#7187a2'), deep=color('#334b69'), leaf=color('#a7a899'), clay=color('#c0b3a4'), wood=color('#b6a48c'), pavement=color('#e7e9eb');
    const glass=color('#8096a8',{roughness:.3}), windowLight=color('#e3dcca',{emissive:'#e6d5b5',emissiveIntensity:.10}), foliage=color('#89958a');
    shopWindowMaterial = windowLight;
    const boxGeo=keep(new T.BoxGeometry(1,1,1));
    const sphereGeo=keep(new T.SphereGeometry(1,20,14));
    const cylinderGeo=keep(new T.CylinderGeometry(1,1,1,32));
    function mesh(geo,mat,x,y,z,sx=1,sy=1,sz=1,parent=store){const m=new T.Mesh(geo,mat);m.position.set(x,y,z);m.scale.set(sx,sy,sz);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;}
    function box(mat,x,y,z,w,h,d){return mesh(boxGeo,mat,x,y,z,w,h,d);}
    function cylinder(mat,x,y,z,r,h){return mesh(cylinderGeo,mat,x,y,z,r,h,r);}
    function arch(mat,x,y,z,w,h,depth=.06){
      const s=new T.Shape();s.moveTo(-w/2,0);s.lineTo(w/2,0);s.lineTo(w/2,h-w/2);s.absarc(0,h-w/2,w/2,0,Math.PI,false);s.lineTo(-w/2,0);
      const g=keep(new T.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:24}));return mesh(g,mat,x,y,z);
    }
    // One miniature shop, made from architectural primitives rather than textures.
    box(pavement,0,-.15,.4,7.35,.22,6.4);
    box(trim,0,-.29,.4,7.5,.09,6.55);
    box(cream,0,1.78,0,4.35,3.32,2.65);
    box(trim,0,3.49,0,4.6,.17,2.9);
    box(sage,0,3.62,0,4.44,.13,2.75);
    box(trim,0,.16,0,4.52,.25,2.8);
    // Door and display window: softened arches and a clear frame.
    arch(trim,-.96,.29,1.35,1.52,2.65,.08);
    arch(deep,-.96,.31,1.45,1.31,2.5,.04);
    arch(windowLight,-.96,.45,1.50,1.09,2.18,.015);
    box(deep,-.96,1.4,1.54,.045,2.1,.03);
    box(deep,-.96,1.65,1.54,1.12,.05,.03);
    cylinder(wood,-.54,1.25,1.58,.045,.25);
    arch(trim,1.05,.77,1.35,1.44,1.95,.08);
    arch(glass,1.05,.87,1.45,1.2,1.72,.035);
    box(trim,1.05,1.55,1.51,.06,1.4,.04);
    box(trim,1.05,1.48,1.51,1.22,.06,.04);
    box(wood,1.05,.79,1.55,1.55,.10,.34);
    // Three tall side windows follow the same geometry.
    for(let i=0;i<3;i++){
      const a=arch(trim,2.19,1.1,.82-i*.82,.57,1.45,.05);a.rotation.y=Math.PI/2;
      const g=arch(glass,2.25,1.17,.82-i*.82,.43,1.29,.025);g.rotation.y=Math.PI/2;
    }
    // Stripe awning and scalloped edge use a shared geometry and two materials.
    for(let i=0;i<12;i++){
      const x=-2.2+(i+.5)*4.4/12, mat=i%2?sage:trim;
      const roof=box(mat,x,2.91,1.83,4.4/12,.10,1.04);roof.rotation.x=.12;
      box(mat,x,2.77,2.34,4.4/12,.22,.07);
    }
    box(trim,-.96,.22,1.95,1.65,.16,.65);
    box(pavement,-.96,.09,2.15,1.95,.10,.85);
    // Roof sign. Canvas typography is local and does not load remote media.
    const signCanvas=document.createElement('canvas');signCanvas.width=768;signCanvas.height=192;
    const ctx=signCanvas.getContext('2d');
    function paintSign(){
      ctx.fillStyle='#334b69';ctx.fillRect(0,0,768,192);
      ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle='#f8faed';ctx.font='550 76px Pretendard, sans-serif';ctx.fillText('망원밥상',384,94);
    }
    paintSign();const signTexture=keep(new T.CanvasTexture(signCanvas));
    if(T.SRGBColorSpace)signTexture.colorSpace=T.SRGBColorSpace;
    const signMat=keep(new T.MeshBasicMaterial({map:signTexture}));
    box(deep,0,3.35,1.51,2.25,.51,.12);
    mesh(keep(new T.PlaneGeometry(2.16,.48)),signMat,0,3.35,1.58);
    document.fonts?.ready.then(()=>{paintSign();signTexture.needsUpdate=true;needsRender=true;requestFrame();});
    // Cylindrical planters, clipped tree crowns, and a small café table.
    for(const [x,z,r] of [[-2.77,1.28,.66],[2.75,-.7,.61]]){
      cylinder(clay,x,.25,z,.38,.50);cylinder(wood,x,.85,z,.075,1.15);
      mesh(sphereGeo,leaf,x,1.64,z,r,.85,r);
      mesh(sphereGeo,foliage,x+.1,1.43,z+.08,r*.8,.6,r*.8);
    }
    cylinder(wood,2.16,.83,2.32,.62,.09);cylinder(deep,2.16,.42,2.32,.055,.78);cylinder(deep,2.16,.05,2.32,.33,.05);
    for(const [x,z]of [[1.6,2.96],[2.9,2.07]]){cylinder(sage,x,.47,z,.27,.10);for(const dx of [-.16,.16])box(wood,x+dx,.23,z,.045,.45,.045);}
    cylinder(clay,1.95,.99,2.30,.10,.23);mesh(sphereGeo,leaf,1.95,1.18,2.30,.14,.2,.14);
    const board=box(wood,-2.0,.59,2.74,.53,.85,.055);board.rotation.x=-.15;
    box(deep,-2.0,.60,2.80,.41,.64,.025);
    for(let i=0;i<3;i++)box(trim,-2.0,.74-i*.13,2.82,.25-i*.035,.018,.01);
    const hemi = new T.HemisphereLight('#ffffff','#d5d8dc',2.1);scene.add(hemi);
    sun = new T.DirectionalLight('#fffef8',3.1);sun.position.set(-6,10,8);sun.castShadow=true;
    sun.shadow.mapSize.set(1024,1024);Object.assign(sun.shadow.camera,{left:-6,right:6,top:6,bottom:-6,near:1,far:30});sun.shadow.normalBias=.035;sun.shadow.bias=-.0002;scene.add(sun);
    const fill = new T.DirectionalLight('#f3f6fa',.7);fill.position.set(6,4,-4);scene.add(fill);
    const groundMat=keep(new T.ShadowMaterial({color:'#647080',opacity:.11}));
    const ground=new T.Mesh(keep(new T.PlaneGeometry(30,30)),groundMat);ground.rotation.x=-Math.PI/2;ground.position.y=-.345;ground.receiveShadow=true;scene.add(ground);
    canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();fallback();});
    story.dataset.renderState='ready';
  }

  function resize() {
    width=stage.clientWidth;height=stage.clientHeight;
    const bounds=story.getBoundingClientRect();
    storyTop=bounds.top+scrollY;storyBottom=storyTop+story.offsetHeight;storyTravel=Math.max(1,story.offsetHeight-innerHeight);
    if(renderer){
      renderer.setSize(width,height,false);
      const aspect=width/Math.max(1,height), halfWidth=Math.max(4.8,4.2*aspect);
      camera.left=-halfWidth;camera.right=halfWidth;camera.top=halfWidth/aspect;camera.bottom=-halfWidth/aspect;
      camera.updateProjectionMatrix();
    }
    resizeDirty=false;needsRender=true;
  }
  function readScroll(){
    target=clamp((scrollY-storyTop)/storyTravel);
    scrollDirty=false;
    return storyBottom>scrollY&&storyTop<scrollY+innerHeight;
  }
  function update(p){
    const fixed=isStatic(), ranges=[[.035,.14,.29,.37],[.35,.44,.64,.72],[.70,.80,1.05,1.12]];
    const entrance = fixed ? 0 : smooth(.02,.15,p);
    const introOpacity = fixed ? 1 : 1-smooth(.025,.115,p);
    intro.style.opacity=String(introOpacity);
    intro.style.transform=fixed?'none':`translate3d(0,${-34*(1-introOpacity)}px,0)`;
    intro.inert=!fixed&&introOpacity<.1;
    const modelSide=-1+2*smooth(.30,.45,p)-2*smooth(.65,.80,p);
    stage.style.transform=fixed?'none':narrow.matches
      ? `translate3d(0,${-19*entrance}vh,0) scale(${1-.16*entrance})`
      : `translate3d(${modelSide*16*entrance}vw,${-10*entrance}vh,0) scale(${1+.04*entrance})`;
    panels.forEach(panel=>{
      const phase=Number(panel.dataset.phase),[a,b,c,d]=ranges[phase];
      const enter=fixed?1:smooth(a,b,p), leave=fixed?0:smooth(c,d,p);
      const opacity=enter*(1-leave), side=panel.classList.contains('left')?-1:1;
      const x=narrow.matches?0:side*((1-enter)*64-leave*38);
      const y=(1-enter)*22-leave*16;
      const scale=1;
      const angle=0;
      panel.style.opacity=opacity.toFixed(3);
      panel.style.transform=fixed?'none':narrow.matches
        ? `translate3d(0,${y}px,0) scale(${scale})`
        : `translate3d(${x}px,calc(-50% + ${y}px),0) rotate(${angle}deg) scale(${scale})`;
      panel.style.pointerEvents=fixed||opacity>.8?'auto':'none';
      panel.setAttribute('aria-hidden',String(!fixed&&opacity<.15));panel.inert=!fixed&&opacity<.15;
    });
    const phase=p<.35?0:p<.70?1:2;
    pager.forEach((link,i)=>{if(i===phase)link.setAttribute('aria-current','step');else link.removeAttribute('aria-current');});
    const fill=fixed?1:smooth(.74,.87,p);
    if(bar)bar.style.transform=`scaleX(${.4*fill})`;
    if(beforeBar)beforeBar.style.transform=`scaleX(${.2*fill})`;
    story.dataset.progress=p.toFixed(3);story.dataset.phase=String(phase+1);
    if(renderer&&!unavailable){
      // Move only the camera; static shadow maps are computed once.
      const angle=fixed?.18:.12+smooth(.05,.55,p)*.42-smooth(.65,.95,p)*.20;
      camera.position.set(8*Math.cos(angle)-1,6.3-.65*smooth(.1,.8,p),10.5+Math.sin(angle)*4);
      camera.lookAt(0,1.65,.3);
      shopWindowMaterial.emissiveIntensity=.12+smooth(.35,.62,p)*.16;
      renderer.render(scene,camera);
      story.dataset.drawCalls=String(renderer.info.render.calls);
      story.dataset.triangles=String(renderer.info.render.triangles);
    }
  }
  function tick(time){
    frame=0;if(document.hidden)return;
    if(resizeDirty)resize();
    if(scrollDirty&&!readScroll()&&!isStatic())return;
    const dt=lastTime?Math.min(50,time-lastTime):16.67;lastTime=time;
    current=magnet?.active?target:current+(target-current)*(1-Math.exp(-dt/55));
    if(Math.abs(current-target)<.0001)current=target;
    if(needsRender||Math.abs(current-lastP)>.00001){update(current);lastP=current;needsRender=false;}
    if(current!==target)requestFrame();
  }
  addEventListener('scroll',()=>{scrollDirty=true;requestFrame();},{passive:true});
  addEventListener('seelo-magnet-frame',()=>{scrollDirty=true;requestFrame();});
  addEventListener('resize',()=>{resizeDirty=scrollDirty=true;requestFrame();},{passive:true});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){lastTime=0;needsRender=true;requestFrame();}else{cancelAnimationFrame(frame);frame=0;}});
  pager.forEach((link,index)=>link.addEventListener('click',event=>{event.preventDefault();if(isStatic()){panels[index].scrollIntoView({behavior:'auto',block:'center'});return;}if(magnet){magnet.go(index+1);return;}const rect=story.getBoundingClientRect(),travel=Math.max(1,story.offsetHeight-innerHeight);window.scrollTo({top:scrollY+rect.top+[.20,.52,.91][index]*travel,behavior:'smooth'});}));
  addEventListener('pagehide',event=>{cancelAnimationFrame(frame);frame=0;if(!event.persisted){magnet?.destroy();resources.forEach(resource=>resource.dispose());renderer?.dispose();}});
  addEventListener('pageshow',event=>{if(event.persisted){lastTime=0;resizeDirty=scrollDirty=needsRender=true;requestFrame();}});
  try{build();}catch(error){console.warn('Shop preview fallback:',error.message);fallback();}
  configureMotion();
  magnet=window.SeeloMagnet?.attach({track:story,stops:[0,.20,.52,.91],disabled:isStatic});
})();
