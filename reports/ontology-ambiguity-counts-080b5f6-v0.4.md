# Jyotiṣa ontology mention-count comparison

- Corpus revision: `080b5f66d34bbf7e7e761b6e9afa0735a6c1994b`
- Release: `retrieval-jyotisham-all-080b5f6-inc-722eba369e`
- Chunk windows: 7,826
- Extractor: `starter-gazetteer-0.2.0`
- Chunk SHA-256: `d37a4fc0133ae424ee3f893a469ef1f56ddb14603679e6cd86c8aebf352d7ae0`
- Base mention artifact SHA-256: `4bd44aa6b202adb019a7dab7c5b6613935be2020faf91babd8feb8fb515dc926`
- Target mention artifact SHA-256: `fedd6cd87b2c31a05ada0956e01d0f6734ea881ddcaf4f90eb630b5045990ea2`
- Previous-target mention artifact SHA-256: `bbb3ab5f20423a88aaff3b9dd2e5e7081bd092cff3261f872c477d8691b53a83`
- Base ontology (v0.3.0) SHA-256: `4b236797419b255913c665dfc9953cf14f71fe1277a1f4146d4b1edddd7f8d2a`
- Target ontology (v0.4.0) SHA-256: `34b7dce163a69180c4ccbb0d18c35cbc811aad0dc81159d075cb61b2375a8689`
- Previous target SHA-256: `c29a69437bb4ec54efd39e7a1d7b4b7042735417574d4f360bcb935d9cc3c544`
- Variant-source ontology (v0.4.0) SHA-256: `34b7dce163a69180c4ccbb0d18c35cbc811aad0dc81159d075cb61b2375a8689`
- Target status-bearing annotations: 39 provisional, 0 approved

Counts are extractor mention rows for each exact entity/form on the identical chunk inventory. “Unflagged” means the form is not listed in the finite ambiguity-marker list; it is not contextual or scholarly verification. The target contains 28 provisional contextual synonyms; these are metadata, not aliases. The 11 provisional spelling variants add +218 matching mention rows against the stated baseline.

## Ambiguity-marked forms (v0.3.0 → v0.4.0)

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

## Removed aliases (v0.3.0 → v0.4.0)

| Entity | Removed form | Before total | After total | Delta |
| --- | --- | ---: | ---: | ---: |
| Kṛttikā (`jyotisha:nakshatra_krittika`) | क्रित्तिका | 0 | 0 | +0 |

## Provisional spelling variants (v0.3.1 → v0.4.0)

| Entity | Variant | Before total | After total | Delta |
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
| v0.3.0 | 27417 | 0 | 0 | 27417 |
| v0.3.1 | 27417 | 1104 | 26313 | 0 |
| v0.4.0 | 27635 | 1104 | 26531 | 0 |
