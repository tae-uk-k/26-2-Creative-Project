let lines = [];
let currentIndex = 0;

async function loadScript() {
    try {
        const res = await fetch("/api/script");
        const data = await res.json();
        lines = data.lines || [];
        currentIndex = 0;
        render();
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
        lines = data.lines || [];
        currentIndex = 0;
        render();
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

        lines = data.lines || [];
        currentIndex = 0;
        render();
        updateFileStatus(`업로드 완료: ${file.name} (${lines.length}줄 인식됨)`);
    } catch (error) {
        console.error(error);
        updateFileStatus(`업로드 실패: ${file.name}`);
        alert(`오류: ${error.message}`);
    }
}

function nextLine() {
    if (currentIndex < lines.length - 1) {
        currentIndex++;
        render();
    }
}

function prevLine() {
    if (currentIndex > 0) {
        currentIndex--;
        render();
    }
}

function render() {
    const prompter = document.getElementById("prompter");
    const status = document.getElementById("line-status");

    if (lines.length === 0) {
        prompter.innerHTML = '<p class="empty">저장된 대본이 없습니다.</p>';
        status.innerText = "0 / 0";
        return;
    }

    prompter.innerHTML = lines
        .map((line, i) => {
            const cls = i === currentIndex ? "line current" : "line";
            return `<p class="${cls}">${line}</p>`;
        })
        .join("");

    status.innerText = `${currentIndex + 1} / ${lines.length}`;

    const currentEl = prompter.querySelector(".current");
    if (currentEl) {
        currentEl.scrollIntoView({block: "center", behavior: "smooth"});
    }
}

window.addEventListener("DOMContentLoaded", () => {
    loadScript();
    document.getElementById("pdf-input").addEventListener("change", () => {
        const file = document.getElementById("pdf-input").files[0];
        updateFileStatus(file ? `선택된 파일: ${file.name}` : "");
    });
});
