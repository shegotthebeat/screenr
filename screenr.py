# requirements.txt
# Flask==3.0.3
# playwright==1.45.0

# -------------------------------------------------------------
# Webpage Archiver Web Application
#
# This script uses Flask to create a web server and Playwright
# to take a full-page screenshot of a user-submitted URL.
#
# The application has two main routes:
# - `/`: Serves the HTML form for URL submission.
# - `/archive`: Receives the URL, launches a headless browser,
#   and saves the screenshot. It then displays the result.
#
# To run this script:
# 1. Ensure you have Python installed.
# 2. Create a virtual environment and install the requirements:
#    pip install -r requirements.txt
# 3. Install the browser binaries for Playwright:
#    playwright install
# 4. Create a `static` directory in the same location as this script.
# 5. Place your `style.css` file inside the `static` directory.
# 6. Run the script:
#    python your_script_name.py
# 7. Access the application in your browser at http://127.0.0.1:8002
# -------------------------------------------------------------

import asyncio
from playwright.async_api import async_playwright
from flask import Flask, render_template_string, request, send_file
import os
from datetime import datetime

app = Flask(__name__)

async def save_webpage_as_image(url: str, output_path: str):
    """
    Launches a headless browser, navigates to a URL, and saves a full-page screenshot.

    Args:
        url (str): The URL of the webpage to capture.
        output_path (str): The filename and path to save the screenshot.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_viewport_size({"width": 1920, "height": 1080})
            await page.goto(url, wait_until="networkidle")
            await page.screenshot(path=output_path, full_page=True)
            await browser.close()
            return True
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

# HTML content for the main page, now linking to an external CSS file.
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

@app.route("/", methods=["GET"])
def home():
    """Renders the main page with the URL input form."""
    return render_template_string(HTML_TEMPLATE, message=None, image_url=None)

@app.route("/archive", methods=["POST"])
async def archive():
    """
    Handles the URL submission, triggers the screenshot process,
    and returns a success or error message.
    """
    url = request.form.get("url")
    if not url:
        return render_template_string(HTML_TEMPLATE, message="Please provide a valid URL.", message_type="error")

    # Generate a unique filename based on the current timestamp.
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"screenr_{timestamp}.png"
    output_path = os.path.join("/mnt/storage/uploads", filename)

    # Ensure the 'static' directory exists.
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    success = await save_webpage_as_image(url, output_path)

    if success:
        message = f"Successfully archived {url}."
        image_url = output_path
        return render_template_string(HTML_TEMPLATE, message=message, message_type="success", image_url=image_url)
    else:
        message = f"Failed to archive {url}. Please check the URL and try again."
        return render_template_string(HTML_TEMPLATE, message=message, message_type="error")

@app.route("/mnt/storage/uploads/<path:filename>")
def serve_static(filename):
    """Serves the static files (screenshots) from the 'static' directory."""
    return send_file(os.path.join("/mnt/storage/uploads", filename))

if __name__ == "__main__":
    # Note: Flask's built-in server is not for production.
    # For production, use a WSGI server like Gunicorn or Waitress.
    app.run(host="0.0.0.0", port=8002, debug=True)

