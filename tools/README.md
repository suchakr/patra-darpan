# Tools

Local workbenches for humans and agents. Tools are not canonical corpus
pipeline entrypoints and should stay decoupled from `scripts/`, `ops/`, and the
public `web/` app unless a workflow is deliberately promoted.

Use this directory for focused review, inspection, and operator-assistance UI
that may read generated artifacts or local assets. Keep mutable local state
inside the relevant tool directory and ignore it in git.

## audit-decoder

Side-by-side review workbench for decoded corpus output:

```bash
python3 tools/audit-decoder/server.py
```

It reads `decoded-corpus/manifest.jsonl`, opens each source PDF beside
`document.md`, provides raw/rendered Markdown views, and records review notes
under `tools/audit-decoder/.state/`. Use its export action to write collected
notes as Markdown under `reports/`.

See `tools/audit-decoder/README.md` for tool-specific details.
