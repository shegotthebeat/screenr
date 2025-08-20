import asyncio
import re
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, request, send_from_directory
from werkzeug.utils import secure_filename
import os

from playwright.async_api import async_playwright

app = Flask(__name__)

# Where to store screenshots:
SAVE_DIR = Path(os.environ.get("ARCHIVE_DIR", "/mnt/storage/uploads")).resolve()
SAVE_DIR.mkdir(parents=True, exist_ok=True)

def normalize_url(raw: str) -> str:
    raw = raw.strip()
    if not re.match(r"^https?://", raw, re.IGNORECASE):
        raw = "https://" + raw
    return raw

async def save_webpage_as_image(url: str, output_path: Path):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=[
                # Helps in some container/ARM environments
                "--no-sandbox", "--disable-setuid-sandbox",
            ])
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            # Navigate with a generous timeout; some pages hang with 'networkidle'
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # Try to make page fully rendered (optional small wait)
            await page.wait_for_timeout(800)

            await page.screenshot(path=str(output_path), full_page=True)
            await browser.close()
            return True, None
    except Exception as e:
        return False, str(e)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Webpage Archiver</title>
  <link rel="stylesheet" href="/static/style.css"/>
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
        {% if error_detail %}
        <div style="margin-top:.5rem;font-size:.9rem;opacity:.8">
          <code>{{ error_detail }}</code>
        </div>
        {% endif %}
      </div>
      {% endif %}

      {% if image_url %}
      <div class="preview-section">
        <h3 class="preview-title">Archived Image</h3>
        <img src="{{ image_url }}" alt="Archived Webpage" style="width:100%;height:auto;border:1px solid #000;">
        <p><a href="{{ image_url }}" download>Download</a></p>
      </div>
      {% endif %}
    </div>
  </div>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML_TEMPLATE, message=None, image_url=None)

@app.route("/archive", methods=["POST"])
async def archive():
    raw_url = request.form.get("url", "").strip()
    if not raw_url:
        return render_template_string(
            HTML_TEMPLATE, message="Please provide a valid URL.", message_type="error"
        )

    url = normalize_url(raw_url)

    # Name the file with timestamp + netloc for readability
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    netloc = urlparse(url).netloc.replace(":", "_")
    base_name = secure_filename(f"{netloc}_{ts}.png") or f"screenshot_{ts}.png"
    output_path = (SAVE_DIR / base_name)

    success, err = await save_webpage_as_image(url, output_path)

    if success:
        message = f"Successfully archived {url}."
        image_url = f"/uploads/{base_name}"
        return render_template_string(
            HTML_TEMPLATE, message=message, message_type="success", image_url=image_url
        )
    else:
        message = f"Failed to archive {url}. See details below."
        return render_template_string(
            HTML_TEMPLATE,
            message=message,
            message_type="error",
            error_detail=err,
            image_url=None,
        )

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    # Serve from the SSD directory
    return send_from_directory(str(SAVE_DIR), filename, as_attachment=False)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002, debug=True)
