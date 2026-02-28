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
- **`web/`**: The web application (Netlify).
  - Contains `index.html`, `assets/`, and `netlify/` functions.
- **`ops/`**: Operational and maintenance utilities.
  - `build_data.py`: Generates `data.js` for the web app.
  - `sync_pdfs.py`: Syncs local PDFs to private GCS bucket.
  - `analyze_tsv.py`: Diagnostic tool to identify duplicates and metadata anomalies.
  - `dedupe_tsv.py`: Surgical utility to clean duplicates from `.cache` files.
- **`.cache/`**: Local data store.
  - Contains `ijhs.tsv` (Source of Truth), `ijhs-classified.tsv`, and intermediate artifacts.

## External Dependencies

Patra Darpan is designed as a **Companion Engine** to an external asset repository. To function fully, it relies on the following external dependencies:

1. **Sibling Asset Repository (`cahcblr.github.io`)**:
   - **Why**: This project does not store PDF files directly to keep the repository lightweight. It relies on a sibling repository located at `~/projects/cahcblr.github.io`.
   - **What it does**: The scraper (`01-scrape.py`) downloads PDFs into `assets/ijhs_potentials` within this sibling repo. The web app uses a symlink to serve these PDFs locally.
2. **Google Cloud Storage (GCS) Credentials**:
   - **Why**: Required by `ops/sync_pdfs.py` to mirror the local PDFs to the private GCS bucket for production serving.
   - **What it does**: Uses your local ADC (Application Default Credentials) via `gcloud`.
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
        Meta[("Metadata Store<br>(.cache/)")]
        DarpanUI(["Darpan UI<br>(Netlify)"])
    end

    subgraph Cloud_Arch ["Cloud"]
        GCS[("GCS Archive")]
    end

    INSA         -->|"Metadata & PDFs"| Pipeline
    Sibling      -->|"P60 / P85 metadata"| Pipeline
    Pipeline     -->|"Downloads PDFs"| Sibling
    Pipeline    <-->|"Read / Write"| Meta
    Meta         -->|"Generates data.js"| DarpanUI
    Sibling      -->|"Sync via ops"| GCS

    DarpanUI -.->|"Production Read<br>(cahc.ju.ac.in)"| Sibling
    DarpanUI -.->|"Production Archive<br>(signed URL)"| GCS
    DarpanUI -.->|"Local Dev Read<br>(local symlink)"| Sibling

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
        P85["p85_search.markdown"]
        ClassMD["ijhs-classified.md<br>(manual copy target)"]
        Potentials["assets/ijhs_potentials/"]
        Cached["assets/cached_papers/rni/"]
        JUSite(("cahc.ju.ac.in<br>(Live Site)"))
    end

    subgraph PatraDarpan ["Patra Darpan"]
        S1["01-scrape.py<br>(Selenium)"]
        S5["05-import-cahcblr.py"]
        S2["02-patch.py"]
        S3["03-classify.py<br>(Gemini LLM)"]
        Build["build_data.py"]
        Sync["sync_pdfs.py"]
        TSV[("ijhs.tsv<br>(source of truth)")]
        CTSV[("ijhs-classified.tsv")]
        ClassMD_out["ijhs-classified.md"]
        DataJS["data.js"]
        DarpanUI(["Darpan UI<br>(Netlify SPA)"])
        NetFn["Netlify Auth Fn"]
    end

    subgraph Cloud_Arch ["Cloud"]
        GCS[("Private GCS Bucket")]
    end

    %% Ingestion – INSA
    INSA      -->|"Scrape HTML"| S1
    S1        -->|"Download PDFs"| Potentials
    S1        -->|"Write metadata"| TSV

    %% Ingestion – Sibling
    P60       -->|"Parse"| S5
    P85       -->|"Parse"| S5
    S5        -->|"Merge new entries<br>(URL-deduped)"| TSV
    S5        -->|"Enrich juUrl<br>(URL-deduped)"| TSV

    %% Processing
    TSV       -->|"Read"| S2
    S2        -->|"Patch in-place"| TSV
    TSV       -->|"Read"| S3
    S3        -->|"Classify"| CTSV
    S3        -->|"Generate"| ClassMD_out

    %% Controlled enrichment loop
    ClassMD_out -.->|"Manual copy/append"| ClassMD
    ClassMD     -.->|"Feeds JU URLs back via P85<br>(URL-deduped guard)"| P85

    %% Ops
    CTSV      -->|"Read"| Build
    Build     -->|"Generate"| DataJS
    DataJS    -->|"Loaded by"| DarpanUI
    Potentials -->|"Scan"| Sync
    Cached     -->|"Scan"| Sync
    Sync      -->|"Upload missing"| GCS

    %% Runtime serving (dotted)
    DarpanUI  -.->|"Production Read (juUrl)"| JUSite
    DarpanUI  -.->|"Production Archive"| NetFn
    NetFn     -.->|"Signed URL"| GCS
    DarpanUI  -.->|"Local Dev Read<br>(via symlink)"| Potentials

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
    participant SibRepo as cahcblr.github.io (Repo)
    participant Meta as .cache/ (Metadata)
    participant Build as build_data.py
    participant DarpanUI as Darpan UI
    participant NetFn as Netlify Auth Fn
    participant GCS as GCS Archive
    participant JUSite as cahc.ju.ac.in (Live)
    participant User as User

    Note over Dev, SibRepo: Phase 1 — Ingestion
    Dev      ->>  Pipe:     Run 01-scrape / 05-import
    Pipe     ->>  INSA:     Fetch HTML & PDFs
    INSA     -->> Pipe:     HTML + PDF bytes
    Pipe     ->>  SibRepo:  Download PDFs to assets/
    Pipe     ->>  Meta:     Write ijhs.tsv
    Pipe     ->>  SibRepo:  Read p60_papers.markdown, p85_search.markdown
    Pipe     ->>  Meta:     Merge entries (URL-deduped) + enrich juUrl

    Note over Dev, Meta: Phase 2 — Processing
    Dev      ->>  Pipe:     Run 02-patch / 03-classify
    Pipe     <<->> Meta:    Read & update ijhs.tsv → ijhs-classified.tsv
    Pipe     ->>  SibRepo:  Write ijhs-classified.md (manual copy target)

    Note over Dev, GCS: Phase 3 — Build & Sync
    Dev      ->>  Build:    Run build_data.py
    Build    ->>  Meta:     Read ijhs-classified.tsv
    Build    -->> DarpanUI: Write data.js
    Dev      ->>  Pipe:     Run sync_pdfs.py
    Pipe     ->>  SibRepo:  Scan local assets/
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
        DarpanUI ->> SibRepo: Read via local symlink (assets/pdfs/)
        SibRepo -->> User:    PDF served directly
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
uv run ops/sync_pdfs.py       # Summarize and ask for confirmation
uv run ops/sync_pdfs.py -y    # Bypass confirmation (non-interactive)
```

### 3. Diagnostics & Maintenance

Use these tools to maintain the health of the local metadata store:

```bash
uv run ops/analyze_tsv.py   # Find potential duplicates/anomalies
uv run ops/dedupe_tsv.py    # Surgically remove duplicates from .cache
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

> [!NOTE]
> The root `netlify.toml` serves as the primary configuration for the entire pipeline, while the `web/` directory is treated as a specialized context for local serving.
