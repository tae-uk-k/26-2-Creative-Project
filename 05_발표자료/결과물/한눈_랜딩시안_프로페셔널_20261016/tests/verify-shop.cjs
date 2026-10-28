// Model and scroll-state checks. Does not substitute for browser/WebGL verification.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const base=path.resolve(__dirname,'..');
const lib={console,AbortController};
vm.runInNewContext(fs.readFileSync(path.join(base,'assets/three.global.js'),'utf8'),lib);
const T=lib.THREE, frames=new Map(),nodes=new Map();let id=0,y=0,reduced=false;
function element(){return {style:{},dataset:{},clientWidth:650,clientHeight:475,offsetHeight:2808,attrs:{},classList:{contains:()=>false,toggle(){}},getBoundingClientRect:()=>({top:-y,bottom:2808-y}),setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},addEventListener(){},scrollIntoView(){}};}
const panels=Array.from({length:3},(_,i)=>{const e=element();e.dataset.phase=String(i);e.classList.contains=()=>i===1;return e;});
const pager=[element(),element(),element()];
const node=s=>{if(!nodes.has(s))nodes.set(s,element());return nodes.get(s);};
const document={hidden:false,body:element(),querySelector:node,querySelectorAll:s=>s==='.satellite'?panels:pager,addEventListener(){},createElement:()=>({width:0,height:0,getContext:()=>({fillRect(){},fillText(){}})})};
let scene,renderCount=0;
class Renderer{constructor(){this.shadowMap={};this.info={render:{calls:0,triangles:0}};}setPixelRatio(){}setClearColor(){}setSize(){}render(s,c){scene=s;s.updateMatrixWorld(true);c.updateMatrixWorld(true);renderCount++;}dispose(){}}
const context={console,Math,Set,document,innerHeight:720,get scrollY(){return y;},devicePixelRatio:1,window:{THREE:{...T,WebGLRenderer:Renderer}},matchMedia:q=>({get matches(){return q.includes('reduced')?reduced:false;},addEventListener(){}}),requestAnimationFrame:f=>{frames.set(++id,f);return id;},cancelAnimationFrame:i=>frames.delete(i),addEventListener(){}};
const src=fs.readFileSync(path.join(base,'assets/shop-model.js'),'utf8').replace(/\}\)\(\);\s*$/,'globalThis.test={update,configureMotion,tick};})();');
vm.runInNewContext(src,context);
assert.equal(node('.shop-story').dataset.renderState,'ready');context.test.tick(16);
let meshes=0,triangles=0;
scene.traverse(o=>{if(o.isMesh){meshes++;triangles+=(o.geometry.index?.count||o.geometry.attributes.position.count)/3;assert([...o.matrixWorld.elements].every(Number.isFinite));}});
assert(triangles<30000);
for(const [p,expected]of [[.18,0],[.52,1],[.90,2]]){context.test.update(p);panels.forEach((e,i)=>assert.equal(e.inert,i!==expected));}
assert.equal(node('[data-orbit-bar]').style.transform,'scaleX(0.4)');
const before=renderCount;context.test.tick(32);context.test.tick(48);assert.equal(renderCount,before,'idle scene must not render continuously');
reduced=true;context.test.configureMotion();context.test.update(0);panels.forEach(e=>assert.equal(e.inert,false));
console.log(`PASS: Three r${T.REVISION}, ${meshes} meshes, ${triangles} triangles; chapter isolation, bar fill, idle rendering, reduced motion.`);
