# Jyotiṣa ontology mention-count comparison

- Corpus revision: `080b5f66d34bbf7e7e761b6e9afa0735a6c1994b`
- Release: `retrieval-jyotisham-all-080b5f6-inc-722eba369e`
- Chunk windows: 7,826
- Extractor: `starter-gazetteer-0.2.0`
- Chunk SHA-256: `d37a4fc0133ae424ee3f893a469ef1f56ddb14603679e6cd86c8aebf352d7ae0`
- v0.3 SHA-256: `4b236797419b255913c665dfc9953cf14f71fe1277a1f4146d4b1edddd7f8d2a`
- v0.3.1 SHA-256: `c29a69437bb4ec54efd39e7a1d7b4b7042735417574d4f360bcb935d9cc3c544`
- Previous target SHA-256: `3b20c62a850fa80dca9e1a131318c9b3cd8054b3467018ea07472a735b2b2d08`
- provisional ontology SHA-256: `ee6cd74393acf66cd1781c1cc76823286204acc774df36d4568336b640ab5406`

Counts are extractor mention rows for each exact entity/form on the identical chunk inventory. “Unflagged” means the form is not listed in the finite ambiguity-marker list; it is not contextual or scholarly verification. v0.3 has no ambiguity assessment field, so its matching rows are unassessed. Contextual synonyms are not aliases and are excluded. The provisional ontology is reported as supplied; it is not rebased by this script.

## Ambiguity-marked forms (v0.3 → v0.3.1)

| Entity | Form | Before total | After total | Flagged | Unflagged | Unassessed | Delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Nati (`jyotisha:concept_nati`) | नति | 7 | 7 | 7 | 0 | 0 | +0 |
| Pāta (`jyotisha:concept_pata`) | पात | 10 | 10 | 10 | 0 | 0 | +0 |
| Valana (`jyotisha:concept_valana`) | वलन | 4 | 4 | 4 | 0 | 0 | +0 |
| Yaṣṭi-yantra (`jyotisha:instrument_yastiyantra`) | Staff | 46 | 46 | 46 | 0 | 0 | +0 |
| Budha (`jyotisha:mercury`) | बुध | 97 | 97 | 97 | 0 | 0 | +0 |
| Candra (`jyotisha:moon`) | सोम | 15 | 15 | 15 | 0 | 0 | +0 |
| Hasta (`jyotisha:nakshatra_hasta`) | हस्त | 32 | 32 | 32 | 0 | 0 | +0 |
| Mūla (`jyotisha:nakshatra_mula`) | मूल | 69 | 69 | 69 | 0 | 0 | +0 |
| Dhanus (`jyotisha:rasi_dhanus`) | धनु | 13 | 13 | 13 | 0 | 0 | +0 |
| Makara (`jyotisha:rasi_makara`) | मकर | 10 | 10 | 10 | 0 | 0 | +0 |
| Meṣa (`jyotisha:rasi_mesa`) | मेष | 20 | 20 | 20 | 0 | 0 | +0 |
| Mīna (`jyotisha:rasi_mina`) | मीन | 14 | 14 | 14 | 0 | 0 | +0 |
| Grīṣma (`jyotisha:rtu_grishma`) | Summer | 260 | 260 | 260 | 0 | 0 | +0 |
| Śarat (`jyotisha:rtu_sharat`) | Autumn | 81 | 81 | 81 | 0 | 0 | +0 |
| Śiśira (`jyotisha:rtu_shishira`) | Winter | 347 | 347 | 347 | 0 | 0 | +0 |
| Vasanta (`jyotisha:rtu_vasanta`) | Spring | 79 | 79 | 79 | 0 | 0 | +0 |

## Removed ambiguity markers (previous target → v0.3.1)

Marker status is a disclosure label and does not affect matching. Counts remain stable where the aliases are unchanged.

| Entity | Form | Previous flagged | Current total | Current flagged | Current unflagged | Current unassessed |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Pāta (`jyotisha:concept_pata`) | Node | 264 | 264 | 0 | 264 | 0 |
| Karka (`jyotisha:rasi_karka`) | Cancer | 42 | 42 | 0 | 42 | 0 |

## Removed aliases (v0.3 → v0.3.1)

| Entity | Removed form | Before total | After total | Delta |
| --- | --- | ---: | ---: | ---: |
| Kṛttikā (`jyotisha:nakshatra_krittika`) | क्रित्तिका | 0 | 0 | +0 |

## Provisional spelling variants (v0.3.1 → v0.4.0-partial)

| Entity | Variant | Before total | Provisional total | Delta |
| --- | --- | ---: | ---: | ---: |
| Abhijit (`jyotisha:nakshatra_abhijit`) | अभिजित | 0 | 1 | +1 |
| Mṛgaśīrṣa (`jyotisha:nakshatra_mrigasira`) | मृगशिर | 0 | 28 | +28 |
| Mūla (`jyotisha:nakshatra_mula`) | Mūlā | 0 | 16 | +16 |
| Punarvasu (`jyotisha:nakshatra_punarvasu`) | Punarvasū | 0 | 29 | +29 |
| Pūrvabhādrapadā (`jyotisha:nakshatra_purva_bhadrapada`) | पूर्वभाद्रपदा | 0 | 3 | +3 |
| Puṣya (`jyotisha:nakshatra_pushya`) | Puṣyā | 0 | 28 | +28 |
| Svātī (`jyotisha:nakshatra_svati`) | Svāti | 0 | 49 | +49 |
| Svātī (`jyotisha:nakshatra_svati`) | स्वाति | 0 | 16 | +16 |
| Uttarabhādrapadā (`jyotisha:nakshatra_uttara_bhadrapada`) | उत्तरभाद्रपदा | 0 | 4 | +4 |
| Uttaraphalgunī (`jyotisha:nakshatra_uttara_phalguni`) | Uttaraphalguni | 0 | 5 | +5 |
| Viśākhā (`jyotisha:nakshatra_visakha`) | Viśākhe | 0 | 39 | +39 |

## Whole-corpus mention assessment

| Ontology | Total | Flagged | Unflagged | Unassessed |
| --- | ---: | ---: | ---: | ---: |
| v0.3 | 27417 | 0 | 0 | 27417 |
| v0.3.1 | 27417 | 1104 | 26313 | 0 |
| v0.4.0-partial | 27635 | 1410 | 26225 | 0 |
