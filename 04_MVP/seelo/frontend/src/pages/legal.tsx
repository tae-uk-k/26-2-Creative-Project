import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Notice } from "../ui/Display";
import { Page, PageHeader } from "../ui/Layout";
import styles from "./legal.module.css";

// 공개 전 검토가 필요한 초안이다. 【】 표시는 운영자가 채워야 하는 값이다.
function Todo({ children }: { children: ReactNode }) {
  return <span className={styles.todo}>【{children}】</span>;
}
function LegalLayout({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <>
      <header className={styles.top}>
        <div className={styles.topInner}>
          <Link to="/" aria-label="seelo 처음으로">
            <img src="/images/logo.png" width="78" height="38" alt="seelo" />
          </Link>
        </div>
      </header>
      <Page width="medium">
        <PageHeader title={title} />
        <div style={{ marginBottom: "1rem" }}>
          <Notice tone="warning" title="검토 전 초안">
            시행일 <Todo>미정</Todo> · 공개 전에 내용을 확정합니다.
          </Notice>
        </div>
        <article className={styles.doc}>{children}</article>
      </Page>
    </>
  );
}
export function TermsPage() {
  return (
    <LegalLayout title="이용약관">
      <h2>제1조 목적</h2>
      <p>
        이 약관은 seelo(이하 “서비스”)가 제공하는 쇼핑몰 상품 정보 정비 서비스의
        이용 조건과 절차, 이용자와 서비스의 권리·의무를 정합니다.
      </p>
      <h2>제2조 정의</h2>
      <ol>
        <li>
          “판매자”는 스마트스토어 또는 카페24에서 상품을 판매하고 이 약관에
          동의해 가입한 사람입니다.
        </li>
        <li>
          “위임”은 판매자가 쇼핑몰 관리 화면에서 서비스 담당자 계정에 상품 수정
          권한을 주는 것입니다.
        </li>
        <li>
          “정비안”은 현재 상품 정보와 바꿀 내용, 그 근거를 모은 승인용
          목록입니다.
        </li>
        <li>
          “반영”은 판매자가 승인한 정비안을 쇼핑몰 관리 화면에 저장하는
          것입니다.
        </li>
      </ol>
      <h2>제3조 약관의 효력과 변경</h2>
      <p>
        서비스는 약관을 바꿀 때 시행일과 바뀌는 내용을 시행일 7일 전부터 서비스
        화면에 알립니다. 판매자에게 불리한 변경은 30일 전부터 알립니다.
      </p>
      <h2>제4조 가입과 계정</h2>
      <ol>
        <li>가입은 이메일 인증 또는 Google·카카오 계정 연결로 완료됩니다.</li>
        <li>판매자는 계정 정보를 다른 사람과 함께 쓰지 않습니다.</li>
      </ol>
      <h2>제5조 서비스 내용</h2>
      <ol>
        <li>등록한 스토어의 상품 정보를 불러와 공개 자료와 대조합니다.</li>
        <li>
          확인한 사실로 정비안을 만들고, 확인하지 못한 필수 정보만 판매자에게
          묻습니다.
        </li>
        <li>
          판매자가 승인한 항목만 쇼핑몰에 반영하고 반영 결과를 확인합니다.
        </li>
        <li>
          정비 전후에 같은 조건으로 AI 답변을 측정하고 보고서를 제공합니다.
        </li>
      </ol>
      <h2>제6조 권한 위임과 수정 범위</h2>
      <ol>
        <li>
          판매자는 정비할 스토어의 관리 권한이 있는 경우에만 스토어를
          등록합니다.
        </li>
        <li>
          서비스는 판매자가 승인한 항목만 수정합니다. 가격·재고·옵션·배송·판매
          상태·구매 조건은 수정하지 않습니다.
        </li>
        <li>
          서비스는 판매자의 쇼핑몰 비밀번호와 2단계 인증 정보를 받지 않습니다.
        </li>
        <li>
          판매자는 언제든 쇼핑몰 관리 화면에서 권한을 거둘 수 있고, 서비스
          화면에서 연결을 해제할 수 있습니다.
        </li>
      </ol>
      <h2>제7조 판매자의 의무</h2>
      <ol>
        <li>판매자는 질문에 답할 때 사실과 같은 정보를 제공합니다.</li>
        <li>판매자는 승인 전에 바뀔 내용을 확인합니다.</li>
      </ol>
      <h2>제8조 서비스의 의무</h2>
      <ol>
        <li>
          서비스는 반영 전 값과 반영 기록을 보관하고, 판매자가 요청하면 승인
          범위의 수정 전 값으로 되돌립니다.
        </li>
        <li>서비스는 확인하지 않은 사양이나 효능을 정비안에 넣지 않습니다.</li>
      </ol>
      <h2>제9조 이용 요금</h2>
      <p>
        요금과 결제 방법은 <Todo>미정</Todo>입니다. 정해지면 시행 전에 알립니다.
      </p>
      <h2>제10조 서비스 변경과 중단</h2>
      <p>
        설비 점검, 쇼핑몰 플랫폼의 정책·화면 변경 등으로 서비스 일부를 멈출 수
        있습니다. 미리 알릴 수 있는 경우 화면에 알립니다.
      </p>
      <h2>제11조 탈퇴와 이용 제한</h2>
      <ol>
        <li>판매자는 계정 화면에서 언제든 탈퇴할 수 있습니다.</li>
        <li>
          권한이 없는 스토어를 등록하거나 서비스를 방해하면 이용을 제한할 수
          있습니다.
        </li>
      </ol>
      <h2>제12조 손해배상</h2>
      <p>
        서비스 또는 판매자가 고의나 과실로 상대방에게 손해를 끼친 경우 관련
        법령에 따라 배상합니다. <Todo>세부 조항 검토</Todo>
      </p>
      <h2>제13조 분쟁 해결</h2>
      <p>
        분쟁은 서로 협의해 해결하고, 협의되지 않으면 <Todo>관할 법원</Todo>을
        관할 법원으로 합니다.
      </p>
    </LegalLayout>
  );
}
export function PrivacyPage() {
  return (
    <LegalLayout title="개인정보 처리방침">
      <h2>1. 처리하는 개인정보</h2>
      <table>
        <thead>
          <tr>
            <th scope="col">구분</th>
            <th scope="col">항목</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">가입·로그인</th>
            <td>
              이메일, 비밀번호(복원할 수 없는 값으로 바꿔 저장), Google·카카오
              회원 식별값, 약관 동의 시각
            </td>
          </tr>
          <tr>
            <th scope="row">서비스 이용</th>
            <td>
              등록한 스토어 주소·플랫폼·스토어 ID, 불러온 상품 정보(상품명·상세
              설명·검색 노출 항목), 판매자 답변, 정비안·승인·반영 기록
            </td>
          </tr>
          <tr>
            <th scope="row">자동 생성</th>
            <td>로그인 유지·보안 쿠키, 접속·작업 기록</td>
          </tr>
        </tbody>
      </table>
      <h2>2. 이용 목적</h2>
      <ul>
        <li>회원 확인과 로그인 유지</li>
        <li>상품 정보 조사, 정비안 작성, 승인한 내용의 쇼핑몰 반영</li>
        <li>정비 전후 AI 노출 측정과 보고서 제공</li>
        <li>보안 사고 예방과 문의 응대</li>
      </ul>
      <h2>3. 보유 기간</h2>
      <p>
        탈퇴하면 계정, 스토어, 상품, 정비안과 기록을 지체 없이 지웁니다. 법령에
        따라 보관해야 하는 기록은 그 기간 동안만 보관합니다.{" "}
        <Todo>보관 항목·기간</Todo>
      </p>
      <h2>4. 처리 위탁과 국외 이전</h2>
      <table>
        <thead>
          <tr>
            <th scope="col">받는 곳</th>
            <th scope="col">하는 일</th>
            <th scope="col">보내는 정보</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>OpenAI(미국)</td>
            <td>상품 자료 조사, 정비안 작성, AI 노출 측정</td>
            <td>상품 정보, 공개 자료, 측정 질문</td>
          </tr>
          <tr>
            <td>Google(미국)</td>
            <td>AI 노출 측정(Gemini)</td>
            <td>측정 질문</td>
          </tr>
          <tr>
            <td>
              Google Cloud <Todo>리전</Todo>
            </td>
            <td>서버 운영과 데이터 보관</td>
            <td>서비스 전체 데이터</td>
          </tr>
          <tr>
            <td>
              <Todo>메일 발송 업체</Todo>
            </td>
            <td>인증·비밀번호 재설정 메일 발송</td>
            <td>이메일</td>
          </tr>
        </tbody>
      </table>
      <p>
        AI에 보내는 정보에는 계정 정보를 넣지 않습니다. 상품 정보에 개인정보가
        들어가지 않도록 판매자도 확인해 주세요.
      </p>
      <h2>5. 제3자 제공</h2>
      <p>
        법령에 근거가 있는 경우를 빼고 개인정보를 다른 곳에 제공하지 않습니다.
      </p>
      <h2>6. 이용자의 권리</h2>
      <p>
        개인정보를 열람·정정·삭제하거나 처리 정지를 요청할 수 있습니다. 계정
        화면에서 비밀번호 변경과 탈퇴를 바로 할 수 있습니다.
      </p>
      <h2>7. 쿠키</h2>
      <p>
        로그인 유지와 요청 위조 방지에 필요한 쿠키만 씁니다. 광고 쿠키는 쓰지
        않습니다.
      </p>
      <h2>8. 안전 조치</h2>
      <ul>
        <li>비밀번호는 복원할 수 없는 값으로 바꿔 저장합니다.</li>
        <li>쇼핑몰 연결 정보와 담당자 로그인 정보는 암호화해 저장합니다.</li>
        <li>
          판매자 본인과 운영자만 스토어 정보를 볼 수 있게 권한을 나눕니다.
        </li>
      </ul>
      <h2>9. 개인정보 보호책임자</h2>
      <p>
        <Todo>이름</Todo> · <Todo>연락처</Todo>
      </p>
    </LegalLayout>
  );
}
