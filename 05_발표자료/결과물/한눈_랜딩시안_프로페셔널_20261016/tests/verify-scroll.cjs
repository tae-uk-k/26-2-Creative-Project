const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const frames=new Map(),events={},mediaEvents={},documentEvents={};let id=0,y=0,reads=0,time=0,reduced=false,measurements=0;
const track={offsetHeight:5000,getBoundingClientRect(){reads++;return {top:100-y,bottom:5100-y};}};
const c={Math,window:{scrollTo(){}},get scrollY(){return y;},innerHeight:1000,document:{hidden:false,addEventListener:(k,v)=>documentEvents[k]=v,removeEventListener(){}},matchMedia:()=>({get matches(){return reduced;},addEventListener:(k,v)=>mediaEvents[k]=v,removeEventListener(){}}),requestAnimationFrame:f=>(frames.set(++id,f),id),cancelAnimationFrame:i=>frames.delete(i),addEventListener:(k,v)=>events[k]=v,removeEventListener(){}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../assets/scroll-story.js'),'utf8'),c);
const samples=[];const driver=c.window.SeeloScroll.create({track,measure:()=>measurements++,render:p=>samples.push(p)});
function drain(){let n=0;while(frames.size){assert(n++<300,'must settle within bounded frames');const batch=[...frames.values()];frames.clear();for(const f of batch)f(time+=16.67);}}
drain();assert.equal(frames.size,0);assert.equal(reads,1);
y=2100;events.scroll();drain();assert.equal(samples.at(-1),.5);assert.equal(reads,1,'scroll frames must not read DOM geometry');assert.equal(measurements,1);
y=4100;events.scroll();drain();assert.equal(samples.at(-1),1);y=100;events.scroll();drain();assert.equal(samples.at(-1),0);
assert(samples.every(p=>Number.isFinite(p)&&p>=0&&p<=1));
for(let chapter=0;chapter<4;chapter++)assert.equal(c.window.SeeloScroll.weight(chapter+.38,chapter),1,'reading stop must have fully visible text');
c.document.hidden=true;documentEvents.visibilitychange();events.scroll();assert.equal(frames.size,0);c.document.hidden=false;documentEvents.visibilitychange();drain();
reduced=true;mediaEvents.change();drain();assert.equal(frames.size,0);
driver.destroy();console.log('PASS: bounded scroll smoothing, fast reverse, stable reading stops, no geometry reads during scroll, idle and hidden frame suspension.');
