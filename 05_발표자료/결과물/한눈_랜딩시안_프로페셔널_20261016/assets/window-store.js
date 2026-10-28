(() => {
  'use strict';
  const canvas=document.getElementById('window-store');if(!canvas)return;
  const fallback=document.querySelector('.store-fallback');
  let renderer, scene, camera, group, cloud, solid, raf=0, width=1,height=1, start=performance.now(), last=0, progress=0, paused=false, reduced=matchMedia('(prefers-reduced-motion:reduce)').matches, visible=true;
  let seed=149;const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
  const smooth=(a,b,v)=>{const t=Math.max(0,Math.min(1,(v-a)/(b-a)));return t*t*(3-2*t);};
  function fail(){canvas.hidden=true;fallback.hidden=false;cancelAnimationFrame(raf);raf=0;}
  if(!window.THREE){fail();return;}
  try {
    const T=THREE;
    renderer=new T.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'low-power'});
    renderer.setPixelRatio(Math.min(devicePixelRatio,1.25));renderer.setClearColor(0,0);renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.35;
    scene=new T.Scene();camera=new T.PerspectiveCamera(32,1,.1,100);camera.position.set(7,5.4,8);camera.lookAt(0,1.35,0);
    group=new T.Group();group.position.y=-.25;scene.add(group);solid=new T.Group();group.add(solid);
    const points=[],colors=[],scatter=[],materials=[];
    function box(w,h,d,x,y,z,color){
      const material=new T.MeshStandardMaterial({color,roughness:.83,metalness:.03,transparent:true,opacity:.82});materials.push(material);
      const geo=new T.BoxGeometry(w,h,d),mesh=new T.Mesh(geo,material);mesh.position.set(x,y,z);solid.add(mesh);
      const c=new T.Color(color);
      for(const face of [0,1,2]){
        const u=face===0?h:w,v=face===2?h:d;
        const count=Math.max(9,Math.floor(u*v*85));
        for(let n=0;n<count;n++){
          const p=[(random()-.5)*w,(random()-.5)*h,(random()-.5)*d];
          p[face]=(random()>.5?1:-1)*[w,h,d][face]/2;
          points.push(p[0]+x,p[1]+y,p[2]+z);
          const light=.70+random()*.30;colors.push(c.r*light,c.g*light,c.b*light);
          scatter.push((random()-.5)*12,(random()-.5)*8+2,(random()-.5)*8);
        }
      }
      return mesh;
    }
    box(5,.18,4.4,0,.02,0,'#d9dfe4');box(3.4,2.4,2.7,0,1.31,0,'#f5f4ee');
    box(3.7,.16,2.98,0,2.59,0,'#d1d8dd');box(3.56,.08,2.85,0,2.72,0,'#f9f8f4');
    box(1.04,1.55,.10,-.88,1.29,1.39,'#536974');box(.94,1.45,.11,-.88,1.29,1.45,'#b3c6ca');
    box(.055,1.45,.12,-.88,1.29,1.52,'#f1f0ea');box(.95,.055,.12,-.88,1.22,1.52,'#f1f0ea');
    box(.92,1.85,.12,.62,1.12,1.40,'#4f6875');box(.74,1.70,.13,.62,1.12,1.46,'#b2c6ca');box(.055,1.70,.12,.62,1.12,1.55,'#e9ebe5');
    box(.09,.09,.15,.88,1.05,1.57,'#797f7d');
    box(.1,1.20,1.45,1.75,1.43,-.12,'#aabcc3');box(.12,.05,1.48,1.81,1.44,-.12,'#edf0e9');box(.12,1.21,.05,1.81,1.43,-.12,'#edf0e9');
    box(3.5,.15,.75,0,2.18,1.53,'#253f68');
    for(let i=0;i<10;i++)box(.18,.16,.76,-1.57+i*.35,2.19,1.54,i%2?'#dce3e5':'#566d85');
    box(1.20,.12,.40,.60,.17,1.64,'#c3ced4');box(1.40,.09,.42,.60,.08,1.85,'#d3dbe0');
    box(.42,.47,.42,-1.65,.34,1.75,'#c6b9a8');box(.60,.65,.58,-1.65,.89,1.75,'#657c6a');box(.45,.43,.44,-1.65,1.35,1.75,'#82917b');
    box(.45,.46,.45,1.62,.34,1.75,'#c6b9a8');box(.64,.65,.61,1.62,.89,1.75,'#7e8b76');
    const signCanvas=document.createElement('canvas');signCanvas.width=512;signCanvas.height=128;const ctx=signCanvas.getContext('2d');
    function drawSign(){ctx.fillStyle='#f7f6f1';ctx.fillRect(0,0,512,128);ctx.fillStyle='#334654';ctx.textAlign='center';ctx.textBaseline='middle';ctx.font='600 49px Pretendard, sans-serif';ctx.fillText('망원밥상',256,64);if(signMaterial.map)signMaterial.map.needsUpdate=true;}
    const signMaterial=new T.MeshStandardMaterial({map:new T.CanvasTexture(signCanvas),transparent:true,roughness:1});materials.push(signMaterial);
    const sign=new T.Mesh(new T.PlaneGeometry(1.55,.38),signMaterial);sign.position.set(0,2.44,1.365);solid.add(sign);drawSign();document.fonts.ready.then(()=>{drawSign();request();});
    const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(points,3));geometry.setAttribute('aScatter',new T.Float32BufferAttribute(scatter,3));geometry.setAttribute('color',new T.Float32BufferAttribute(colors,3));
    const pointMaterial=new T.ShaderMaterial({transparent:true,depthWrite:false,vertexColors:true,uniforms:{uAssemble:{value:0},uPixel:{value:Math.min(devicePixelRatio,1.5)},uOpacity:{value:1}},vertexShader:`attribute vec3 aScatter; uniform float uAssemble; uniform float uPixel; varying vec3 vColor; void main(){vColor=color;vec3 p=mix(aScatter,position,uAssemble);vec4 mv=modelViewMatrix*vec4(p,1.);gl_Position=projectionMatrix*mv;gl_PointSize=clamp(31.*uPixel/-mv.z,1.4,4.);}`,fragmentShader:`varying vec3 vColor;uniform float uOpacity;void main(){float d=length(gl_PointCoord-.5);if(d>.48)discard;gl_FragColor=vec4(vColor,uOpacity*smoothstep(.5,.30,d));}`});
    cloud=new T.Points(geometry,pointMaterial);group.add(cloud);
    scene.add(new T.HemisphereLight('#fffefa','#b4c1cf',2.8));const light=new T.DirectionalLight('#ffffff',3.3);light.position.set(-3,7,5);scene.add(light);const fill=new T.DirectionalLight('#e5edfa',1.2);fill.position.set(5,2,-3);scene.add(fill);
    const shadow=new T.Mesh(new T.CircleGeometry(2.5,48),new T.MeshBasicMaterial({color:'#a1b0be',transparent:true,opacity:.07,depthWrite:false}));shadow.rotation.x=-Math.PI/2;shadow.position.y=-.09;shadow.scale.y=.8;group.add(shadow);
    canvas.dataset.points=String(points.length/3);
    function resize(){width=canvas.clientWidth;height=canvas.clientHeight;if(!width||!height)return;renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();request();}
    function draw(now){
      raf=0;if(!visible||document.hidden)return;
      if(!last)last=now;const elapsed=(now-start)/1000;
      const assemble=reduced||paused||progress>.05?1:smooth(.05,2.3,elapsed);
      cloud.material.uniforms.uAssemble.value=assemble;
      const solidReveal=reduced||progress>.05?1:smooth(1.05,2.6,elapsed);
      materials.forEach(m=>m.opacity=(m===signMaterial?1:.82)*solidReveal);
      cloud.material.uniforms.uOpacity.value=1-.65*solidReveal;
      group.rotation.y=-.18+progress*.48;
      group.position.y=-.25;
      renderer.render(scene,camera);canvas.dataset.ready='true';canvas.dataset.renderMode=elapsed<2.6&&progress<=.05&&!paused&&!reduced?'assembling':'on-demand';last=now;
      if(!paused&&!reduced&&visible&&elapsed<2.6&&progress<=.05)request();
    }
    function request(){if(!raf&&visible&&!document.hidden)raf=requestAnimationFrame(draw);}
    const resizeObserver=new ResizeObserver(resize);resizeObserver.observe(canvas);
    const observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible)request();else{cancelAnimationFrame(raf);raf=0;}},{threshold:.01});observer.observe(canvas);
    addEventListener('seelo-scene',e=>{
      progress=e.detail.progress;paused=e.detail.paused;reduced=e.detail.reduced;
      // The story already runs inside RAF. Draw its 3D pose in that same frame.
      cancelAnimationFrame(raf);raf=0;
      draw(e.detail.time||performance.now());
    });
    document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(raf);raf=0;}else request();});
    canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();fail();});
    addEventListener('pagehide',e=>{if(e.persisted)return;cancelAnimationFrame(raf);resizeObserver.disconnect();observer.disconnect();scene.traverse(o=>{o.geometry?.dispose();if(o.material){for(const m of Array.isArray(o.material)?o.material:[o.material]){m.map?.dispose();m.dispose();}}});renderer.dispose();},{once:true});
    resize();
  } catch(e){console.warn('Store preview unavailable:',e.message);fail();}
})();
