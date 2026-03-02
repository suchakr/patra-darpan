# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas",
# ]
# ///

import pandas as pd
import json
import os
import pathlib
import sys
# Paths
BASE_DIR = pathlib.Path(__file__).parent.parent # patra-darpan root
TSV_PATH = BASE_DIR / "corpus" / "index.tsv"
OUTPUT_JS_PATH = BASE_DIR / "web" / "assets" / "js" / "data.js"
SYMLINK_DIR = BASE_DIR / "web" / "assets" / "pdfs"

# Corpus directories — canonical local PDF home
CORPUS_ROOT = BASE_DIR / "corpus"
CORPUS_IJHS = CORPUS_ROOT / "ijhs"
CORPUS_OTHER = CORPUS_ROOT / "other"

def setup_symlink():
    """Creates a relative symlink web/assets/pdfs -> ../../corpus/"""
    if not CORPUS_ROOT.exists():
        print(f"Warning: Corpus root not found at {CORPUS_ROOT}")
        return

    target_link = SYMLINK_DIR
    relative_target = os.path.relpath(CORPUS_ROOT, target_link.parent)

    if target_link.exists() or target_link.is_symlink():
        target_link.unlink()

    try:
        target_link.symlink_to(relative_target)
        print(f"Symlink created: {target_link} -> {relative_target}")
    except Exception as e:
        print(f"Failed to create symlink: {e}")

def find_local_path(url_filename, gcs_key=""):
    """
    Tries to find the file in the corpus directories.
    Returns the path RELATIVE to the 'pdfs' symlink (which points to 'corpus/').
    Uses gcs_key to determine the right subdirectory.
    """
    if not isinstance(url_filename, str) and not gcs_key:
        return None

    # If we have a gcs_key, use it directly
    if gcs_key:
        # gcs_key is like 'ijhs/Vol01_1_1.pdf' or 'other/ajpem_2022.pdf'
        local_path = CORPUS_ROOT / gcs_key
        if local_path.exists():
            return f"assets/pdfs/{gcs_key}"

    # Fallback: extract filename from URL and search both dirs
    if isinstance(url_filename, str):
        filename = url_filename.split('/')[-1]
        if (CORPUS_IJHS / filename).exists():
            return f"assets/pdfs/ijhs/{filename}"
        if (CORPUS_OTHER / filename).exists():
            return f"assets/pdfs/other/{filename}"

    return None

def main():
    print(f"Reading TSV from {TSV_PATH}")
    if not TSV_PATH.exists():
        print("TSV file not found!")
        sys.exit(1)

    df = pd.read_csv(TSV_PATH, sep='\t')
    
    papers = []
    found_count = 0
    
    for _, row in df.iterrows():
        # Helper to clean numeric strings (remove .0)
        def clean_num(v):
            if pd.isna(v) or str(v).lower() == 'nan': return ""
            s = str(v)
            if s.endswith('.0'): return s[:-2]
            return s

        paper = {
            "journal": clean_num(row.get("journal", "")),
            "title": clean_num(row.get("paper", "Untitled")),
            "author": clean_num(row.get("author", "Unknown")),
            "category": clean_num(row.get("category", "Uncategorized")),
            "subject": clean_num(row.get("subject", "General")),
            "year": clean_num(row.get("year", "")),
            "remoteUrl": row.get("url", ""),
            "juUrl": clean_num(row.get("ju_url", "")),
            "size": row.get("size_in_kb", 0),
            "cahc_authored": str(row.get("cahc_authored", "false")).lower() == "true",
            "entry_type": clean_num(row.get("entry_type", "pdf")),
            "source": clean_num(row.get("source", "insa")),
            "gcs_key": clean_num(row.get("gcs_key", "")),
        }

        # Normalization: If primary is JU but secondary is empty, use primary for JU features
        if "jainuniversity" in str(paper["remoteUrl"]) and not paper["juUrl"]:
            paper["juUrl"] = paper["remoteUrl"]
        
        # Fix size: Ensure it's numeric and non-NaN
        try:
            if pd.isna(paper["size"]) or str(paper["size"]).lower() == 'nan':
                paper["size"] = 0
            else:
                paper["size"] = float(paper["size"])
        except:
            paper["size"] = 0
        
        # Try to parse year from journal string if missing (e.g. IJHS-1-1966-Issue-1)
        if not paper["year"] or paper["year"] == "nan":
            parts = paper["journal"].split('-')
            for part in parts:
                if part.isdigit() and len(part) == 4:
                    paper["year"] = part
                    break
        
        # Resolve local path
        gcs_key = clean_num(row.get("gcs_key", ""))
        local_path = find_local_path(paper["remoteUrl"], gcs_key)
        if local_path:
            paper["localPath"] = local_path
            found_count += 1

            # If size is 0/missing in metadata, try to get it from local disk
            if paper["size"] <= 0:
                abspath = CORPUS_ROOT / gcs_key if gcs_key else None
                if abspath and abspath.exists():
                    paper["size"] = abspath.stat().st_size / 1024.0
        else:
            paper["localPath"] = None
            
        papers.append(paper)

    print(f"Processed {len(papers)} papers. Found local PDF for {found_count} of them.")
    
    # Write to JS
    js_content = f"const PAPERS = {json.dumps(papers, indent=2)};\n"
    
    with open(OUTPUT_JS_PATH, "w") as f:
        f.write(js_content)
    
    print(f"Data written to {OUTPUT_JS_PATH}")
    
    # Setup Symlink
    setup_symlink()

if __name__ == "__main__":
    main()
