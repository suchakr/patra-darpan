# Corpus Input Audit

## Summary
- checks run: 11
- severity counts: {'info': 16, 'warning': 8}

## root_inventory
- ijhs_rows: 1954
- curated_pdf_rows: 50
- curated_link_rows: 7
- registry_entries: 74
- mirror_rows: 17
- shared_ijhs_files: 1954
- shared_other_files: 50
- issue_count: 0

## root_input_validation
- ijhs_missing_required: 0
- ijhs_non_pdf_url: 0
- ijhs_non_numeric_size: 0
- ijhs_unmatched_local_filename: 0
- ijhs_unexpected_blank_author: 8
- ijhs_expected_authorless: 197
- curated_pdfs_missing_required: 0
- curated_pdfs_non_pdf_url: 0
- curated_pdfs_non_numeric_year: 0
- curated_pdfs_blank_size_in_kb: 46
- curated_pdfs_unmatched_local_filename: 0
- curated_links_missing_required: 0
- curated_links_non_numeric_year: 0
- mirror_missing_required: 0
- mirror_non_pdf_url: 0
- mirror_same_source_and_target: 0
- mirror_source_unmatched: 0
- registry_blank_entries: 0
- registry_duplicate_entries: 0
- issue_count: 8

### Sample Issues
- [info] IJHS root row has blank author outside the expected procedural patterns (row_number=477, paper='A Glance at Military Techniques in Ramayana and Mahabharata', journal='IJHS-24-1989-Issue-3')
- [info] IJHS root row has blank author outside the expected procedural patterns (row_number=561, paper='Orbituary: S N Sen', journal='IJHS-27-1992-Issue-4')
- [info] IJHS root row has blank author outside the expected procedural patterns (row_number=629, paper='A National Report on Studies in HOS in India (1990-93)', journal='IJHS-30-1995-Issue-1')
- [info] IJHS root row has blank author outside the expected procedural patterns (row_number=656, paper='Book Review and News', journal='IJHS-31-1996-Issue-3')
- [info] IJHS root row has blank author outside the expected procedural patterns (row_number=944, paper='Historical Note: Magic Square for 2006', journal='IJHS-41-2006-Issue-1')
- [info] IJHS root row has blank author outside the expected procedural patterns (row_number=1108, paper='Reminiscence', journal='IJHS-44-2009-Issue-4')
- [info] IJHS root row has blank author outside the expected procedural patterns (row_number=1179, paper='Index', journal='IJHS-45-2010-Issue-4')
- [info] IJHS root row has blank author outside the expected procedural patterns (row_number=1376, paper='Book Review: R N Iyengar - Parasaratantra: Ancient Sanskrit Text on Astronomy and Natural Sciences', journal='IJHS-49-2014-Issue-2')

## canonical_inventory
- documents: 2011
- document_sources: 2011
- asset_refs: 2028
- documents_by_source: {'curated-links.tsv': 7, 'curated-pdfs.tsv': 50, 'ijhs.tsv': 1954}
- documents_by_entry_type: {'link': 7, 'pdf': 2004}
- issue_count: 0

## core_field_quality
- missing_title: 0
- missing_author_display: 8
- expected_authorless_procedural_entries: 197
- missing_journal_label: 0
- missing_entry_type: 0
- missing_year: 0
- year_derivable_from_ijhs_journal_label: 0
- issue_count: 8

### Sample Issues
- [warning] Missing core field `author_display` (doc_id='Vol24_4_2_SAParamhans', source_root='ijhs.tsv')
- [warning] Missing core field `author_display` (doc_id='Vol27_4_13_Obituary_SNSen', source_root='ijhs.tsv')
- [warning] Missing core field `author_display` (doc_id='Vol30_1_8_ReviewReport', source_root='ijhs.tsv')
- [warning] Missing core field `author_display` (doc_id='Vol31_3_6_BookReviewandNews', source_root='ijhs.tsv')
- [warning] Missing core field `author_display` (doc_id='Vol41_1_8_Magic%20Square', source_root='ijhs.tsv')
- [warning] Missing core field `author_display` (doc_id='Vol44_4_12_Reminiscenses', source_root='ijhs.tsv')
- [warning] Missing core field `author_display` (doc_id='Vol45_4_26_Index', source_root='ijhs.tsv')
- [warning] Missing core field `author_display` (doc_id='Vol49_2_10_BookReview', source_root='ijhs.tsv')

## deferred_field_status
- documents_by_source_root: {'curated-links.tsv': 7, 'curated-pdfs.tsv': 50, 'ijhs.tsv': 1954}
- cahc_authored_true_by_source_root: {'curated-links.tsv': 7, 'curated-pdfs.tsv': 50, 'ijhs.tsv': 17}
- subject_status: deferred; export currently leaves subject blank
- category_status: deferred; export currently leaves category blank
- cahc_authored_status: present as a curated label in documents; still needs clearer long-term placement
- issue_count: 0

## missing_local_files
- issue_count: 0
- issue_count: 0

## orphan_files
- issue_count: 0
- issue_count: 0

## duplicate_asset_mappings
- issue_count: 0
- issue_count: 0

## doc_id_collisions
- issue_count: 8
- issue_count: 8

### Sample Issues
- [info] doc_id has observed collision suffix (doc_id='1-13', title='Precise Determination of the Ascendant in the Lagnaprakaraṇa-IV', source_root='ijhs.tsv')
- [info] doc_id has observed collision suffix (doc_id='14-19', title='Could the “Case for Revising the Date of Vedāṅga Jyotiṣa” be Flawed?', source_root='ijhs.tsv')
- [info] doc_id has observed collision suffix (doc_id='20-27', title='Genius and Premature Birth: Little Evidence that Claims About Historically Eminent Scientists are...', source_root='ijhs.tsv')
- [info] doc_id has observed collision suffix (doc_id='28-36', title='Whiggism, Creativity and the Historiography of Technoscience', source_root='ijhs.tsv')
- [info] doc_id has observed collision suffix (doc_id='37-48', title='Putting Nicobar Islands on the Map: Intersections of Colonial Knowledge, Trade and...', source_root='ijhs.tsv')
- [info] doc_id has observed collision suffix (doc_id='49-59', title='An Assessment of Environment Friendly Methods of Khadi Manufacturing', source_root='ijhs.tsv')
- [info] doc_id has observed collision suffix (doc_id='60-64', title='Historical Notes: A Brief History of the Fertilizer Nitrogen', source_root='ijhs.tsv')
- [info] doc_id has observed collision suffix (doc_id='65-69', title='Historical Notes: A papier-maché Human Anatomical Model used in the Madras Medical Establishment...', source_root='ijhs.tsv')

## cahc_registry_mismatches
- issue_count: 0
- issue_count: 0

## mirror_registry_mismatches
- issue_count: 0
- issue_count: 0
