/* Local, original architectural geometry and repeatable surface textures. */
window.SeeloCity = {
  build(T, scene, renderer, resources, invalidate) {
    let seed = 71027;
    const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
    const own = value => { resources.push(value); return value; };
    const batches = new Map(), labels = [];
    const boxGeometry = own(new T.BoxGeometry(1, 1, 1));
    const cylinderGeometry = own(new T.CylinderGeometry(1, 1, 1, 10));
    const sphereGeometry = own(new T.SphereGeometry(1, 10, 7));
    const leafGeometry = own(new T.PlaneGeometry(1, 1));
    const leafCanvas = document.createElement('canvas'); leafCanvas.width = leafCanvas.height = 128;
    const leafContext = leafCanvas.getContext('2d');
    for (let i = 0; i < 5; i++) {
      leafContext.save(); leafContext.translate(64 + (i % 2 ? -18 : 18), 24 + i * 18); leafContext.rotate(i % 2 ? -.7 : .7);
      const gradient = leafContext.createLinearGradient(-10,0,10,0); gradient.addColorStop(0,'#334e28'); gradient.addColorStop(.5,'#82975b'); gradient.addColorStop(1,'#536d37');
      leafContext.fillStyle = gradient; leafContext.beginPath(); leafContext.ellipse(0,0,11,25,0,0,Math.PI*2); leafContext.fill();
      leafContext.strokeStyle='#b0b97888'; leafContext.lineWidth=1; leafContext.beginPath(); leafContext.moveTo(0,-22); leafContext.lineTo(0,22); leafContext.stroke(); leafContext.restore();
    }
    const leafTexture = own(new T.CanvasTexture(leafCanvas)); leafTexture.colorSpace=T.SRGBColorSpace;
    const leafCards = own(new T.MeshStandardMaterial({ map:leafTexture, alphaTest:.45, side:T.DoubleSide, roughness:.95 }));
    const metal = material('#4b514d', .44, .68), black = material('#272c2b', .6);
    const cream = material('#ddd8ca', .85), concreteEdge = material('#a6a79b', .94);
    const timber = surface('wood', '#99734f', .72), concrete = surface('plaster', '#d6d2c8', .92);
    const whitePlaster = surface('plaster', '#e4e0d7', .92);
    const redBrick = surface('brick', '#a47560', .92), paleBrick = surface('brick', '#cbc2aa', .94);
    const darkBrick = surface('brick', '#827c6e', .96), roofMaterial = surface('roof', '#8d9586', .93);
    const asphalt = surface('asphalt', '#6b706c', .97), pavement = surface('paving', '#d1cec3', .95);
    const leafMaterial = material('#607647', .92), leafLight = material('#78915b', .96);
    const bark = surface('wood', '#6a5b49', .97), terracotta = surface('plaster', '#968271', .96);
    const paintedWhite = material('#deddd4', .84), yellow = material('#c6ac63', .91);
    const reflectionCanvas = document.createElement('canvas'); reflectionCanvas.width=128; reflectionCanvas.height=256;
    const reflectionContext=reflectionCanvas.getContext('2d'),reflectionGradient=reflectionContext.createLinearGradient(0,0,0,256);
    reflectionGradient.addColorStop(0,'#b6cad2');reflectionGradient.addColorStop(.42,'#879c9d');reflectionGradient.addColorStop(1,'#4c6263');
    reflectionContext.fillStyle=reflectionGradient;reflectionContext.fillRect(0,0,128,256);
    reflectionContext.fillStyle='#e9f1e91a';reflectionContext.beginPath();reflectionContext.moveTo(8,0);reflectionContext.lineTo(25,0);reflectionContext.lineTo(112,256);reflectionContext.lineTo(100,256);reflectionContext.fill();
    const glassReflection=own(new T.CanvasTexture(reflectionCanvas));glassReflection.colorSpace=T.SRGBColorSpace;
    const darkGlass = own(new T.MeshPhysicalMaterial({ map:glassReflection, color:'#c4d0ce', roughness:.16, metalness:.22, envMapIntensity:1.8, clearcoat:.8 }));
    const clearGlass = own(new T.MeshPhysicalMaterial({ color: '#c8d9d6', roughness: .08, metalness: .18, transparent: true, opacity: .34, depthWrite: false, envMapIntensity: 2.4, clearcoat: 1 }));
    const warmGlow = own(new T.MeshStandardMaterial({ color: '#f4d39a', emissive: '#eac086', emissiveIntensity: .5, roughness: .7 }));
    const shopAccent = material('#887057', .66, .08);
    shopAccent.userData.destination = new T.Color('#335d3e');
    const shopLight = material('#77867a', .7);
    shopLight.userData.destination = new T.Color('#b5ac76');
    shopLight.emissive.set('#d4ac6e');

    function material(color, roughness = .85, metalness = 0) {
      return own(new T.MeshStandardMaterial({ color, roughness, metalness }));
    }
    function texture(type, base) {
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 512;
      const c = canvas.getContext('2d'); c.fillStyle = base; c.fillRect(0, 0, 512, 512);
      if (type === 'brick') {
        c.fillStyle = '#aaa398'; c.fillRect(0, 0, 512, 512);
        for (let row = -1; row < 11; row++) for (let col = -1; col < 5; col++) {
          const x = col * 128 + (row % 2 ? 64 : 0), y = row * 48;
          c.fillStyle = base; c.fillRect(x + 3, y + 3, 122, 42);
          c.fillStyle = `rgba(${random() > .5 ? '255,244,224' : '40,30,22'},${.06 + random() * .14})`;
          c.fillRect(x + 3, y + 3, 122, 42);
          c.fillStyle = '#00000012'; c.fillRect(x + 3, y + 42, 122, 3);
          c.fillStyle = '#ffffff12'; c.fillRect(x + 3, y + 3, 122, 2);
        }
      } else if (type === 'paving') {
        c.strokeStyle = '#918f8580'; c.lineWidth = 3;
        for (let y = 0; y <= 512; y += 128) {
          c.beginPath(); c.moveTo(0, y); c.lineTo(512, y); c.stroke();
          for (let x = (y % 256 ? -128 : 0); x <= 512; x += 256) { c.beginPath(); c.moveTo(x, y); c.lineTo(x, y + 128); c.stroke(); }
        }
      } else if (type === 'wood') {
        for (let x = 0; x < 512; x += 3) {
          c.strokeStyle = `rgba(39,25,12,${random() * .2})`; c.lineWidth = .5 + random() * 1.5;
          c.beginPath(); c.moveTo(x, 0); c.bezierCurveTo(x + random() * 12, 150, x - random() * 9, 350, x, 512); c.stroke();
        }
        for (let x = 0; x < 512; x += 128) { c.fillStyle = '#26190e36'; c.fillRect(x, 0, 3, 512); }
      } else if (type === 'roof') {
        c.strokeStyle = '#5a63565e'; c.lineWidth = 2;
        for (let x = 0; x < 512; x += 64) { c.beginPath(); c.moveTo(x, 0); c.lineTo(x, 512); c.stroke(); }
      } else if (type === 'plaster') {
        for (let i = 0; i < 65; i++) {
          const x = random() * 512, y = random() * 512;
          const gradient = c.createRadialGradient(x, y, 0, x, y, 35 + random() * 80);
          gradient.addColorStop(0, '#7773670c'); gradient.addColorStop(1, '#77736700');
          c.fillStyle = gradient; c.fillRect(0, 0, 512, 512);
        }
      }
      const image = c.getImageData(0, 0, 512, 512);
      for (let i = 0; i < image.data.length; i += 4) {
        const grain = (random() - .5) * (type === 'asphalt' ? 40 : 17);
        for (let channel = 0; channel < 3; channel++) image.data[i + channel] += grain;
      }
      c.putImageData(image, 0, 0);
      const result = own(new T.CanvasTexture(canvas)); result.colorSpace = T.SRGBColorSpace;
      result.wrapS = result.wrapT = T.RepeatWrapping; result.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());
      return result;
    }
    function surface(type, color, roughness) {
      const map = texture(type, color);
      const result = own(new T.MeshStandardMaterial({ map, bumpMap: map, bumpScale: type === 'brick' ? .038 : .015, roughness }));
      result.userData.tileScale = type === 'brick' ? .75 : type === 'wood' ? 1 : .6;
      result.onBeforeCompile = shader => {
        shader.vertexShader = '#ifdef USE_INSTANCING\nattribute vec3 instanceSurfaceScale;\n#endif\n' + shader.vertexShader;
        shader.vertexShader = shader.vertexShader.replace('#include <uv_vertex>', '#include <uv_vertex>\n#ifdef USE_INSTANCING\nvec3 surfaceNormal=abs(normal);\nvec2 surfaceUV=surfaceNormal.z>.5?instanceSurfaceScale.xy:surfaceNormal.x>.5?instanceSurfaceScale.zy:instanceSurfaceScale.xz;\n#ifdef USE_MAP\nvMapUv *= surfaceUV;\n#endif\n#ifdef USE_BUMPMAP\nvBumpMapUv *= surfaceUV;\n#endif\n#endif');
      };
      result.customProgramCacheKey = () => 'seelo-architectural-surface-v1';
      return result;
    }
    function instance(geometry, mat, x, y, z, sx, sy, sz, rotation = null, shadow = true) {
      const key = geometry.uuid + mat.uuid + shadow;
      if (!batches.has(key)) batches.set(key, { geometry, mat, shadow, instances: [] });
      batches.get(key).instances.push({ x, y, z, sx, sy, sz, rotation });
    }
    function box(w, h, d, x, y, z, mat, shadow = true, rotation = null) { instance(boxGeometry, mat, x, y, z, w, h, d, rotation, shadow); }
    function cylinder(radius, height, x, y, z, mat, rotation = null) { instance(cylinderGeometry, mat, x, y, z, radius, height, radius, rotation); }
    function ball(x, y, z, sx, sy, sz, mat, rotation = null) { instance(sphereGeometry, mat, x, y, z, sx, sy, sz, rotation); }
    function label(text, w, h, x, y, z, foreground = '#e9e4d6', background = '#3e4d44', rotationY = 0) {
      const canvas = document.createElement('canvas'); canvas.width = Math.min(2048,Math.max(256,Math.round(256*w/h))); canvas.height = 256;
      const texture = own(new T.CanvasTexture(canvas)); texture.colorSpace = T.SRGBColorSpace;
      const mat = own(new T.MeshStandardMaterial({ map: texture, roughness: .8 }));
      const mesh = new T.Mesh(own(new T.PlaneGeometry(w, h)), mat); mesh.position.set(x, y, z); mesh.rotation.y = rotationY; scene.add(mesh);
      const draw = () => {
        const c = canvas.getContext('2d'); c.fillStyle = background; c.fillRect(0, 0, canvas.width, 256);
        c.strokeStyle = foreground + '50'; c.lineWidth = 2; c.strokeRect(13, 13, canvas.width-26, 230);
        c.fillStyle = foreground; c.textAlign = 'center'; c.textBaseline = 'middle';
        c.font = '500 145px Pretendard, sans-serif';
        const fontSize=Math.min(145,145*(canvas.width-65)/c.measureText(text).width);
        c.font = `500 ${fontSize}px Pretendard, sans-serif`; c.fillText(text,canvas.width/2,130);
        texture.needsUpdate = true;
      };
      draw(); labels.push(draw); return mesh;
    }

    // A soft photographic-style sky reflection, generated locally rather than fetched.
    const sky = document.createElement('canvas'); sky.width = 512; sky.height = 256;
    const skyContext = sky.getContext('2d'), skyGradient = skyContext.createLinearGradient(0, 0, 0, 256);
    skyGradient.addColorStop(0, '#9fb9cb'); skyGradient.addColorStop(.47, '#e6e9e3'); skyGradient.addColorStop(.62, '#a8ab9e'); skyGradient.addColorStop(1, '#7b8070');
    skyContext.fillStyle = skyGradient; skyContext.fillRect(0, 0, 512, 256);
    for (let i = 0; i < 22; i++) { skyContext.fillStyle = '#8f988c'; skyContext.fillRect(i * 27, 124 - (i % 4) * 8, 16 + i % 7, 31 + i % 13); }
    const skyTexture = own(new T.CanvasTexture(sky)); skyTexture.mapping = T.EquirectangularReflectionMapping; skyTexture.colorSpace = T.SRGBColorSpace;
    const pmrem = new T.PMREMGenerator(renderer), environment = pmrem.fromEquirectangular(skyTexture); own(environment); pmrem.dispose();
    scene.environment = environment.texture; scene.environmentIntensity = .42;
    scene.add(new T.HemisphereLight('#e3edf1', '#a2a28c', 1.45));
    const sun = new T.DirectionalLight('#fff1d7', 2.8); sun.position.set(-23, 35, 24); sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048); sun.shadow.normalBias = .025; sun.shadow.bias = -.00012; sun.shadow.radius = 3;
    Object.assign(sun.shadow.camera, { left: -35, right: 35, top: 36, bottom: -36, near: 1, far: 110 }); scene.add(sun);

    box(105, .25, 105, 0, -.27, 0, concreteEdge, false);
    box(5.6, .06, 93, 0, -.075, 0, asphalt, false);
    for (const side of [-1, 1]) {
      box(2.0, .16, 93, side * 3.8, .015, 0, pavement, false);
      for (let z = -46; z < 46; z += 1.3) box(.16, .23, 1.27, side * 2.88, .015, z, concreteEdge, false);
      box(.06, .012, 88, side * .09, -.035, 0, yellow, false);
      for (let z = -40; z < 42; z += 14) {
        box(.42, .018, .62, side * 2.36, -.028, z, metal, false);
        for (let i = 0; i < 5; i++) box(.014, .022, .57, side * 2.36 - .16 + i * .08, -.01, z, concreteEdge, false);
      }
    }
    for (let i = 0; i < 7; i++) box(.43, .015, 1.7, -2.2 + i * .73, -.027, 7, paintedWhite, false);
    // Front and side window frames have real depth and reflective recessed glazing.
    function facadeWindow(x, y, z, w, h, side = false, curtains = false) {
      const frame = curtains ? concreteEdge : metal;
      if (!side) {
        box(w + .18, h + .18, .15, x, y, z, frame, false);
        box(w, h, .035, x, y, z + .09, darkGlass, false);
        box(.045, h, .045, x, y, z + .12, frame, false);
        box(w, .06, .24, x, y - h / 2 - .035, z + .02, concreteEdge, false);
        if (curtains) for (let j = 0; j < 5; j++) box(w * .13, h * .82, .012, x - w * .34 + j * w * .17, y, z + .111, cream, false);
      } else {
        box(.15, h + .18, w + .18, x, y, z, frame, false);
        box(.035, h, w, x + (x < 0 ? .09 : -.09), y, z, darkGlass, false);
        box(.045, h, .045, x + (x < 0 ? .12 : -.12), y, z, frame, false);
      }
    }
    const neighbors = ['COFFEE', '서점', '꽃과 식물', '사진관', 'BAKERY', '작은 공방'];
    for (const side of [-1, 1]) for (let col = 0; col < 2; col++) for (let row = 0; row < 8; row++) {
      if (side === -1 && col === 0 && (row === 2 || row === 3)) continue;
      const k = row * 7 + col * 3 + (side + 1) * 4;
      const x = side * (7.1 + col * 9), z = -35 + row * 10.5, w = 4.6 + (k % 3) * .45, h = 5.6 + k % 4 * 1.5, d = 6.4;
      const wall = [whitePlaster, redBrick, concrete, paleBrick, darkBrick][k % 5];
      box(w, h, d, x, h / 2, z, wall);
      box(w + .15, .15, d + .15, x, h + .03, z, concreteEdge);
      box(w - .22, .065, d - .22, x, h + .15, z, roofMaterial, false);
      [-1,1].forEach(s => { box(.1,.33,d,x+s*(w/2-.09),h+.3,z,concreteEdge); box(w,.33,.1,x,h+.3,z+s*(d/2-.09),concreteEdge); });
      box(1.0, .7, .75, x + .7, h + .5, z - 1, paintedWhite);
      box(.82, .035, .6, x + .7, h + .87, z - 1, metal, false);
      for (let y = 3.4; y < h - .6; y += 2.45) {
        for (let n = -1; n <= 1; n++) facadeWindow(x + n * w * .3, y, z + 3.22, .78, 1.23, false, (k + n) % 5 === 0);
        for (let n = -1; n <= 1; n++) facadeWindow(x - side * (w / 2 + .02), y, z + n * 1.9, .85, 1.23, true);
        if (k % 3 === 0) {
          box(1.75, .1, .55, x, y - .78, z + 3.5, concreteEdge);
          box(1.7, .045, .035, x, y - .2, z + 3.76, metal);
          for (let n = 0; n < 6; n++) box(.025, .59, .025, x - .78 + n * .31, y - .49, z + 3.76, metal);
        }
      }
      box(w * .83, 1.95, .12, x, 1.13, z + 3.23, metal, false);
      box(w * .78, 1.8, .04, x, 1.13, z + 3.31, darkGlass, false);
      for (let n = -1; n <= 1; n++) box(.055, 1.8, .06, x + n * w * .25, 1.13, z + 3.35, cream, false);
      box(w * .94, .45, .13, x, 2.55, z + 3.29, k % 2 ? metal : timber);
      if (col === 0) label(neighbors[k % neighbors.length], w * .65, .32, x, 2.55, z + 3.37);
      box(.12, h - .4, .12, x + w / 2 - .18, (h - .4) / 2, z + 3.3, metal, false);
      if (k % 2 === 0) {
        box(.82, .57, .3, x - w / 2 + .68, 2.2, z + 3.53, cream);
        for (let n = 0; n < 5; n++) box(.7, .018, .025, x - w / 2 + .68, 2.0 + n * .08, z + 3.7, metal, false);
      }
    }

    const sx = -7.1, sz = -14;
    // Open shell: the tables, counter and pendant lights are behind the glass.
    box(4.8, .18, 6.4, sx, .09, sz, timber);
    box(4.8, 4.05, .22, sx, 2.1, sz - 3.1, whitePlaster);
    box(.22, 4.05, 6.4, sx - 2.3, 2.1, sz, paleBrick);
    box(.22, 4.05, 6.4, sx + 2.3, 2.1, sz, paleBrick);
    box(4.8, 1.4, .25, sx, 3.42, sz + 3.1, whitePlaster);
    box(5.0, .18, 6.6, sx, 4.2, sz, shopAccent);
    box(4.65, .06, 6.25, sx, 4.32, sz, roofMaterial, false);
    box(4.38,.07,6.02,sx,2.88,sz,cream,false);
    box(1.2, .7, .85, sx + 1.1, 4.69, sz - 1.4, cream);
    for (let i = 0; i < 5; i++) box(1.05,.025,.035,sx+1.1,4.48+i*.1,sz-.96,metal,false);
    box(4.35, 2.42, .018, sx, 1.42, sz + 3.23, clearGlass, false);
    [-2.18, -.67, .67, 2.18].forEach(offset => box(.075, 2.48, .11, sx + offset, 1.42, sz + 3.27, shopAccent));
    [ .22, 2.63 ].forEach(y => box(4.5, .07, .11, sx, y, sz + 3.27, shopAccent));
    box(.04, .42, .07, sx + .47, 1.23, sz + 3.36, metal, false);
    box(4.45, .63, .19, sx, 3.37, sz + 3.29, timber);
    label('망원밥상', 3.95, .55, sx, 3.37, sz + 3.4, '#e9e5d8', '#344b3b');
    label('KOREAN KITCHEN', 1.6, .16, sx, 2.86, sz + 3.25, '#635d4a', '#ddd6be');
    box(5.02, .12, 1.1, sx, 2.72, sz + 3.64, shopAccent);
    for (let n = 0; n < 12; n++) box(.405, .04, 1.08, sx - 2.23 + n * .405, 2.79, sz + 3.64, n % 2 ? cream : shopAccent, true, [ .13, 0, 0 ]);
    box(4.94, .17, .06, sx, 2.58, sz + 4.18, shopAccent);
    for (const x of [sx - 1.17, sx + 1.17]) for (const z of [sz + 1.7, sz - .6]) {
      box(.95, .08, .72, x, .92, z, timber);
      cylinder(.045, .77, x, .49, z, black);
      for (const side of [-1, 1]) {
        box(.4, .07, .4, x, .53, z + side * .65, timber);
        for (const dx of [-.14,.14]) for (const dz of [-.14,.14]) cylinder(.018,.43,x+dx,.28,z+side*.65+dz,black);
        box(.4, .32, .045, x, .79, z + side * .81, timber);
      }
      cylinder(.2,.12,x,2.43,z,metal); cylinder(.024,.38,x,2.68,z,black);
      cylinder(.16,.025,x,2.36,z,shopLight);
    }
    box(1.1, 1.0, 2.35, sx - 1.52, .68, sz - 1.52, timber);
    box(1.15,.08,2.4,sx-1.52,1.21,sz-1.52,cream);
    label('오늘의 한식',1.2,.65,sx+.8,1.9,sz-2.96,'#e3d6b5','#34453b');
    const interiorLight = new T.PointLight('#ffdbab', 14, 8, 2); interiorLight.position.set(sx,2.55,sz+.5); scene.add(interiorLight);
    box(5.0, .08, 2.05, sx, .13, sz + 4.3, pavement, false);
    for (const x of [sx - 1.3, sx + 1.3]) {
      for (let i = 0; i < 4; i++) box(1.13,.055,.105,x,.56,sz+4.08+i*.12,timber);
      for (const dx of [-.43,.43]) box(.07,.43,.38,x+dx,.31,sz+4.28,metal);
    }
    box(.6,.8,.16,sx+2.96,.73,sz+4.0,timber,true,[-.13,0,0]);
    label('한식 · 점심',.52,.5,sx+2.96,.79,sz+4.13,'#ece4cf','#394536');

    function tree(x, z, size = 1, pot = false) {
      if (pot) box(.62,.62,.62,x,.4,z,terracotta);
      else { box(1.1,.08,1.1,x,.13,z,concreteEdge,false); box(.9,.08,.9,x,.16,z,bark,false); }
      cylinder(.075 * size, 1.85 * size, x, .18 + .92 * size, z, bark);
      const top = .18 + 2.45 * size;
      for (let i = 0; i < 3; i++) {
        const angle = i * 2.1 + random() * .4;
        cylinder(.027*size,.9*size,x+Math.cos(angle)*.19*size,top-.5*size,z+Math.sin(angle)*.19*size,bark,[Math.cos(angle)*.5,0,Math.sin(angle)*.5]);
      }
      for (let i = 0; i < 12; i++) {
        const a = random() * Math.PI * 2, r = Math.sqrt(random()) * .8 * size;
        const y = top + (random() - .35) * size;
        ball(x + Math.cos(a) * r, y, z + Math.sin(a) * r, (.28+random()*.18)*size, (.28+random()*.18)*size, (.28+random()*.16)*size, i % 3 ? leafMaterial : leafLight, [random(),random(),random()]);
      }
      for (let i=0;i<(pot?110:280);i++) {
        const angle=random()*Math.PI*2, vertical=random()*2-1, radius=Math.sqrt(1-vertical*vertical)*(.55+random()*.5)*size;
        const scale=(.32+random()*.17)*size;
        instance(leafGeometry,leafCards,x+Math.cos(angle)*radius,top+.1*size+vertical*.87*size,z+Math.sin(angle)*radius,scale,scale,scale,[random()*Math.PI,random()*Math.PI,random()*Math.PI]);
      }
    }
    for (const side of [-1, 1]) for (let i = 0; i < 7; i++) {
      const z = -32 + i * 12;
      // Keep the entrance clear as the camera reaches the restaurant.
      if (!(side < 0 && (i === 1 || i === 2))) tree(side * 4.08,z,.9+random()*.16);
      if (i % 2 === 0 && !(side < 0 && i === 2)) {
        cylinder(.045,3.2,side*3.13,1.7,z+3,metal);
        box(.5,.07,.24,side*3.13,3.34,z+3,metal);
        box(.36,.018,.18,side*3.13,3.3,z+3,warmGlow,false);
      }
    }
    tree(sx-2.85,sz+3.98,.42,true); tree(sx+2.8,sz+3.25,.5,true);
    // Small wheel and frame geometry gives a bicycle a recognizable scale.
    const tire = material('#313631',.92);
    const wheelGeometry = own(new T.TorusGeometry(.32,.024,5,22));
    for (const z of [-.57,.57]) {
      const wheel = new T.Mesh(wheelGeometry,tire); wheel.rotation.y = Math.PI/2; wheel.position.set(-4.55,.48,1+z); scene.add(wheel);
      cylinder(.012,.64,-4.55,.48,1+z,metal,[Math.PI/2,0,0]);
    }
    box(.045,.67,.045,-4.55,.9,.47,shopAccent,true,[-.3,0,0]);
    box(.045,.04,1.0,-4.55,.84,1,shopAccent);
    box(.045,.65,.045,-4.55,.83,1.5,shopAccent,true,[.6,0,0]);
    box(.23,.055,.24,-4.55,1.2,.55,black); box(.32,.035,.035,-4.55,1.27,1.62,metal);

    function roundedBody(w,h,d,r) {
      const shape = new T.Shape(), left=-w/2, bottom=-h/2;
      shape.moveTo(left+r,bottom); shape.lineTo(left+w-r,bottom); shape.quadraticCurveTo(left+w,bottom,left+w,bottom+r);
      shape.lineTo(left+w,bottom+h-r); shape.quadraticCurveTo(left+w,bottom+h,left+w-r,bottom+h);
      shape.lineTo(left+r,bottom+h); shape.quadraticCurveTo(left,bottom+h,left,bottom+h-r);
      shape.lineTo(left,bottom+r); shape.quadraticCurveTo(left,bottom,left+r,bottom);
      const geometry = own(new T.ExtrudeGeometry(shape,{depth:d-2*r,bevelEnabled:true,bevelSegments:2,steps:1,bevelSize:r*.45,bevelThickness:r,curveSegments:4})); geometry.translate(0,0,-d/2+r); return geometry;
    }
    const carBody = roundedBody(1.65,.58,3.9,.14), carCabin = roundedBody(1.4,.63,1.9,.14);
    const paint = material('#d5d8d3',.3,.43), lights = material('#e8e7cf',.2), tail = material('#8b3a30',.3);
    for (const [x,z] of [[1.55,24],[-1.55,-27]]) {
      const body = new T.Mesh(carBody,paint);body.position.set(x,.61,z);body.castShadow=true;scene.add(body);
      const cabin = new T.Mesh(carCabin,darkGlass);cabin.position.set(x,1.13,z-.1);cabin.castShadow=true;scene.add(cabin);
      box(1.32,.065,1.15,x,1.48,z-.12,paint);
      for (const dx of [-.78,.78]) for (const dz of [-1.2,1.2]) {
        cylinder(.31,.16,x+dx,.37,z+dz,tire,[0,0,Math.PI/2]);
        cylinder(.17,.17,x+dx,.37,z+dz,metal,[0,0,Math.PI/2]);
      }
      for (const dx of [-.53,.53]) {box(.35,.12,.04,x+dx,.69,z+1.98,lights,false);box(.3,.12,.04,x+dx,.72,z-1.98,tail,false);}
      box(.52,.16,.02,x,.48,z+1.99,paintedWhite,false); box(1.0,.1,.025,x,.46,z+2.0,black,false);
      for (const dx of [-.9,.9]) box(.16,.1,.22,x+dx,1.13,z+.55,paint);
    }

    // Repeated frames, bricks, vegetation and furniture share draw calls.
    const transform = new T.Object3D(); let instances = 0;
    for (const batch of batches.values()) {
      const geometry = own(batch.geometry.clone());
      const uvScale = new Float32Array(batch.instances.length * 3);
      const mesh = new T.InstancedMesh(geometry,batch.mat,batch.instances.length); mesh.castShadow=batch.shadow; mesh.receiveShadow=true;
      batch.instances.forEach((item,index) => {
        transform.position.set(item.x,item.y,item.z);transform.scale.set(item.sx,item.sy,item.sz);transform.rotation.set(...(item.rotation||[0,0,0]));transform.updateMatrix();mesh.setMatrixAt(index,transform.matrix);
        const tile = batch.mat.userData.tileScale || 1;
        uvScale[index*3]=Math.max(.1,item.sx)*tile;
        uvScale[index*3+1]=Math.max(.1,item.sy)*tile;
        uvScale[index*3+2]=Math.max(.1,item.sz)*tile;
      });
      geometry.setAttribute('instanceSurfaceScale',new T.InstancedBufferAttribute(uvScale,3));mesh.instanceMatrix.needsUpdate=true;mesh.computeBoundingSphere();scene.add(mesh);instances+=batch.instances.length;
    }
    document.fonts.ready.then(() => { labels.forEach(draw=>draw()); invalidate(); });
    return { shopAccent, shopLight, instances, batches: batches.size };
  }
};
