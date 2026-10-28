function authArt(p){const stage=figma.createFrame();stage.name='가게를 중심으로 이어지는 정보 창';p.appendChild(stage);stage.resize(500,430);stage.fills=[];stage.clipsContent=false;const backdrop=figma.createEllipse();stage.appendChild(backdrop);backdrop.resize(350,350);backdrop.x=65;backdrop.y=40;backdrop.fills=[paint('subtle')];const model=store(stage,330);model.x=80;model.y=64;const a=windowBox(stage,'AI 추천 진단',210,16);a.root.x=275;a.root.y=12;T(a.body,'ChatGPT · Gemini',14,'muted');T(a.body,'추천 현황 확인',18,'ink','Bold');const b=windowBox(stage,'가게 정보 정비',235,16);b.root.x=5;b.root.y=270;T(b.body,'영문 메뉴 · 영업시간',15,'ink','Medium');const c=windowBox(stage,'전후 비교',180,16);c.root.x=305;c.root.y=310;T(c.body,'2주 뒤 다시 측정',15,'ink','Medium');}
function authIntro(p,label){const left=col(p,500,24);T(left,'우리 가게의 AI 추천 현황을\n확인하고, 정보를 정비하세요.',40,'ink','Bold',500);T(left,'진단부터 Google·카카오 정보 정비,\n2주 뒤 전후 비교까지 seelo와 함께.',17,'muted','Regular',500);authArt(left);return left;}
function social(p,text,g=false){const id=S.components.buttons.secondary;const n=button(p,text,480,'neutral');if(!g)n.fills=[{type:'SOLID',color:{r:1,g:.9,b:0}}];return n;}
{
 const q=await page('auth','S02','회원가입','public');const r=row(q.body,1160,120);authIntro(r);const right=col(r,480,24);title(right,'SEELO ACCOUNT','무료 진단으로 시작해 보세요.','가게를 운영하는 사장님을 위한 seelo 계정',480);social(right,'Google로 시작하기',true);social(right,'카카오로 시작하기');T(right,'또는 이메일로 가입',14,'muted','Regular',480);field(right,'이메일','','',480);field(right,'비밀번호','','8자 이상, 영문과 숫자를 함께 써 주세요.',480);field(right,'비밀번호 확인','','',480);rule(right,480);check(right,'전체 동의',480);check(right,'[필수] 이용약관 동의                         보기',480);check(right,'[필수] 개인정보 수집·이용 동의        보기',480);button(right,'가입하기',480,'disabled');T(right,'이미 계정이 있나요?  로그인',15,'muted','Regular',480);
}
{
 const q=await page('auth','S03','이메일 인증 안내','public');const r=row(q.body,1160,120);authIntro(r);const right=col(r,480,28);icon(right,'mail',48);title(right,'EMAIL VERIFICATION','메일함을 확인해 주세요.','인증 메일의 링크를 누르면 가입이 완료돼요.',480);note(right,'owner@restaurant.com으로 보냈어요.',480);T(right,'인증 링크는 24시간 동안 사용할 수 있어요.\n메일이 보이지 않으면 스팸함도 확인해 주세요.',16,'muted','Regular',480);button(right,'인증 메일 다시 보내기',480,'secondary');T(right,'다시 보내기까지 00:59',14,'faint');T(right,'이메일 주소 바꾸기',15,'blueDark','Medium');rule(right,480);T(right,'인증을 마치면 내 가게 화면으로 이동합니다.',14,'muted','Regular',480);
}
{
 const q=await page('auth','S04','카카오 이메일 입력','public');const r=row(q.body,1160,120);authIntro(r);const right=col(r,480,28);icon(right,'mail',48);title(right,'KAKAO ACCOUNT','이메일을 알려주세요.','카카오에서 이메일을 받지 못했어요.\n인증과 진단 결과 안내에 사용할 주소가 필요해요.',480);field(right,'이메일','','실제로 확인할 수 있는 이메일을 입력해 주세요.',480);button(right,'인증 메일 보내기',480);T(right,'이미 사용 중인 계정이 있나요?  로그인',15,'muted','Regular',480);
}
{
 const q=await page('auth','S05','로그인','public');const r=row(q.body,1160,120);authIntro(r);const right=col(r,480,24);title(right,'WELCOME BACK','다시 만나 반가워요.','우리 가게의 추천 현황을 이어서 확인하세요.',480);social(right,'Google로 로그인',true);social(right,'카카오로 로그인');T(right,'또는 이메일로 로그인',14,'muted');field(right,'이메일','','',480);field(right,'비밀번호','','',480);const links=row(right,480,40);T(links,'14일 동안 로그인 유지',14,'muted');T(links,'비밀번호를 잊으셨나요?',14,'blueDark','Medium');button(right,'로그인',480);T(right,'아직 계정이 없나요?  회원가입',15,'muted','Regular',480);
}
{
 const q=await page('auth','S06','비밀번호 재설정','public');const r=row(q.body,1160,120);authIntro(r);const right=col(r,480,28);icon(right,'mail',48);title(right,'RESET PASSWORD','비밀번호를 재설정해요.','가입할 때 사용한 이메일을 입력해 주세요.',480);field(right,'이메일','','',480);button(right,'재설정 메일 보내기',480);T(right,'로그인으로 돌아가기',15,'blueDark','Medium');note(right,'가입된 이메일이면 재설정 링크를 보내드려요.',480);
}
{
 const q=await page('auth','S06-B','새 비밀번호 입력','public');const r=row(q.body,1160,120);authIntro(r);const right=col(r,480,28);title(right,'NEW PASSWORD','새 비밀번호를 입력하세요.','안전하게 사용할 새 비밀번호를 설정해 주세요.',480);field(right,'새 비밀번호','','8자 이상, 영문과 숫자를 함께 써 주세요.',480);field(right,'새 비밀번호 확인','','',480);button(right,'비밀번호 변경',480);T(right,'링크가 만료됐나요?  다시 요청하기',15,'blueDark','Medium',480);
}
return finalize();
