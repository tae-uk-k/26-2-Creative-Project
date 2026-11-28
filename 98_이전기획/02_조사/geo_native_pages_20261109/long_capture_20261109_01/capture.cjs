// Capture only our local static artifacts in an isolated headless Edge process.
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const root = __dirname;
const profile = path.join(root, 'browser-profile');
fs.mkdirSync(profile, {recursive:true});
const launchTime = Date.now();
const edge = spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', ['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'], {windowsHide:true,stdio:'ignore'});
const delay = ms => new Promise(r=>setTimeout(r,ms));
let socket;
let seq=0;
const pending = new Map();
async function cdp(method,params={}){
  const id=++seq;
  const result=new Promise((resolve,reject)=>pending.set(id,{resolve,reject}));
  socket.send(JSON.stringify({id,method,params}));
  return result;
}
(async()=>{
  try{
    const active=path.join(profile,'DevToolsActivePort');
    for(let i=0;i<100;i++){if(fs.existsSync(active)&&fs.statSync(active).mtimeMs>=launchTime-1000)break;await delay(100);}
    const port=fs.readFileSync(active,'utf8').split('\n')[0];
    const targets=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();
    const target=targets.find(t=>t.type==='page');
    socket=new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((r,j)=>{socket.addEventListener('open',r,{once:true});socket.addEventListener('error',j,{once:true});});
    socket.addEventListener('message',event=>{const msg=JSON.parse(event.data);if(msg.id&&pending.has(msg.id)){const p=pending.get(msg.id);pending.delete(msg.id);msg.error?p.reject(new Error(JSON.stringify(msg.error))):p.resolve(msg.result);}});
    await cdp('Page.enable');
    await cdp('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:2,mobile:false});
    const results=[];
    for(const input of JSON.parse(fs.readFileSync(path.join(root,'inputs.json'),'utf8'))){
      await cdp('Page.navigate',{url:input.url});
      for(let i=0;i<100;i++){
        const a=await cdp('Runtime.evaluate',{expression:"document.readyState==='complete'&&!!document.querySelector("+JSON.stringify(input.selector)+")",returnByValue:true});
        if(a.result.value)break;
        await delay(100);
      }
      await cdp('Runtime.evaluate',{expression:'document.fonts.ready.then(()=>true)',awaitPromise:true,returnByValue:true});
      await delay(700);
      const result=await cdp('Runtime.evaluate',{expression:`(()=>{const e=document.querySelector(${JSON.stringify(input.selector)});const r=e.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,text:e.innerText,scrolling:[...e.querySelectorAll('*')].filter(n=>n.clientHeight>10&&n.scrollHeight>n.clientHeight+2&&['auto','scroll'].includes(getComputedStyle(n).overflowY)).map(n=>({tag:n.tagName,h:n.clientHeight,total:n.scrollHeight}))}})()`,returnByValue:true});
      const data=result.result.value;
      const png=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:data.x,y:data.y,width:data.width,height:data.height,scale:1}});
      fs.writeFileSync(path.join(root,input.name+'-long.png'),Buffer.from(png.data,'base64'));
      results.push({...input,...data,pixelWidth:Math.round(data.width*2),pixelHeight:Math.round(data.height*2)});
    }
    fs.writeFileSync(path.join(root,'capture-results.json'),JSON.stringify(results,null,2));
    console.log(JSON.stringify(results.map(({text,...r})=>r),null,2));
  }finally{
    if(socket?.readyState===WebSocket.OPEN){try{await cdp('Browser.close');}catch{}socket.close();}
    else edge.kill();
  }
})().catch(e=>{console.error(e);process.exitCode=1;edge.kill();});
