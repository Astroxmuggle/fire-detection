"""Build a self-contained ``download.html`` that hands the deck to the browser.

The PowerPoint file is embedded as base64, so the page works from a file:// URL
or from any static server without a second request. Regenerate it after running
``generate_deck.py``.

    python create_download_page.py
"""

from __future__ import annotations

import base64
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DECK_PATH = PROJECT_ROOT / "FireWatch_AI_Presentation_Manai_Jesser.pptx"
OUTPUT_PATH = PROJECT_ROOT / "download.html"
DOWNLOAD_NAME = "FireWatch_AI_Presentation_Manai_Jesser.pptx"

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Download FireWatch AI Presentation</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: #0f172a; color: #f8fafc; display: flex; align-items: center;
      justify-content: center; min-height: 100vh; margin: 0; padding: 1.5rem; box-sizing: border-box;
    }
    .card {
      background: #1e293b; border: 1px solid #334155; padding: 3rem 2.5rem;
      border-radius: 20px; text-align: center; max-width: 520px; width: 100%;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
    }
    .icon { font-size: 3.5rem; margin-bottom: 1rem; }
    h1 { font-size: 1.75rem; font-weight: 800; margin: 0 0 0.5rem; color: #fff; }
    .subtitle {
      color: #f97316; font-weight: 700; font-size: 0.95rem; text-transform: uppercase;
      letter-spacing: 0.05em; margin-bottom: 1.5rem;
    }
    .desc { color: #94a3b8; font-size: 0.95rem; line-height: 1.5; margin-bottom: 2rem; }
    .btn {
      background: #f97316; color: #fff; border: none; padding: 1rem 2rem; font-size: 1.1rem;
      font-weight: 700; border-radius: 12px; cursor: pointer; display: inline-flex;
      align-items: center; gap: 0.5rem; box-shadow: 0 10px 15px -3px rgba(249, 115, 22, 0.4);
      transition: all 0.2s;
    }
    .btn:hover { background: #ea580c; transform: translateY(-2px); }
    .status { margin-top: 1.5rem; font-size: 0.85rem; color: #22c55e; font-weight: 600; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">📊</div>
    <h1>FireWatch AI Presentation</h1>
    <div class="subtitle">Author: Manai Jesser</div>
    <p class="desc">
      The 12-slide defence deck with embedded training curves, validation images and speaker notes.
    </p>
    <button class="btn" type="button" onclick="triggerDownload()">📥 Download Presentation (.pptx)</button>
    <div class="status" id="statusMsg">Your download will trigger automatically…</div>
  </div>

  <script>
    const B64_DATA = "__BASE64__";
    const FILE_NAME = "__FILE_NAME__";

    function triggerDownload() {
      const binary = atob(B64_DATA);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
      }
      const blob = new Blob([bytes], {
        type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = FILE_NAME;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      document.getElementById("statusMsg").textContent = "✓ Download started — check your browser downloads.";
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    }

    window.addEventListener("DOMContentLoaded", () => setTimeout(triggerDownload, 500));
  </script>
</body>
</html>
"""


def build_download_page(deck_path: Path = DECK_PATH, output_path: Path = OUTPUT_PATH) -> Path:
    if not deck_path.is_file():
        raise FileNotFoundError(f"Deck not found: {deck_path} — run generate_deck.py first")

    encoded = base64.b64encode(deck_path.read_bytes()).decode("ascii")
    html = (
        PAGE_TEMPLATE
        .replace("__BASE64__", encoded)
        .replace("__FILE_NAME__", DOWNLOAD_NAME)
    )
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> int:
    output = build_download_page()
    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"Wrote {output} ({size_mb:.2f} MB, deck embedded as base64)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
