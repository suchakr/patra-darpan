# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas",
# ]
# ///

import pandas as pd

import os

# Relative path to cache
CACHE_DIR = os.path.join(os.path.dirname(__file__), "../corpus")
tsv_path = os.path.join(CACHE_DIR, 'ijhs.tsv')
print(f"Reading {tsv_path}...")
df = pd.read_csv(tsv_path, sep='\t')

# Logic to fix Issue 2 -> Issue 3 for Vol 49
# Also fix IJHS-47 (2012) mislabeled as 2011/Vol 46
# Also fix IJHS-42 (2007) mislabeled as 2006/Vol 41 (if applicable)
# Also fix IJHS-24 (1989) mislabeled

corrections = [
    # (Wrong Journal Name, URL pattern, Correct Journal Name)
    ('IJHS-49-2014-Issue-2', 'Vol49_3', 'IJHS-49-2014-Issue-3'),
    ('IJHS-46-2011-Issue-3', 'Vol47_3', 'IJHS-47-2012-Issue-3'), # Fix Manda Puzzle etc
    ('IJHS-41-2006-Issue-2', 'Vol42_2', 'IJHS-42-2007-Issue-2'), # Historical Note BG Tilak
    ('IJHS-24-1989-Issue-2', 'Vol24_3', 'IJHS-24-1989-Issue-3'), # Fix issue 3 overlap
]

# New Author Correction Logic
author_corrections = [
    # (URL Pattern, Correct Author)
    ('Vol46_1_2_RNIyenger.pdf', 'R N Iyengar'),
]

# Manual Authorship Tagging from persistent registry
registry_path = os.path.join(CACHE_DIR, 'cahc_authored_registry.txt')
cahc_authored_patterns = []
if os.path.exists(registry_path):
    with open(registry_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Ignore comments and blank lines
            if line and not line.startswith('#'):
                cahc_authored_patterns.append(line)

count = 0
for wrong_journal, url_pattern, correct_journal in corrections:
    try:
        mask = (df['journal'] == wrong_journal) & (df['url'].str.contains(url_pattern, na=False))
        matches = mask.sum()
        if matches > 0:
            print(f"Patching {matches} rows: {wrong_journal} -> {correct_journal}")
            df.loc[mask, 'journal'] = correct_journal
            count += matches
    except Exception as e:
        print(f"Error checking {wrong_journal}: {e}")

author_count = 0
for url_pattern, correct_author in author_corrections:
    mask = (df['url'].str.contains(url_pattern, na=False))
    matches = mask.sum()
    if matches > 0:
        print(f"Patching Author for {matches} rows: {correct_author}")
        df.loc[mask, 'author'] = correct_author
        author_count += matches

tag_count = 0
for url_pattern in cahc_authored_patterns:
    # Ensure exact filename matching to prevent '1.pdf' from matching 'Vol11.pdf'
    mask_url = df['url'].str.endswith('/' + url_pattern, na=False) | (df['url'] == url_pattern)
    mask_ju = df['ju_url'].str.endswith('/' + url_pattern, na=False) | (df['ju_url'] == url_pattern) if 'ju_url' in df.columns else False
    
    mask = mask_url | mask_ju
    matches = mask.sum()
    
    if matches > 0:
        df.loc[mask, 'cahc_authored'] = True
        tag_count += matches

print(f"Applied CAHC authorship tags to {tag_count} rows from registry.")

if count > 0 or author_count > 0 or tag_count > 0:
    df.to_csv(tsv_path, sep='\t', index=False)
    print(f"Total patched: {count} journals, {author_count} authors, {tag_count} authorship tags.")
else:
    print("No rows found to patch.")
