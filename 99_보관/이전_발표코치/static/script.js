let lines = [];
let currentIndex = 0;
let playing = false;
let timer = null;

async function loadScript() {
    try {
        const res = await fetch("/api/script");
        const data = await res.json();
        lines = data.lines || [];
        currentIndex = 0;
        renderLine(true);
    } catch (error) {
        console.error(error);
    }
}

async function saveScript() {
    const text = document.getElementById("script-input").value;

    try {
        const res = await fetch("/api/script", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({text: text})
        });

        if (!res.ok) {
            throw new Error(`서버 오류: ${res.status}`);
        }

        const data = await res.json();
        stopPlay();
        lines = data.lines || [];
        currentIndex = 0;
        renderLine(true);
    } catch (error) {
        console.error(error);
        alert(`오류: ${error.message}`);
    }
}

function updateFileStatus(text) {
    document.getElementById("file-status").innerText = text;
}

async function uploadPdf() {
    const fileInput = document.getElementById("pdf-input");
    const file = fileInput.files[0];

    if (!file) {
        alert("PDF 파일을 선택하세요.");
        return;
    }

    updateFileStatus(`업로드 중: ${file.name}`);

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch("/api/script/upload", {
            method: "POST",
            body: formData
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.error || `서버 오류: ${res.status}`);
        }

        stopPlay();
        lines = data.lines || [];
        currentIndex = 0;
        renderLine(true);
        updateFileStatus(`업로드 완료: ${file.name} (${lines.length}줄 인식됨)`);
    } catch (error) {
        console.error(error);
        updateFileStatus(`업로드 실패: ${file.name}`);
        alert(`오류: ${error.message}`);
    }
}

// skipFade가 true면 페이드 없이 즉시 표시(최초 로드), false면 사라졌다가 다시 나타남
function renderLine(skipFade) {
    const stageLine = document.getElementById("stage-line");
    const status = document.getElementById("stage-status");

    if (lines.length === 0) {
        stageLine.classList.remove("visible");
        stageLine.innerText = "저장된 대본이 없습니다.";
        window.requestAnimationFrame(() => stageLine.classList.add("visible"));
        status.innerText = "0 / 0";
        return;
    }

    status.innerText = `${currentIndex + 1} / ${lines.length}`;

    if (skipFade) {
        stageLine.innerText = lines[currentIndex];
        stageLine.classList.add("visible");
        return;
    }

    stageLine.classList.remove("visible");
    window.setTimeout(() => {
        stageLine.innerText = lines[currentIndex];
        stageLine.classList.add("visible");
    }, 350);
}

function nextLine() {
    if (lines.length === 0) return;
    currentIndex = (currentIndex + 1) % lines.length;
    renderLine(false);
}

function prevLine() {
    if (lines.length === 0) return;
    currentIndex = (currentIndex - 1 + lines.length) % lines.length;
    renderLine(false);
}

function togglePlay() {
    if (playing) {
        stopPlay();
    } else {
        startPlay();
    }
}

function startPlay() {
    if (lines.length === 0) return;
    playing = true;
    document.getElementById("play-btn").innerText = "자동재생 정지";
    scheduleNext();
}

function stopPlay() {
    playing = false;
    document.getElementById("play-btn").innerText = "자동재생 시작";
    if (timer) {
        clearTimeout(timer);
        timer = null;
    }
}

function scheduleNext() {
    if (!playing) return;
    const seconds = parseFloat(document.getElementById("interval-input").value) || 2.5;
    timer = window.setTimeout(() => {
        nextLine();
        scheduleNext();
    }, seconds * 1000);
}

window.addEventListener("DOMContentLoaded", () => {
    loadScript();
    document.getElementById("pdf-input").addEventListener("change", () => {
        const file = document.getElementById("pdf-input").files[0];
        updateFileStatus(file ? `선택된 파일: ${file.name}` : "");
    });
});
