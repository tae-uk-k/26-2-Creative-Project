/* One scroll measurement and one bounded animation loop per story. */
(() => {
  'use strict';
  const clamp=(n,a=0,b=1)=>Math.max(a,Math.min(b,n));
  const ease=(a,b,n)=>{const t=clamp((n-a)/(b-a));return t*t*(3-2*t);};
  function weight(x,index,last=3){
    const enter=index===0?1:ease(index-.10,index+.16,x);
    const leave=index===last?0:ease(index+.74,index+.99,x);
    return enter*(1-leave);
  }
  function create({track,render,measure=()=>{},prepare=()=>{},smoothing=46,snapStops=null,disabled=()=>false}){
    let frame=0,top=0,travel=1,target=0,value=0,last=0,drawn=-1,layoutDirty=true,force=true,visible=true,destroyed=false;
    const magnet=snapStops&&window.SeeloMagnet?window.SeeloMagnet.attach({track,stops:snapStops,disabled}):null;
    const reduce=matchMedia('(prefers-reduced-motion: reduce)');
    const readTarget=()=>{target=clamp((scrollY-top)/travel);};
    function request(){if(!frame&&!destroyed&&!document.hidden)frame=requestAnimationFrame(tick);}
    function tick(now){
      frame=0;if(destroyed||document.hidden)return;
      if(layoutDirty){
        prepare({reduced:reduce.matches});measure();
        const bounds=track.getBoundingClientRect();
        top=bounds.top+scrollY;travel=Math.max(1,track.offsetHeight-innerHeight);
        readTarget();layoutDirty=false;force=true;
        if(drawn<0)value=target;
      }
      if(!visible&&!force){last=0;return;}
      const dt=last?Math.min(34,now-last):16.67;last=now;
      value=reduce.matches||magnet?.active?target:value+(target-value)*(1-Math.exp(-dt/smoothing));
      if(Math.abs(target-value)<.000015)value=target;
      if(force||Math.abs(drawn-value)>.000008){render(value,{reduced:reduce.matches,time:now,travel,top});drawn=value;force=false;}
      if(value!==target)request();else last=0;
    }
    const onScroll=()=>{readTarget();request();};
    const refresh=()=>{layoutDirty=true;force=true;request();};
    const onVisibility=()=>{if(document.hidden){cancelAnimationFrame(frame);frame=0;last=0;}else refresh();};
    addEventListener('scroll',onScroll,{passive:true});addEventListener('seelo-magnet-frame',onScroll);addEventListener('resize',refresh,{passive:true});
    document.addEventListener('visibilitychange',onVisibility);reduce.addEventListener('change',refresh);
    const observer='IntersectionObserver' in window?new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible){force=true;request();}},{rootMargin:'100px'}):null;
    observer?.observe(track);document.fonts?.ready.then(refresh);
    addEventListener('pageshow',refresh);
    request();
    return {refresh,request,go(index,last=3){if(magnet&&!reduce.matches&&!disabled())return magnet.go(index);const p=index===0?0:(index+.38)/(last+.45);window.scrollTo({top:top+p*travel,behavior:reduce.matches?'instant':'smooth'});},destroy(){destroyed=true;cancelAnimationFrame(frame);magnet?.destroy();observer?.disconnect();removeEventListener('scroll',onScroll);removeEventListener('seelo-magnet-frame',onScroll);removeEventListener('resize',refresh);document.removeEventListener('visibilitychange',onVisibility);reduce.removeEventListener('change',refresh);}};
  }
  window.SeeloScroll={create,clamp,ease,weight};
})();
