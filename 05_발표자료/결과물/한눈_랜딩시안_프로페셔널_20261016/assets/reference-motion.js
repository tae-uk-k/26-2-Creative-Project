(() => {
  'use strict';
  const track=document.querySelector('[data-motion-track]');if(!track||!window.SeeloScroll)return;
  const {clamp,ease,weight,create}=window.SeeloScroll;
  const pin=document.querySelector('[data-motion-pin]'),kinetic=document.body.classList.contains('kinetic');
  const scenes=[...document.querySelectorAll('[data-scene]')],chapters=[...document.querySelectorAll('[data-chapter]')];
  const originalWindows=[...document.querySelectorAll('[data-window]')],narratives=[...document.querySelectorAll('[data-narrative]')];
  const store=document.querySelector('.store-window'),intro=document.querySelector('.window-intro'),stage=document.querySelector('.desktop-stage');
  const context=document.querySelector('.focus-context'),contextTitle=document.querySelector('[data-focus-title]'),contextCount=document.querySelector('[data-focus-count]');
  const orbit=document.querySelector('.orbit-path'),art=document.querySelector('.kinetic-art'),toggle=document.querySelector('.motion-switch');
  const names=['전체 보기','AI 추천 진단','가게 정보 정비','정비 전후 비교'];
  const mobile=matchMedia('(max-width:760px)'),states=new WeakMap(),focusCards=[],flight=[];
  const angles=[-5,5,-5,4,-4,4,0];let paused=false,currentPhase=-1,deck,width=1,height=1;
  const kineticParts=kinetic?scenes.map(el=>({
    types:[...el.querySelectorAll('[data-kinetic-type]')],
    report:el.querySelector('.find-demo'),shapes:[...el.querySelectorAll('.find-shapes i')],
    sheets:[...el.querySelectorAll('.edit-sheet')],backdrop:[...el.querySelectorAll('.fix-backdrop i,.measure-backdrop i')],
    symbol:el.querySelector('.fix-symbol i'),numbers:[...el.querySelectorAll('[data-kinetic-number]')],
    arrow:el.querySelector('.comparison-arrow')
  })):[];
  const artModel=art?.querySelector('.art-pill img'),artCircle=art?.querySelector('.art-circle'),artTags=art?[...art.querySelectorAll('.art-tag')]:[];
  function move(el,value){if(el)el.style.transform=paused?'none':value;}
  if(!kinetic){
    deck=document.createElement('div');deck.className='focus-deck';stage.append(deck);
    [1,6,4].forEach(id=>{
      const original=originalWindows.find(el=>Number(el.dataset.window)===id),card=original.cloneNode(true);
      card.removeAttribute('data-window');card.removeAttribute('aria-hidden');card.classList.add('focus-card','is-focus-window');
      card.style.cssText='--focus:1';card.querySelectorAll('[id]').forEach(el=>el.removeAttribute('id'));
      card.querySelectorAll('.focus-detail').forEach(el=>el.removeAttribute('aria-hidden'));deck.append(card);focusCards.push(card);
    });
  }
  function show(el,opacity,interactive=true){
    if(!el)return;el.style.opacity=opacity.toFixed(4);
    const hidden=opacity<.06;
    if(states.get(el)!==hidden){el.inert=hidden;el.setAttribute('aria-hidden',String(hidden));states.set(el,hidden);}
    el.style.pointerEvents=interactive&&opacity>.8?'auto':'none';
  }
  function measure(){
    if(!stage)return;
    width=stage.clientWidth;height=stage.clientHeight;
    deck.style.top=mobile.matches?`${Math.max(0,innerHeight*.42-stage.offsetTop)}px`:'';
    const left=deck.offsetLeft,top=deck.offsetTop,deckWidth=deck.clientWidth;
    [1,6,4].forEach((id,index)=>{
      const original=originalWindows.find(el=>Number(el.dataset.window)===id);
      const centerX=original.offsetLeft+original.offsetWidth/2,centerY=original.offsetTop+original.offsetHeight/2;
      flight[index]={x:centerX-(left+deckWidth/2),y:centerY-(top+focusCards[index].offsetHeight/2),scale:clamp(original.offsetWidth/Math.max(1,deckWidth),.35,.72)};
    });
  }
  function render(p,{reduced,time}){
    const x=p*3.45,weights=[0,1,2,3].map(i=>weight(x,i));
    document.body.classList.toggle('motion-static',reduced);
    if(reduced){
      [...scenes,...narratives,...originalWindows].forEach(el=>{show(el,1);el.style.transform='none';});
      kineticParts.forEach(part=>[...part.types,part.report,...part.shapes,...part.sheets,...part.backdrop,part.symbol,...part.numbers,part.arrow].forEach(el=>{if(el)el.style.transform='none';}));
      [art,artModel,artCircle,...artTags].forEach(el=>{if(el)el.style.transform='none';});
      focusCards.forEach(el=>show(el,0));
      window.dispatchEvent(new CustomEvent('seelo-scene',{detail:{progress:p,phase:0,paused:true,reduced:true,time}}));return;
    }
    const phase=weights.reduce((best,v,i)=>v>weights[best]?i:best,0);
    if(phase!==currentPhase){
      currentPhase=phase;pin.dataset.phase=String(phase);
      chapters.forEach((el,i)=>{if(i===phase)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');});
      if(contextTitle)contextTitle.textContent=names[phase];if(contextCount)contextCount.textContent=String(phase).padStart(2,'0');
    }
    if(kinetic){
      scenes.forEach((el,i)=>{
        const enter=i===0?1:ease(i-.10,i+.16,x),leave=i===3?0:ease(i+.74,i+.99,x);
        show(el,weights[i]);el.style.transform=`translate3d(0,${paused?0:26*(1-enter)-18*leave}px,0)`;
        el.style.setProperty('--reveal',ease(i+.06,i+.36,x).toFixed(4));
        const part=kineticParts[i],local=clamp(x-i,0,1);
        part.types.forEach((type,j)=>{
          const lift=ease(i-.10+j*.04,i+.16+j*.04,x);
          move(type,`translate3d(${(1-lift)*-12}px,${(1-lift)*108}%,0) rotate(${(1-lift)*2.5}deg)`);
        });
        move(part.report,`translate3d(${110*(1-enter)}px,0,0) rotate(${3*(1-enter)}deg) scale(${.94+.06*enter})`);
        part.shapes.forEach((shape,j)=>{
          const growth=ease(i-.04+j*.035,i+.24+j*.035,x),side=j%2?1:-1;
          move(shape,`translate3d(0,${(1-growth)*145-side*local*32}px,0) rotate(${side*((1-growth)*22+local*11)}deg) scale(${.7+.3*growth})`);
        });
        part.sheets.forEach((sheet,j)=>{const side=j?1:-1;move(sheet,`translate3d(${side*((1-enter)*115+local*8)}px,${(1-enter)*30}px,0) rotate(${side*(2+(1-enter)*7)}deg)`);});
        part.backdrop.forEach((shape,j)=>move(shape,`translate3d(${(j?1:-1)*(1-enter)*80}px,${local*(j?-25:25)}px,0) scale(${.7+.3*enter})`));
        move(part.symbol,`rotate(${(1-enter)*-90+local*35}deg) scale(${.55+.45*enter})`);
        part.numbers.forEach((number,j)=>{const lift=ease(i-.04+j*.055,i+.25+j*.055,x);move(number,`translate3d(0,${(1-lift)*115}%,0)`);});
        move(part.arrow,`rotate(${(1-enter)*-40}deg) scale(${.5+.5*enter})`);
      });
      const heroMove=ease(0,.85,x);
      move(art,`translate3d(0,${-28*heroMove}px,0) rotate(${-2+heroMove*7}deg)`);
      move(artModel,`translate3d(${heroMove*16}px,${-heroMove*15}px,0) rotate(${-8+heroMove*15}deg)`);
      move(artCircle,`translate3d(${heroMove*60}px,${-heroMove*35}px,0) scale(${.9+heroMove*.28})`);
      artTags.forEach((tag,j)=>move(tag,`translate3d(${(j%2?1:-1)*heroMove*26}px,${heroMove*(j-1)*28}px,0) rotate(${[-5,4,-3][j]+heroMove*(j%2?7:-6)}deg)`));
    }else{
      const overview=1-ease(.42,.88,x),focus=ease(.42,.98,x);
      show(intro,overview,false);intro.style.transform=`translate3d(0,${-18*(1-overview)}px,0)`;show(context,focus,false);
      originalWindows.forEach((el,i)=>{
        const visible=Number(el.dataset.window)===6?0:overview;show(el,visible,false);
        el.style.transform=`translate3d(${paused?0:(i%2?14:-14)*focus}px,${-12*focus}px,0) rotate(${paused?0:angles[i]}deg)`;
      });
      focusCards.forEach((el,j)=>{
        const i=j+1,enter=ease(i-.10,i+.16,x),leave=i===3?0:ease(i+.74,i+.99,x),f=flight[j];
        show(el,weights[i],false);
        el.style.transform=`translate3d(${paused?0:f.x*(1-enter)}px,${paused?0:f.y*(1-enter)-leave*18}px,0) scale(${paused?1:(f.scale+(1-f.scale)*enter)*(1-.015*leave)})`;
      });
      store.style.transform=`translate3d(${-width*.26*focus}px,${height*.30*focus}px,0) scale(${1-.52*focus})`;
      store.style.opacity=String(1-.82*focus);if(orbit)orbit.style.opacity=String(1-focus);
      narratives.forEach((el,i)=>{
        if(!i)return;show(el,weights[i]);
        const enter=ease(i-.10,i+.16,x),leave=i===3?0:ease(i+.74,i+.99,x);
        el.style.transform=`translate3d(0,${paused?0:(1-enter)*22-leave*14}px,0)`;
      });
      window.dispatchEvent(new CustomEvent('seelo-scene',{detail:{progress:p,phase,paused,reduced:false,time}}));
    }
    pin.dataset.progress=p.toFixed(3);
  }
  const driver=create({track,prepare:({reduced})=>document.body.classList.toggle('motion-static',reduced),measure,render,smoothing:46,snapStops:[0,1.38/3.45,2.38/3.45,3.38/3.45]});
  chapters.forEach((el,i)=>el.addEventListener('click',()=>driver.go(i)));
  toggle?.addEventListener('click',()=>{paused=!paused;document.body.classList.toggle('motion-off',paused);toggle.setAttribute('aria-pressed',String(paused));toggle.textContent=paused?'모션 재생 ▶':'모션 정지 Ⅱ';driver.refresh();});
  mobile.addEventListener('change',()=>driver.refresh());
})();
