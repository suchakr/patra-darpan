#!/usr/bin/env python3
"""
generate_juni_embeds.py

Automates the generation of Jekyll-compatible HTML snippets for the JUNI repository
and a local sandbox page for Patra Darpan.

Generates:
  1. darpan_p85.html (Full search) -> JUNI/_includes/
  2. darpan_p60.html (RNI papers) -> JUNI/_includes/
  3. iframe-sandbox.html -> patra-darpan/web/

Usage:
    python ops/generate_juni_embeds.py [--prod] [--local]
"""

import os
import sys
from pathlib import Path

# --- Configuration ---
LOCAL_URL = "http://localhost:8888"
PROD_URL = "https://patra-darpan.netlify.app"

JUNI_DIR = Path.home() / "projects/cahcblr.github.io"
JUNI_INCLUDES = JUNI_DIR / "_includes"
SANDBOX_PATH = Path(__file__).parent.parent / "web/iframe-sandbox.html"

# --- Iframe Template ---
IFRAME_TEMPLATE = """
<div class="darpan-embed-wrapper" style="width: 100%; margin: 2rem 0; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.15); border: 1px solid rgba(0,0,0,0.05); background: #f8fafc;">
    <iframe 
        src="{url}" 
        style="width: 100%; height: 850px; border: none; display: block;"
        id="{id}"
        loading="lazy"
        title="{title}">
    </iframe>
</div>
"""

SANDBOX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Darpan Iframe Sandbox</title>
    <style>
        body {{ font-family: sans-serif; padding: 40px; background: #e2e8f0; color: #1e293b; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ text-align: center; margin-bottom: 40px; }}
        .section {{ margin-bottom: 60px; }}
        h2 {{ border-bottom: 2px solid #cbd5e1; padding-bottom: 10px; margin-bottom: 20px; }}
        .mock-juni-header {{ background: #1e293b; color: white; padding: 20px; border-radius: 8px 8px 0 0; font-weight: bold; }}
        .mock-juni-footer {{ background: #f1f5f9; padding: 20px; border-radius: 0 0 8px 8px; text-align: center; font-size: 0.8rem; color: #64748b; border: 1px solid #e2e8f0; border-top: none; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Patra Darpan — Pre-flight Sandbox</h1>
        
        <div class="section">
            <h2>View 1: p85 (Full Search)</h2>
            <div class="mock-juni-header">JAI UNIVERSITY — ARCHIVE SEARCH (Mock)</div>
            {p85_content}
            <div class="mock-juni-footer">© 2026 Centre for Ancient History and Culture</div>
        </div>

        <div class="section">
            <h2>View 2: p60 (RNI Papers)</h2>
            <div class="mock-juni-header">PROF. R N IYENGAR — PAPERS (Mock)</div>
            {p60_content}
            <div class="mock-juni-footer">© 2026 Centre for Ancient History and Culture</div>
        </div>
    </div>
</body>
</html>
"""

def generate(url_base):
    print(f"--- Generating Embeds (Base URL: {url_base}) ---")
    
    # Define Targets
    targets = {
        "p85": {
            "name": "darpan_p85.html",
            "url": f"{url_base}/?embed=1&theme=light",
            "id": "darpan-p85-frame",
            "title": "Patra Darpan Full Search"
        },
        "p60": {
            "name": "darpan_p60.html",
            "url": f"{url_base}/?embed=1&theme=light&search=Iyengar",
            "id": "darpan-p60-frame",
            "title": "Patra Darpan RNI Collection"
        }
    }

    # Generate Snippets
    p85_html = IFRAME_TEMPLATE.format(**targets["p85"])
    p60_html = IFRAME_TEMPLATE.format(**targets["p60"])

    # Write JUNI Snippets
    if JUNI_INCLUDES.exists():
        with open(JUNI_INCLUDES / targets["p85"]["name"], "w") as f:
            f.write(p85_html)
        with open(JUNI_INCLUDES / targets["p60"]["name"], "w") as f:
            f.write(p60_html)
        print(f"✅ Written {targets['p85']['name']} and {targets['p60']['name']} to {JUNI_INCLUDES}")
    else:
        print(f"⚠️ JUNI includes directory not found: {JUNI_INCLUDES}. Skipping export.")

    # Write Sandbox
    sandbox_content = SANDBOX_TEMPLATE.format(
        p85_content=p85_html,
        p60_content=p60_html
    )
    with open(SANDBOX_PATH, "w") as f:
        f.write(sandbox_content)
    print(f"✅ Written sandbox to {SANDBOX_PATH}")

if __name__ == "__main__":
    is_prod = "--prod" in sys.argv
    base = PROD_URL if is_prod else LOCAL_URL
    generate(base)
