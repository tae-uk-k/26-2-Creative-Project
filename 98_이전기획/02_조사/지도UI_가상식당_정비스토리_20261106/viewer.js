const stories={
  kakao:{before:'소개는 “정성을 담은 한 끼” 한 줄. 메뉴는 “수제비·제육·온담세트”와 가격만 있어 음식 종류, 인분, 세트 구성을 알기 어렵습니다.',source:'메뉴판 1장에서 정확한 이름·인분·중량·포함 구성을, 다음 장에서 직접 반죽·들깨 육수·국내산 돼지고기·맵기·평일 주문 시간을 찾아냈습니다.',after:'브랜드 첫 문장은 살리고 음식 특징으로 소개를 완성했습니다. 메뉴 3개에 판매 단위·구성·선택·시간을 각각 연결했고 가격은 유지했습니다.'},
  google:{before:'소개는 “편하게 즐기는 한 끼, 정성껏 준비”뿐. “소바·우동·소담세트”에 설명이 없어 세트 구성과 추가금을 알 수 없습니다.',source:'메뉴판에서 메밀면 중량·육수·유부 수량을, 이용 안내에서 주문 후 튀기는 돈가스와 점심세트 시간·우동 변경 추가금을 찾았습니다.',after:'소개에는 실제 음식과 조리 특징을 담았습니다. 곱빼기 1,500원은 우동에, 변경 500원과 평일 시간은 점심세트에만 붙였습니다.'}
};
let active='kakao',view='menu';
function fit(){document.querySelectorAll('.viewport').forEach(v=>{const s=v.querySelector('.stage'),f=v.querySelector('iframe');const scale=Math.min(1,v.clientWidth/600);s.style.transform=`scale(${scale})`;s.style.marginLeft=Math.max(0,(v.clientWidth-600*scale)/2)+'px';s.style.height='720px';v.style.height=720*scale+'px';f.style.width=(active==='kakao'?1280:600)+'px';f.style.height='720px';f.style.left=(active==='kakao'?-340:0)+'px'})}
function render(){
 const c=caseData[active],st=stories[active];
 document.querySelectorAll('[data-case]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.case===active)));
 document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)));
 for(const state of ['before','after']){const url=`${active}_${view}_${state}.html`;document.getElementById(state).src=url;document.getElementById(state+'-link').href=url}
 document.getElementById('issue').textContent=view==='menu'?'이름과 가격은 있지만, 음식·인분·구성과 주문 조건을 알기 어려운 상태':'감성적인 소개만 있고, 어떤 음식과 조리 특징이 있는지 드러나지 않는 상태';
 document.getElementById('story-title').textContent=c.name+' · 정비 스토리';
 for(const [id,key] of [['before-story','before'],['source-story','source'],['after-story','after']])document.getElementById(id).textContent=st[key];
 document.getElementById('intro-result').textContent=c.intro_after;
 const sources=document.getElementById('sources');sources.replaceChildren();
 c.sources.forEach(x=>{const article=document.createElement('article'),b=document.createElement('b'),p=document.createElement('p');b.textContent=x.id+' · '+x.type;p.textContent=x.quote;article.append(b,p);sources.append(article)});
 const boards=document.getElementById('boards');boards.replaceChildren();
 [1,2].forEach(i=>{let a=document.createElement('a'),img=document.createElement('img'),span=document.createElement('span');a.href=`sources/${active}_board_${i}.svg`;a.target='_blank';img.src=a.href;img.alt='정비 근거로 설정한 가상 메뉴판 '+i;span.textContent='가상 메뉴판 '+i+' 확대 ↗';a.append(img,span);boards.append(a)});
 document.getElementById('pending').textContent='자료에서 알 수 없어 추가하지 않은 정보: '+c.unresolved.join(' · ');
 document.getElementById('png').href=`images/${active}_story_before_after.png`;
 fit();
}
document.querySelectorAll('[data-case]').forEach(b=>b.addEventListener('click',()=>{active=b.dataset.case;render()}));
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{view=b.dataset.view;render()}));
window.addEventListener('resize',fit);render();
