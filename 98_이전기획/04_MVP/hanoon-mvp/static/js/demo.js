const panels = ["input-panel", "loading-panel", "review-panel", "comparison-panel"];
const form = document.getElementById("store-form");
const example = window.HANOON_EXAMPLE;

let currentReport = null;
let loadingTimer = null;

const stageMeta = {
    input: {
        eyebrow: "STEP 1 / 3",
        title: "어느 가게를 진단할까요?",
        description: "기본 정보와 현재 운영 중인 공개 채널을 입력해 주세요.",
    },
    loading: {
        eyebrow: "DIAGNOSIS",
        title: "가게 정보를 분석하고 있습니다",
        description: "공개 채널을 비교해 추천을 막는 원인을 찾습니다.",
    },
    review: {
        eyebrow: "STEP 2 / 3",
        title: "문제와 수정안을 같이 확인하세요",
        description: "왜 노출이 어려운지, 한눈이 무엇을 바꿀지 연결해서 보여드립니다.",
    },
    comparison: {
        eyebrow: "STEP 3 / 3",
        title: "정보 정비 전후를 비교했습니다",
        description: "같은 질문 조건으로 추천 등장과 정보 정확도의 변화를 확인합니다.",
    },
};

const metricDefinitions = [
    {
        key: "appearanceRate",
        label: "추천 등장률",
        suffix: "%",
        help: "전체 답변 중 가게가 추천된 비율",
    },
    {
        key: "averageRank",
        label: "평균 추천 순서",
        suffix: "위",
        help: "낮을수록 상단에 가깝습니다",
    },
    {
        key: "accuracy",
        label: "정보 정확도",
        suffix: "%",
        help: "주소·시간·메뉴가 맞는 비율",
    },
    {
        key: "conditionCoverage",
        label: "조건 반영률",
        suffix: "%",
        help: "관광객 조건을 답변에 반영한 비율",
    },
];

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function setStep(step) {
    document.querySelectorAll("[data-step-indicator]").forEach((item) => {
        const itemStep = Number(item.dataset.stepIndicator);
        const isActive = itemStep === step;
        item.classList.toggle("active", isActive);
        item.classList.toggle("complete", itemStep < step);
        if (isActive) item.setAttribute("aria-current", "step");
        else item.removeAttribute("aria-current");
    });
}

function setWorkspaceHeader(metaKey) {
    const meta = stageMeta[metaKey];
    document.getElementById("workspace-eyebrow").textContent = meta.eyebrow;
    document.getElementById("workspace-title").textContent = meta.title;
    document.getElementById("workspace-description").textContent = meta.description;
}

function showPanel(panelId, step, metaKey, shouldScroll = true) {
    panels.forEach((id) => {
        document.getElementById(id).hidden = id !== panelId;
    });
    setStep(step);
    setWorkspaceHeader(metaKey);

    if (shouldScroll) {
        const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
        document.querySelector(".diagnostic-shell").scrollIntoView({ behavior, block: "start" });
    }
}

function setFieldError(fieldName, message) {
    const input = document.getElementById(fieldName);
    const error = document.getElementById(`${fieldName}-error`);
    if (!input || !error) return;
    input.classList.toggle("invalid", Boolean(message));
    input.setAttribute("aria-invalid", message ? "true" : "false");
    error.textContent = message || "";
}

function clearErrors() {
    ["storeName", "category", "area", "primaryUrl", "naverUrl", "instagramUrl"].forEach((name) => {
        setFieldError(name, "");
    });
}

function isHttpUrl(value) {
    try {
        const url = new URL(value);
        return url.protocol === "http:" || url.protocol === "https:";
    } catch (_error) {
        return false;
    }
}

function readForm() {
    return Object.fromEntries(new FormData(form).entries());
}

function validateForm(values) {
    clearErrors();
    const errors = {};
    const required = {
        storeName: "가게명을 입력해 주세요.",
        category: "업종을 입력해 주세요.",
        area: "지역을 입력해 주세요.",
        primaryUrl: "대표 채널 링크를 입력해 주세요.",
    };

    Object.entries(required).forEach(([field, message]) => {
        if (!String(values[field] || "").trim()) errors[field] = message;
    });

    ["primaryUrl", "naverUrl", "instagramUrl"].forEach((field) => {
        const value = String(values[field] || "").trim();
        if (value && !isHttpUrl(value)) errors[field] = "https://로 시작하는 올바른 링크를 입력해 주세요.";
    });

    Object.entries(errors).forEach(([field, message]) => setFieldError(field, message));
    const firstInvalid = document.querySelector(".field input.invalid");
    if (firstInvalid) firstInvalid.focus();
    return Object.keys(errors).length === 0;
}

function wait(milliseconds) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function startLoadingAnimation() {
    const progress = document.getElementById("loading-progress");
    const message = document.getElementById("loading-message");
    const states = [
        [22, "관광객이 물어볼 질문 조건을 구성하는 중..."],
        [52, "대표 채널의 영업시간과 이용 정보를 비교하는 중..."],
        [80, "AI가 인용할 수 있는 영문 근거를 확인하는 중..."],
        [96, "문제와 수정안을 연결해 정리하는 중..."],
    ];
    let index = 0;
    progress.style.width = "4%";
    message.textContent = states[0][1];

    loadingTimer = window.setInterval(() => {
        const [width, text] = states[index];
        progress.style.width = `${width}%`;
        message.textContent = text;
        index = Math.min(index + 1, states.length - 1);
    }, 480);
}

function stopLoadingAnimation() {
    if (loadingTimer) window.clearInterval(loadingTimer);
    loadingTimer = null;
    document.getElementById("loading-progress").style.width = "100%";
}

async function submitAnalysis(event) {
    event.preventDefault();
    const values = readForm();
    if (!validateForm(values)) return;

    showPanel("loading-panel", 1, "loading");
    startLoadingAnimation();

    try {
        const [response] = await Promise.all([
            fetch("/api/demo/analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(values),
            }),
            wait(2100),
        ]);
        const data = await response.json();

        if (!response.ok) {
            if (data.error?.fields) {
                Object.entries(data.error.fields).forEach(([field, message]) => setFieldError(field, message));
            }
            throw new Error(data.error?.message || "진단을 완료하지 못했습니다.");
        }

        currentReport = data.report;
        renderReview(currentReport);
        stopLoadingAnimation();
        await wait(220);
        showPanel("review-panel", 2, "review");
    } catch (error) {
        stopLoadingAnimation();
        showPanel("input-panel", 1, "input");
        showToast(error.message || "잠시 후 다시 시도해 주세요.");
    }
}

function renderReview(report) {
    document.getElementById("review-summary").innerHTML = `<strong>${escapeHtml(report.store.nameKo)}</strong>의 공개 채널에서 추천을 막는 원인과 수정안을 찾았습니다.`;

    document.getElementById("metric-grid").innerHTML = metricDefinitions
        .map((metric) => {
            const value = report.before[metric.key];
            return `
                <article class="metric-cell">
                    <span>${escapeHtml(metric.label)}</span>
                    <strong>${escapeHtml(value)}${escapeHtml(metric.suffix)}</strong>
                    <small>${escapeHtml(metric.help)}</small>
                </article>`;
        })
        .join("");

    document.getElementById("audit-list").innerHTML = report.issues
        .map(
            (issue, index) => `
                <article class="audit-row" role="row">
                    <div class="audit-problem" role="cell">
                        <div class="audit-row-top">
                            <span class="audit-index">${String(index + 1).padStart(2, "0")}</span>
                            <span class="severity-badge ${issue.severity === "높음" ? "high" : "medium"}">${escapeHtml(issue.severity)}</span>
                        </div>
                        <strong>${escapeHtml(issue.title)}</strong>
                        <p>${escapeHtml(issue.description)}</p>
                        <small><b>확인 근거</b>${escapeHtml(issue.evidence)}</small>
                    </div>
                    <div class="audit-fix" role="cell">
                        <span>개선 방향</span>
                        <strong>${escapeHtml(issue.fix || "누락된 정보를 보완하고 채널별 내용을 일치시킵니다.")}</strong>
                        <p>${escapeHtml(issue.type)} 기준으로 공개 정보와 AI가 읽는 근거를 함께 정비합니다.</p>
                    </div>
                </article>`,
        )
        .join("");

    const improvements = report.improvements;
    document.getElementById("english-description").value = improvements.englishDescription;
    document.getElementById("fact-list").innerHTML = improvements.facts
        .map(
            (fact) => `
                <div class="fact-item">
                    <span>${escapeHtml(fact.label)}</span>
                    <strong>${escapeHtml(fact.value)}</strong>
                </div>`,
        )
        .join("");

    document.getElementById("channel-list").innerHTML = improvements.channelActions
        .map(
            (item) => `
                <article class="channel-item">
                    <strong>${escapeHtml(item.channel)}</strong>
                    <p>${escapeHtml(item.action)}</p>
                    <span class="channel-status">${escapeHtml(item.status)}</span>
                </article>`,
        )
        .join("");

    const measurement = report.measurement;
    document.getElementById("measurement-note").innerHTML = `
        <strong>측정 기준</strong><span>질문 ${escapeHtml(measurement.promptCount)}개 × ${escapeHtml(measurement.repeatCount)}회 ·
        ${escapeHtml(measurement.models.join(" · "))} · ${escapeHtml(measurement.language)} · 총 ${escapeHtml(measurement.responseCount)}개 응답</span>
        <small>${escapeHtml(report.disclaimer)}</small>`;
}

function comparisonBarValue(key, value) {
    if (key === "averageRank") return Math.max(8, Math.min(100, ((6 - value) / 5) * 100));
    return Math.max(4, Math.min(100, value));
}

function formatDelta(metric, before, after) {
    if (metric.key === "averageRank") return `${before}위 → ${after}위`;
    return `+${after - before}%p`;
}

function renderComparison(report) {
    document.getElementById("hero-before-rate").textContent = `${report.before.appearanceRate}%`;
    document.getElementById("hero-after-rate").textContent = `${report.after.appearanceRate}%`;

    document.getElementById("comparison-list").innerHTML = metricDefinitions
        .map((metric) => {
            const before = report.before[metric.key];
            const after = report.after[metric.key];
            const beforeWidth = comparisonBarValue(metric.key, before);
            const afterWidth = comparisonBarValue(metric.key, after);
            return `
                <article class="comparison-item">
                    <div class="comparison-label">
                        <h4>${escapeHtml(metric.label)}</h4>
                        <p>${escapeHtml(metric.help)}</p>
                    </div>
                    <div class="comparison-bars" aria-label="정비 전 ${escapeHtml(before)}${escapeHtml(metric.suffix)}, 정비 후 ${escapeHtml(after)}${escapeHtml(metric.suffix)}">
                        <div class="bar-row"><span>정비 전</span><div class="bar-track"><i style="width:${beforeWidth}%"></i></div><strong>${escapeHtml(before)}${escapeHtml(metric.suffix)}</strong></div>
                        <div class="bar-row after"><span>정비 후</span><div class="bar-track"><i style="width:${afterWidth}%"></i></div><strong>${escapeHtml(after)}${escapeHtml(metric.suffix)}</strong></div>
                    </div>
                    <span class="delta-badge">${escapeHtml(formatDelta(metric, before, after))}</span>
                </article>`;
        })
        .join("");
}

async function approveImprovement() {
    if (!currentReport) return;
    const description = document.getElementById("english-description").value.trim();
    if (description.length < 30) {
        showToast("영문 소개는 30자 이상 입력해 주세요.");
        document.getElementById("english-description").focus();
        return;
    }

    const button = document.getElementById("approve-improvement");
    button.disabled = true;
    button.textContent = "결과를 계산하는 중...";

    try {
        const response = await fetch("/api/demo/approve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reportId: currentReport.id, englishDescription: description }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error?.message || "수정안을 승인하지 못했습니다.");

        sessionStorage.setItem("hanoonApprovedDescription", description);
        renderComparison(currentReport);
        showPanel("comparison-panel", 3, "comparison");
        showToast("동일한 조건으로 전후 비교를 완료했습니다.");
    } catch (error) {
        showToast(error.message || "잠시 후 다시 시도해 주세요.");
    } finally {
        button.disabled = false;
        button.textContent = "수정안 승인 후 결과 보기";
    }
}

function resetExample() {
    form.reset();
    document.getElementById("storeName").value = example.nameKo;
    document.getElementById("category").value = example.categoryKo;
    document.getElementById("area").value = example.areaKo;
    document.getElementById("primaryUrl").value = example.primaryUrl;
    clearErrors();
}

async function copyDescription() {
    const text = document.getElementById("english-description").value;
    try {
        await navigator.clipboard.writeText(text);
        showToast("영문 소개 문안을 복사했습니다.");
    } catch (_error) {
        const textarea = document.getElementById("english-description");
        textarea.select();
        document.execCommand("copy");
        showToast("영문 소개 문안을 복사했습니다.");
    }
}

function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
        toast.hidden = true;
    }, 2600);
}

form.addEventListener("submit", submitAnalysis);
document.getElementById("reset-example").addEventListener("click", resetExample);
document.getElementById("copy-description").addEventListener("click", copyDescription);
document.getElementById("approve-improvement").addEventListener("click", approveImprovement);

document.addEventListener("click", (event) => {
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (action !== "restart") return;
    currentReport = null;
    resetExample();
    showPanel("input-panel", 1, "input");
});

showPanel("input-panel", 1, "input", false);
