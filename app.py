from flask import Flask, request, jsonify, send_file, make_response
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading
import time

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, expose_headers=["Content-Disposition", "Content-Length", "Content-Type"])

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

COOKIE_FILE = "cookies.txt"

def cleanup_file(path, delay=120):
    def _delete():
        time.sleep(delay)
        if os.path.exists(path):
            os.remove(path)
    threading.Thread(target=_delete, daemon=True).start()

@app.after_request
def after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Expose-Headers"] = "Content-Disposition, Content-Length, Content-Type"
    return response

def base_ydl_opts():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "web"],
                "player_skip": ["webpage"],
            }
        },
    }
    if os.path.exists(COOKIE_FILE):
        opts["cookiefile"] = COOKIE_FILE
    return opts

@app.route("/info", methods=["POST", "OPTIONS"])
def get_info():
    if request.method == "OPTIONS":
        return make_response("", 204)
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL gerekli"}), 400
    ydl_opts = base_ydl_opts()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                "title": info.get("title", "Bilinmiyor"),
                "thumbnail": info.get("thumbnail", ""),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", "Bilinmiyor"),
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/download", methods=["POST", "OPTIONS"])
def download():
    if request.method == "OPTIONS":
        return make_response("", 204)
    data = request.json
    url = data.get("url", "").strip()
    fmt = data.get("format", "mp4")
    quality = data.get("quality", "best")
    if not url:
        return jsonify({"error": "URL gerekli"}), 400
    file_id = str(uuid.uuid4())

    ydl_opts = base_ydl_opts()

    if fmt == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "outtmpl": os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        height_map = {"1080p": 1080, "720p": 720, "480p": 480, "360p": 360}
        if quality in height_map:
            h = height_map[quality]
            fmt_str = f"bestvideo[height<={h}]+bestaudio/bestvideo[height<={h}]/best[height<={h}]/best"
        else:
            fmt_str = "bestvideo+bestaudio/best"
        ydl_opts.update({
            "format": fmt_str,
            "outtmpl": os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s"),
            "merge_output_format": "mp4",
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")

        actual_path = None
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id):
                actual_path = os.path.join(DOWNLOAD_DIR, f)
                break

        if not actual_path:
            return jsonify({"error": "Dosya oluşturulamadı"}), 500

        safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()[:80]
        cleanup_file(actual_path)

        response = make_response(send_file(
            actual_path,
            as_attachment=True,
            download_name=f"{safe_title}.{fmt}",
            mimetype="audio/mpeg" if fmt == "mp3" else "video/mp4"
        ))
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "Content-Disposition, Content-Length"
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
