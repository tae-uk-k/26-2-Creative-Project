const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
let now=0,y=0,id=0,dialog=false,reduced=false,geometryReads=0;
const jobs=new Map();
function target(){const handlers=new Map();return {addEventListener(t,f){if(!handlers.has(t))handlers.set(t,new Set());handlers.get(t).add(f);},removeEventListener(t,f){handlers.get(t)?.delete(f);},dispatchEvent(e){for(const f of [...handlers.get(e.type)||[]])f(e);}};}
const win=target(),doc=Object.assign(target(),{hidden:false,documentElement:{scrollHeight:7000},querySelector:()=>dialog?{}:null});
win.scrollTo=({top})=>{const changed=Math.abs(y-top)>.0001;y=top;if(changed)win.dispatchEvent({type:'scroll'});};
const track={offsetHeight:5000,dataset:{},getBoundingClientRect(){geometryReads++;return {top:80-y,bottom:5080-y};}};
const context={console,Math,window:win,document:doc,get scrollY(){return y;},innerHeight:1000,performance:{now:()=>now},CustomEvent:class{constructor(type,init){this.type=type;this.detail=init?.detail;}},matchMedia:()=>({get matches(){return reduced;},addEventListener(){},removeEventListener(){}}),requestAnimationFrame:f=>{jobs.set(++id,{at:now+16,f,raf:true});return id;},cancelAnimationFrame:i=>jobs.delete(i),setTimeout:(f,delay)=>{jobs.set(++id,{at:now+delay,f});return id;},clearTimeout:i=>jobs.delete(i)};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../assets/magnetic-scroll.js'),'utf8'),context);
const magnet=win.SeeloMagnet.attach({track,stops:[0,.25,.5,.85]});
function advance(ms){const end=now+ms;let count=0;for(;;){const next=[...jobs].filter(([,j])=>j.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;assert(count++<1000,'animation/timer loop must terminate');jobs.delete(next[0]);now=next[1].at;next[1].f(now);}now=end;}
const empty={closest:()=>null};
function wheel(delta,target=empty){const event={type:'wheel',deltaY:delta,deltaX:0,deltaMode:0,target,cancelable:true,prevented:false,preventDefault(){this.prevented=true;}};win.dispatchEvent(event);return event;}
function closeTo(a,b){assert(Math.abs(a-b)<.01,`${a} must equal ${b}`);}
assert.deepEqual(Array.from(magnet.positions),[0,1080,2080,3480]);
// Slow take-off and landing; no initial jump or overshoot.
assert(win.SeeloMagnet.spring(.1)<.01);assert(win.SeeloMagnet.spring(.2)<.06);
assert(Math.abs(win.SeeloMagnet.spring(.5)-.5)<1e-8);assert(win.SeeloMagnet.spring(.9)>.99);
let previous=0;for(let i=0;i<=100;i++){const next=win.SeeloMagnet.spring(i/100);assert(next>=previous-1e-9&&next<=1);previous=next;}
magnet.go(1);advance(150);assert(y>0&&y<1080*.1,'first 150ms must ease in slowly');advance(1400);closeTo(y,1080);magnet.go(0);advance(1500);closeTo(y,0);
assert(wheel(100).prevented);advance(1500);closeTo(y,1080);assert.equal(track.dataset.snapState,'settled');assert.equal(jobs.size,0,'settled page must have no running animation or retry timer');
wheel(100);for(let i=0;i<8;i++){advance(15);wheel(20-i*2);}advance(1500);closeTo(y,2080); // inertial tail is one gesture
// A small movement must settle along the gesture, even when the old stop is closer.
magnet.go(1);advance(1500);win.scrollTo({top:1100});advance(1700);closeTo(y,2080);
magnet.go(2);advance(1500);win.scrollTo({top:2060});advance(1700);closeTo(y,1080);
// Native wheel fallback between stops must not pull against its direction.
magnet.go(1);advance(1500);win.scrollTo({top:1100});assert(!wheel(4).prevented);win.scrollTo({top:1104});advance(1700);closeTo(y,2080);
magnet.go(2);advance(1500);win.scrollTo({top:2060});assert(!wheel(-4).prevented);win.scrollTo({top:2056});advance(1700);closeTo(y,1080);
// Below-threshold wheel gestures still advance softly after release.
magnet.go(1);advance(1500);assert(wheel(4).prevented);advance(1700);closeTo(y,2080);
magnet.go(2);advance(1500);assert(wheel(-4).prevented);advance(1700);closeTo(y,1080);
// Pointer/scrollbar movement follows its release direction as well.
magnet.go(2);advance(1500);win.dispatchEvent({type:'pointerdown',target:empty});win.scrollTo({top:1720});win.dispatchEvent({type:'pointerup'});advance(1700);closeTo(y,1080);
magnet.go(1);advance(1500);win.dispatchEvent({type:'pointerdown',target:empty});win.scrollTo({top:1140});win.dispatchEvent({type:'pointerup'});advance(1700);closeTo(y,2080);
wheel(-100);advance(1500);closeTo(y,1080);
dialog=true;assert(!wheel(100).prevented);advance(1500);closeTo(y,1080);dialog=false;
const panel={scrollHeight:600,clientHeight:200,scrollTop:20,closest(){return this;}};
assert(!wheel(100,panel).prevented);closeTo(y,1080);panel.scrollTop=400;assert(wheel(100,panel).prevented);advance(1500);closeTo(y,2080);
magnet.go(3);advance(1500);closeTo(y,3480);wheel(100);advance(1500);closeTo(y,5080);assert.equal(track.dataset.snapIndex,'after');assert(!wheel(100).prevented);
magnet.go(0);advance(1500);win.dispatchEvent({type:'touchstart',touches:[{clientY:600}],target:empty});win.scrollTo({top:100});win.dispatchEvent({type:'touchend',changedTouches:[{clientY:540}],target:empty});advance(1700);closeTo(y,1080);
// A long swipe must never be pulled back to the first stop it already passed.
magnet.go(0);advance(1500);win.dispatchEvent({type:'touchstart',touches:[{clientY:800}],target:empty});win.scrollTo({top:1400});win.dispatchEvent({type:'touchend',changedTouches:[{clientY:200}],target:empty});
let lastPosition=y;for(let i=0;i<110;i++){advance(16);assert(y>=lastPosition,'downward settling must never reverse');lastPosition=y;}closeTo(y,2080);
magnet.go(3);advance(1500);win.dispatchEvent({type:'touchstart',touches:[{clientY:200}],target:empty});win.scrollTo({top:1700});win.dispatchEvent({type:'touchend',changedTouches:[{clientY:800}],target:empty});
lastPosition=y;for(let i=0;i<110;i++){advance(16);assert(y<=lastPosition,'upward settling must never reverse');lastPosition=y;}closeTo(y,1080);
// The region after the last stop exits forward instead of attracting backwards.
magnet.go(3);advance(1500);win.scrollTo({top:3500});advance(1700);closeTo(y,5080);
assert.equal(geometryReads,1,'no geometry reads while snapping');
// Home must cancel a running snap rather than fight the browser's navigation.
magnet.go(2);advance(30);win.dispatchEvent({type:'keydown',key:'Home',target:empty});win.scrollTo({top:0});advance(1500);closeTo(y,0);
// A touch inside an overflowing card keeps scrolling the card first.
magnet.go(1);advance(1500);panel.scrollTop=20;win.dispatchEvent({type:'touchstart',touches:[{clientY:600}],target:panel});win.dispatchEvent({type:'touchend',changedTouches:[{clientY:520}],target:panel});advance(1700);closeTo(y,1080);
reduced=true;assert(!wheel(100).prevented);assert.equal(magnet.go(2),false);
magnet.destroy();assert.equal(jobs.size,0);
console.log('PASS: wheel paging, inertia guard, directional gravity without rollback, reverse, native card scroll, modal bypass, last-scene exit, touch paging, reduced motion and zero per-frame geometry reads.');
