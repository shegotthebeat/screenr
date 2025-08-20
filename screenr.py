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
import os
import traceback
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template_string, request, url_for, send_from_directory, abort
from werkzeug.utils import secure_filename
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

app = Flask(__name__)

# -------- Storage --------
UPLOAD_DIRECTORY = Path("/mnt/storage/uploads")
UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)

# -------- Config toggles (env-driven for quick tests) --------
HEADLESS = os.getenv("HEADLESS", "1") != "0"      # set HEADLESS=0 to watch locally
NAV_TIMEOUT_MS = int(os.getenv("NAV_TIMEOUT_MS", "60000"))  # 60s default

# -------- Basic template --------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Webpage Archiver</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div class="container">
    <div class="sidebar"><h1>Web Archiver</h1></div>
    <div class="content">
      <h2 class="page-title">Archive a Webpage</h2>
      <form action="/archive" method="post">
        <label for="url">URL</label>
        <input type="text" id="url" name="url" placeholder="https://example.com" required>
        <button type="submit" class="btn">Archive</button>
      </form>

      {% if message %}
      <div class="status-message status-{{ message_type }}">{{ message }}</div>
      {% endif %}

      {% if image_url %}
      <div class="preview-section">
        <h3 class="preview-title">Archived Image</h3>
        <img src="{{ image_url }}" alt="Archived Webpage" style="width:100%;height:auto;border:1px solid #000;">
      </div>
      {% endif %}
    </div>
  </div>
</body>
</html>
"""

UA_DESKTOP = (
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
  "AppleWebKit/537.36 (KHTML, like Gecko) "
  "Chrome/121.0.0.0 Safari/537.36"
)

EXTRA_HEADERS = {
  "Sec-CH-UA": '"Chromium";v="121", "Not(A:Brand";v="24", "Google Chrome";v="121"',
  "Sec-CH-UA-Platform": '"Windows"',
  "Sec-CH-UA-Mobile": "?0",
  "Upgrade-Insecure-Requests": "1",
  "Accept-Language": "en-US,en;q=0.9",
}

INIT_STEALTH_SCRIPT = r"""
// minimal evasions
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'language', { get: () => 'en-US' });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
// Permissions.query noisy probes
const originalQuery = navigator.permissions && navigator.permissions.query;
if (originalQuery) {
  navigator.permissions.query = (parameters) => (
    parameters && parameters.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(parameters)
  );
}
"""

async def _try_nav_and_shot(page, url, out_path, load_state):
  # One attempt with a given load state
  await page.goto(url, wait_until=load_state, timeout=NAV_TIMEOUT_MS)
  # Give dynamic pages a moment to settle
  await page.wait_for_timeout(1500)

  # If page is very tall and full_page shots are flaky, we can scroll to bottom
  try:
    height = await page.evaluate("document.body.scrollHeight")
    if height and height > 3000:
      await page.evaluate("""
        new Promise(r => {
          let y = 0;
          const step = 1200;
          const timer = setInterval(() => {
            window.scrollTo(0, y += step);
            if (y >= document.body.scrollHeight) { clearInterval(timer); r(); }
          }, 100);
        });
      """)
      await page.wait_for_timeout(500)
  except Exception:
    pass

  await page.screenshot(path=str(out_path), full_page=True)
  return True

async def save_webpage_as_image(url: str, output_path: str):
  """
  Robust screenshot with:
    - Chromium then Firefox fallback
    - networkidle -> load -> domcontentloaded retries
    - desktop UA, headers, timezone, ignore_https_errors
    - stealth-ish init script
    - failure artifacts (.fail.png and .fail.html)
  """
  out = Path(output_path)
  fail_png = out.with_suffix(".fail.png")
  fail_html = out.with_suffix(".fail.html")
  last_err = None

  async with async_playwright() as p:
    for engine_name in ("chromium", "firefox"):
      browser_type = getattr(p, engine_name)
      try:
        browser = await browser_type.launch(headless=HEADLESS)
        context = await browser.new_context(
          viewport={"width": 1920, "height": 1080},
          user_agent=UA_DESKTOP,
          extra_http_headers=EXTRA_HEADERS,
          ignore_https_errors=True,
          java_script_enabled=True,
          timezone_id="America/New_York",
        )
        context.set_default_navigation_timeout(NAV_TIMEOUT_MS)
        context.set_default_timeout(NAV_TIMEOUT_MS)

        page = await context.new_page()
        await page.add_init_script(INIT_STEALTH_SCRIPT)

        # Console/network logging (visible in server logs)
        page.on("console", lambda m: print(f"[{engine_name} console] {m.type()}: {m.text()}"))
        page.on("pageerror", lambda e: print(f"[{engine_name} pageerror] {e}"))

        # Try multiple load states
        for load_state in ("networkidle", "load", "domcontentloaded"):
          try:
            print(f"[INFO] {engine_name} goto(wait_until='{load_state}') {url}")
            await _try_nav_and_shot(page, url, out, load_state)
            await browser.close()
            return True
          except Exception as e:
            last_err = e
            print(f"[WARN] {engine_name} failed on '{load_state}': {e!r}")
            # capture what we can
            try:
              await page.screenshot(path=str(fail_png), full_page=False)
            except Exception as se:
              print(f"[WARN] could not save {fail_png.name}: {se!r}")
            try:
              html = await page.content()
              fail_html.write_text(html, encoding="utf-8")
            except Exception as he:
              print(f"[WARN] could not save {fail_html.name}: {he!r}")

        await browser.close()
      except Exception as e:
        last_err = e
        print(f"[WARN] could not start/use {engine_name}: {e!r}")

  print("[ERROR] All attempts failed.")
  if last_err:
    traceback.print_exception(type(last_err), last_err, last_err.__traceback__)
  return False

# -------- Routes --------
@app.route("/", methods=["GET"])
def home():
  return render_template_string(HTML_TEMPLATE, message=None, image_url=None)

@app.route("/archive", methods=["POST"])
async def archive():
  url = request.form.get("url", "").strip()
  if not (url.startswith("http://") or url.startswith("https://")):
    return render_template_string(HTML_TEMPLATE, message="Provide a valid http(s) URL.", message_type="error")

  filename = secure_filename(f"screenr_{datetime.now():%Y%m%d%H%M%S}.png")
  output_path = UPLOAD_DIRECTORY / filename

  print(f"[INFO] Target file: {output_path}")
  ok = await save_webpage_as_image(url, str(output_path))

  if ok and output_path.exists():
    image_url = url_for("serve_upload", filename=filename)
    print(f"[INFO] Saved OK: {output_path}")
    return render_template_string(HTML_TEMPLATE, message=f"Archived {url}.", message_type="success", image_url=image_url)

  fail_png = output_path.with_suffix(".fail.png")
  fail_html = output_path.with_suffix(".fail.html")
  hint = []
  if fail_png.exists(): hint.append(f"fail PNG at {fail_png}")
  if fail_html.exists(): hint.append(f"fail HTML at {fail_html}")
  suffix = f" See: {', '.join(hint)}" if hint else ""
  return render_template_string(HTML_TEMPLATE, message=f"Failed to archive {url}.{suffix}", message_type="error")

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
  try:
    return send_from_directory(UPLOAD_DIRECTORY, filename)
  except FileNotFoundError:
    abort(404)

@app.route("/permcheck")
def permcheck():
  try:
    tf = UPLOAD_DIRECTORY / ".flask_perm_ok"
    with open(tf, "w") as f: f.write("ok")
    tf.unlink(missing_ok=True)
    return "WRITE_OK", 200
  except Exception as e:
    return f"WRITE_FAIL: {e!r}", 500

if __name__ == "__main__":
  app.run(host="0.0.0.0", port=8002, debug=True)
