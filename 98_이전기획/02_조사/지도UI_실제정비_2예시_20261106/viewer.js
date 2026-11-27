const cases={
  kakao:{width:1280,height:720,focus:600,offset:-340,summary:'메뉴판 사진 속 재료·소스 선택 정보를 해당 메뉴의 텍스트 설명으로 연결',url:'https://place.map.kakao.com/465733251#menuInfo'},
  google:{width:1208,height:765,focus:600,offset:0,summary:'한 문단에 섞인 기본 구성·면 중량·추가금·무료 요청을 세 문단으로 정리',url:'https://www.google.co.kr/maps/place/힛사츠와자/data=!4m5!3m4!1s0x357c990006a61961:0x93b46c4afa816b00!10e9!16s%2Fg%2F11xsrqylhh'}
};
let active=new URLSearchParams(location.search).get('map')==='google'?'google':'kakao',full=false;
function fit(){
  const c=cases[active];
  document.querySelectorAll('.viewport').forEach(view=>{
    const stage=view.querySelector('.stage'),frame=view.querySelector('iframe');
    const width=full?c.width:c.focus,scale=Math.min(view.clientWidth/width,1);
    stage.style.width=width+'px';stage.style.height=c.height+'px';stage.style.transform=`scale(${scale})`;
    view.style.height=c.height*scale+'px';stage.style.marginLeft=Math.max(0,(view.clientWidth-width*scale)/2)+'px';
    frame.style.width=c.width+'px';frame.style.height=c.height+'px';frame.style.left=(full?0:c.offset)+'px';
  });
}
function select(key){
  active=key;document.querySelectorAll('[data-case]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.case===key)));
  document.getElementById('summary').textContent=cases[key].summary;document.getElementById('source').href=cases[key].url;
  for(const state of ['before','after']){document.getElementById(state).src=`${key}_${state}.html`;document.getElementById(state+'-link').href=`${key}_${state}.html`;}
  for(const name of ['kakao','google'])document.getElementById(name+'-proof').hidden=name!==key;
  fit();
}
document.querySelectorAll('[data-case]').forEach(b=>b.addEventListener('click',()=>select(b.dataset.case)));
document.getElementById('layout').addEventListener('click',e=>{full=!full;e.target.textContent=full?'메뉴 영역 크게 보기':'전체 화면 축소 보기';fit()});
window.addEventListener('resize',fit);
select(active);
