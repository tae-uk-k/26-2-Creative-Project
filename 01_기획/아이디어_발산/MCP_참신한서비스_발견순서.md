# 최근 참신한 MCP 서비스 조사 — 발견 순서 기록

조사일: 2026-09-20  
범위: GitHub, 공식 MCP Registry, Glama, PulseMCP, Smithery, mcp.so, MCP 판매·호스팅 마켓, Reddit/Hacker News 커뮤니티  
제외: GitHub·Slack·Notion 같은 대기업 서비스 연결기, 데이터베이스 연결기, 코딩·테스트·DevOps 보조 도구

## 읽는 법

- 순서는 이번 조사에서 새로 확인한 순서다. 기존 아이디어 문서에 이미 기록된 MCP는 넣지 않았다.
- `구현체`는 직접 설치하거나 연결하는 MCP, `서비스`는 웹 제품과 MCP가 함께 있는 경우, `시장`은 검색·판매·호스팅 플랫폼이다.
- GitHub나 디렉터리에 있다는 사실만으로 안전성과 완성도가 보장되지는 않는다. 실제 사용 전 권한·네트워크 요청·최근 커밋을 별도로 확인해야 한다.

## 단계별 조사 계획과 진행 상태

1. 문제·퀴즈·학습 MCP 탐색 — 완료
2. 계획·판단·사고 보조 MCP 탐색 — 완료
3. 생활·건강·취미·문화 MCP 탐색 — 완료
4. 국내 공공데이터·지역 특화 MCP 탐색 — 완료
5. MCP 디렉터리·판매·호스팅 시장 탐색 — 완료
6. 기존 목록 및 코딩 도구와 중복 제거 — 완료
7. 실제 동작·보안·최근 유지보수 심층 검증 — 후보 선정 후 진행

## 발견 순서

### #001 Tutor MCP — 구현체

어떤 주제든 개념 선후관계와 학습 경로를 만들고, 오답과 복습 시점을 기억해 다음 문제를 조절하는 적응형 개인교사 MCP다.  
출처: [GitHub](https://github.com/ArnaudGuiovanna/tutor-mcp)

### #002 QuizHP MCP — 구현체·MCP App

AI가 만든 객관식·참거짓 문제를 활쏘기, 폭탄 해체, 피아노 같은 100여 종의 미니게임 화면으로 바꿔 채팅 안에서 풀게 한다.  
출처: [GitHub](https://github.com/bassimeledath/quizhp-mcp)

### #003 Agentic Planning — 구현체

목표·결정·약속·진행상태뿐 아니라 포기한 선택지와 후회까지 파일에 남겨 AI가 장기 계획을 이어가게 한다.  
출처: [GitHub](https://github.com/agentralabs/agentic-planning)

### #004 Achriom MCP — 서비스

책·영화·음악·애니·팟캐스트·게임을 한 개인 취향 라이브러리로 모으고 평점·진행률·메모와 장르 패턴을 AI가 읽고 갱신한다.  
출처: [GitHub](https://github.com/achriom/achriom-mcp)

### #005 wger MCP — 구현체

운동 루틴, 세트 기록, 체중, 영양 목표와 식사를 AI가 함께 관리하게 하는 오픈소스 피트니스·영양 MCP다.  
출처: [GitHub](https://github.com/wger-project/mcp-server)

### #006 OpticQuiz MCP — 구현체

이미지와 색상표가 색각이상 사용자에게 구별되는지 검사하고, 안전한 팔레트와 이시하라식 테스트 이미지를 만든다.  
출처: [GitHub](https://github.com/vince-gonzalez/opticquiz-mcp)

### #007 Multi AI Advisor MCP — 구현체

하나의 결정에 여러 AI가 독립적으로 의견을 낸 뒤 합의점과 이견을 모아 보여 주는 작은 의사결정 위원회다.  
출처: [GitHub](https://github.com/YuChenSSR/multi-ai-advisor-mcp)

### #008 Think MCP — 구현체

AI가 바로 답하지 않고 단계별로 가설과 판단을 기록하도록 별도의 사고 공간을 제공한다.  
출처: [GitHub](https://github.com/Rai220/think-mcp)

### #009 Lucidity MCP — 구현체

답변 과정의 모호한 가정과 논리적 빈틈을 다시 살펴보게 만드는 명료성·추론 보조 MCP다.  
출처: [GitHub](https://github.com/hyperb1iss/lucidity-mcp)

### #010 Actor-Critic Thinking MCP — 구현체

한 AI가 해결책을 제안하고 다른 관점이 비판하게 해 결정을 한 번 더 검토하는 이중 관점 사고 도구다.  
출처: [GitHub](https://github.com/aquarius-wing/actor-critic-thinking-mcp)

### #011 UpTier — 구현체

할 일의 우선순위, 목표, 여러 생활 프로필을 데스크톱 화면과 MCP 양쪽에서 관리하는 개인 실행 시스템이다.  
출처: [GitHub](https://github.com/foxintheloop/UpTier)

### #012 Context Apps MCP — 구현체

할 일·아이디어·일기·타이머를 작은 로컬 앱으로 묶어 AI가 사용자의 하루 맥락을 이어받게 한다.  
출처: [GitHub](https://github.com/tubasasakunn/context-apps-mcp)

### #013 Keepsake MCP — 구현체

사람별 만남·대화·후속 할 일·메모를 기억하는 개인용 관계관리 MCP다.  
출처: [GitHub](https://github.com/nicolascroce/keepsake-mcp)

### #014 Scryfall MCP — 구현체

AI가 매직 더 개더링 카드 데이터베이스를 검색하고 덱 구성에 필요한 카드와 규칙 정보를 찾게 한다.  
출처: [GitHub](https://github.com/cryppadotta/scryfall-mcp)

### #015 Pokémon MCP — 구현체

포켓몬 종·기술·타입 정보를 AI 대화에 연결한 작은 팬 데이터 MCP 실험이다.  
출처: [GitHub](https://github.com/metajar/pokemon-mcp)

### #016 Lichess MCP — 구현체

자연어로 체스 게임과 계정 정보를 조회하고 Lichess 기능을 이용하게 한다.  
출처: [GitHub](https://github.com/karayaman/lichess-mcp)

### #017 Dice Server — 구현체

AI가 TRPG나 보드게임 중 임의의 주사위를 굴리고 결과를 게임 상태에 반영하는 극소형 MCP다.  
출처: [GitHub](https://github.com/TKpon/dice-server)

### #018 Quizlar — 서비스

유튜브·PDF·URL을 플래시카드로 만들고 음성이나 문자로 퀴즈를 진행하며 복습 간격까지 관리한다.  
출처: [GitHub 조직](https://github.com/quizlar) · [공식](https://www.quizlar.app/)

### #019 Socratic Tutor — 구현체

정답을 바로 주지 않고 학생이 같은 과제에서 도움을 요청한 횟수에 따라 힌트를 조금씩 구체화하는 수업용 MCP다.  
출처: [GitHub](https://github.com/benrosche/socratic-tutor)

### #020 Spacedrep — 구현체

AI가 플래시카드를 만들고 대화로 시험하며 FSRS 알고리즘으로 다음 복습일을 결정하는 로컬 학습 MCP다.  
출처: [GitHub](https://github.com/wpwilson10/spacedrep)

### #021 Open Cognition — 구현체·서비스

지식 그래프와 회상 기록을 바탕으로 AI가 강의 대신 소크라테스식 질문과 파인만 설명을 유도한다.  
출처: [GitHub](https://github.com/lfnovo/open-cognition)

### #022 MCP TRPG Game — 구현체

AI가 게임마스터가 되어 캐릭터·장면·NPC·주사위·정신력 판정을 관리하고 플레이 기록을 보존한다.  
출처: [GitHub](https://github.com/tse-wei-chen/MCP-TRPG-Game)

### #023 AstroWay MCP — 서비스

점성술 차트, 궁합, 타로, 수비학, 휴먼디자인 계산을 AI가 구조화된 도구로 호출하게 한다.  
출처: [GitHub](https://github.com/astroway/astroway-mcp)

### #024 RoxyAPI MCP — 서비스

점성술·타로·수비학·크리스털·꿈 상징 같은 영성 콘텐츠용 데이터를 여러 원격 MCP로 판매한다.  
출처: [GitHub 조직](https://github.com/roxyapi) · [공식](https://roxyapi.com/)

### #025 HowToCook MCP — 구현체·서비스

인원과 식단 제한을 받아 중국 요리 중심의 주간 식단, 조리법, 오늘 먹을 메뉴를 추천한다.  
출처: [GitHub](https://github.com/worryzyy/HowToCook-mcp)

### #026 Brewers Almanack — 구현체

맥주 스타일·홉·맥아·효모·수질 데이터를 바탕으로 홈브루잉 레시피를 만들고 이상한 맛의 원인을 진단한다.  
출처: [GitHub](https://github.com/gregario/brewers-almanack)

### #027 MealDB Recipe MCP — 구현체

레시피 검색에서 끝나지 않고 선택한 요리들을 PDF와 통합 장보기 목록으로 만든다.  
출처: [GitHub](https://github.com/BrachaLeah1/MCP_server_mealDB)

### #028 Personal Finance MCP — 구현체·서비스

대출·연금·투자·현금흐름 등 다수의 결정론적 계산기를 AI가 호출하고 결과를 하나의 재무 계획으로 묶는다.  
출처: [GitHub](https://github.com/sarveshtalele/personal-finance-mcp)

### #029 Tandoor Recipes MCP — 구현체

보유 식재료, 레시피, 주간 식단, 장보기 목록과 실제 조리 기록을 하나의 대화로 관리한다.  
출처: [GitHub](https://github.com/Cliftonz/tandoor-recipe-mcp)

### #030 Wikibooks Cookbook MCP — 구현체

공개 위키 조리법을 검색하고 인원수에 맞춰 재료 양을 다시 계산해 준다.  
출처: [GitHub](https://github.com/smeet666/mcp-wikibooks-cookbook)

### #031 Touch Grass — 구현체

현재 날씨·일몰·작업시간을 보고 밖에 나갈 타이밍과 짧은 야외 활동을 제안하고 실천 기록을 남긴다.  
출처: [GitHub](https://github.com/nalediym/touch-grass)

### #032 BirdNET-Go MCP — 구현체

야외 마이크가 감지한 새소리 기록과 녹음을 AI가 검색해 최근 출현 종과 시간대를 설명한다.  
출처: [GitHub](https://github.com/zax0rz/birdnet-go-mcp)

### #033 Atmospore MCP — 서비스

세계 어느 위치든 식물 종별 꽃가루 예보를 제공해 알레르기 일정이나 야외 계획에 활용하게 한다.  
출처: [GitHub](https://github.com/atmospore/atmospore-mcp)

### #034 GridCarbon MCP — 구현체

지역별 전력 탄소집약도와 최신성까지 알려 줘 전기 사용이나 작업 실행 시간을 탄소가 낮을 때로 옮기게 한다.  
출처: [GitHub](https://github.com/gridcarbon/clients)

### #035 Travel Art MCP — 서비스

비엔날레·아트페어·주요 미술관 가이드를 엮어 미술 중심 여행 일정을 추천한다.  
출처: [GitHub](https://github.com/alexzavialov/travel-art-mcp) · [공식](https://travel.art/)

### #036 Shahnameh MCP — 구현체

페르시아 서사시 샤나메의 구절·단락·해설을 AI가 찾아 문화·문학 대화에 활용하게 한다.  
출처: [GitHub](https://github.com/aliafsahnoudeh/shahnameh-mcp-server)

### #037 MyInstants MCP — 구현체

AI가 수백만 개의 밈 효과음을 검색하고 상황에 맞춰 바로 재생하는 사운드보드 MCP다.  
출처: [GitHub](https://github.com/austenstone/myinstants-mcp)

### #038 AO3 MCP — 구현체

팬픽을 검색하고 별도의 모델이 작품 전문을 읽게 해 소개문이 아니라 실제 내용에 근거한 추천을 만든다.  
출처: [GitHub](https://github.com/ArturLys/ao3-mcp)

### #039 Open Library MCP — 구현체

AI가 오픈 라이브러리에서 책·저자·판본·ISBN 정보를 대화형으로 검색하게 한다.  
출처: [GitHub](https://github.com/8enSmith/mcp-open-library)

### #040 SansFiction MCP — 서비스

책 검색과 함께 개인 독서 상태·진행률·평점·리뷰·컬렉션·독서 통계를 관리한다.  
출처: [GitHub](https://github.com/fgbytes/sansfiction-mcp) · [공식](https://sansfiction.com/)

### #041 VisitKorea MCP — 구현체

한국관광공사 데이터를 이용해 위치·날짜·키워드별 관광지, 축제, 숙박, 음식점과 사진을 찾는다.  
출처: [GitHub](https://github.com/leejaew/visitkorea-mcp)

### #042 Korea Public Data Catalog MCP — 서비스·구현체

만들고 싶은 서비스를 말하면 약 9만 건의 국내 공공데이터 목록에서 조합할 데이터 후보와 공식 링크를 제안한다.  
출처: [GitHub](https://github.com/obundh/korea-public-data-catalog-mcp)

### #043 Korea Stats MCP — 구현체

인구·고용·주거·범죄·관광·교통·환경 같은 KOSIS 지표를 자연어로 찾아 공식 정의와 값을 돌려준다.  
출처: [GitHub](https://github.com/Dayoooun/korea-stats-mcp)

### #044 Seoul OpenData MCP — 구현체

서울의 실시간 인구밀집, 교통, 따릉이, 주차, 대기질, 문화행사 데이터를 한 MCP에서 질의한다.  
출처: [GitHub](https://github.com/whchoi98/seoul-opendata-mcp)

### #045 K-Sign MCP — 구현체

국립국어원 한국수어 사전의 단어, 설명, 이미지와 동영상 자료를 AI가 검색하게 한다.  
출처: [GitHub](https://github.com/a4file/k-sign-mcp-server)

### #046 Public Data Lens — 서비스·구현체

국내 공공데이터를 찾는 데서 끝나지 않고 출처와 규칙을 근거로 품질·활용 가능성을 비교한다.  
출처: [GitHub](https://github.com/hike-lab/public-data-lens)

### #047 KORAIL MCP — 구현체

한국철도공사 공개데이터를 AI가 조회할 수 있도록 여러 기능별 MCP로 나눈 프로젝트다.  
출처: [GitHub](https://github.com/lovelyquality/korail-mcp)

### #048 MCP Korea Tourism API — 구현체

한국의 축제·사찰·맛집·숙박·쇼핑 정보를 다국어로 검색하고 위치 주변 장소와 상세 이용정보를 가져온다.  
출처: [GitHub](https://github.com/harimkang/mcp-korea-tourism-api)

### #049 Architect Certification Prep MCP — 구현체·MCP App

시나리오 문제, 모의시험, 클릭형 답안 화면, 복습 알고리즘을 하나로 묶은 자격시험 준비 MCP다.  
출처: [GitHub](https://github.com/Connectry-io/connectrylab-architect-cert-mcp)

### #050 ICTExam MCP — 서비스·구현체

교사가 시험지를 만들고 학생이 풀면 자동 채점과 문항별 난이도·정답률 분석을 제공한다.  
출처: [GitHub](https://github.com/ictinnovations/ictexam-mcp)

### #051 Pronunciation Coach MCP — 구현체

영어 음성을 분석해 발음·문법·유창성·음소 단위 문제를 찾고 개인별 연습 문제를 낸다.  
출처: [GitHub](https://github.com/JuhongPark/mcp-server-pronunciation)

### #052 Learn Shell — 구현체·서비스

강의·문제·플래시카드·실시간 수업·채점 기록을 기억하며 AI가 스스로 수업을 개선하는 작은 학습 운영체제다.  
출처: [GitHub](https://github.com/sf-shenfeng/learn-shell)

### #053 Signs of AI — 구현체

AI 작성 가능성 점수만 주지 않고 반복 어휘·문장 리듬·출처 문제 등 판단 근거와 수정 위치를 보여 준다.  
출처: [GitHub](https://github.com/peopleworks/SignsofAI)

### #054 SRDCheck — 구현체

D&D 한 턴의 행동이 규칙상 가능한지 원문 근거와 함께 판정하고 규칙이 정하지 않은 것은 판정을 거부한다.  
출처: [GitHub](https://github.com/chaoz23/srdcheck)

### #055 Lorcana MCP — 구현체

디즈니 로카나 카드 검색, 덱 규칙 검증, 비용곡선·색상·키워드 통계를 제공한다.  
출처: [GitHub](https://github.com/danielenricocahall/lorcana-mcp)

### #056 BizHawk MCP — 구현체

AI가 고전 게임 에뮬레이터의 화면·메모리·버튼·저장상태를 도구로 받아 여러 콘솔 게임을 플레이하게 한다.  
출처: [GitHub](https://github.com/dmang-dev/mcp-bizhawk)

### #057 mGBA MCP — 구현체

AI가 게임보이 어드밴스 화면을 보고 버튼을 누르며 세이브 상태와 프레임을 제어하게 한다.  
출처: [GitHub](https://github.com/dmang-dev/mcp-mgba)

### #058 FreeBazi MCP — 구현체

인터넷 없이 생년월일과 위치로 진태양시를 반영한 사주팔자와 대운·십신·지지 관계를 계산한다.  
출처: [GitHub](https://github.com/alexsu1212/freebazi-mcp)

### #059 VedaKsha — 구현체

베다 점성술 차트·다샤·무후르타·궁합을 로컬에서 결정론적으로 계산하는 MCP다.  
출처: [GitHub](https://github.com/arthiqlabs/vedaksha)

### #060 Astral MCP — 구현체

별도 계정 없이 출생차트·현재 행성 이동·궁합·달의 위상을 계산하고 개인정보를 작게 보내는 모드를 제공한다.  
출처: [GitHub](https://github.com/davidmosiah/astral-mcp)

### #061 Telugu Calendar Utilities — 구현체

텔루구 전통 달력의 티티·낙샤트라·길일·축제·별자리 운세를 계산한다.  
출처: [GitHub](https://github.com/socraticsurge/telugu-calendar-utilities)

### #062 AIm — 서비스

세트·중량·추정 1RM·근육별 운동량과 회복 상태를 대화 밖에 저장해 다음 운동을 실제 기록으로 계획한다.  
출처: [GitHub](https://github.com/persistmcp/aim)

### #063 ChessCEO MCP — 서비스·구현체

대규모 기보와 선수 기록에서 오프닝 성향, 특정 포지션 통계, 상대전적과 진행 중 대회를 찾는다.  
출처: [GitHub](https://github.com/chessceo/chessceo-mcp) · [공식](https://chess.ceo/)

### #064 Pick a Dive MCP — 서비스

특정 날짜와 장소의 다이빙 조건, 계절별 적기, 관찰 가능한 해양생물, 주변 다이빙 포인트를 함께 추천한다.  
출처: [GitHub](https://github.com/afiliptsov/pickadive-mcp) · [공식](https://pickadive.com/)

### #065 Nightlife MCP — 서비스

도쿄의 밤 행사·공연자·장소를 검색하고 취향 기반 추천과 VIP 테이블 예약까지 이어 준다.  
출처: [GitHub](https://github.com/alcylu/nightlife-mcp)

### #066 Luxembourg MCP — 서비스·구현체

법률·통계·주차·교통·날씨 경보·환경·의회·대중교통을 한 나라 단위의 공개 MCP로 묶었다.  
출처: [GitHub](https://github.com/amirdaraee/luxembourg-mcp)

### #067 Campertunity MCP — 서비스

세계 캠핑장을 검색하고 일정별 이용 가능 여부와 예약 링크를 돌려준다.  
출처: [GitHub](https://github.com/campertunity/mcp-server)

### #068 Korea Nationwide Data MCP — 서비스

국내 관광지, 138개 도시 버스정류장, 30년 평년기후를 계정 없이 하나의 원격 MCP에서 조회한다.  
출처: [원격 MCP 목록](https://github.com/punkpeye/awesome-remote-mcp-servers)

### #069 VoyageHacks MCP — 서비스

검증된 여행 가이드를 검색하고 짐 꾸리기 목록과 항공·숙소·통신·렌터카 선택지를 만든다.  
출처: [공식](https://voyagehacks.com/mcp)

### #070 ToolsMonk MCP — 서비스

PDF·이미지·텍스트·SEO 작업을 설명하면 200여 개의 작은 브라우저 도구 중 맞는 것을 찾아준다.  
출처: [공식](https://toolsmonk.com/api/mcp)

### #071 Turnale MCP — 서비스

동호인 라켓 스포츠 대회의 대진표·일정·순위와 갑작스러운 불참 처리를 채팅으로 운영한다.  
출처: [원격 MCP 목록](https://github.com/punkpeye/awesome-remote-mcp-servers)

### #072 Tribeunal MCP — 서비스

사람과 AI가 사건을 올리고 증거를 검토해 함께 투표하는 커뮤니티 배심·중재 플랫폼이다.  
출처: [GitHub](https://github.com/tribeunal/mcp-server)

### #073 Cairn MCP — 서비스

다른 AI가 실제 작업에서 배운 한 문장짜리 ‘해야 할 것·하지 말아야 할 것’을 상황별로 공유한다.  
출처: [GitHub](https://github.com/bborota/cairn-mcp)

### #074 Library MCP — 서비스

공개저작권 책의 본문·장·인용구를 검색하고 특정 책에 질문하는 호출당 과금형 지식 MCP다.  
출처: [GitHub](https://github.com/forgemeshlabs/library-mcp)

### #075 CrossPaste MCP — 구현체

여러 기기의 클립보드 기록과 복사한 이미지의 OCR 텍스트를 AI가 검색하고 다시 꺼내 쓰게 한다.  
출처: [GitHub](https://github.com/CrossPaste/crosspaste-desktop)

### #076 Decision Anchor — 서비스

AI와 사람 사이에서 누가 어떤 결정을 책임지는지 내용 자체를 보지 않고 외부 기록으로 고정한다.  
출처: [GitHub 목록](https://github.com/punkpeye/awesome-mcp-servers)

### #077 Ergonia — 서비스

AI 에이전트가 다른 사람이 독립적으로 검증할 수 있는 과제를 등록·수행하고 공개 평판을 쌓는 작업 시장이다.  
출처: [GitHub 목록](https://github.com/punkpeye/awesome-mcp-servers)

### #078 Agent Bounties — 서비스

사람이 원하는 결과를 과제로 내고 AI가 작업물을 제출하며 검증 결과에 따라 보상을 받는 MCP형 바운티 시장이다.  
출처: [Glama 검색](https://glama.ai/mcp/servers)

### #079 Ani MCP — 구현체

애니 시청기록과 취향을 분석해 작품을 추천하고 목록·통계·소셜 기능까지 관리한다.  
출처: [GitHub](https://github.com/gavxm/ani-mcp)

### #080 Wellness Nourish — 구현체

계정 없이 음식 검색, 바코드 조회, 식사 영양 추정, 수분·섭취 기록과 하루 요약을 제공한다.  
출처: [GitHub](https://github.com/davidmosiah/wellness-nourish)

### #081 Nutrients MCP — 구현체

음식 사진이나 한 줄 설명에서 열량·영양소·알레르기·식단 주의사항을 구조화해 돌려준다.  
출처: [GitHub 목록](https://github.com/punkpeye/awesome-mcp-servers)

### #082 GeraCast MCP — 서비스

팟캐스트와 에피소드를 검색하고 녹취를 가져오며 구독 목록을 관리하는 소형 원격 MCP다.  
출처: [Cline 마켓 제출 기록](https://github.com/cline/mcp-marketplace/issues/1423)

### #083 Map Traveler MCP — 구현체

AI 아바타가 지도 위를 가상 여행하고 방문한 장소를 관찰·기록해 여행 보고서를 만든다.  
출처: [GitHub](https://github.com/mfukushim/map-traveler-mcp)

### #084 Money MCP — 서비스

은행 거래를 읽어 순자산·지출 패턴을 분석하고 예산·목표·알림을 대화로 수정한다.  
출처: [GitHub](https://github.com/Parsons-ai/money-mcp-server)

### #085 Actual Budget MCP — 구현체

자가호스팅 가계부의 지출 추세와 예산 대비 실적을 분석하며 삭제 전에 영향 범위를 미리 보여 준다.  
출처: [GitHub](https://github.com/henfrydls/actual-budget-mcp)

### #086 Pronounce MCP — 구현체

nginx·GIF·LaTeX처럼 사람마다 다르게 읽는 기술·제품 이름의 IPA, 발음 표기, 근거와 신뢰도를 제공한다.  
출처: [GitHub](https://github.com/anzy-renlab-ai/pronounce)

### #087 Free-Will MCP — 구현체·실험

AI가 외부 요청만 기다리지 않고 스스로 다음 질문과 탐색 방향을 제안하게 하는 자기 프롬프팅 실험이다.  
출처: [GitHub](https://github.com/gwbischof/free-will-mcp)

### #088 Inner Monologue MCP — 구현체·실험

AI의 즉답과 별도로 내부 검토 메모를 만들고 답변 전에 스스로 반박하게 하는 사고 실험이다.  
출처: [GitHub](https://github.com/abhinav-mangla/inner-monologue-mcp)

## MCP 스토어·판매·배포 플랫폼 — 발견 순서

### S01 AgentStack

제작자가 MCP나 에이전트 스킬에 가격을 붙이고 호스팅·설치·보안검사를 함께 제공한다고 홍보하는 유료 마켓이다. 수익·등록 수치는 플랫폼의 자체 주장이라 별도 검증이 필요하다.  
출처: [판매자 페이지](https://agentstack.voostack.com/sell)

### S02 MCP Marketplace

로컬 패키지의 라이선스 키 판매와 원격 MCP 월 구독을 지원하고 결제·라이선스·분석을 대신 처리한다.  
출처: [제작자 페이지](https://mcp-marketplace.io/for-creators) · [수익화 안내](https://mcp-marketplace.io/blog/how-to-monetize-mcp-server)

### S03 cursor.store

무료·프리미엄 MCP를 등록하고 설치 설정을 제공하는 큐레이션형 마켓이다. 이름과 달리 특정 대기업 공식 스토어는 아니다.  
출처: [공식](https://www.cursor.store/)

### S04 FiatDock

제작자가 MCP 도구별 호출 가격을 정하면 AI가 x402 방식으로 호출할 때 USDC로 자동 정산하는 마켓이다.  
출처: [판매자 페이지](https://www.fiatdock.com/sell-mcp-service.html)

### S05 dotMCP

OpenAPI·Postman·GraphQL 또는 로컬 서버를 MCP로 가져와 배포하고 구독 수익을 나누는 플랫폼이다.  
출처: [공식 문서](https://docs.dotmcp.io/)

### S06 XPack MCP Market

기존 OpenAPI를 유료 MCP로 바꾸거나 자기만의 MCP 상점을 직접 운영하게 하는 오픈소스 마켓 구축 도구다.  
출처: [오픈소스 소개](https://xpack.ai/opensource)

### S07 MCPRush

MCP는 월 구독으로, 에이전트 스킬은 일회성 상품으로 판매하도록 설계된 호스팅·마켓 플랫폼이다.  
출처: [공식](https://mcprush.com/)

### S08 MCPChannel

MCP를 검색·등록하고 웹에서 간단히 제작해 공개하는 소규모 채널형 마켓이다.  
출처: [공식](https://www.mcpchannel.ai/)

### S09 Official MCP Registry

MCP 서버의 이름·버전·패키지·원격 주소를 배포하는 공식 메타데이터 원장이다. 상점보다는 다른 디렉터리들이 가져가는 기준 데이터에 가깝다.  
출처: [공식 Registry 문서](https://registry.modelcontextprotocol.io/docs)

### S10 Glama

GitHub와 공식 Registry의 MCP를 대규모로 색인하고 도구 스키마 품질, 유지보수, 라이선스 등의 평가 정보를 붙인다.  
출처: [MCP 디렉터리](https://glama.ai/mcp/servers)

### S11 PulseMCP

출시일·최근 업데이트·인기도·원격 연결 여부를 기준으로 탐색하기 좋은 큐레이션형 디렉터리와 뉴스레터다.  
출처: [서버 디렉터리](https://www.pulsemcp.com/servers)

### S12 Smithery

MCP 검색과 설치 명령, 원격 호스팅을 함께 제공해 ‘찾은 뒤 직접 서버를 띄우는’ 단계를 줄인다.  
출처: [공식](https://smithery.ai/)

### S13 mcp.so

커뮤니티가 제출한 MCP를 범주별로 둘러보고 설정 예시를 복사하는 대형 웹 디렉터리다.  
출처: [공식](https://mcp.so/)

### S14 MCP Market

MCP와 에이전트 스킬을 범주·인기 순위로 탐색하고 제작자가 무료로 등록하는 디렉터리다.  
출처: [공식](https://mcpmarket.com/)

### S15 MCPFind

여러 Registry를 한 번에 검색해 용도에 맞는 MCP와 클라이언트별 설치 설정을 만들어 주는 ‘MCP를 찾는 MCP’다.  
출처: [공식](https://mcpfind.org/)

### S16 Unyly

디렉터리 검색뿐 아니라 여러 AI 클라이언트 설정에 선택한 MCP를 직접 추가하고 하나의 게이트웨이로 묶는 서비스다.  
출처: [공식](https://unyly.org/)

### S17 AgentHotspot

제작자가 MCP 연결기를 등록하고 검색·배포·수익화하게 하는 에이전트 도구 시장이다.  
출처: [GitHub](https://github.com/AgentHotspot/agenthotspot-mcp)

### S18 FindAgent

AI가 필요한 일을 설명하면 검수된 실행 에이전트를 찾아 호출하게 하는 MCP 자체가 에이전트 마켓의 입구 역할을 한다.  
출처: [GitHub](https://github.com/team886/findagent-mcp)

### S19 BotHire

AI 에이전트가 다른 에이전트의 능력·신뢰도를 검색하고 스테이블코인으로 고용하는 기계 간 서비스 시장이다.  
출처: [GitHub](https://github.com/BotHireAgent/BotHireMCPServer)

### S20 AI Skill Store

AI가 스스로 필요한 스킬을 검색·구매·연결하도록 MCP를 상점 인터페이스로 사용한다.  
출처: [GitHub](https://github.com/garasegae/aiskillstore)

### S21 AgentBodega

검색·공공데이터·미디어 변환 같은 소형 도구를 호출당 결제 방식으로 모은 AI용 도구 상점이다.  
출처: [GitHub](https://github.com/agentbodegastore/agentbodega)

### S22 AgentForge

여러 제작자가 만든 AI 에이전트를 하나의 API와 마켓으로 배포하고 호출 수익을 나누는 자가호스팅 가능 플랫폼이다.  
출처: [GitHub](https://github.com/doggychip/agentforge)

### S23 Fatstack

계정 없이 MCP를 연결하고 필요한 API를 호출할 때만 USDC로 결제하는 원격 도구 마켓이다.  
출처: [원격 MCP 목록](https://github.com/punkpeye/awesome-remote-mcp-servers)

### S24 nohumans.directory

AI가 기능·가격·실제 호출 성공 기록을 보고 호출당 과금 API를 고르게 하는 기계 사용자 전용 디렉터리다.  
출처: [공식](https://nohumans.directory/)

## 범주별 빠른 색인

- 문제·학습: #001, #002, #018~#021, #049~#053, #086
- 계획·사고·판단: #003, #007~#013, #072~#078, #087~#088
- 게임·팬덤·놀이: #014~#017, #022~#024, #037~#038, #054~#061, #063, #079
- 요리·운동·건강: #005, #025~#030, #031~#034, #062, #080~#081
- 책·문화·여행: #004, #035~#040, #064~#071, #082~#083
- 국내 특화: #041~#048, #068
- 개인 기록·돈·생활: #011~#013, #028, #062, #075, #084~#085
- 판매·배포 시장: S01~S24

## 이번 조사에서 보인 참신한 사업 패턴

1. **MCP 안에 작은 화면을 넣는다.** QuizHP처럼 단순 도구 호출을 문제풀이 게임이나 대시보드로 바꾸면 일반 사용자도 MCP를 서비스로 느낀다.
2. **대화가 잊는 상태를 외부에 보존한다.** 학습 숙련도, 운동 기록, 독서 진행률, 인간관계 후속조치처럼 누적될수록 가치가 커지는 데이터가 적합하다.
3. **좁은 취미에 결정 데이터를 붙인다.** 다이빙 날짜, 홈브루잉 이상 맛, 꽃가루 종, 카드 덱 규칙처럼 범위가 좁을수록 작은 팀도 신뢰를 만들기 쉽다.
4. **정답보다 다음 행동을 판정한다.** 오늘 무엇을 복습할지, 밖에 나갈지, 어떤 행동이 게임 규칙상 가능한지를 반환하는 MCP가 단순 검색보다 제품성이 높다.
5. **공개데이터의 검색보다 조합을 판다.** 국내 공공데이터 목록을 서비스 아이디어에 맞게 엮어 주는 방식은 API 래퍼보다 차별화된다.
6. **판매 방식이 월 구독에서 호출당 과금으로 넓어졌다.** MCP 자체를 유료 API 포장지로 사용하고 x402·라이선스 키·호스팅 구독으로 과금하는 시장이 형성되고 있다.

## 우선 벤치마킹할 12개

|순위|서비스|볼 이유|
|---:|---|---|
|1|QuizHP|MCP가 채팅 뒤의 도구가 아니라 직접 사용하는 화면이 될 수 있음|
|2|Tutor MCP|학습 상태와 복습 근거를 구조화해 장기 사용 이유가 명확함|
|3|Open Cognition|답을 주지 않고 생각하게 만드는 이전 아이디어와 직접 연결됨|
|4|Touch Grass|날씨·사용시간·행동 기록만 조합한 아주 작은 생활 개입 서비스|
|5|Pick a Dive|여러 환경 데이터를 특정 취미의 ‘좋은 시점’으로 변환함|
|6|Brewers Almanack|좁은 전문가 지식을 진단·레시피·추천으로 나눈 구성이 좋음|
|7|Achriom|여러 콘텐츠 소비 기록을 하나의 개인 취향 메모리로 묶음|
|8|Korea Public Data Catalog|국내 데이터 조합 자체를 아이디어 생성 기능으로 만듦|
|9|Tribeunal|AI와 사람이 함께 증거를 보고 판정하는 새로운 상호작용|
|10|Decision Anchor|AI 결과가 아니라 사람과 AI의 책임 경계를 상품화함|
|11|FiatDock|작은 MCP 하나도 호출당 판매할 수 있는 구조를 보여 줌|
|12|MCP Marketplace|로컬 패키지와 원격 서비스의 서로 다른 과금 방식을 비교 가능|

## 검증상 주의

- 디렉터리의 서버 수·수익·사용량은 서비스가 자체 표시한 값이 많아 이 문서에는 핵심 근거로 사용하지 않았다.
- MCP 디렉터리는 검색용이다. 설치 전에는 원본 저장소, 최근 릴리스, 요청 권한, 환경변수, 외부 전송 대상을 다시 확인해야 한다.
- 얼굴·건강·금융·학습 기록을 다루는 MCP는 기능이 참신해도 개인정보 보관 방식이 불명확하면 아이디어 참고에만 사용한다.
- 영성·운세 MCP는 계산 구조와 제품 포장 사례로만 참고하고, 결과의 사실성을 보증하는 서비스로 보지 않는다.
