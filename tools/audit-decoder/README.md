# audit-decoder

Local review workbench for comparing decoded Markdown against source PDFs.

Run from the repository root:

```bash
python3 tools/audit-decoder/server.py
```

Then open the printed local URL.

The tool reads `decoded-corpus/manifest.jsonl` and each
`decoded-corpus/by-doc/<doc-id>/manifest.json`. Review state is kept inside
`tools/audit-decoder/.state/`, which is ignored by git.

The Markdown pane defaults to raw text. Rendered preview uses browser-loaded
`markdown-it` and KaTeX CDN assets when available; raw text remains the audit
source of truth.
