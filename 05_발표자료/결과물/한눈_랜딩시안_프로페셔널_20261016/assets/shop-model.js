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
  let width = 1, height = 1, sun, models = [], visibleShop = -1, storyTop = 0, storyTravel = 1, storyBottom = 1;
  const shopWindowMaterials = [];
  const captionName = document.querySelector('.shop-caption strong');
  const captionType = document.querySelector('.shop-caption span');
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
    renderer.toneMappingExposure = 1.3;
    if(T.SRGBColorSpace)renderer.outputColorSpace=T.SRGBColorSpace;
    scene = new T.Scene();
    camera = new T.OrthographicCamera(-5,5,5,-5,.1,60);
    store = new T.Group(); scene.add(store);

    const boxGeo=keep(new T.BoxGeometry(1,1,1));
    const sphereGeo=keep(new T.SphereGeometry(1,20,14));
    const cylinderGeo=keep(new T.CylinderGeometry(1,1,1,28));
    const canopyGeo=keep(new T.ConeGeometry(1,.48,28));
    const configurations=[
      {kind:'restaurant',name:'망원밥상',label:'한식집 · 옐로 차양',wall:'#fff4df',accent:'#ffc54f',frame:'#3f779c',roof:'#fffaf0',plant:'#63bc8a',sign:'#ffc54f',ink:'#273b4a'},
      {kind:'cafe',name:'seelo café',label:'카페 · 민트 파사드',wall:'#dff7eb',accent:'#54c5aa',frame:'#397d92',roof:'#f6fffb',plant:'#72bf8d',sign:'#e9fff5',ink:'#246e62'},
      {kind:'bakery',name:'온기 베이커리',label:'베이커리 · 코랄 지붕',wall:'#fff1e5',accent:'#ff9f81',frame:'#af614d',roof:'#f38971',plant:'#7abb79',sign:'#fff6e8',ink:'#a35543'}
    ];
    function makeShop(config){
      const group=new T.Group();store.add(group);
      const materials=[];
      const color=(hex,extra={})=>{const m=keep(new T.MeshStandardMaterial({color:hex,roughness:.76,metalness:0,transparent:true,...extra}));materials.push(m);return m;};
      const m={
        wall:color(config.wall),trim:color('#fffdf6'),accent:color(config.accent),
        frame:color(config.frame),roof:color(config.roof),wood:color('#dba96f'),
        paving:color('#faf3e7'),pot:color('#f5c9ab'),leaf:color(config.plant),leafLight:color('#9cdb9e'),
        glass:color('#a9dff3',{roughness:.24,emissive:'#c5f3ff',emissiveIntensity:.12}),
        warm:color('#fff1cb',{emissive:'#ffe8b0',emissiveIntensity:.18}),bread:color('#e9b35e')
      };
      shopWindowMaterials.push(m.warm);
      function mesh(geo,mat,x,y,z,sx=1,sy=1,sz=1){const obj=new T.Mesh(geo,mat);obj.position.set(x,y,z);obj.scale.set(sx,sy,sz);obj.castShadow=true;obj.receiveShadow=true;group.add(obj);return obj;}
      const box=(mat,x,y,z,w,h,d)=>mesh(boxGeo,mat,x,y,z,w,h,d);
      const cylinder=(mat,x,y,z,r,h)=>mesh(cylinderGeo,mat,x,y,z,r,h,r);
      const ball=(mat,x,y,z,rx,ry=rx,rz=rx)=>mesh(sphereGeo,mat,x,y,z,rx,ry,rz);
      function arch(mat,x,y,z,w,h,depth=.05){
        const shape=new T.Shape();shape.moveTo(-w/2,0);shape.lineTo(w/2,0);shape.lineTo(w/2,h-w/2);
        shape.absarc(0,h-w/2,w/2,0,Math.PI,false);shape.lineTo(-w/2,0);
        return mesh(keep(new T.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:18})),mat,x,y,z);
      }
      function sign(text,x,y,z,w,h){
        const surface=document.createElement('canvas');surface.width=768;surface.height=192;
        const ctx=surface.getContext('2d');
        const paint=()=>{ctx.fillStyle=config.sign;ctx.fillRect(0,0,768,192);ctx.fillStyle=config.ink;ctx.textAlign='center';ctx.textBaseline='middle';ctx.font='650 72px Pretendard, sans-serif';ctx.fillText(text,384,98,700);};
        paint();const texture=keep(new T.CanvasTexture(surface));if(T.SRGBColorSpace)texture.colorSpace=T.SRGBColorSpace;
        const mat=keep(new T.MeshBasicMaterial({map:texture,transparent:true}));materials.push(mat);
        box(m.frame,x,y,z-.045,w+.10,h+.08,.12);
        mesh(keep(new T.PlaneGeometry(w,h)),mat,x,y,z+.025);
        document.fonts?.ready.then(()=>{paint();texture.needsUpdate=true;needsRender=true;requestFrame();});
      }
      function awning(y,width,first,second){
        for(let i=0;i<12;i++){
          const x=-width/2+(i+.5)*width/12,mat=i%2?first:second;
          const top=box(mat,x,y,1.83,width/12,.09,1.02);top.rotation.x=.12;
          box(mat,x,y-.14,2.34,width/12,.22,.07);
        }
      }
      function tree(x,z,r=.57){
        cylinder(m.pot,x,.22,z,.35,.44);cylinder(m.wood,x,.78,z,.065,1.05);
        ball(m.leaf,x,1.57,z,r,.73,r);ball(m.leafLight,x-.17,1.37,z+.10,r*.7,.47,r*.7);
      }
      function table(x,z){
        cylinder(m.wood,x,.78,z,.48,.09);cylinder(m.frame,x,.39,z,.045,.73);cylinder(m.frame,x,.035,z,.25,.05);
        for(const [dx,dz]of [[-.65,.14],[.53,-.38]]){
          cylinder(m.accent,x+dx,.43,z+dz,.23,.09);
          for(const d of [-.14,.14])box(m.wood,x+dx+d,.21,z+dz,.035,.42,.035);
        }
        cylinder(m.trim,x,.91,z,.075,.17);
      }
      box(m.paving,0,-.16,.4,7.35,.22,6.4);
      box(m.trim,0,-.30,.4,7.5,.07,6.55);
      if(config.kind==='restaurant'){
        box(m.wall,0,1.77,0,4.35,3.3,2.65);box(m.trim,0,3.47,0,4.60,.18,2.90);
        box(m.accent,0,3.60,0,4.44,.12,2.75);box(m.trim,0,.15,0,4.52,.24,2.8);
        arch(m.trim,-.96,.28,1.35,1.52,2.65,.08);arch(m.frame,-.96,.31,1.45,1.31,2.50,.04);
        arch(m.warm,-.96,.44,1.50,1.09,2.18,.015);
        box(m.frame,-.96,1.43,1.54,.045,2.10,.03);box(m.frame,-.96,1.65,1.54,1.12,.05,.03);
        box(m.wood,-.52,1.24,1.58,.045,.25,.045);
        arch(m.trim,1.05,.75,1.35,1.46,1.98,.08);arch(m.glass,1.05,.86,1.45,1.22,1.73,.035);
        box(m.trim,1.05,1.55,1.51,.055,1.42,.04);box(m.trim,1.05,1.49,1.51,1.24,.055,.04);
        box(m.wood,1.05,.78,1.55,1.56,.10,.35);
        for(let i=0;i<3;i++){
          const border=arch(m.trim,2.19,1.10,.82-i*.82,.58,1.46);border.rotation.y=Math.PI/2;
          const glass=arch(m.glass,2.25,1.17,.82-i*.82,.44,1.29,.025);glass.rotation.y=Math.PI/2;
        }
        awning(2.90,4.40,m.accent,m.trim);sign(config.name,0,3.35,1.57,2.18,.47);
        box(m.trim,-.96,.20,1.94,1.66,.15,.66);tree(-2.77,1.28,.62);tree(2.74,-.70,.56);table(2.10,2.30);
        const board=box(m.wood,-2.0,.56,2.74,.53,.82,.06);board.rotation.x=-.15;
        box(m.frame,-2.0,.58,2.80,.41,.62,.025);
        for(let i=0;i<3;i++)box(m.trim,-2.0,.72-i*.13,2.82,.25-i*.035,.018,.01);
      }else if(config.kind==='cafe'){
        box(m.wall,0,1.89,0,3.90,3.55,2.70);box(m.trim,0,3.71,0,4.18,.18,2.98);
        box(m.accent,0,3.85,0,4.02,.12,2.82);box(m.trim,0,.13,0,4.06,.22,2.84);
        box(m.frame,-.65,1.70,1.39,1.94,1.92,.11);box(m.glass,-.65,1.70,1.46,1.76,1.74,.04);
        box(m.trim,-.65,1.70,1.50,.055,1.78,.035);box(m.wood,-.65,.81,1.55,2.03,.13,.40);
        arch(m.trim,1.18,.26,1.37,1.18,2.64,.07);arch(m.frame,1.18,.30,1.45,1.02,2.49,.03);
        arch(m.glass,1.18,.42,1.50,.83,2.25,.02);box(m.wood,1.50,1.30,1.56,.04,.31,.04);
        box(m.accent,0,2.87,1.74,4.20,.16,.85);box(m.trim,0,2.76,2.17,4.20,.12,.06);
        sign('seelo café',0,3.31,1.45,2.48,.51);
        for(let i=0;i<2;i++){box(m.trim,1.99,1.77,.63-i*1.2,.10,1.84,.89);box(m.glass,2.05,1.77,.63-i*1.2,.03,1.64,.70);}
        tree(2.73,-.72,.57);table(2.26,2.31);
        cylinder(m.frame,-2.55,1.15,2.05,.035,2.30);mesh(canopyGeo,m.trim,-2.55,2.38,2.05,1.02,1,1.02);
        cylinder(m.pot,-2.55,.04,2.05,.28,.07);
        box(m.wood,-1.43,.47,2.55,1.28,.12,.46);
        for(const x of [-1.94,-.92])box(m.frame,x,.22,2.55,.055,.42,.36);
        for(let i=0;i<3;i++){cylinder(m.trim,-1.25+i*.45,.96,1.60,.07,.17);ball(m.leaf,-1.25+i*.45,1.13,1.60,.10,.13,.10);}
      }else{
        box(m.wall,0,1.59,0,4.55,2.94,2.72);box(m.trim,0,.12,0,4.74,.20,2.90);
        const roofShape=new T.Shape();roofShape.moveTo(-2.48,0);roofShape.lineTo(2.48,0);roofShape.lineTo(0,1.08);roofShape.closePath();
        mesh(keep(new T.ExtrudeGeometry(roofShape,{depth:3.04,bevelEnabled:false})),m.roof,0,3.06,-1.52);
        const slope=Math.atan(1.08/2.48),roofWidth=Math.hypot(2.48,1.08);
        for(const side of [-1,1]){
          const roof=box(m.roof,side*1.24,3.61,0,roofWidth+.12,.12,3.18);roof.rotation.z=-side*slope;
          const fascia=box(m.trim,side*1.24,3.61,1.62,roofWidth+.16,.14,.08);fascia.rotation.z=-side*slope;
        }
        box(m.frame,-.83,1.49,1.41,2.13,1.72,.10);box(m.glass,-.83,1.49,1.48,1.98,1.57,.025);
        for(const y of [.94,1.49]){box(m.wood,-.83,y,1.56,2.05,.075,.20);for(let i=0;i<4;i++)ball(m.bread,-1.55+i*.48,y+.14,1.61,.17,.11,.10);}
        box(m.trim,-.83,1.49,1.66,.045,1.65,.035);
        arch(m.trim,1.37,.23,1.39,1.19,2.42,.07);arch(m.frame,1.37,.27,1.48,1.03,2.27,.03);
        arch(m.warm,1.37,.39,1.53,.84,2.02,.02);box(m.wood,1.69,1.20,1.58,.04,.26,.04);
        awning(2.61,4.70,m.accent,m.trim);sign('온기 bakery',0,2.96,1.60,2.47,.43);
        const sideWindow=arch(m.trim,2.30,.91,0,1.42,1.65);sideWindow.rotation.y=Math.PI/2;
        const sideGlass=arch(m.glass,2.36,1.02,0,1.20,1.43,.025);sideGlass.rotation.y=Math.PI/2;
        box(m.wood,-2.90,.49,.94,.52,.14,1.45);
        for(const z of [.38,1.49])box(m.frame,-2.90,.23,z,.44,.42,.06);
        tree(2.95,-.72,.58);tree(-2.95,-1.2,.48);
        cylinder(m.pot,2.74,.20,2.44,.32,.40);ball(m.leaf,2.74,.70,2.44,.42,.50,.42);
        box(m.wood,-1.90,.17,2.02,1.05,.15,.62);
      }
      return {group,materials,...config};
    }
    models=configurations.map(makeShop);
    models.forEach((model,i)=>{model.group.visible=i===0;});
    story.dataset.modelCount=String(models.length);

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
      ? `translate3d(0,${-43*entrance}vh,0) scale(${1-.16*entrance})`
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
      const cafeMix=fixed?0:smooth(.31,.40,p),bakeryMix=fixed?0:smooth(.66,.75,p);
      const weights=[1-cafeMix,cafeMix*(1-bakeryMix),bakeryMix];
      const selected=weights.indexOf(Math.max(...weights));
      models.forEach((model,i)=>{
        const opacity=weights[i];model.group.visible=opacity>.004;
        model.materials.forEach(mat=>{mat.opacity=opacity;mat.depthWrite=opacity>.98;});
      });
      if(selected!==visibleShop){
        visibleShop=selected;const model=models[selected];
        captionName.textContent=model.name;captionType.textContent=model.label;
        stage.setAttribute('aria-label',model.label+' 가게 모형');
        story.dataset.model=model.kind;renderer.shadowMap.needsUpdate=true;
      }
      shopWindowMaterials.forEach(mat=>{mat.emissiveIntensity=.14+smooth(.35,.62,p)*.12;});
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
