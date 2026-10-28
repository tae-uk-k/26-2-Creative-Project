/* Reading stops, not a narrow proximity hint: one gesture advances one scene. */
(() => {
  'use strict';
  const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
  const nearest=(points,y)=>points.reduce((best,p,i)=>Math.abs(p-y)<Math.abs(points[best]-y)?i:best,0);
  const spring=t=>t*t*t*(t*(t*6-15)+10);
  function attach({track,stops,disabled=()=>false}){
    let points=[],top=0,travel=1,exit=0,end=0,raf=0,timer=0,wheelTimer=0;
    let settling=false,held=false,armed=false,locked=false,escape=0,intent=0,lastDirection=0,origin=0,lastWheelAt=0;
    let touchY=null,touchStartY=null,touchIndex=-1,pendingStep=null,touchPanel=null,destroyed=false;
    let snapDirection=0,lastY=scrollY;
    const reduce=matchMedia('(prefers-reduced-motion: reduce)'),listeners=[];
    const off=()=>destroyed||reduce.matches||disabled()||document.hidden||!!document.querySelector('dialog[open]');
    function listen(target,type,fn,options){target.addEventListener(type,fn,options);listeners.push(()=>target.removeEventListener(type,fn,options));}
    function notify(){window.dispatchEvent(new CustomEvent('seelo-magnet-frame'));}
    function state(value,index){track.dataset.snapState=value;if(index!==undefined)track.dataset.snapIndex=String(index);}
    function cancel(){cancelAnimationFrame(raf);raf=0;settling=false;clearTimeout(timer);timer=0;state('idle');}
    function refresh(){
      const bounds=track.getBoundingClientRect(),nextTop=bounds.top+scrollY,nextTravel=Math.max(1,track.offsetHeight-innerHeight);
      const nextPoints=stops.map((p,i)=>i===0&&p===0&&nextTop<140?0:nextTop+p*nextTravel);
      if(points.length!==nextPoints.length||nextPoints.some((p,i)=>Math.abs(p-points[i])>.5))cancel();
      top=nextTop;travel=nextTravel;points=nextPoints;
      end=top+travel;exit=top+track.offsetHeight;
      track.dataset.snapStops=points.map(Math.round).join(',');
    }
    function inside(){return points.length&&scrollY>=points[0]-2&&scrollY<=end+2;}
    function scrollable(target,direction){
      const panel=target?.closest?.('.detail-card,.city-chapter,.focus-card,textarea,[data-native-scroll]');
      if(!panel||panel.scrollHeight<=panel.clientHeight+2)return false;
      return direction>0?panel.scrollTop+panel.clientHeight<panel.scrollHeight-2:panel.scrollTop>2;
    }
    function animate(y,index){
      if(off())return false;
      cancel();armed=false;origin=nearest(points,scrollY);
      const from=scrollY,to=clamp(y,0,Math.max(0,document.documentElement.scrollHeight-innerHeight));
      if(Math.abs(from-to)<.75){window.scrollTo({top:to,behavior:'instant'});state('settled',index);notify();return true;}
      const start=performance.now(),duration=clamp(850+Math.abs(to-from)*.18,900,1200);
      settling=true;state('settling',index);
      function step(now){
        raf=0;if(off()){cancel();return;}
        const t=clamp((now-start)/duration,0,1);
        window.scrollTo({top:t===1?to:from+(to-from)*spring(t),behavior:'instant'});notify();
        if(t<1)raf=requestAnimationFrame(step);
        else{settling=false;state('settled',index);if(locked&&performance.now()-lastWheelAt>=170){locked=false;intent=0;lastDirection=0;clearTimeout(wheelTimer);}notify();}
      }
      raf=requestAnimationFrame(step);return true;
    }
    function go(index){escape=0;pendingStep=null;return animate(points[clamp(index,0,points.length-1)],clamp(index,0,points.length-1));}
    function advance(index,direction){
      if(index===points.length-1&&direction>0){escape=1;return animate(exit,'after');}
      if(index===0&&direction<0){escape=-1;return false;}
      escape=0;return go(index+direction);
    }
    function settle(){
      timer=0;if(off()||held||settling||!armed||escape||!inside())return;
      const pending=pendingStep;pendingStep=null;
      const direction=pending?.direction||snapDirection;
      // Only attract stops ahead in the user's direction, never the closer stop behind.
      // A long native swipe can pass its original next stop; do not pull back to it.
      if(direction>0){
        const first=pending?pending.index+1:0;
        const index=points.findIndex((p,i)=>i>=first&&p>=scrollY);
        if(index<0){escape=1;animate(exit,'after');}else go(index);
      }else if(direction<0){
        const last=pending?pending.index-1:points.length-1;
        let index=-1;for(let i=points.length-1;i>=0;i--){if(i<=last&&points[i]<=scrollY){index=i;break;}}
        if(index<0){escape=-1;}else go(index);
      }else go(nearest(points,scrollY));
    }
    function queue(delay=170){clearTimeout(timer);if(!off()&&!held&&!settling&&armed&&!escape)timer=setTimeout(settle,delay);}
    function unlock(){
      clearTimeout(wheelTimer);wheelTimer=setTimeout(()=>{
        if(settling){unlock();return;}
        locked=false;intent=0;lastDirection=0;
      },170);
    }
    function wheel(event){
      if(off()||event.ctrlKey||Math.abs(event.deltaX||0)>=Math.abs(event.deltaY||0))return;
      const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?innerHeight:1),direction=Math.sign(delta);
      if(!direction||scrollable(event.target,direction))return;
      lastWheelAt=performance.now();snapDirection=direction;
      if(escape&&direction!==escape)escape=0;
      if(settling){
        if(event.cancelable)event.preventDefault();
        if(lastDirection&&direction!==lastDirection&&Math.abs(delta)>30){const back=origin;go(back);lastDirection=direction;}
        unlock();return;
      }
      if(!inside()||escape)return;
      const index=nearest(points,scrollY),latched=Math.abs(points[index]-scrollY)<14;
      if(settling||locked){
        if(event.cancelable)event.preventDefault();
        if(lastDirection&&direction!==lastDirection&&Math.abs(delta)>30){const back=origin;go(back);lastDirection=direction;}
        unlock();return;
      }
      if(latched){
        if(index===0&&direction<0){escape=-1;return;}
        if(event.cancelable)event.preventDefault();
        if(direction!==lastDirection)intent=0;
        lastDirection=direction;intent+=Math.abs(delta);unlock();
        if(intent>=32){locked=true;advance(index,direction);}
        else{pendingStep={index,direction};armed=true;queue();}
      }else{armed=true;queue();}
    }
    function key(event){
      if(off()||event.ctrlKey||event.metaKey||event.altKey||event.target?.closest?.('input,textarea,select,[contenteditable="true"]'))return;
      if(event.key===' '&&event.target?.closest?.('button,a'))return;
      if(event.key==='Home'||event.key==='End'){cancel();armed=false;escape=event.key==='Home'?-1:1;locked=false;clearTimeout(wheelTimer);return;}
      const direction=['ArrowDown','PageDown',' '].includes(event.key)?(event.shiftKey?-1:1):['ArrowUp','PageUp'].includes(event.key)?-1:0;
      if(!direction||scrollable(event.target,direction))return;
      if(escape&&direction!==escape)escape=0;
      if(!inside()||escape)return;
      const index=nearest(points,scrollY);
      if(index===0&&direction<0)return;
      event.preventDefault();
      if(event.repeat)return;
      if(settling){if(direction!==lastDirection)go(origin);return;}
      lastDirection=direction;advance(index,direction);
    }
    function pointerDown(event){
      if(off()||!inside()||event.target?.closest?.('a,button,input,textarea,select,dialog'))return;
      cancel();held=true;armed=true;escape=0;pendingStep=null;snapDirection=0;lastY=scrollY;
    }
    function pointerUp(){if(held){held=false;queue(140);}}
    function touchStart(event){
      if(off()||event.touches?.length!==1)return;
      cancel();escape=0;held=true;armed=true;pendingStep=null;snapDirection=0;lastY=scrollY;touchStartY=scrollY;touchY=event.touches[0].clientY;
      const panel=event.target?.closest?.('.detail-card,.city-chapter,.focus-card,textarea,[data-native-scroll]');
      touchPanel=panel?{top:panel.scrollTop,height:panel.clientHeight,scrollHeight:panel.scrollHeight}:null;
      const index=nearest(points,scrollY);touchIndex=Math.abs(points[index]-scrollY)<16?index:-1;
    }
    function touchEnd(event){
      if(touchY===null)return;
      const distance=touchY-(event.changedTouches?.[0]?.clientY??touchY),direction=Math.sign(distance);
      const nativeAtStart=touchPanel&&touchPanel.scrollHeight>touchPanel.height+2&&(direction>0?touchPanel.top+touchPanel.height<touchPanel.scrollHeight-2:touchPanel.top>2);
      if(touchIndex>=0&&Math.abs(distance)>40&&!nativeAtStart)pendingStep={index:touchIndex,direction};
      if(touchStartY>end&&direction<0)escape=0;
      touchY=touchStartY=null;touchIndex=-1;touchPanel=null;held=false;queue(140);
    }
    function scrolled(){
      const delta=scrollY-lastY;lastY=scrollY;
      if(!settling&&inside()){
        if(Math.abs(delta)>.01)snapDirection=Math.sign(delta);
        armed=true;queue();
      }
    }
    function visibility(){if(document.hidden){cancel();clearTimeout(wheelTimer);locked=held=false;}else refresh();}
    listen(window,'wheel',wheel,{passive:false});listen(window,'keydown',key);
    listen(window,'pointerdown',pointerDown,{passive:true});listen(window,'pointerup',pointerUp,{passive:true});listen(window,'pointercancel',pointerUp,{passive:true});
    listen(window,'touchstart',touchStart,{passive:true});listen(window,'touchend',touchEnd,{passive:true});listen(window,'touchcancel',()=>{held=false;touchY=null;queue();},{passive:true});
    listen(window,'scroll',scrolled,{passive:true});listen(window,'scrollend',()=>queue(100));listen(window,'resize',refresh,{passive:true});
    listen(window,'blur',()=>{cancel();held=false;locked=false;clearTimeout(wheelTimer);});
    listen(document,'visibilitychange',visibility);reduce.addEventListener('change',refresh);document.fonts?.ready.then(refresh);listen(window,'pageshow',refresh);
    refresh();
    return {go,refresh,cancel,get active(){return settling;},get positions(){return [...points];},destroy(){cancel();destroyed=true;clearTimeout(wheelTimer);listeners.forEach(fn=>fn());reduce.removeEventListener('change',refresh);}};
  }
  window.SeeloMagnet={attach,nearest,spring};
})();
