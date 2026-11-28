import { useLayoutEffect } from "react";
import { Link } from "react-router-dom";
import base from "./landing-base.css?inline";
import dark from "./landing-dark.css?inline";
import extra from "./landing-app.css?inline";

// 랜딩 시안(05_발표자료/결과물/seelo_쇼핑몰_랜딩_새시안_20261125/dark.html)을 그대로 옮긴다.
// 히어로의 `무료 진단받기`도 시안처럼 준비 중 안내만 띄운다.
// 시안 스타일은 전역 선택자를 쓰므로 이 화면이 열려 있을 때만 붙인다.
function useLandingStyle() {
  useLayoutEffect(() => {
    const style = document.createElement("style");
    style.dataset.seelo = "landing";
    style.textContent = `${base}\n${dark}\n${extra}`;
    document.head.append(style);
    const title = document.title;
    document.title = "seelo | 쇼핑몰 상품 정보 정비";
    return () => {
      style.remove();
      document.title = title;
    };
  }, []);
}
export function LandingPage({ signedIn }: { signedIn: boolean }) {
  useLandingStyle();
  return (
    <div className="landing" id="top">
      <a className="skip-link" href="#main">
        본문 바로가기
      </a>
      <header className="site-header">
        <div className="wrap header-content">
          <a className="brand" href="#top" aria-label="seelo 처음으로">
            <img src="/images/logo.png" width="78" height="38" alt="seelo" />
          </a>
          <nav aria-label="주요 메뉴">
            <a href="#ai-shopping">서비스 소개</a>
            <a href="#workflow">이용 방법</a>
            <a href="#channels">지원 쇼핑몰</a>
          </nav>
          <Link className="header-login" to={signedIn ? "/home" : "/login"}>
            {signedIn ? "내 스토어" : "로그인"}
          </Link>
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        <section className="dark-first-screen" aria-labelledby="hero-title">
          <div className="wrap dark-hero">
            {/* 녹색과 청록색이 섞인 배경광을 먼저 골라 남색으로 보정한다. */}
            <svg
              className="hero-filter"
              width="0"
              height="0"
              aria-hidden="true"
              focusable="false"
            >
              <filter id="navy-backdrop" colorInterpolationFilters="sRGB">
                <feColorMatrix
                  in="SourceGraphic"
                  type="matrix"
                  values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -10 20 -10 0 0"
                  result="green-bias"
                />
                <feColorMatrix
                  in="SourceGraphic"
                  type="matrix"
                  values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -24 0 24 0 0"
                  result="cool-bias"
                />
                <feComposite
                  in="green-bias"
                  in2="cool-bias"
                  operator="in"
                  result="backdrop"
                />
                <feColorMatrix
                  in="SourceGraphic"
                  type="matrix"
                  values=".5 .1 0 0 0  0 .65 0 0 0  0 .28 .79 0 0  0 0 0 1 0"
                  result="navy"
                />
                <feComposite
                  in="navy"
                  in2="backdrop"
                  operator="in"
                  result="tinted"
                />
                <feComposite in="tinted" in2="SourceGraphic" operator="over" />
              </filter>
            </svg>
            <div className="hero-intro">
              <h1 id="hero-title">AI 검색에서 우리 상품이 답이 되도록</h1>
              <p className="lead">
                스마트스토어·카페24 상품 정보를 AI가 읽기 쉽게 정리합니다.
              </p>
              <div className="hero-actions">
                <a className="button hero-action-secondary" href="#workflow">
                  이용 과정 보기
                </a>
                {/* 시안과 같다. 진단 기능이 생기기 전까지는 준비 중 안내만 띄운다. */}
                <button
                  className="button hero-action-primary"
                  type="button"
                  popoverTarget="diagnosis-notice"
                >
                  무료 진단받기
                </button>
              </div>
              <p
                className="diagnosis-notice"
                id="diagnosis-notice"
                popover="auto"
                role="status"
              >
                무료 진단은 준비 중이에요.
              </p>
            </div>
            <img
              className="dark-hero-art"
              src="/images/stores-layered.webp"
              alt="어두운 배경에 신발, 뷰티, 디지털, 리빙, 캠핑 쇼핑몰 화면이 겹쳐 있는 모습"
              width="1672"
              height="941"
              fetchPriority="high"
            />
          </div>
        </section>

        <section
          className="section"
          id="ai-shopping"
          aria-labelledby="shopping-title"
        >
          <div className="wrap detail-layout">
            <div className="detail-copy">
              <h2 id="shopping-title">
                AI가 못 찾으면,
                <br />
                고객도 못 찾습니다.
              </h2>
              <p className="lead">
                AI가 조건에 맞는 상품을 골라줄 때, 우리 상품도 후보에 들어갈 수
                있을까요?
              </p>
              <ul className="provider-list" aria-label="AI 검색 서비스 예시">
                <li>ChatGPT</li>
                <li>Gemini</li>
                <li>Claude</li>
                <li>Perplexity</li>
              </ul>
            </div>
            <figure className="agent-window">
              <figcaption className="agent-toolbar">
                <span className="agent-traffic" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <span>AI Search Agent</span>
              </figcaption>
              <div className="agent-message agent-query">
                <p>
                  <span aria-hidden="true">🔍</span>{" "}
                  <span>울함량 50% 이상의 니트 7만원대로 찾아줘</span>
                </p>
                <span className="agent-avatar agent-user" aria-hidden="true" />
              </div>
              <div className="agent-message">
                <span className="agent-avatar agent-spark" aria-hidden="true">
                  ✨
                </span>
                <span
                  className="agent-loading"
                  role="img"
                  aria-label="응답 대기"
                >
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            </figure>
          </div>
        </section>

        <section
          className="section"
          id="delegation"
          aria-labelledby="delegation-title"
        >
          <div className="wrap delegation-copy">
            <p>
              지금까지의 전자상거래가 &apos;검색(Search)&apos;과
              &apos;발견&apos;의 시대였다면,
            </p>
            <h2 id="delegation-title">
              앞으로 다가올 미래는 &apos;위임(Delegation)&apos;의 시대입니다,
            </h2>
            <p>- 에이전틱 커머스(Agentic Commerce) -</p>
          </div>
        </section>

        <section
          className="section"
          id="seo-geo"
          aria-labelledby="comparison-title"
        >
          <div className="wrap comparison-layout">
            <div className="detail-copy comparison-copy">
              <h2 id="comparison-title">SEO랑 다른건가요?</h2>
              <p className="lead">
                이제는 검색 엔진 최적화(SEO)를 넘어,
                <br />
                <strong>생성형 엔진 최적화(GEO)</strong>가 필요합니다.
              </p>
            </div>
            <div className="comparison-table">
              <table aria-labelledby="comparison-title">
                <thead>
                  <tr>
                    <th scope="col">구분</th>
                    <th scope="col">SEO</th>
                    <th scope="col">GEO</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">목표</th>
                    <td>네이버/구글 검색 순위</td>
                    <td>AI 추천 답변</td>
                  </tr>
                  <tr>
                    <th scope="row">경쟁</th>
                    <td>10개 링크 중 1등</td>
                    <td>단 하나의 정답</td>
                  </tr>
                  <tr>
                    <th scope="row">사용자 행동</th>
                    <td>여러 링크 클릭해서 비교</td>
                    <td>AI 답변 그대로 신뢰</td>
                  </tr>
                  <tr>
                    <th scope="row">노출 방식</th>
                    <td>링크 목록</td>
                    <td>대화형 추천</td>
                  </tr>
                  <tr>
                    <th scope="row">핵심 기술</th>
                    <td>키워드, 백링크</td>
                    <td>구조화 데이터, Schema</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="comparison-summary">
              GEO는 AI가 선택한 <strong>&apos;단 하나의 정답&apos;</strong>이
              되는 것입니다.
            </p>
          </div>
        </section>

        <section
          className="section"
          id="workflow"
          aria-labelledby="workflow-title"
        >
          <div className="wrap detail-layout">
            <div className="detail-copy">
              <h2 id="workflow-title">
                측정하고, 정비하고,
                <br />
                달라진 점을 확인하세요.
              </h2>
              <p className="lead">
                스마트스토어·카페24 상품이 AI 답변에 어떻게 보이는지 먼저
                측정합니다. 정비 후 같은 조건으로 다시 측정해 전후 결과를
                보고서로 보여드립니다.
              </p>
            </div>
            <ol className="detail-panel detail-rows workflow-steps" role="list">
              <li>
                <span className="step-index" aria-hidden="true">
                  1
                </span>
                <h3>정비 전 AI 노출 측정</h3>
                <p>
                  고객이 할 법한 질문으로 AI 답변에서 상품이 언급·추천되는지,
                  상품 링크가 인용되는지 확인합니다.
                </p>
              </li>
              <li>
                <span className="step-index" aria-hidden="true">
                  2
                </span>
                <h3>상품 정보 정비와 반영</h3>
                <p>
                  상품 자료와 상세페이지를 대조해 빠진 정보를 보완합니다.
                  판매자가 승인한 변경을 반영하고 공개 페이지에서 확인합니다.
                </p>
                <details className="product-example" id="overview">
                  <summary className="detail-action">
                    상품 설명 정비 전후 예시
                    <span className="row-chevron" aria-hidden="true" />
                  </summary>
                  <dl>
                    <div>
                      <dt>기존 설명</dt>
                      <dd>부드럽고 따뜻한 라운드넥 니트입니다.</dd>
                    </div>
                    <div>
                      <dt>정비안</dt>
                      <dd>울 55%와 나일론 45%를 혼방한 라운드넥 니트입니다.</dd>
                    </div>
                    <div>
                      <dt>확인한 자료</dt>
                      <dd>판매자가 제공한 혼용률 표기</dd>
                    </div>
                  </dl>
                </details>
              </li>
              <li>
                <span className="step-index" aria-hidden="true">
                  3
                </span>
                <h3>일정 기간 후 재측정과 보고서</h3>
                <p>
                  정비 전과 같은 질문과 조건으로 다시 측정합니다. 보고서에서
                  상품 언급, 추천, 링크 인용의 전후 결과를 비교합니다.
                </p>
              </li>
            </ol>
          </div>
        </section>

        <section
          className="section"
          id="channels"
          aria-labelledby="channels-title"
        >
          <div className="wrap channels-layout">
            <div className="detail-copy">
              <h2 id="channels-title">
                현재는 네이버 스마트스토어와 카페24만 지원합니다.
                <br />
                다른 쇼핑몰도 곧 추가합니다.
              </h2>
              <p className="lead">
                상품 편집 권한을 연결한 뒤 정비할 상품을 선택합니다.
              </p>
            </div>
            <ul className="channel-options" role="list">
              <li>
                <a
                  className="channel-brand detail-action"
                  href="https://sell.smartstore.naver.com/"
                >
                  <span className="channel-logo">
                    <img
                      className="smartstore-logo"
                      src="/images/smartstore.png"
                      width="127"
                      height="131"
                      alt=""
                    />
                  </span>
                  <span>
                    <span className="channel-name">네이버 스마트스토어</span>
                    <span className="channel-note">
                      판매자센터에서 seelo를 대행사 매니저로 초대합니다.
                    </span>
                  </span>
                  <span className="row-chevron" aria-hidden="true" />
                </a>
              </li>
              <li>
                <a
                  className="channel-brand detail-action"
                  href="https://eclogin.cafe24.com/Shop/"
                >
                  <span className="channel-logo">
                    <img
                      className="cafe24-logo"
                      src="/images/cafe24.svg"
                      width="112"
                      height="20"
                      alt=""
                    />
                  </span>
                  <span>
                    <span className="channel-name">카페24</span>
                    <span className="channel-note">
                      쇼핑몰 관리자에서 상품 수정 권한이 있는 부운영자를
                      연결합니다.
                    </span>
                  </span>
                  <span className="row-chevron" aria-hidden="true" />
                </a>
              </li>
            </ul>
            <div className="candidate-platforms">
              <h3>추가 지원 검토</h3>
              <ul
                className="candidate-list"
                aria-label="추가 지원 검토 중인 쇼핑몰 플랫폼"
              >
                <li>
                  <img src="/images/imweb.svg" width="20" height="20" alt="" />
                  <span>아임웹</span>
                </li>
                <li>
                  <img
                    src="/images/makeshop.svg"
                    width="100"
                    height="42"
                    alt="메이크샵"
                  />
                </li>
                <li>
                  <img
                    className="candidate-logo-on-dark"
                    src="/images/godomall.png"
                    width="127"
                    height="34"
                    alt="고도몰"
                  />
                </li>
              </ul>
            </div>
          </div>
        </section>

        <section className="section faq" id="faq" aria-labelledby="faq-title">
          <div className="wrap detail-layout">
            <h2 id="faq-title">자주 묻는 질문</h2>
            <div className="detail-panel questions">
              {[
                [
                  "어떤 쇼핑몰을 지원하나요?",
                  "네이버 스마트스토어와 카페24를 지원합니다.",
                ],
                [
                  "정비안을 먼저 볼 수 있나요?",
                  "현재 상품 설명과 새 정비안을 확인할 수 있습니다. seelo는 판매자가 승인한 내용을 쇼핑몰에 반영합니다.",
                ],
                [
                  "상품 정보가 부족하면 어떻게 하나요?",
                  "현재 상세페이지와 제공한 자료를 먼저 조사합니다. 필수 정보가 확인되지 않으면 판매자에게 필요한 내용을 물어봅니다.",
                ],
                [
                  "어떤 상품 자료를 준비하면 되나요?",
                  "쇼핑몰 주소만 등록하면 seelo가 현재 상세페이지와 공개 자료를 먼저 조사하고, 확인되지 않은 정보만 여쭤봅니다.",
                ],
              ].map(([question, answer]) => (
                <details key={question}>
                  <summary className="detail-action">
                    <span className="question-prefix" aria-hidden="true">
                      Q
                    </span>
                    <span>{question}</span>
                    <span className="row-chevron" aria-hidden="true" />
                  </summary>
                  <p>{answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      </main>
      <footer className="site-footer">
        <div className="wrap footer-content">
          <a className="brand" href="#top" aria-label="seelo 처음으로">
            <img src="/images/logo.png" width="78" height="38" alt="seelo" />
          </a>
          <p>쇼핑몰 상품 정보 정비</p>
          <span className="footer-links">
            <Link to="/terms">이용약관</Link>
            <Link to="/privacy">개인정보 처리방침</Link>
          </span>
        </div>
      </footer>
    </div>
  );
}
