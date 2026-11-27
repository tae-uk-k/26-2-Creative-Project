async page => {
  const location = new URL(page.url());
  if (!location.pathname.endsWith('/dark.html')) {
    throw new Error('검사 전에 dark.html을 브라우저에서 여세요.');
  }
  location.hash = '';
  const expected = {
    headline: 'AI 검색에서 우리 상품이 답이 되도록',
    question: '울함량 50% 이상의 니트 7만원대로 찾아줘',
    delegation: "지금까지의 전자상거래가 '검색(Search)'과 '발견'의 시대였다면, 앞으로 다가올 미래는 '위임(Delegation)'의 시대입니다, - 에이전틱 커머스(Agentic Commerce) -",
    platforms: '현재는 네이버 스마트스토어와 카페24만 지원합니다. 다른 쇼핑몰도 곧 추가합니다.',
    comparisonTitle: 'SEO랑 다른건가요?',
    comparisonLead: '이제는 검색 엔진 최적화(SEO)를 넘어, 생성형 엔진 최적화(GEO)가 필요합니다.',
    comparisonRows: [
      ['구분', 'SEO', 'GEO'],
      ['목표', '네이버/구글 검색 순위', 'AI 추천 답변'],
      ['경쟁', '10개 링크 중 1등', '단 하나의 정답'],
      ['사용자 행동', '여러 링크 클릭해서 비교', 'AI 답변 그대로 신뢰'],
      ['노출 방식', '링크 목록', '대화형 추천'],
      ['핵심 기술', '키워드, 백링크', '구조화 데이터, Schema'],
    ],
    comparisonSummary: "GEO는 AI가 선택한 '단 하나의 정답'이 되는 것입니다.",
  };
  const failures = [];
  const widths = [1440, 1024, 768, 390, 320];
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(location.href);
    await page.evaluate(() => document.fonts.ready);
    const issues = await page.evaluate(({ expected, width }) => {
      const issues = [];
      const text = element => element?.innerText.replace(/\s+/g, ' ').trim();
      const expect = (condition, message) => { if (!condition) issues.push(message); };
      const title = document.querySelector('#hero-title');
      expect(text(title) === expected.headline, '첫 문구가 지정 문구와 다릅니다.');
      const titleStyle = getComputedStyle(title);
      const headingText = document.createTreeWalker(title, NodeFilter.SHOW_TEXT);
      for (let node = headingText.nextNode(); node; node = headingText.nextNode()) {
        if (!node.textContent.trim()) continue;
        const style = getComputedStyle(node.parentElement);
        expect(style.fontSize === titleStyle.fontSize &&
          style.fontWeight === titleStyle.fontWeight && Number(style.fontWeight) >= 700,
        '제목 전체가 같은 크기와 굵기로 표시되어야 합니다.');
      }
      expect(getComputedStyle(document.querySelector('.dark-hero')).backgroundColor === 'rgb(8, 8, 8)', '첫 화면 왼쪽 배경은 가까운 검정 계열이어야 합니다.');

      const sections = [...document.querySelectorAll('main > .section')];
      expect(sections.length > 0 && sections.every(section => {
        const { borderTopWidth, borderTopStyle, borderTopColor } = getComputedStyle(section);
        return borderTopWidth === '1px' && borderTopStyle === 'solid' && borderTopColor === 'rgb(229, 232, 235)';
      }), '하단 구간 구분선은 모두 같은 1px 회색 실선이어야 합니다.');

      const agent = document.querySelector('#ai-shopping figure');
      expect(text(agent) === `AI Search Agent 🔍 ${expected.question} ✨`, '대화창의 문구가 참고 이미지와 다릅니다.');
      expect(agent?.querySelectorAll('.agent-toolbar i').length === 3 &&
        agent?.querySelectorAll('.agent-loading i').length === 3 &&
        !!agent.querySelector('.agent-user'), '대화창에 창 표시, 고객 아이콘, 응답 대기 표시가 있어야 합니다.');
      const shopping = document.querySelector('#ai-shopping .detail-layout');
      const providers = [...shopping.querySelectorAll('.provider-list li')];
      expect(providers.map(text).join('|') === 'ChatGPT|Gemini|Claude|Perplexity' &&
        providers.every(provider => getComputedStyle(provider).backgroundColor === 'rgb(242, 244, 246)'), 'AI 검색 서비스 이름은 각각 토스 회색 상자에 표시해야 합니다.');
      if (width >= 1024) {
        const panelBox = agent.getBoundingClientRect();
        const copyBox = shopping.querySelector('.detail-copy').getBoundingClientRect();
        expect(panelBox.left - copyBox.right <= 48, '설명과 대화창 사이 간격이 48px을 넘습니다.');
        const shoppingBox = shopping.getBoundingClientRect();
        const workflowBox = document.querySelector('#workflow .detail-layout').getBoundingClientRect();
        expect(Math.abs(shoppingBox.left - workflowBox.left) < 1 &&
          Math.abs(shoppingBox.right - workflowBox.right) < 1, '이용 과정은 AI 검색 구간과 같은 중앙 폭을 사용해야 합니다.');
      }

      expect(text(document.querySelector('#delegation .delegation-copy')) === expected.delegation, '위임 구간의 첨부 문구와 문장부호가 다릅니다.');
      expect(text(document.querySelector('#comparison-title')) === expected.comparisonTitle &&
        text(document.querySelector('.comparison-copy .lead')) === expected.comparisonLead &&
        text(document.querySelector('.comparison-summary')) === expected.comparisonSummary, 'SEO·GEO 구간의 설명 문구가 첨부 이미지와 다릅니다.');
      const comparison = document.querySelector('#seo-geo table');
      const comparisonText = [...comparison.rows].map(row => [...row.cells].map(text));
      expect(JSON.stringify(comparisonText) === JSON.stringify(expected.comparisonRows), 'SEO·GEO 표의 문구나 셀 순서가 첨부 이미지와 다릅니다.');
      expect([...comparison.querySelectorAll('th, td')].every(cell => cell.scrollWidth <= cell.clientWidth + 1), 'SEO·GEO 표의 셀 안에서 글이 넘칩니다.');
      expect(text(document.querySelector('#channels-title')) === expected.platforms, '지원 범위와 추가 예정 문구가 다릅니다.');
      const platforms = [...document.querySelectorAll('#channels .channel-brand')];
      expect(platforms.map(element => text(element.querySelector('.channel-name'))).join('|') ===
        '네이버 스마트스토어|카페24', '지원 쇼핑몰은 지정한 두 곳입니다.');
      expect(platforms.every(platform => platform.querySelector('img')?.naturalWidth > 0), '지원 쇼핑몰 로고가 표시되어야 합니다.');
      const candidates = [...document.querySelectorAll('.candidate-list li')];
      expect(candidates.map(item => text(item) || item.querySelector('img')?.alt).join('|') === '아임웹|메이크샵|고도몰' &&
        candidates.every(item => item.querySelector('img')?.naturalWidth > 0 && !item.querySelector('a')), '추가 지원 검토 후보 세 곳의 로고가 보여야 합니다.');
      if (width >= 1024 && platforms.length === 2) {
        const [first, second] = platforms.map(element => element.getBoundingClientRect());
        expect(second.left >= first.right && Math.abs(second.top - first.top) < 2, '지원 쇼핑몰 카드는 데스크톱에서 나란히 있어야 합니다.');
      }
      expect(document.documentElement.scrollWidth === width, '화면에 가로 넘침이 있습니다.');
      return [...new Set(issues)];
    }, { expected, width });
    failures.push(...issues.map(issue => `${width}px · ${issue}`));
  }
  if (failures.length) throw new Error(failures.join('\n'));
  return `${widths.join('·')}px 검사 통과`;
}
