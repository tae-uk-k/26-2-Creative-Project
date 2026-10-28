(() => {
  'use strict';
  const story=document.querySelector('.city-story');if(!story||!window.SeeloScroll)return;
  const {clamp,ease:smooth,create}=window.SeeloScroll;
  const canvas=document.querySelector('#city-canvas'),hero=document.querySelector('.city-hero');
  const chapters=[...document.querySelectorAll('.city-chapter')],cue=document.querySelector('.city-scroll-cue');
  const progress=document.querySelector('.city-chapter-progress'),note=document.querySelector('.city-art-note'),marker=document.querySelector('.store-marker');
  const beforeBar=document.querySelector('[data-before-bar]'),afterBar=document.querySelector('[data-after-bar]');
  const navLinks=[...document.querySelectorAll('.city-nav nav a')],progressLabel=progress.querySelector('.current'),progressFill=progress.querySelector('i');
  const mobile=matchMedia('(max-width:580px)'),reduce=matchMedia('(prefers-reduced-motion: reduce)');
  const resources=[];let renderer,scene,camera,path,lookPath,projected,shopAccent,shopLight,driver,unavailable=false,activeChapter=-1,storyTop=0,travel=1;
  const setText=(node,value)=>{if(node&&node.textContent!==value)node.textContent=value;};
  const markerText=document.createTextNode('');marker.replaceChildren(document.createElement('span'),markerText);
  function fallback(){unavailable=true;canvas.hidden=true;document.querySelector('.city-fallback').hidden=false;story.dataset.renderState='unavailable';document.body.classList.add('reduced-motion');driver?.refresh();}
  function createCity() {
    const T = window.THREE;
    if (!T) throw new Error('Three.js unavailable');
    renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'default' });
    renderer.setPixelRatio(Math.min(devicePixelRatio, innerWidth<760?1:1.25));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = T.PCFSoftShadowMap;
    // Buildings and sunlight are static; the camera does not change their shadow map.
    renderer.shadowMap.autoUpdate = false;
    renderer.shadowMap.needsUpdate = true;
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.toneMappingExposure = .96;
    scene = new T.Scene();
    scene.background = new T.Color('#faf8f5');
    scene.fog = new T.Fog('#faf8f5', 65, 135);
    camera = new T.PerspectiveCamera(39, 1, .1, 180);
    projected = new T.Vector3();
    const city = window.SeeloCity.build(T, scene, renderer, resources, () => { renderer.shadowMap.needsUpdate = true; driver?.refresh(); });
    shopAccent = city.shopAccent; shopLight = city.shopLight;
    story.dataset.instances = String(city.instances);
    story.dataset.geometryBatches = String(city.batches);
    // Enter above the rooftops, then descend along the open road, not through a facade.
    const points = [[24, 29, 52], [1, 22, 32], [0, 10, 14], [0, 4.6, 0], [0, 3.4, -5.8]];
    path = new T.CatmullRomCurve3(points.map(p => new T.Vector3(...p)), false, 'centripetal');
    lookPath = new T.CatmullRomCurve3([[0, 2, -9], [-3, 2, -11], [-4, 2.3, -12], [-3.3, 2.1, -12], [-3.7, 2.05, -12]].map(p => new T.Vector3(...p)), false, 'catmullrom', .3);
    canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); fallback(); });
    story.dataset.buildings = '31';
  }
  function update(p) {
    const reduced = document.body.classList.contains('reduced-motion');
    const heroOpacity = 1 - smooth(.035, .15, p);
    hero.style.opacity = heroOpacity;
    hero.style.transform = `translate3d(0,${-35 * (1 - heroOpacity)}px,0)`;
    hero.inert = !reduced && heroOpacity < .1;
    cue.style.opacity = 1 - smooth(.01, .10, p);
    const ranges = [[.12, .16, .345, .38], [.38, .415, .645, .68], [.68, .715, 1.02, 1.08]];
    chapters.forEach((chapter, i) => {
      const [a, b, c, d] = ranges[i], opacity = smooth(a, b, p) * (1 - smooth(c, d, p));
      chapter.style.opacity = opacity;
      const side = i === 1 ? -1 : 1;
      chapter.style.transform = mobile.matches ? `translate3d(0,${(1 - opacity) * 18}px,0)` : `translate3d(${side * (1 - opacity) * 24}px,-50%,0)`;
      // Move the reading surface once; no nested line animation or per-frame DOM queries.
      chapter.setAttribute('aria-hidden', !reduced && opacity < .1 ? 'true' : 'false');
      chapter.style.pointerEvents = reduced || opacity > .8 ? 'auto' : 'none';
    });
    const chapterIndex = p < .38 ? 1 : p < .68 ? 2 : 3;
    navLinks.forEach((link, i) => {
      if (!reduced && p > .12 && p < .99 && i === chapterIndex - 1) link.setAttribute('aria-current', 'step');
      else link.removeAttribute('aria-current');
    });
    const countProgress = reduced ? 1 : smooth(.70, .815, p);
    if (beforeBar) beforeBar.style.transform = `scaleX(${.2 * countProgress})`;
    if (afterBar) afterBar.style.transform = `scaleX(${.4 * countProgress})`;
    if (activeChapter !== chapterIndex) {
      markerText.textContent = p < .38 ? '우리 가게 · 진단 중' : p < .68 ? '우리 가게 · 정보 정비' : '우리 가게 · 전후 비교';
      setText(progressLabel, String(chapterIndex).padStart(2, '0'));
      activeChapter = chapterIndex;
    }
    progressFill.style.transform = `scaleX(${p})`;
    progress.style.opacity = note.style.opacity = smooth(.14, .2, p);
    story.dataset.progress = p.toFixed(3); story.dataset.chapter = String(chapterIndex);
    if (renderer && !unavailable) {
      const position = reduced ? .32 : p;
      const lift = reduced ? 1 : smooth(.405, .58, p);
      shopAccent.color.set('#887057').lerp(shopAccent.userData.destination, lift);
      shopLight.color.set('#877b71').lerp(shopLight.userData.destination, lift);
      shopLight.emissiveIntensity = lift * .2;
      camera.position.copy(path.getPoint(position));
      const aim = lookPath.getPoint(position);
      if (mobile.matches && !reduced) {
        const focus = smooth(.30, .65, p);
        aim.x += (-6.7 - aim.x) * focus;
        aim.y -= 2.5 * focus;
      }
      camera.lookAt(aim);
      canvas.style.transform = `translate3d(0,${(1 - smooth(.01, .17, p)) * innerHeight * (mobile.matches ? .32 : .48)}px,0)`;
      renderer.render(scene, camera);
      story.dataset.renderState = 'ready';
      story.dataset.drawCalls = String(renderer.info.render.calls);
      story.dataset.triangles = String(renderer.info.render.triangles);

    }
  }
  try{createCity();}catch(error){console.warn('City preview uses a static fallback:',error.message);fallback();}
  driver=create({track:story,smoothing:42,snapStops:[0,.25,.52,.84],disabled:()=>unavailable,
    prepare:({reduced})=>document.body.classList.toggle('reduced-motion',reduced||unavailable),
    measure(){if(renderer&&!unavailable){renderer.setSize(innerWidth,innerHeight,false);camera.aspect=innerWidth/innerHeight;camera.fov=mobile.matches?53:39;camera.updateProjectionMatrix();}},
    render(p,meta){storyTop=meta.top;travel=meta.travel;update(p);}
  });
  document.querySelectorAll('a[href="#diagnose"],a[href="#optimize"],a[href="#impact"]').forEach(link=>link.addEventListener('click',event=>{
    event.preventDefault();
    const index={'#diagnose':0,'#optimize':1,'#impact':2}[link.getAttribute('href')];
    if(reduce.matches||unavailable)chapters[index].scrollIntoView({behavior:'auto',block:'center'});
    else driver.go(index+1);
  }));
  addEventListener('pagehide',event=>{if(!event.persisted){driver.destroy();resources.forEach(r=>r.dispose());renderer?.dispose();}});
})();
