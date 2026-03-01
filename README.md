# Patra Darpan

Patra Darpan (Mirror of Documents) is a platform for indexing, classifying, and serving scholarly collections, research papers, and archival documents curated or referenced by the Centre for Ancient History and Culture (CAHC).

## Project Structure

This project has been refactored (Jan 2026) into the following components:

- **`pipeline/`**: Data ingestion and processing scripts.
  - `01-scrape.py`: Scrapes metadata from INSA portal.
  - `02-patch.py`: Fixes metadata errors.
  - `03-classify.py`: Uses Gemini LLM to classify new papers.
  - `04-compare.py`: Compares classification with legacy p85 search.
  - `05-import-cahcblr.py`: Imports non-IJHS metadata from Prof. R.N. Iyengar's collection (`p60`).
  - `bootstrap-ingest.py`: Hardened end-to-end ingestion and deduplication utility.
- **`web/`**: The web application (Netlify).
  - Contains `index.html`, `assets/`, and `netlify/` functions.
- **`corpus/`**: Primary Metadata Store (Tracked in Git).
  - `index.tsv`: The unified master index (Source of Truth for the web app).
  - `ijhs.tsv`: Raw metadata from INSA.
  - `ijhs-classified.tsv`: Machine-classified metadata with subject/category.
- **`.cache/`**: Transient data and intermediate artifacts (Git ignored).
  - Contains `.pkl` caches, `~.tsv` checkpoint files, and `ijhs-classified.md` reports.
- **`ops/`**: Operational utilities.
  - `sync_gcs.py`: Syncs local assets to Google Cloud Storage.
  - `migrate_index.py`: Builds the final index from individual metadata sources.
  - `generate_juni_embeds.py`: Generates the search snippets and sandbox for the JUNI website.

## Setup

Patra Darpan uses `uv` for lightning-fast, reproducible dependency management.

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Run `uv sync` from the project root to build the `.venv`.
3. Commands in this repository use `uv run <script>` to automatically execute within the isolated environment.

## External Dependencies

Patra Darpan is designed as a **Companion Engine** to an external asset repository, but it is architecturally **self-contained** regarding its metadata and internal PDF storage.

1. **Google Cloud Storage (GCS) Credentials**:
   - **Why**: Required by `ops/sync_gcs.py` to mirror the local PDFs to the private GCS bucket for production archiving.
   - **What it does**: Uses your local ADC (Application Default Credentials) via `gcloud`.
2. **Sibling Asset Repository (`cahcblr.github.io`) / Legacy JUNI**:
   - **Why**: Used strictly as an import source for non-IJHS metadata (via `05-import-cahcblr.py`), or as a deployment target for `p85`/`p60` embeds. The `cahc_authored_registry.txt` inside Patra Darpan removes any dependency on this repo for defining core authorship.
3. **Chrome Browser & Selenium**:
   - **Why**: The INSA portal requires JavaScript execution for navigation. `pipeline/01-scrape.py` uses Selenium to automate Chrome for scraping metadata.

## Data Flow Architecture

### 1. High-Level View

```mermaid
graph LR
    subgraph INSA_Ext ["INSA Portal"]
        INSA["insa.nic.in"]
    end

    subgraph Sibling_Ext ["cahcblr.github.io"]
        Sibling[("Sibling Repo<br>+ Live Site")]
    end

    subgraph PatraDarpan ["Patra Darpan"]
        Pipeline["Data Pipeline"]
        Meta[("Metadata Store<br>(corpus/)")]
        Cache[("Intermediate Cache<br>(.cache/)")]
        DarpanUI(["Darpan UI<br>(Netlify)"])
    end

    subgraph Cloud_Arch ["Cloud"]
        GCS[("GCS Archive")]
    end

    INSA         -->|"Metadata & PDFs"| Pipeline
    Sibling      -->|"Legacy P60 metadata"| Pipeline
    Pipeline    <-->|"Read / Write Clear"| Meta
    Pipeline    <-->|"Cache Partial"| Cache
    Meta         -->|"Generates data.js"| DarpanUI
    Meta         -->|"Sync via ops"| GCS

    DarpanUI -.->|"Production Read<br>(cahc.ju.ac.in)"| Sibling
    DarpanUI -.->|"Production Archive<br>(signed URL)"| GCS
    DarpanUI -.->|"Local Dev Read<br>(local symlink)"| Meta

    style INSA_Ext    fill:#fce4ec,stroke:#e91e63
    style Sibling_Ext fill:#e8f5e9,stroke:#66bb6a
    style PatraDarpan fill:#fff3e0,stroke:#ffa726
    style Cloud_Arch  fill:#e3f2fd,stroke:#29b6f6
```

### 2. Detailed View

_Each color zone is a zoom-in of the corresponding box in the High-Level View above. Every node maps to a real file or script._

```mermaid
graph TD
    subgraph INSA_Ext ["INSA Portal"]
        INSA["insa.nic.in<br>(HTML + PDFs)"]
    end

    subgraph Sibling_Ext ["cahcblr.github.io"]
        P60["p60_papers.markdown"]
        ClassMD["ijhs-classified.md<br>(manual copy target)"]
        JUSite(("cahc.ju.ac.in<br>(Live Site)"))
    end

    subgraph PatraDarpan ["Patra Darpan"]
        S1["01-scrape.py<br>(Selenium)"]
        S5["05-import-cahcblr.py"]
        S2["02-patch.py"]
        S3["03-classify.py<br>(Gemini LLM)"]
        Build["build_data.py"]
        Sync["sync_gcs.py"]
        PD_PDFs["corpus/ijhs/<br>(Potentials)"]
        TSV[("ijhs.tsv")]
        CTSV[("ijhs-classified.tsv")]
        Index[("index.tsv<br>(Final)")]
        Registry["cahc_authored_registry.txt"]
        CacheFiles[(".cache/*.pkl<br>~.tsv")]
        ClassMD_out["ijhs-classified.md<br>(in .cache/)"]
        DataJS["data.js"]
        DarpanUI(["Darpan UI<br>(Netlify SPA)"])
        NetFn["Netlify Auth Fn"]
    end

    subgraph Cloud_Arch ["Cloud"]
        GCS[("Private GCS Bucket")]
    end

    %% Ingestion – INSA
    INSA      -->|"Scrape HTML"| S1
    S1        -->|"Download PDFs"| PD_PDFs
    S1        -->|"Write metadata"| TSV

    %% Ingestion – Sibling
    P60       -->|"Parse"| S5
    S5        -->|"Merge new entries<br>(URL-deduped)"| TSV

    %% Processing
    Registry  -->|"Read tags"| S2
    TSV       -->|"Read"| S2
    S2        -->|"Patch in-place"| TSV
    TSV       -->|"Read"| S3
    S3        -->|"Write Result"| CTSV
    S3       <-->|"Cache"| CacheFiles
    S3        -->|"Generate Report"| ClassMD_out

    %% Controlled enrichment loop
    ClassMD_out -.->|"Manual copy/append"| ClassMD

    %% Ops
    CTSV      -->|"Read"| Build
    Build     -->|"Generate"| DataJS
    DataJS    -->|"Loaded by"| DarpanUI
    PD_PDFs   -->|"Scan"| Sync
    Sync      -->|"Upload missing"| GCS

    %% Runtime serving (dotted)
    DarpanUI  -.->|"Production Read (juUrl)"| JUSite
    DarpanUI  -.->|"Production Archive"| NetFn
    NetFn     -.->|"Signed URL"| GCS
    DarpanUI  -.->|"Local Dev Read<br>(via symlink)"| PD_PDFs

    style INSA_Ext    fill:#fce4ec,stroke:#e91e63
    style Sibling_Ext fill:#e8f5e9,stroke:#66bb6a
    style PatraDarpan fill:#fff3e0,stroke:#ffa726
    style Cloud_Arch  fill:#e3f2fd,stroke:#29b6f6
```

> [!NOTE]
> **On the apparent data cycle between `ijhs-classified.md` and `p85_search.markdown`**: After `03-classify.py` generates `ijhs-classified.md`, it is manually appended to `p85_search.markdown` in the sibling repo. One might expect this to cause `05-import-cahcblr.py` to re-import those same papers on its next run, causing an ever-growing metadata store. This does not happen. The import script checks every candidate URL against the existing `ijhs.tsv` and skips any paper already present. The only data that flows back through `p85` are **JU mirror URLs** (`juUrl`) for papers discovered there — an intentional enrichment step, not a re-import.

### 3. Runtime Sequence

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant Pipe as Pipeline Scripts
    participant INSA as INSA Portal
    participant Meta as corpus/ (Metadata/PDFs)
    participant SibRepo as cahcblr.github.io (Repo)
    participant Build as build_data.py
    participant DarpanUI as Darpan UI
    participant NetFn as Netlify Auth Fn
    participant GCS as GCS Archive
    participant JUSite as cahc.ju.ac.in (Live)
    participant User as User

    Note over Dev, Meta: Phase 1 — Ingestion
    Dev      ->>  Pipe:     Run 01-scrape / 05-import
    Pipe     ->>  INSA:     Fetch HTML & PDFs
    INSA     -->> Pipe:     HTML + PDF bytes
    Pipe     ->>  Meta:     Download PDFs to corpus/ijhs/
    Pipe     ->>  Meta:     Write ijhs.tsv
    Pipe     ->>  SibRepo:  Read p60_papers.markdown (Legacy)
    Pipe     ->>  Meta:     Merge legacy entries (URL-deduped)

    Note over Dev, Meta: Phase 2 — Processing
    Dev      ->>  Pipe:     Run 02-patch / 03-classify
    Pipe     <<->> Meta:    Read cahc_authored_registry.txt
    Pipe     <<->> Meta:    Patch ijhs.tsv → Classify → ijhs-classified.tsv
    Pipe     ->>  SibRepo:  Write ijhs-classified.md (manual copy target)

    Note over Dev, GCS: Phase 3 — Build & Sync
    Dev      ->>  Build:    Run build_data.py
    Build    ->>  Meta:     Read index.tsv
    Build    -->> DarpanUI: Write data.js
    Dev      ->>  Pipe:     Run sync_gcs.py
    Pipe     ->>  Meta:     Scan local corpus/ PDFs
    Pipe     ->>  GCS:      Upload missing PDFs
    Dev      ->>  DarpanUI: netlify deploy --prod

    Note over User, JUSite: Phase 4 — Serving
    User     ->>  DarpanUI: Click "Read"
    alt Production Mode (JU Mirror)
        DarpanUI ->> JUSite: Redirect via juUrl
        JUSite -->> User:   PDF served
    else Production Archive (GCS)
        DarpanUI ->> NetFn:  Request signed URL
        NetFn    ->> GCS:    Get signed URL
        GCS     -->> NetFn:  URL (15min validity)
        NetFn   -->> User:   Redirect to GCS PDF
    else Local Dev Mode
        DarpanUI ->> Meta: Read via local symlink (assets/pdfs/)
        Meta -->> User:    PDF served directly
    end
```

## Usage

### 1. Data Pipeline

The pipeline scripts should be run in sequence to ensure data integrity:

```bash
uv run pipeline/01-scrape.py   # Scrape new metadata
uv run pipeline/05-import-cahcblr.py # Import non-IJHS metadata
uv run pipeline/02-patch.py    # Fix known metadata errors
uv run pipeline/03-classify.py # Classify new papers
```

### 2. Operations

To regenerate the web application data:

```bash
uv run ops/build_data.py
```

To sync PDFs to GCS (uses local ADC/gcloud credentials):

```bash
uv run ops/sync_gcs.py       # Summarize and ask for confirmation
uv run ops/sync_gcs.py -y    # Bypass confirmation (non-interactive)
```

### 3. Diagnostics & Maintenance

Use these tools to maintain the health of the local metadata store:

```bash
uv run ops/analyze_tsv.py   # Find potential duplicates/anomalies
uv run ops/dedupe_tsv.py    # Surgically remove duplicates from corpus
```

### 4. Web Development & Deployment

The Netlify CLI usage differs slightly depending on your objective:

- **Local Development**: Run `dev` from the `web/` directory for a direct local preview.
  ```bash
  cd web
  netlify dev
  ```
- **Local Mode Toggle**: When running `netlify dev`, look for the **Simulation Mode** badge in the header. Click it to toggle between:
  - **Simulation Mode**: Uses INSA for "Read" and GCS (Cloud) for "Archive".
  - **Local Mode**: Uses your local PDF files for "Read" and INSA for "Archive".
- **Production Deployment**: Run `deploy` from the **project root**.
  ```bash
  netlify deploy --prod
  ```

## Content Maintenance Guide

Patra Darpan is a living archive. Follow these workflows to keep the collection current:

### 1. New IJHS Volume Released

When a new volume of the _Indian Journal of History of Science_ is published:

1.  **Scrape**: Run `uv run pipeline/01-scrape.py`. This downloads new PDFs to `corpus/ijhs/` and updates `corpus/ijhs.tsv`.
2.  **Authorship (if applicable)**: If the new volume contains CAHC-authored papers, append the new Paper ID (e.g., `Vol60_1_5.pdf`) to `corpus/cahc_authored_registry.txt`.
3.  **Patch**: Run `uv run pipeline/02-patch.py` to seamlessly apply the registry tags and automated metadata fixes.
4.  **Classify**: Run `uv run pipeline/03-classify.py` to use Gemini for subject/category assignment.
5.  **Merge**: Run `uv run ops/migrate_index.py` to update the master `corpus/index.tsv`.
6.  **Deploy**: Run `uv run ops/build_data.py` followed by `netlify deploy --prod`.

### 2. New CAHC-Authored Paper (PDF)

For papers where you have a local PDF file (AJPEM, ALT, etc.):

1.  **Placement**: Copy the PDF to `corpus/other/`.
2.  **Ingest**: Run `uv run pipeline/bootstrap-ingest.py`. It extracts metadata from the filename and appends a row to `corpus/index.tsv`.
3.  **Cloud Sync**: Run `uv run ops/sync_gcs.py` to upload the new asset to the GCS archive.
4.  **Deploy**: Run `uv run ops/build_data.py` and deploy.

### 3. New External Post/Link

For articles that are only available as external web links (e.g., JSTOR, News):

1.  **Manual Entry**: Manually add a row to `corpus/index.tsv` with the `url` and metadata. Set `source="ext"` and `cahc_authored="true"`.
2.  **Deploy**: Run `uv run ops/build_data.py` and deploy.
