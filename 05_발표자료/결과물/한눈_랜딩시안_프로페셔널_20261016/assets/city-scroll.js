(() => {
  'use strict';
  const story = document.querySelector('.city-story');
  if (!story) return;
  const canvas = document.querySelector('#city-canvas');
  const hero = document.querySelector('.city-hero');
  const chapters = [...document.querySelectorAll('.city-chapter')];
  const cue = document.querySelector('.city-scroll-cue');
  const progress = document.querySelector('.city-chapter-progress');
  const note = document.querySelector('.city-art-note');
  const marker = document.querySelector('.store-marker');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const mobile = matchMedia('(max-width:580px)');
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
  let renderer, scene, camera, path, lookPath, projected, animation, shopAccent, shopLight, paused = false;
  const coordinate = document.querySelector('.scene-coordinate');
  const rate = document.querySelector('[data-after-rate]');
  const delta = document.querySelector('[data-rate-delta]');
  const afterBar = document.querySelector('[data-after-bar]');
  const markerText = document.createTextNode('');
  marker.replaceChildren(Object.assign(document.createElement('span'), {}), markerText);
  let target = 0, current = 0, last = -1, dirty = true, lastTime = 0;
  const resources = [];
  function readScroll() {
    target = clamp(-story.getBoundingClientRect().top / Math.max(1, story.offsetHeight - innerHeight));
    dirty = true;
  }
  function setMotion() {
    document.body.classList.toggle('reduced-motion', reduce.matches);
    dirty = true;
    readScroll();
  }
  setMotion();
  reduce.addEventListener('change', setMotion);
  function fallback() {
    canvas.hidden = true;
    canvas.style.display = 'none';
    document.querySelector('.city-fallback').hidden = false;
    story.dataset.renderState = 'unavailable';
    document.body.classList.add('reduced-motion');
  }
  function createCity() {
    const T = window.THREE;
    if (!T) throw new Error('Three.js unavailable');
    renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'low-power' });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = T.PCFSoftShadowMap;
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.toneMappingExposure = .96;
    scene = new T.Scene();
    scene.background = new T.Color('#f5f3ed');
    scene.fog = new T.Fog('#f5f3ed', 65, 135);
    camera = new T.PerspectiveCamera(39, 1, .1, 180);
    projected = new T.Vector3();
    const city = window.SeeloCity.build(T, scene, renderer, resources, () => { dirty = true; });
    shopAccent = city.shopAccent; shopLight = city.shopLight;
    story.dataset.instances = String(city.instances);
    story.dataset.geometryBatches = String(city.batches);
    // Enter above the rooftops, then descend along the open road, not through a facade.
    const points = [[24, 29, 52], [1, 22, 32], [0, 10, 14], [0, 4.6, 0], [0, 3.4, -5.8]];
    path = new T.CatmullRomCurve3(points.map(p => new T.Vector3(...p)), false, 'centripetal');
    lookPath = new T.CatmullRomCurve3([[0, 2, -9], [-3, 2, -11], [-4, 2.3, -12], [-3.3, 2.1, -12], [-3.7, 2.05, -12]].map(p => new T.Vector3(...p)), false, 'catmullrom', .3);
    function resize() { const w = innerWidth, h = innerHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.fov = mobile.matches ? 53 : 39; camera.updateProjectionMatrix(); dirty = true; readScroll(); }
    resize(); addEventListener('resize', resize, { passive: true });
    canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); fallback(); paused = true; });
    story.dataset.buildings = '31';
  }
  try { createCity(); } catch (error) { console.warn('City preview uses a static fallback:', error.message); fallback(); }
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
      chapter.style.transform = mobile.matches ? `translateY(${(1 - opacity) * 32}px)` : `translateY(calc(-50% + ${(1 - opacity) * 42}px))`;
      chapter.querySelectorAll('.headline-line>b').forEach((line, j) => {
        const enter = reduced ? 1 : smooth(a + j * .006, b + j * .006, p);
        const leave = reduced ? 0 : smooth(c, d, p);
        line.style.transform = `translateY(${(1 - enter) * 105 - leave * 55}%)`;
        line.style.opacity = enter * (1 - leave);
      });
      chapter.setAttribute('aria-hidden', !reduced && opacity < .1 ? 'true' : 'false');
      chapter.style.pointerEvents = reduced || opacity > .8 ? 'auto' : 'none';
    });
    const chapterIndex = p < .38 ? 1 : p < .68 ? 2 : 3;
    if (coordinate) {
      coordinate.style.opacity = smooth(.09, .15, p);
      coordinate.querySelector('b').textContent = ['01 — FIND THE GAP', '02 — CHANGE THE INFORMATION', '03 — MEASURE THE DIFFERENCE'][chapterIndex - 1];
    }
    const countProgress = reduced ? 1 : smooth(.72, .82, p);
    if (rate) rate.textContent = String(20 + Math.round(countProgress * 20));
    if (delta) delta.textContent = String(Math.round(countProgress * 20));
    if (afterBar) afterBar.style.width = `${40 + countProgress * 40}%`;
    markerText.textContent = p < .38 ? '우리 가게 · 진단 중' : p < .68 ? '우리 가게 · 정보 정비' : '우리 가게 · 전후 비교';
    progress.querySelector('.current').textContent = String(chapterIndex).padStart(2, '0');
    progress.querySelector('i').style.width = `${p * 100}%`;
    progress.style.opacity = note.style.opacity = smooth(.14, .2, p);
    story.dataset.progress = p.toFixed(3); story.dataset.chapter = String(chapterIndex);
    if (renderer && !paused) {
      const position = reduced ? .32 : p;
      const lift = reduced ? 1 : smooth(.405, .58, p);
      shopAccent.color.set('#887057').lerp(shopAccent.userData.destination, lift);
      shopLight.color.set('#77867a').lerp(shopLight.userData.destination, lift);
      shopLight.emissiveIntensity = lift * .2;
      camera.position.copy(path.getPoint(position));
      const aim = lookPath.getPoint(position);
      if (mobile.matches && !reduced) {
        const focus = smooth(.30, .65, p);
        aim.x += (-6.7 - aim.x) * focus;
        aim.y -= 2.5 * focus;
      }
      camera.lookAt(aim);
      canvas.style.transform = `translate3d(0,${(1 - smooth(.01, .17, p)) * innerHeight * .48}px,0)`;
      renderer.render(scene, camera);
      story.dataset.renderState = 'ready';
      story.dataset.drawCalls = String(renderer.info.render.calls);
      story.dataset.triangles = String(renderer.info.render.triangles);
      projected.set(-7.1, 4.5, -10.8).project(camera);
      const x = (projected.x * .5 + .5) * innerWidth, y = (-projected.y * .5 + .5) * innerHeight;
      marker.style.transform = `translate3d(${x - 18}px,${y - 54}px,0)`;
      marker.style.opacity = !reduced && p > .22 && projected.z < 1 && x > 25 && x < innerWidth - 100 && y > 110 && y < innerHeight - 80 ? smooth(.22, .28, p) : 0;
    }
  }
  function tick(time) {
    animation = requestAnimationFrame(tick);
    if (paused || time - lastTime < 30) return;
    lastTime = time;
    current += (target - current) * .16;
    if (Math.abs(target - current) < .0001) current = target;
    if (dirty || Math.abs(current - last) > .00001) { update(current); last = current; dirty = false; }
  }
  document.querySelectorAll('a[href="#diagnose"],a[href="#optimize"],a[href="#impact"]').forEach(link => link.addEventListener('click', event => {
    if (!document.body.classList.contains('reduced-motion')) return;
    const index = { '#diagnose': 0, '#optimize': 1, '#impact': 2 }[link.getAttribute('href')];
    event.preventDefault();
    chapters[index].scrollIntoView({ behavior: 'auto', block: 'center' });
  }));
  addEventListener('scroll', readScroll, { passive: true });
  addEventListener('resize', readScroll, { passive: true });
  addEventListener('pagehide', event => { paused = true; cancelAnimationFrame(animation); if (!event.persisted && renderer) { resources.forEach(r => r.dispose()); renderer.dispose(); } });
  addEventListener('pageshow', event => { if (event.persisted) { paused = false; dirty = true; animation = requestAnimationFrame(tick); } });
  readScroll(); animation = requestAnimationFrame(tick);
})();
