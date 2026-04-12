# Patra Darpan (Mirror)

A high-performance, single-page application for browsing the Indian Journal of History of Science (IJHS) archives.

> **Darpan** (Sanskrit) means "Mirror". This project mirrors the INSA archives with a modern, reflection-like instant interface.

## 🚀 Features

- **Instant Search**: Fuzzy search across 2000+ papers.
- **Hybrid Link Technology**:
  - **Local Serve Mode (`http.server`)**: Reads PDFs directly from
    `assets/pdfs`, which is a symlink to the shared local PDF asset root.
  - **Netlify Dev / Deploy Mode**: Uses the same web payload, but changes link
    preference:
    - `Read` prefers `ju_url` when available, otherwise the primary `url`
    - archive access uses the Netlify `authorize-pdf` function and `gcs_key`
      to open a signed GCS URL
    - URL-only entries open their publisher URL directly
  - **Shared corpus model**:
    - all PDF records may have a local shared copy
    - all PDF records are expected to have a GCS archive copy
    - some curated PDFs also have a CAHC/JU mirror URL
  - **Access chips**: Cards show compact access icons for the default target
    and any alternates. `Local` is shown only in local/testing mode; deployed
    cards do not expose storage or mirror labels to end users.
- **Glassmorphism UI**: Premium aesthetic with dark mode by default.

## 🛠️ Local Setup

1. **Prerequisites**:
   Ensure the shared PDF asset root exists in the sibling `patra-darpan`
   checkout with these subdirectories:
   - `corpus/ijhs`
   - `corpus/other`

   In this repository layout, this repository's `corpus/` directory contains
   metadata root inputs only. Local PDFs are served from the shared asset root
   in the sibling `patra-darpan` checkout.

2. **Generate Data**:
   Run the Patra Darpan export script to project `exports/index.tsv` into
   `assets/js/data.js` and create the PDF symlink.

   Run this command from the repository root:

   ```bash
   uv run python ops/export_patra_darpan_data_js.py
   ```

   This does three things:
   - reads `exports/index.tsv`
   - writes `web/assets/js/data.js`
   - rewrites `web/assets/pdfs` to point at the shared PDF asset root in the
     sibling `patra-darpan` checkout

   By default, the exporter tries these shared asset roots in order:
   - `corpus/` in the current checkout, if it contains `ijhs/` and `other/`
   - `../patra-darpan/corpus` in a sibling checkout

   If your local layout differs, set `SHARED_ASSET_ROOT` when running the
   exporter, for example:

   ```bash
   SHARED_ASSET_ROOT=/path/to/shared/corpus uv run python ops/export_patra_darpan_data_js.py
   ```

3. **Run Locally**:
   Change into `web/` and serve the app locally:

   ```bash
   cd web
   uv run python -m http.server 8000
   ```
   Then open:
   - `http://127.0.0.1:8000`

   The app will detect that it is running locally and serve PDFs from
   `assets/pdfs`, which resolves into the shared asset root.

   In this mode:
   - PDF cards prefer the local shared PDF copy
   - URL-only cards open the original URL directly
   - the Netlify archive function is not involved, so the GCS archive path is
     not used from plain `http.server` local mode

## ☁️ Deployment Workflow

We use **Netlify CLI** for a manual deployment strategy because PDFs are not
bundled with the deployed site. They remain on their original source sites
where possible, and some are mirrored on a peer site and/or in GCS to improve
availability and work around source-site outages.

### 1. Test Locally (`netlify dev`)

Simulates the Netlify environment locally.

Run from `web/`:

```bash
cd web
npm install
netlify dev
```

- access at `http://localhost:8888`
- App label should show the **Simulation Mode** badge by default.

In this mode:
- PDF cards prefer `ju_url` when available, otherwise `url`
- archive access goes through `/.netlify/functions/authorize-pdf?...`
- URL-only cards open the original URL directly

Requirements for archive access to work in `netlify dev`:
- install the `web/` Node dependencies with `npm install`
- provide `GCS_CREDENTIALS` locally for the Netlify function, for example by
  exporting it in the shell before starting `netlify dev` or by using your
  local Netlify environment setup

### 2. Partial/Draft Deploy (`deploy`)

Push a private draft to a unique URL. Use this to share with the team for review before going live.

Run from `web/`:

```bash
cd web
netlify deploy
```

- **Output**: A "Website Draft URL" (e.g., `https://draft-id--patra-darpan.netlify.app`).
- **Note**: The `assets/pdfs` folder is **ignored** (via `.netlifyignore`) to keep uploads fast and small (< 1MB).
- **Hybrid Mode**:
  - `Read` prefers `ju_url` when available, otherwise `url`
  - archive access uses GCS via the Netlify function
  - URL-only entries open the original URL directly

### 3. Production Deploy (`deploy --prod`)

Push the changes to the main live URL.

Run from `web/`:

```bash
cd web
netlify deploy --prod
```

- Updates the main site immediately.

Runtime link behavior matches the draft deploy:
- `Read` prefers `ju_url` when available, otherwise `url`
- archive access uses GCS via the Netlify function
- URL-only entries open the original URL directly

## ⚙️ Configuration

- **`netlify.toml`**: Configures build settings and headers.
- **`.netlifyignore`**: Ensures `assets/pdfs` is NEVER uploaded.

## 🏗️ Architecture

- **`web/index.html`**: The single page shell. Detects hostname to switch modes.
- **`exports/index.tsv`**: Compatibility projection generated from canonical
  corpus state.
- **`assets/js/data.js`**: Patra Darpan web payload generated from
  `exports/index.tsv` by `ops/export_patra_darpan_data_js.py`.
- **`assets/pdfs`**: A symbolic link to the shared PDF asset root in the
  sibling `patra-darpan` checkout. Ignored by git and Netlify.
- **`url` / `ju_url` / `gcs_key`**: The web payload carries all three link
  targets. The UI chooses among them depending on local vs Netlify mode.

## 📝 License

Code in this repository is licensed under the MIT License. PDF ownership and
access rights vary by source and remain with their respective publishers,
repositories, or mirror providers.
