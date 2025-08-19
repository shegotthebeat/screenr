# requirements.txt
# Flask==3.0.3
# playwright==1.45.0

# -------------------------------------------------------------
# Webpage Archiver Web Application
#
# This script uses Flask to create a web server and Playwright
# to take a full-page screenshot of a user-submitted URL.
#
# http://127.0.0.1:8002
# -------------------------------------------------------------

import asyncio
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright
from flask import Flask, render_template_string, request, url_for, send_from_directory, abort
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Upload location: external SSD
UPLOAD_DIRECTORY = Path("/mnt/storage/uploads")
UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------------------
# Async helper: save webpage screenshot
# -------------------------------------------------------------
async def save_webpage_as_image(url: str, output_path: str):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_viewport_size({"width": 1920, "height": 1080})
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.screenshot(path=output_path, full_page=True)
            await browser.close()
            return True
    except Exception as e:
        print(f"[ERROR] Screenshot failed: {e!r}")
        return False


# -------------------------------------------------------------
# HTML template
# -------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Webpage Archiver</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="container">
        <div class="sidebar">
            <h1>Web Archiver</h1>
            <div class="nav-section">
                <h3>Main</h3>
                <ul>
                    <li class="nav-item active"><a href="/">Archive URL</a></li>
                </ul>
            </div>
        </div>
        <div class="content">
            <h2 class="page-title">Archive a Webpage</h2>
            <div class="form-section">
                <h3 class="form-title">Enter URL to Archive</h3>
                <form action="/archive" method="post">
                    <div class="form-group">
                        <label for="url">URL</label>
                        <input type="text" class="form-control" id="url" name="url" placeholder="https://example.com" required>
                    </div>
                    <button type="submit" class="btn">Archive</button>
                </form>
            </div>
            {% if message %}
            <div class="status-message status-{{ message_type }}">
                {{ message }}
            </div>
            {% endif %}
            {% if image_url %}
            <div class="preview-section">
                <h3 class="preview-title">Archived Image</h3>
                <img src="{{ image_url }}" alt="Archived Webpage" style="width: 100%; height: auto; border: 1px solid #000;">
            </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""


# -------------------------------------------------------------
# Routes
# -------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML_TEMPLATE, message=None, image_url=None)


@app.route("/archive", methods=["POST"])
async def archive():
    url = request.form.get("url", "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return render_template_string(HTML_TEMPLATE, message="Provide a valid http(s) URL.", message_type="error")

    # Timestamped, sanitized filename
    filename = secure_filename(f"screenr_{datetime.now():%Y%m%d%H%M%S}.png")
    output_path = UPLOAD_DIRECTORY / filename

    print(f"[INFO] Attempting to save screenshot → {output_path}")

    success = await save_webpage_as_image(url, str(output_path))

    if success and output_path.exists():
        message = f"Successfully archived {url}."
        image_url = url_for("serve_upload", filename=filename)
        print(f"[INFO] Saved OK: {output_path}")
        return render_template_string(HTML_TEMPLATE, message=message, message_type="success", image_url=image_url)
    else:
        message = f"Failed to archive {url}. Check logs."
        print(f"[ERROR] Save failed for {url} → {output_path}")
        return render_template_string(HTML_TEMPLATE, message=message, message_type="error")


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    try:
        return send_from_directory(UPLOAD_DIRECTORY, filename)
    except FileNotFoundError:
        abort(404)


# Debug endpoint: check write perms from inside Flask
@app.route("/permcheck")
def permcheck():
    try:
        testfile = UPLOAD_DIRECTORY / ".flask_perm_ok"
        with open(testfile, "w") as f:
            f.write("ok")
        testfile.unlink(missing_ok=True)
        return "WRITE_OK", 200
    except Exception as e:
        return f"WRITE_FAIL: {e!r}", 500


# -------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002, debug=True)
