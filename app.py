import json
import re
from pathlib import Path
from flask import Flask, request, jsonify, render_template
from pypdf import PdfReader
from pypdf.errors import PdfReadError

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 업로드 파일 10MB 제한

DATA_FILE = Path(__file__).parent / "data" / "scripts.json"


def split_script(text):
    text = text.strip()
    if not text:
        return []
    # 줄바꿈 또는 문장부호(. ? !) 뒤에서 문장 단위로 분리
    parts = re.split(r"(?<=[.?!])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/script", methods=["GET"])
def get_script():
    # 데이터베이스(JSON)에서 대본 읽어오기
    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)


@app.route("/api/script", methods=["POST"])
def save_script():
    body = request.get_json()
    text = body.get("text", "")

    lines = split_script(text)
    data = {"lines": lines}

    # 데이터베이스(JSON)에 대본 저장하기
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return jsonify(data)


@app.route("/api/script/upload", methods=["POST"])
def upload_script():
    file = request.files.get("file")
    if file is None or file.filename == "":
        return jsonify({"error": "파일이 없습니다."}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "PDF 파일만 업로드할 수 있습니다."}), 400

    try:
        reader = PdfReader(file.stream)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except PdfReadError:
        return jsonify({"error": "PDF 파일을 읽을 수 없습니다."}), 400

    lines = split_script(text)
    data = {"lines": lines}

    # 데이터베이스(JSON)에 대본 저장하기
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True)
