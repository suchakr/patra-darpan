# Filename Encoding Duplicate Pairs

Most of these are on-disk sibling PDFs whose filenames differ only by URL encoding, most commonly space vs `%20`.
One additional pair is included because it is an exact on-disk duplicate already covered by the current canonical mapping, even though it is not an encoding-only variant.

- canonical rule used here: prefer the variant that the current canonical build already maps
- because every pair is already mapped through exactly one variant, the report uses that mapped variant as canonical
- operational recommendation for later cleanup: retain the canonical variant, remove the sibling alias only after checking any downstream GCS or sync dependencies

- pair count: 65

| # | Bucket | Canonical | Basis | Variants |
|---|---|---|---|---|
| 1 | ijhs | `ijhs/13-Books%20Received%20for%20Review.pdf` | `currently_mapped_in_canonical_build` | `ijhs/13-Books Received for Review.pdf`<br>`ijhs/13-Books%20Received%20for%20Review.pdf` |
| 2 | ijhs | `ijhs/1_PM%20Dolas.pdf` | `currently_mapped_in_canonical_build` | `ijhs/1_PM Dolas.pdf`<br>`ijhs/1_PM%20Dolas.pdf` |
| 3 | ijhs | `ijhs/2_NC%20Shah.pdf` | `currently_mapped_in_canonical_build` | `ijhs/2_NC Shah.pdf`<br>`ijhs/2_NC%20Shah.pdf` |
| 4 | ijhs | `ijhs/3_F%20Di%20Giacomo.pdf` | `currently_mapped_in_canonical_build` | `ijhs/3_F Di Giacomo.pdf`<br>`ijhs/3_F%20Di%20Giacomo.pdf` |
| 5 | ijhs | `ijhs/4_S%20Dasgupta.pdf` | `currently_mapped_in_canonical_build` | `ijhs/4_S Dasgupta.pdf`<br>`ijhs/4_S%20Dasgupta.pdf` |
| 6 | ijhs | `ijhs/5_P%20Sharma.pdf` | `currently_mapped_in_canonical_build` | `ijhs/5_P Sharma.pdf`<br>`ijhs/5_P%20Sharma.pdf` |
| 7 | ijhs | `ijhs/6_R%20Ghosh.pdf` | `currently_mapped_in_canonical_build` | `ijhs/6_R Ghosh.pdf`<br>`ijhs/6_R%20Ghosh.pdf` |
| 8 | ijhs | `ijhs/6__Arnab%20Rai%20Choudhuri.pdf` | `currently_mapped_in_canonical_build` | `ijhs/6__Arnab Rai Choudhuri.pdf`<br>`ijhs/6__Arnab%20Rai%20Choudhuri.pdf` |
| 9 | ijhs | `ijhs/7_MA%20Wani.pdf` | `currently_mapped_in_canonical_build` | `ijhs/7_MA Wani.pdf`<br>`ijhs/7_MA%20Wani.pdf` |
| 10 | ijhs | `ijhs/8_S%20Kulangara.pdf` | `currently_mapped_in_canonical_build` | `ijhs/8_S Kulangara.pdf`<br>`ijhs/8_S%20Kulangara.pdf` |
| 11 | ijhs | `ijhs/9_B%20Goswami.pdf` | `currently_mapped_in_canonical_build` | `ijhs/9_B Goswami.pdf`<br>`ijhs/9_B%20Goswami.pdf` |
| 12 | ijhs | `ijhs/Cumulative%20Index_58_ijhs.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Cumulative Index_58_ijhs.pdf`<br>`ijhs/Cumulative%20Index_58_ijhs.pdf` |
| 13 | ijhs | `ijhs/IJHS_60_3_1.pdf` | `currently_mapped_in_canonical_build_exact_duplicate` | `ijhs/IJHS_60_3_1.pdf`<br>`ijhs/IJHS_60_3_1_mean_motions.pdf` |
| 14 | ijhs | `ijhs/Pages%20from%20Vol4_2005_10_HISTORICAL%20NOTES_1.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Pages from Vol4_2005_10_HISTORICAL NOTES_1.pdf`<br>`ijhs/Pages%20from%20Vol4_2005_10_HISTORICAL%20NOTES_1.pdf` |
| 15 | ijhs | `ijhs/Vol1_2005_02_ENVIRONMENT%20AND%20ECOLOGY%20IN%20THE%20RAMAYANA.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol1_2005_02_ENVIRONMENT AND ECOLOGY IN THE RAMAYANA.pdf`<br>`ijhs/Vol1_2005_02_ENVIRONMENT%20AND%20ECOLOGY%20IN%20THE%20RAMAYANA.pdf` |
| 16 | ijhs | `ijhs/Vol1_2005_03_MYSTICAL%20MATHEMATICS%20IN%20ANCIENT%20PLANETS.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol1_2005_03_MYSTICAL MATHEMATICS IN ANCIENT PLANETS.pdf`<br>`ijhs/Vol1_2005_03_MYSTICAL%20MATHEMATICS%20IN%20ANCIENT%20PLANETS.pdf` |
| 17 | ijhs | `ijhs/Vol1_2005_04_CONGRESS%20AND%20CONSERVATION.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol1_2005_04_CONGRESS AND CONSERVATION.pdf`<br>`ijhs/Vol1_2005_04_CONGRESS%20AND%20CONSERVATION.pdf` |
| 18 | ijhs | `ijhs/Vol2_2005_02_MANAGEMENT%20OF%20FISTULA%20IN%20ANO%20IN%20ANCIENT%20GREEK%20AND%20AYURVEDIC%20MEDICINE%20A%20HISTORICAL%20AN.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol2_2005_02_MANAGEMENT OF FISTULA IN ANO IN ANCIENT GREEK AND AYURVEDIC MEDICINE A HISTORICAL AN.pdf`<br>`ijhs/Vol2_2005_02_MANAGEMENT%20OF%20FISTULA%20IN%20ANO%20IN%20ANCIENT%20GREEK%20AND%20AYURVEDIC%20MEDICINE%20A%20HISTORICAL%20AN.pdf` |
| 19 | ijhs | `ijhs/Vol2_2005_03_HIPPARCHUS'S%203600%20BASED%20CHORD%20TABLE%20AND%20ITS%20PLACE%20IN%20THE%20HISTORY%20OF%20ANCIENT%20GREEK%20AN.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol2_2005_03_HIPPARCHUS'S 3600 BASED CHORD TABLE AND ITS PLACE IN THE HISTORY OF ANCIENT GREEK AN.pdf`<br>`ijhs/Vol2_2005_03_HIPPARCHUS'S%203600%20BASED%20CHORD%20TABLE%20AND%20ITS%20PLACE%20IN%20THE%20HISTORY%20OF%20ANCIENT%20GREEK%20AN.pdf` |
| 20 | ijhs | `ijhs/Vol2_2005_04_HINDUS%20SCIENTIFIC%20CONTRIBUTIONS%20IN%20INDO%20CALENDAR.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol2_2005_04_HINDUS SCIENTIFIC CONTRIBUTIONS IN INDO CALENDAR.pdf`<br>`ijhs/Vol2_2005_04_HINDUS%20SCIENTIFIC%20CONTRIBUTIONS%20IN%20INDO%20CALENDAR.pdf` |
| 21 | ijhs | `ijhs/Vol2_2005_05_HISTORICAL%20NOTES_1.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol2_2005_05_HISTORICAL NOTES_1.pdf`<br>`ijhs/Vol2_2005_05_HISTORICAL%20NOTES_1.pdf` |
| 22 | ijhs | `ijhs/Vol2_2005_05_HISTORICAL%20NOTES_2.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol2_2005_05_HISTORICAL NOTES_2.pdf`<br>`ijhs/Vol2_2005_05_HISTORICAL%20NOTES_2.pdf` |
| 23 | ijhs | `ijhs/Vol2_2005_06_BOOK%20REVIEW.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol2_2005_06_BOOK REVIEW.pdf`<br>`ijhs/Vol2_2005_06_BOOK%20REVIEW.pdf` |
| 24 | ijhs | `ijhs/Vol31_1_8_SupplementBibliographyon%20MagneticStudies.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol31_1_8_SupplementBibliographyon MagneticStudies.pdf`<br>`ijhs/Vol31_1_8_SupplementBibliographyon%20MagneticStudies.pdf` |
| 25 | ijhs | `ijhs/Vol37_1_9_Supplement%20ScientificPeriodicals.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol37_1_9_Supplement ScientificPeriodicals.pdf`<br>`ijhs/Vol37_1_9_Supplement%20ScientificPeriodicals.pdf` |
| 26 | ijhs | `ijhs/Vol3_2005_01_THE%20FIRST%20CATALOGUE%20ON%20FORGE%20WELDED%20IRON%20CANNONS%20BY%20NEOGI.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol3_2005_01_THE FIRST CATALOGUE ON FORGE WELDED IRON CANNONS BY NEOGI.pdf`<br>`ijhs/Vol3_2005_01_THE%20FIRST%20CATALOGUE%20ON%20FORGE%20WELDED%20IRON%20CANNONS%20BY%20NEOGI.pdf` |
| 27 | ijhs | `ijhs/Vol3_2005_02_RAJAGOPALA%20THE%20MASSIVE%20IRON%20CANNON%20AT%20THANJAVUR%20IN%20TAMIL%20NADU.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol3_2005_02_RAJAGOPALA THE MASSIVE IRON CANNON AT THANJAVUR IN TAMIL NADU.pdf`<br>`ijhs/Vol3_2005_02_RAJAGOPALA%20THE%20MASSIVE%20IRON%20CANNON%20AT%20THANJAVUR%20IN%20TAMIL%20NADU.pdf` |
| 28 | ijhs | `ijhs/Vol3_2005_03_DAL%20MARDAN%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BISHNUPUR.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol3_2005_03_DAL MARDAN THE FORGE WELDED IRON CANNON AT BISHNUPUR.pdf`<br>`ijhs/Vol3_2005_03_DAL%20MARDAN%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BISHNUPUR.pdf` |
| 29 | ijhs | `ijhs/Vol3_2005_04_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BADA%20BURJ%20OF%20GOLCONDA%20FORT%20RAMPART.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol3_2005_04_THE FORGE WELDED IRON CANNON AT BADA BURJ OF GOLCONDA FORT RAMPART.pdf`<br>`ijhs/Vol3_2005_04_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BADA%20BURJ%20OF%20GOLCONDA%20FORT%20RAMPART.pdf` |
| 30 | ijhs | `ijhs/Vol3_2005_05_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20FATEH%20BURJ%20OF%20GOLCONDA%20FORST%20RAMPART.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol3_2005_05_THE FORGE WELDED IRON CANNON AT FATEH BURJ OF GOLCONDA FORST RAMPART.pdf`<br>`ijhs/Vol3_2005_05_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20FATEH%20BURJ%20OF%20GOLCONDA%20FORST%20RAMPART.pdf` |
| 31 | ijhs | `ijhs/Vol3_2005_06_BHAVANI%20SANKAR%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol3_2005_06_BHAVANI SANKAR THE FORGE WELDED IRON CANNON AT JHANSI FORT.pdf`<br>`ijhs/Vol3_2005_06_BHAVANI%20SANKAR%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf` |
| 32 | ijhs | `ijhs/Vol3_2005_07_KADAK%20BIJLI%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol3_2005_07_KADAK BIJLI THE FORGE WELDED IRON CANNON AT JHANSI FORT.pdf`<br>`ijhs/Vol3_2005_07_KADAK%20BIJLI%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf` |
| 33 | ijhs | `ijhs/Vol3_2005_08_AZDAHA%20PAIKAR%20THE%20COMPOSITE%20IRON%20BROZE%20CANNON%20AT%20MUSA%20BURJ%20OF%20GOLCONDA%20FORT.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol3_2005_08_AZDAHA PAIKAR THE COMPOSITE IRON BROZE CANNON AT MUSA BURJ OF GOLCONDA FORT.pdf`<br>`ijhs/Vol3_2005_08_AZDAHA%20PAIKAR%20THE%20COMPOSITE%20IRON%20BROZE%20CANNON%20AT%20MUSA%20BURJ%20OF%20GOLCONDA%20FORT.pdf` |
| 34 | ijhs | `ijhs/Vol3_2005_09_FATH%20RAIHBAR%20THE%20MASSIVE%20BRONZE%20CANNON%20AT%20PETLA%20BURJ%20OF%20GOLCONDA%20FORT.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol3_2005_09_FATH RAIHBAR THE MASSIVE BRONZE CANNON AT PETLA BURJ OF GOLCONDA FORT.pdf`<br>`ijhs/Vol3_2005_09_FATH%20RAIHBAR%20THE%20MASSIVE%20BRONZE%20CANNON%20AT%20PETLA%20BURJ%20OF%20GOLCONDA%20FORT.pdf` |
| 35 | ijhs | `ijhs/Vol3_2005_10_HISTORICAL%20NOTES.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol3_2005_10_HISTORICAL NOTES.pdf`<br>`ijhs/Vol3_2005_10_HISTORICAL%20NOTES.pdf` |
| 36 | ijhs | `ijhs/Vol41_1_8_Magic%20Square.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol41_1_8_Magic Square.pdf`<br>`ijhs/Vol41_1_8_Magic%20Square.pdf` |
| 37 | ijhs | `ijhs/Vol42_3_15_Historical%20NoteRBalasubramaniam.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol42_3_15_Historical NoteRBalasubramaniam.pdf`<br>`ijhs/Vol42_3_15_Historical%20NoteRBalasubramaniam.pdf` |
| 38 | ijhs | `ijhs/Vol44_1_6_Historical%20Notes.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol44_1_6_Historical Notes.pdf`<br>`ijhs/Vol44_1_6_Historical%20Notes.pdf` |
| 39 | ijhs | `ijhs/Vol44_1_9_Book%20Review.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol44_1_9_Book Review.pdf`<br>`ijhs/Vol44_1_9_Book%20Review.pdf` |
| 40 | ijhs | `ijhs/Vol44_2_5_PT%20Craddock.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol44_2_5_PT Craddock.pdf`<br>`ijhs/Vol44_2_5_PT%20Craddock.pdf` |
| 41 | ijhs | `ijhs/Vol44_3_5_Historical%20Notes.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol44_3_5_Historical Notes.pdf`<br>`ijhs/Vol44_3_5_Historical%20Notes.pdf` |
| 42 | ijhs | `ijhs/Vol44_4_6_Historical%20Notes.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol44_4_6_Historical Notes.pdf`<br>`ijhs/Vol44_4_6_Historical%20Notes.pdf` |
| 43 | ijhs | `ijhs/Vol46_1_10_Project%20reportAKSeth.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol46_1_10_Project reportAKSeth.pdf`<br>`ijhs/Vol46_1_10_Project%20reportAKSeth.pdf` |
| 44 | ijhs | `ijhs/Vol46_1_11_Project%20reportSSen.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol46_1_11_Project reportSSen.pdf`<br>`ijhs/Vol46_1_11_Project%20reportSSen.pdf` |
| 45 | ijhs | `ijhs/Vol48_1_13_Form%20IV.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol48_1_13_Form IV.pdf`<br>`ijhs/Vol48_1_13_Form%20IV.pdf` |
| 46 | ijhs | `ijhs/Vol48_3_9_Project%20Reports.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol48_3_9_Project Reports.pdf`<br>`ijhs/Vol48_3_9_Project%20Reports.pdf` |
| 47 | ijhs | `ijhs/Vol48_4_10_ProjectReport_%20BKSen.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol48_4_10_ProjectReport_ BKSen.pdf`<br>`ijhs/Vol48_4_10_ProjectReport_%20BKSen.pdf` |
| 48 | ijhs | `ijhs/Vol48_4_11_%20News.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol48_4_11_ News.pdf`<br>`ijhs/Vol48_4_11_%20News.pdf` |
| 49 | ijhs | `ijhs/Vol48_4_3_%20AMSharan.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol48_4_3_ AMSharan.pdf`<br>`ijhs/Vol48_4_3_%20AMSharan.pdf` |
| 50 | ijhs | `ijhs/Vol48_4_6_%20RCGupta.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol48_4_6_ RCGupta.pdf`<br>`ijhs/Vol48_4_6_%20RCGupta.pdf` |
| 51 | ijhs | `ijhs/Vol48_4_8_Book%20Review.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol48_4_8_Book Review.pdf`<br>`ijhs/Vol48_4_8_Book%20Review.pdf` |
| 52 | ijhs | `ijhs/Vol48_4_9_Project%20Report_%20Jbhattacharyya.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol48_4_9_Project Report_ Jbhattacharyya.pdf`<br>`ijhs/Vol48_4_9_Project%20Report_%20Jbhattacharyya.pdf` |
| 53 | ijhs | `ijhs/Vol49_1_10_Book%20Review.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol49_1_10_Book Review.pdf`<br>`ijhs/Vol49_1_10_Book%20Review.pdf` |
| 54 | ijhs | `ijhs/Vol4_2005_01_IRON%20CANNONS%20OF%20CHINA.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_01_IRON CANNONS OF CHINA.pdf`<br>`ijhs/Vol4_2005_01_IRON%20CANNONS%20OF%20CHINA.pdf` |
| 55 | ijhs | `ijhs/Vol4_2005_02_MONSTER%20CANNON%20WROUGHT%20IRON%20BOMBARDS%20OF%20EUROPE.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_02_MONSTER CANNON WROUGHT IRON BOMBARDS OF EUROPE.pdf`<br>`ijhs/Vol4_2005_02_MONSTER%20CANNON%20WROUGHT%20IRON%20BOMBARDS%20OF%20EUROPE.pdf` |
| 56 | ijhs | `ijhs/Vol4_2005_03_CANNONS%20OF%20EASTERN%20INDIA.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_03_CANNONS OF EASTERN INDIA.pdf`<br>`ijhs/Vol4_2005_03_CANNONS%20OF%20EASTERN%20INDIA.pdf` |
| 57 | ijhs | `ijhs/Vol4_2005_04_FORGE%20WELDED%20CANNONS%20IN%20THE%20FORTS%20OF%20KARIMNAGAR%20DISTRICT%20IN%20THE%20ANDHRA%20PRADESH.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_04_FORGE WELDED CANNONS IN THE FORTS OF KARIMNAGAR DISTRICT IN THE ANDHRA PRADESH.pdf`<br>`ijhs/Vol4_2005_04_FORGE%20WELDED%20CANNONS%20IN%20THE%20FORTS%20OF%20KARIMNAGAR%20DISTRICT%20IN%20THE%20ANDHRA%20PRADESH.pdf` |
| 58 | ijhs | `ijhs/Vol4_2005_05_DEVELOPMENT%20OF%20CANNON%20TECHNOLOGY%20IN%20INDIA.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_05_DEVELOPMENT OF CANNON TECHNOLOGY IN INDIA.pdf`<br>`ijhs/Vol4_2005_05_DEVELOPMENT%20OF%20CANNON%20TECHNOLOGY%20IN%20INDIA.pdf` |
| 59 | ijhs | `ijhs/Vol4_2005_06_EPIC%20OF%20SALTPETRE%20TO%20GUNPOWDER.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_06_EPIC OF SALTPETRE TO GUNPOWDER.pdf`<br>`ijhs/Vol4_2005_06_EPIC%20OF%20SALTPETRE%20TO%20GUNPOWDER.pdf` |
| 60 | ijhs | `ijhs/Vol4_2005_07_GUNPOWDER%20ARTILLERY%20AND%20MILITARY%20ARCHITECTURE%20IN%20SOUTH%20INDIA%20(15-18TH%20CENTURY).pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_07_GUNPOWDER ARTILLERY AND MILITARY ARCHITECTURE IN SOUTH INDIA (15-18TH CENTURY).pdf`<br>`ijhs/Vol4_2005_07_GUNPOWDER%20ARTILLERY%20AND%20MILITARY%20ARCHITECTURE%20IN%20SOUTH%20INDIA%20(15-18TH%20CENTURY).pdf` |
| 61 | ijhs | `ijhs/Vol4_2005_08_FIREPOWER%20CENTRIC%20WARFARE%20IN%20INDIA%20AND%20MILITARY%20MODERNIZATION%20OF%20THE%20MARATHAS%201740-1.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_08_FIREPOWER CENTRIC WARFARE IN INDIA AND MILITARY MODERNIZATION OF THE MARATHAS 1740-1.pdf`<br>`ijhs/Vol4_2005_08_FIREPOWER%20CENTRIC%20WARFARE%20IN%20INDIA%20AND%20MILITARY%20MODERNIZATION%20OF%20THE%20MARATHAS%201740-1.pdf` |
| 62 | ijhs | `ijhs/Vol4_2005_09_ROCKETS%20UNDER%20HAIDAR%20ALI%20AND%20TIPU%20SULTAN'.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_09_ROCKETS UNDER HAIDAR ALI AND TIPU SULTAN'.pdf`<br>`ijhs/Vol4_2005_09_ROCKETS%20UNDER%20HAIDAR%20ALI%20AND%20TIPU%20SULTAN'.pdf` |
| 63 | ijhs | `ijhs/Vol4_2005_10_HISTORICAL%20NOTES_2.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_10_HISTORICAL NOTES_2.pdf`<br>`ijhs/Vol4_2005_10_HISTORICAL%20NOTES_2.pdf` |
| 64 | ijhs | `ijhs/Vol4_2005_10_HISTORICAL%20NOTES_3.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_10_HISTORICAL NOTES_3.pdf`<br>`ijhs/Vol4_2005_10_HISTORICAL%20NOTES_3.pdf` |
| 65 | ijhs | `ijhs/Vol4_2005_11_BOOK%20REVIEW.pdf` | `currently_mapped_in_canonical_build` | `ijhs/Vol4_2005_11_BOOK REVIEW.pdf`<br>`ijhs/Vol4_2005_11_BOOK%20REVIEW.pdf` |

## Mapped Details

### Pair 1
- canonical: `ijhs/13-Books%20Received%20for%20Review.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/13-Books Received for Review.pdf`
  - `ijhs/13-Books%20Received%20for%20Review.pdf`
- mapped variants:
  - `ijhs/13-Books%20Received%20for%20Review.pdf` -> doc_id=`13-Books%20Received%20for%20Review`, asset_role=`primary_pdf`

### Pair 2
- canonical: `ijhs/1_PM%20Dolas.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/1_PM Dolas.pdf`
  - `ijhs/1_PM%20Dolas.pdf`
- mapped variants:
  - `ijhs/1_PM%20Dolas.pdf` -> doc_id=`1_PM%20Dolas`, asset_role=`primary_pdf`

### Pair 3
- canonical: `ijhs/2_NC%20Shah.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/2_NC Shah.pdf`
  - `ijhs/2_NC%20Shah.pdf`
- mapped variants:
  - `ijhs/2_NC%20Shah.pdf` -> doc_id=`2_NC%20Shah`, asset_role=`primary_pdf`

### Pair 4
- canonical: `ijhs/3_F%20Di%20Giacomo.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/3_F Di Giacomo.pdf`
  - `ijhs/3_F%20Di%20Giacomo.pdf`
- mapped variants:
  - `ijhs/3_F%20Di%20Giacomo.pdf` -> doc_id=`3_F%20Di%20Giacomo`, asset_role=`primary_pdf`

### Pair 5
- canonical: `ijhs/4_S%20Dasgupta.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/4_S Dasgupta.pdf`
  - `ijhs/4_S%20Dasgupta.pdf`
- mapped variants:
  - `ijhs/4_S%20Dasgupta.pdf` -> doc_id=`4_S%20Dasgupta`, asset_role=`primary_pdf`

### Pair 6
- canonical: `ijhs/5_P%20Sharma.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/5_P Sharma.pdf`
  - `ijhs/5_P%20Sharma.pdf`
- mapped variants:
  - `ijhs/5_P%20Sharma.pdf` -> doc_id=`5_P%20Sharma`, asset_role=`primary_pdf`

### Pair 7
- canonical: `ijhs/6_R%20Ghosh.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/6_R Ghosh.pdf`
  - `ijhs/6_R%20Ghosh.pdf`
- mapped variants:
  - `ijhs/6_R%20Ghosh.pdf` -> doc_id=`6_R%20Ghosh`, asset_role=`primary_pdf`

### Pair 8
- canonical: `ijhs/6__Arnab%20Rai%20Choudhuri.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/6__Arnab Rai Choudhuri.pdf`
  - `ijhs/6__Arnab%20Rai%20Choudhuri.pdf`
- mapped variants:
  - `ijhs/6__Arnab%20Rai%20Choudhuri.pdf` -> doc_id=`6__Arnab%20Rai%20Choudhuri`, asset_role=`primary_pdf`

### Pair 9
- canonical: `ijhs/7_MA%20Wani.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/7_MA Wani.pdf`
  - `ijhs/7_MA%20Wani.pdf`
- mapped variants:
  - `ijhs/7_MA%20Wani.pdf` -> doc_id=`7_MA%20Wani`, asset_role=`primary_pdf`

### Pair 10
- canonical: `ijhs/8_S%20Kulangara.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/8_S Kulangara.pdf`
  - `ijhs/8_S%20Kulangara.pdf`
- mapped variants:
  - `ijhs/8_S%20Kulangara.pdf` -> doc_id=`8_S%20Kulangara`, asset_role=`primary_pdf`

### Pair 11
- canonical: `ijhs/9_B%20Goswami.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/9_B Goswami.pdf`
  - `ijhs/9_B%20Goswami.pdf`
- mapped variants:
  - `ijhs/9_B%20Goswami.pdf` -> doc_id=`9_B%20Goswami`, asset_role=`primary_pdf`

### Pair 12
- canonical: `ijhs/Cumulative%20Index_58_ijhs.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Cumulative Index_58_ijhs.pdf`
  - `ijhs/Cumulative%20Index_58_ijhs.pdf`
- mapped variants:
  - `ijhs/Cumulative%20Index_58_ijhs.pdf` -> doc_id=`Cumulative%20Index_58_ijhs`, asset_role=`primary_pdf`

### Pair 13
- canonical: `ijhs/IJHS_60_3_1.pdf`
- basis: `currently_mapped_in_canonical_build_exact_duplicate`
- variants:
  - `ijhs/IJHS_60_3_1.pdf`
  - `ijhs/IJHS_60_3_1_mean_motions.pdf`
- mapped variants:
  - `ijhs/IJHS_60_3_1.pdf` -> doc_id=`IJHS_60_3_1`, asset_role=`primary_pdf`

### Pair 14
- canonical: `ijhs/Pages%20from%20Vol4_2005_10_HISTORICAL%20NOTES_1.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Pages from Vol4_2005_10_HISTORICAL NOTES_1.pdf`
  - `ijhs/Pages%20from%20Vol4_2005_10_HISTORICAL%20NOTES_1.pdf`
- mapped variants:
  - `ijhs/Pages%20from%20Vol4_2005_10_HISTORICAL%20NOTES_1.pdf` -> doc_id=`Pages%20from%20Vol4_2005_10_HISTORICAL%20NOTES_1`, asset_role=`primary_pdf`

### Pair 15
- canonical: `ijhs/Vol1_2005_02_ENVIRONMENT%20AND%20ECOLOGY%20IN%20THE%20RAMAYANA.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol1_2005_02_ENVIRONMENT AND ECOLOGY IN THE RAMAYANA.pdf`
  - `ijhs/Vol1_2005_02_ENVIRONMENT%20AND%20ECOLOGY%20IN%20THE%20RAMAYANA.pdf`
- mapped variants:
  - `ijhs/Vol1_2005_02_ENVIRONMENT%20AND%20ECOLOGY%20IN%20THE%20RAMAYANA.pdf` -> doc_id=`Vol1_2005_02_ENVIRONMENT%20AND%20ECOLOGY%20IN%20THE%20RAMAYANA`, asset_role=`primary_pdf`

### Pair 16
- canonical: `ijhs/Vol1_2005_03_MYSTICAL%20MATHEMATICS%20IN%20ANCIENT%20PLANETS.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol1_2005_03_MYSTICAL MATHEMATICS IN ANCIENT PLANETS.pdf`
  - `ijhs/Vol1_2005_03_MYSTICAL%20MATHEMATICS%20IN%20ANCIENT%20PLANETS.pdf`
- mapped variants:
  - `ijhs/Vol1_2005_03_MYSTICAL%20MATHEMATICS%20IN%20ANCIENT%20PLANETS.pdf` -> doc_id=`Vol1_2005_03_MYSTICAL%20MATHEMATICS%20IN%20ANCIENT%20PLANETS`, asset_role=`primary_pdf`

### Pair 17
- canonical: `ijhs/Vol1_2005_04_CONGRESS%20AND%20CONSERVATION.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol1_2005_04_CONGRESS AND CONSERVATION.pdf`
  - `ijhs/Vol1_2005_04_CONGRESS%20AND%20CONSERVATION.pdf`
- mapped variants:
  - `ijhs/Vol1_2005_04_CONGRESS%20AND%20CONSERVATION.pdf` -> doc_id=`Vol1_2005_04_CONGRESS%20AND%20CONSERVATION`, asset_role=`primary_pdf`

### Pair 18
- canonical: `ijhs/Vol2_2005_02_MANAGEMENT%20OF%20FISTULA%20IN%20ANO%20IN%20ANCIENT%20GREEK%20AND%20AYURVEDIC%20MEDICINE%20A%20HISTORICAL%20AN.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol2_2005_02_MANAGEMENT OF FISTULA IN ANO IN ANCIENT GREEK AND AYURVEDIC MEDICINE A HISTORICAL AN.pdf`
  - `ijhs/Vol2_2005_02_MANAGEMENT%20OF%20FISTULA%20IN%20ANO%20IN%20ANCIENT%20GREEK%20AND%20AYURVEDIC%20MEDICINE%20A%20HISTORICAL%20AN.pdf`
- mapped variants:
  - `ijhs/Vol2_2005_02_MANAGEMENT%20OF%20FISTULA%20IN%20ANO%20IN%20ANCIENT%20GREEK%20AND%20AYURVEDIC%20MEDICINE%20A%20HISTORICAL%20AN.pdf` -> doc_id=`Vol2_2005_02_MANAGEMENT%20OF%20FISTULA%20IN%20ANO%20IN%20ANCIENT%20GREEK%20AND%20AYURVEDIC%20MEDICINE%20A%20HISTORICAL%20AN`, asset_role=`primary_pdf`

### Pair 19
- canonical: `ijhs/Vol2_2005_03_HIPPARCHUS'S%203600%20BASED%20CHORD%20TABLE%20AND%20ITS%20PLACE%20IN%20THE%20HISTORY%20OF%20ANCIENT%20GREEK%20AN.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol2_2005_03_HIPPARCHUS'S 3600 BASED CHORD TABLE AND ITS PLACE IN THE HISTORY OF ANCIENT GREEK AN.pdf`
  - `ijhs/Vol2_2005_03_HIPPARCHUS'S%203600%20BASED%20CHORD%20TABLE%20AND%20ITS%20PLACE%20IN%20THE%20HISTORY%20OF%20ANCIENT%20GREEK%20AN.pdf`
- mapped variants:
  - `ijhs/Vol2_2005_03_HIPPARCHUS'S%203600%20BASED%20CHORD%20TABLE%20AND%20ITS%20PLACE%20IN%20THE%20HISTORY%20OF%20ANCIENT%20GREEK%20AN.pdf` -> doc_id=`Vol2_2005_03_HIPPARCHUS'S%203600%20BASED%20CHORD%20TABLE%20AND%20ITS%20PLACE%20IN%20THE%20HISTORY%20OF%20ANCIENT%20GREEK%20AN`, asset_role=`primary_pdf`

### Pair 20
- canonical: `ijhs/Vol2_2005_04_HINDUS%20SCIENTIFIC%20CONTRIBUTIONS%20IN%20INDO%20CALENDAR.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol2_2005_04_HINDUS SCIENTIFIC CONTRIBUTIONS IN INDO CALENDAR.pdf`
  - `ijhs/Vol2_2005_04_HINDUS%20SCIENTIFIC%20CONTRIBUTIONS%20IN%20INDO%20CALENDAR.pdf`
- mapped variants:
  - `ijhs/Vol2_2005_04_HINDUS%20SCIENTIFIC%20CONTRIBUTIONS%20IN%20INDO%20CALENDAR.pdf` -> doc_id=`Vol2_2005_04_HINDUS%20SCIENTIFIC%20CONTRIBUTIONS%20IN%20INDO%20CALENDAR`, asset_role=`primary_pdf`

### Pair 21
- canonical: `ijhs/Vol2_2005_05_HISTORICAL%20NOTES_1.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol2_2005_05_HISTORICAL NOTES_1.pdf`
  - `ijhs/Vol2_2005_05_HISTORICAL%20NOTES_1.pdf`
- mapped variants:
  - `ijhs/Vol2_2005_05_HISTORICAL%20NOTES_1.pdf` -> doc_id=`Vol2_2005_05_HISTORICAL%20NOTES_1`, asset_role=`primary_pdf`

### Pair 22
- canonical: `ijhs/Vol2_2005_05_HISTORICAL%20NOTES_2.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol2_2005_05_HISTORICAL NOTES_2.pdf`
  - `ijhs/Vol2_2005_05_HISTORICAL%20NOTES_2.pdf`
- mapped variants:
  - `ijhs/Vol2_2005_05_HISTORICAL%20NOTES_2.pdf` -> doc_id=`Vol2_2005_05_HISTORICAL%20NOTES_2`, asset_role=`primary_pdf`

### Pair 23
- canonical: `ijhs/Vol2_2005_06_BOOK%20REVIEW.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol2_2005_06_BOOK REVIEW.pdf`
  - `ijhs/Vol2_2005_06_BOOK%20REVIEW.pdf`
- mapped variants:
  - `ijhs/Vol2_2005_06_BOOK%20REVIEW.pdf` -> doc_id=`Vol2_2005_06_BOOK%20REVIEW`, asset_role=`primary_pdf`

### Pair 24
- canonical: `ijhs/Vol31_1_8_SupplementBibliographyon%20MagneticStudies.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol31_1_8_SupplementBibliographyon MagneticStudies.pdf`
  - `ijhs/Vol31_1_8_SupplementBibliographyon%20MagneticStudies.pdf`
- mapped variants:
  - `ijhs/Vol31_1_8_SupplementBibliographyon%20MagneticStudies.pdf` -> doc_id=`Vol31_1_8_SupplementBibliographyon%20MagneticStudies`, asset_role=`primary_pdf`

### Pair 25
- canonical: `ijhs/Vol37_1_9_Supplement%20ScientificPeriodicals.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol37_1_9_Supplement ScientificPeriodicals.pdf`
  - `ijhs/Vol37_1_9_Supplement%20ScientificPeriodicals.pdf`
- mapped variants:
  - `ijhs/Vol37_1_9_Supplement%20ScientificPeriodicals.pdf` -> doc_id=`Vol37_1_9_Supplement%20ScientificPeriodicals`, asset_role=`primary_pdf`

### Pair 26
- canonical: `ijhs/Vol3_2005_01_THE%20FIRST%20CATALOGUE%20ON%20FORGE%20WELDED%20IRON%20CANNONS%20BY%20NEOGI.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol3_2005_01_THE FIRST CATALOGUE ON FORGE WELDED IRON CANNONS BY NEOGI.pdf`
  - `ijhs/Vol3_2005_01_THE%20FIRST%20CATALOGUE%20ON%20FORGE%20WELDED%20IRON%20CANNONS%20BY%20NEOGI.pdf`
- mapped variants:
  - `ijhs/Vol3_2005_01_THE%20FIRST%20CATALOGUE%20ON%20FORGE%20WELDED%20IRON%20CANNONS%20BY%20NEOGI.pdf` -> doc_id=`Vol3_2005_01_THE%20FIRST%20CATALOGUE%20ON%20FORGE%20WELDED%20IRON%20CANNONS%20BY%20NEOGI`, asset_role=`primary_pdf`

### Pair 27
- canonical: `ijhs/Vol3_2005_02_RAJAGOPALA%20THE%20MASSIVE%20IRON%20CANNON%20AT%20THANJAVUR%20IN%20TAMIL%20NADU.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol3_2005_02_RAJAGOPALA THE MASSIVE IRON CANNON AT THANJAVUR IN TAMIL NADU.pdf`
  - `ijhs/Vol3_2005_02_RAJAGOPALA%20THE%20MASSIVE%20IRON%20CANNON%20AT%20THANJAVUR%20IN%20TAMIL%20NADU.pdf`
- mapped variants:
  - `ijhs/Vol3_2005_02_RAJAGOPALA%20THE%20MASSIVE%20IRON%20CANNON%20AT%20THANJAVUR%20IN%20TAMIL%20NADU.pdf` -> doc_id=`Vol3_2005_02_RAJAGOPALA%20THE%20MASSIVE%20IRON%20CANNON%20AT%20THANJAVUR%20IN%20TAMIL%20NADU`, asset_role=`primary_pdf`

### Pair 28
- canonical: `ijhs/Vol3_2005_03_DAL%20MARDAN%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BISHNUPUR.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol3_2005_03_DAL MARDAN THE FORGE WELDED IRON CANNON AT BISHNUPUR.pdf`
  - `ijhs/Vol3_2005_03_DAL%20MARDAN%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BISHNUPUR.pdf`
- mapped variants:
  - `ijhs/Vol3_2005_03_DAL%20MARDAN%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BISHNUPUR.pdf` -> doc_id=`Vol3_2005_03_DAL%20MARDAN%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BISHNUPUR`, asset_role=`primary_pdf`

### Pair 29
- canonical: `ijhs/Vol3_2005_04_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BADA%20BURJ%20OF%20GOLCONDA%20FORT%20RAMPART.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol3_2005_04_THE FORGE WELDED IRON CANNON AT BADA BURJ OF GOLCONDA FORT RAMPART.pdf`
  - `ijhs/Vol3_2005_04_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BADA%20BURJ%20OF%20GOLCONDA%20FORT%20RAMPART.pdf`
- mapped variants:
  - `ijhs/Vol3_2005_04_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BADA%20BURJ%20OF%20GOLCONDA%20FORT%20RAMPART.pdf` -> doc_id=`Vol3_2005_04_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BADA%20BURJ%20OF%20GOLCONDA%20FORT%20RAMPART`, asset_role=`primary_pdf`

### Pair 30
- canonical: `ijhs/Vol3_2005_05_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20FATEH%20BURJ%20OF%20GOLCONDA%20FORST%20RAMPART.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol3_2005_05_THE FORGE WELDED IRON CANNON AT FATEH BURJ OF GOLCONDA FORST RAMPART.pdf`
  - `ijhs/Vol3_2005_05_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20FATEH%20BURJ%20OF%20GOLCONDA%20FORST%20RAMPART.pdf`
- mapped variants:
  - `ijhs/Vol3_2005_05_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20FATEH%20BURJ%20OF%20GOLCONDA%20FORST%20RAMPART.pdf` -> doc_id=`Vol3_2005_05_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20FATEH%20BURJ%20OF%20GOLCONDA%20FORST%20RAMPART`, asset_role=`primary_pdf`

### Pair 31
- canonical: `ijhs/Vol3_2005_06_BHAVANI%20SANKAR%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol3_2005_06_BHAVANI SANKAR THE FORGE WELDED IRON CANNON AT JHANSI FORT.pdf`
  - `ijhs/Vol3_2005_06_BHAVANI%20SANKAR%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf`
- mapped variants:
  - `ijhs/Vol3_2005_06_BHAVANI%20SANKAR%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf` -> doc_id=`Vol3_2005_06_BHAVANI%20SANKAR%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT`, asset_role=`primary_pdf`

### Pair 32
- canonical: `ijhs/Vol3_2005_07_KADAK%20BIJLI%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol3_2005_07_KADAK BIJLI THE FORGE WELDED IRON CANNON AT JHANSI FORT.pdf`
  - `ijhs/Vol3_2005_07_KADAK%20BIJLI%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf`
- mapped variants:
  - `ijhs/Vol3_2005_07_KADAK%20BIJLI%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf` -> doc_id=`Vol3_2005_07_KADAK%20BIJLI%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT`, asset_role=`primary_pdf`

### Pair 33
- canonical: `ijhs/Vol3_2005_08_AZDAHA%20PAIKAR%20THE%20COMPOSITE%20IRON%20BROZE%20CANNON%20AT%20MUSA%20BURJ%20OF%20GOLCONDA%20FORT.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol3_2005_08_AZDAHA PAIKAR THE COMPOSITE IRON BROZE CANNON AT MUSA BURJ OF GOLCONDA FORT.pdf`
  - `ijhs/Vol3_2005_08_AZDAHA%20PAIKAR%20THE%20COMPOSITE%20IRON%20BROZE%20CANNON%20AT%20MUSA%20BURJ%20OF%20GOLCONDA%20FORT.pdf`
- mapped variants:
  - `ijhs/Vol3_2005_08_AZDAHA%20PAIKAR%20THE%20COMPOSITE%20IRON%20BROZE%20CANNON%20AT%20MUSA%20BURJ%20OF%20GOLCONDA%20FORT.pdf` -> doc_id=`Vol3_2005_08_AZDAHA%20PAIKAR%20THE%20COMPOSITE%20IRON%20BROZE%20CANNON%20AT%20MUSA%20BURJ%20OF%20GOLCONDA%20FORT`, asset_role=`primary_pdf`

### Pair 34
- canonical: `ijhs/Vol3_2005_09_FATH%20RAIHBAR%20THE%20MASSIVE%20BRONZE%20CANNON%20AT%20PETLA%20BURJ%20OF%20GOLCONDA%20FORT.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol3_2005_09_FATH RAIHBAR THE MASSIVE BRONZE CANNON AT PETLA BURJ OF GOLCONDA FORT.pdf`
  - `ijhs/Vol3_2005_09_FATH%20RAIHBAR%20THE%20MASSIVE%20BRONZE%20CANNON%20AT%20PETLA%20BURJ%20OF%20GOLCONDA%20FORT.pdf`
- mapped variants:
  - `ijhs/Vol3_2005_09_FATH%20RAIHBAR%20THE%20MASSIVE%20BRONZE%20CANNON%20AT%20PETLA%20BURJ%20OF%20GOLCONDA%20FORT.pdf` -> doc_id=`Vol3_2005_09_FATH%20RAIHBAR%20THE%20MASSIVE%20BRONZE%20CANNON%20AT%20PETLA%20BURJ%20OF%20GOLCONDA%20FORT`, asset_role=`primary_pdf`

### Pair 35
- canonical: `ijhs/Vol3_2005_10_HISTORICAL%20NOTES.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol3_2005_10_HISTORICAL NOTES.pdf`
  - `ijhs/Vol3_2005_10_HISTORICAL%20NOTES.pdf`
- mapped variants:
  - `ijhs/Vol3_2005_10_HISTORICAL%20NOTES.pdf` -> doc_id=`Vol3_2005_10_HISTORICAL%20NOTES`, asset_role=`primary_pdf`

### Pair 36
- canonical: `ijhs/Vol41_1_8_Magic%20Square.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol41_1_8_Magic Square.pdf`
  - `ijhs/Vol41_1_8_Magic%20Square.pdf`
- mapped variants:
  - `ijhs/Vol41_1_8_Magic%20Square.pdf` -> doc_id=`Vol41_1_8_Magic%20Square`, asset_role=`primary_pdf`

### Pair 37
- canonical: `ijhs/Vol42_3_15_Historical%20NoteRBalasubramaniam.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol42_3_15_Historical NoteRBalasubramaniam.pdf`
  - `ijhs/Vol42_3_15_Historical%20NoteRBalasubramaniam.pdf`
- mapped variants:
  - `ijhs/Vol42_3_15_Historical%20NoteRBalasubramaniam.pdf` -> doc_id=`Vol42_3_15_Historical%20NoteRBalasubramaniam`, asset_role=`primary_pdf`

### Pair 38
- canonical: `ijhs/Vol44_1_6_Historical%20Notes.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol44_1_6_Historical Notes.pdf`
  - `ijhs/Vol44_1_6_Historical%20Notes.pdf`
- mapped variants:
  - `ijhs/Vol44_1_6_Historical%20Notes.pdf` -> doc_id=`Vol44_1_6_Historical%20Notes`, asset_role=`primary_pdf`

### Pair 39
- canonical: `ijhs/Vol44_1_9_Book%20Review.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol44_1_9_Book Review.pdf`
  - `ijhs/Vol44_1_9_Book%20Review.pdf`
- mapped variants:
  - `ijhs/Vol44_1_9_Book%20Review.pdf` -> doc_id=`Vol44_1_9_Book%20Review`, asset_role=`primary_pdf`

### Pair 40
- canonical: `ijhs/Vol44_2_5_PT%20Craddock.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol44_2_5_PT Craddock.pdf`
  - `ijhs/Vol44_2_5_PT%20Craddock.pdf`
- mapped variants:
  - `ijhs/Vol44_2_5_PT%20Craddock.pdf` -> doc_id=`Vol44_2_5_PT%20Craddock`, asset_role=`primary_pdf`

### Pair 41
- canonical: `ijhs/Vol44_3_5_Historical%20Notes.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol44_3_5_Historical Notes.pdf`
  - `ijhs/Vol44_3_5_Historical%20Notes.pdf`
- mapped variants:
  - `ijhs/Vol44_3_5_Historical%20Notes.pdf` -> doc_id=`Vol44_3_5_Historical%20Notes`, asset_role=`primary_pdf`

### Pair 42
- canonical: `ijhs/Vol44_4_6_Historical%20Notes.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol44_4_6_Historical Notes.pdf`
  - `ijhs/Vol44_4_6_Historical%20Notes.pdf`
- mapped variants:
  - `ijhs/Vol44_4_6_Historical%20Notes.pdf` -> doc_id=`Vol44_4_6_Historical%20Notes`, asset_role=`primary_pdf`

### Pair 43
- canonical: `ijhs/Vol46_1_10_Project%20reportAKSeth.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol46_1_10_Project reportAKSeth.pdf`
  - `ijhs/Vol46_1_10_Project%20reportAKSeth.pdf`
- mapped variants:
  - `ijhs/Vol46_1_10_Project%20reportAKSeth.pdf` -> doc_id=`Vol46_1_10_Project%20reportAKSeth`, asset_role=`primary_pdf`

### Pair 44
- canonical: `ijhs/Vol46_1_11_Project%20reportSSen.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol46_1_11_Project reportSSen.pdf`
  - `ijhs/Vol46_1_11_Project%20reportSSen.pdf`
- mapped variants:
  - `ijhs/Vol46_1_11_Project%20reportSSen.pdf` -> doc_id=`Vol46_1_11_Project%20reportSSen`, asset_role=`primary_pdf`

### Pair 45
- canonical: `ijhs/Vol48_1_13_Form%20IV.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol48_1_13_Form IV.pdf`
  - `ijhs/Vol48_1_13_Form%20IV.pdf`
- mapped variants:
  - `ijhs/Vol48_1_13_Form%20IV.pdf` -> doc_id=`Vol48_1_13_Form%20IV`, asset_role=`primary_pdf`

### Pair 46
- canonical: `ijhs/Vol48_3_9_Project%20Reports.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol48_3_9_Project Reports.pdf`
  - `ijhs/Vol48_3_9_Project%20Reports.pdf`
- mapped variants:
  - `ijhs/Vol48_3_9_Project%20Reports.pdf` -> doc_id=`Vol48_3_9_Project%20Reports`, asset_role=`primary_pdf`

### Pair 47
- canonical: `ijhs/Vol48_4_10_ProjectReport_%20BKSen.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol48_4_10_ProjectReport_ BKSen.pdf`
  - `ijhs/Vol48_4_10_ProjectReport_%20BKSen.pdf`
- mapped variants:
  - `ijhs/Vol48_4_10_ProjectReport_%20BKSen.pdf` -> doc_id=`Vol48_4_10_ProjectReport_%20BKSen`, asset_role=`primary_pdf`

### Pair 48
- canonical: `ijhs/Vol48_4_11_%20News.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol48_4_11_ News.pdf`
  - `ijhs/Vol48_4_11_%20News.pdf`
- mapped variants:
  - `ijhs/Vol48_4_11_%20News.pdf` -> doc_id=`Vol48_4_11_%20News`, asset_role=`primary_pdf`

### Pair 49
- canonical: `ijhs/Vol48_4_3_%20AMSharan.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol48_4_3_ AMSharan.pdf`
  - `ijhs/Vol48_4_3_%20AMSharan.pdf`
- mapped variants:
  - `ijhs/Vol48_4_3_%20AMSharan.pdf` -> doc_id=`Vol48_4_3_%20AMSharan`, asset_role=`primary_pdf`

### Pair 50
- canonical: `ijhs/Vol48_4_6_%20RCGupta.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol48_4_6_ RCGupta.pdf`
  - `ijhs/Vol48_4_6_%20RCGupta.pdf`
- mapped variants:
  - `ijhs/Vol48_4_6_%20RCGupta.pdf` -> doc_id=`Vol48_4_6_%20RCGupta`, asset_role=`primary_pdf`

### Pair 51
- canonical: `ijhs/Vol48_4_8_Book%20Review.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol48_4_8_Book Review.pdf`
  - `ijhs/Vol48_4_8_Book%20Review.pdf`
- mapped variants:
  - `ijhs/Vol48_4_8_Book%20Review.pdf` -> doc_id=`Vol48_4_8_Book%20Review`, asset_role=`primary_pdf`

### Pair 52
- canonical: `ijhs/Vol48_4_9_Project%20Report_%20Jbhattacharyya.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol48_4_9_Project Report_ Jbhattacharyya.pdf`
  - `ijhs/Vol48_4_9_Project%20Report_%20Jbhattacharyya.pdf`
- mapped variants:
  - `ijhs/Vol48_4_9_Project%20Report_%20Jbhattacharyya.pdf` -> doc_id=`Vol48_4_9_Project%20Report_%20Jbhattacharyya`, asset_role=`primary_pdf`

### Pair 53
- canonical: `ijhs/Vol49_1_10_Book%20Review.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol49_1_10_Book Review.pdf`
  - `ijhs/Vol49_1_10_Book%20Review.pdf`
- mapped variants:
  - `ijhs/Vol49_1_10_Book%20Review.pdf` -> doc_id=`Vol49_1_10_Book%20Review`, asset_role=`primary_pdf`

### Pair 54
- canonical: `ijhs/Vol4_2005_01_IRON%20CANNONS%20OF%20CHINA.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_01_IRON CANNONS OF CHINA.pdf`
  - `ijhs/Vol4_2005_01_IRON%20CANNONS%20OF%20CHINA.pdf`
- mapped variants:
  - `ijhs/Vol4_2005_01_IRON%20CANNONS%20OF%20CHINA.pdf` -> doc_id=`Vol4_2005_01_IRON%20CANNONS%20OF%20CHINA`, asset_role=`primary_pdf`

### Pair 55
- canonical: `ijhs/Vol4_2005_02_MONSTER%20CANNON%20WROUGHT%20IRON%20BOMBARDS%20OF%20EUROPE.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_02_MONSTER CANNON WROUGHT IRON BOMBARDS OF EUROPE.pdf`
  - `ijhs/Vol4_2005_02_MONSTER%20CANNON%20WROUGHT%20IRON%20BOMBARDS%20OF%20EUROPE.pdf`
- mapped variants:
  - `ijhs/Vol4_2005_02_MONSTER%20CANNON%20WROUGHT%20IRON%20BOMBARDS%20OF%20EUROPE.pdf` -> doc_id=`Vol4_2005_02_MONSTER%20CANNON%20WROUGHT%20IRON%20BOMBARDS%20OF%20EUROPE`, asset_role=`primary_pdf`

### Pair 56
- canonical: `ijhs/Vol4_2005_03_CANNONS%20OF%20EASTERN%20INDIA.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_03_CANNONS OF EASTERN INDIA.pdf`
  - `ijhs/Vol4_2005_03_CANNONS%20OF%20EASTERN%20INDIA.pdf`
- mapped variants:
  - `ijhs/Vol4_2005_03_CANNONS%20OF%20EASTERN%20INDIA.pdf` -> doc_id=`Vol4_2005_03_CANNONS%20OF%20EASTERN%20INDIA`, asset_role=`primary_pdf`

### Pair 57
- canonical: `ijhs/Vol4_2005_04_FORGE%20WELDED%20CANNONS%20IN%20THE%20FORTS%20OF%20KARIMNAGAR%20DISTRICT%20IN%20THE%20ANDHRA%20PRADESH.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_04_FORGE WELDED CANNONS IN THE FORTS OF KARIMNAGAR DISTRICT IN THE ANDHRA PRADESH.pdf`
  - `ijhs/Vol4_2005_04_FORGE%20WELDED%20CANNONS%20IN%20THE%20FORTS%20OF%20KARIMNAGAR%20DISTRICT%20IN%20THE%20ANDHRA%20PRADESH.pdf`
- mapped variants:
  - `ijhs/Vol4_2005_04_FORGE%20WELDED%20CANNONS%20IN%20THE%20FORTS%20OF%20KARIMNAGAR%20DISTRICT%20IN%20THE%20ANDHRA%20PRADESH.pdf` -> doc_id=`Vol4_2005_04_FORGE%20WELDED%20CANNONS%20IN%20THE%20FORTS%20OF%20KARIMNAGAR%20DISTRICT%20IN%20THE%20ANDHRA%20PRADESH`, asset_role=`primary_pdf`

### Pair 58
- canonical: `ijhs/Vol4_2005_05_DEVELOPMENT%20OF%20CANNON%20TECHNOLOGY%20IN%20INDIA.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_05_DEVELOPMENT OF CANNON TECHNOLOGY IN INDIA.pdf`
  - `ijhs/Vol4_2005_05_DEVELOPMENT%20OF%20CANNON%20TECHNOLOGY%20IN%20INDIA.pdf`
- mapped variants:
  - `ijhs/Vol4_2005_05_DEVELOPMENT%20OF%20CANNON%20TECHNOLOGY%20IN%20INDIA.pdf` -> doc_id=`Vol4_2005_05_DEVELOPMENT%20OF%20CANNON%20TECHNOLOGY%20IN%20INDIA`, asset_role=`primary_pdf`

### Pair 59
- canonical: `ijhs/Vol4_2005_06_EPIC%20OF%20SALTPETRE%20TO%20GUNPOWDER.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_06_EPIC OF SALTPETRE TO GUNPOWDER.pdf`
  - `ijhs/Vol4_2005_06_EPIC%20OF%20SALTPETRE%20TO%20GUNPOWDER.pdf`
- mapped variants:
  - `ijhs/Vol4_2005_06_EPIC%20OF%20SALTPETRE%20TO%20GUNPOWDER.pdf` -> doc_id=`Vol4_2005_06_EPIC%20OF%20SALTPETRE%20TO%20GUNPOWDER`, asset_role=`primary_pdf`

### Pair 60
- canonical: `ijhs/Vol4_2005_07_GUNPOWDER%20ARTILLERY%20AND%20MILITARY%20ARCHITECTURE%20IN%20SOUTH%20INDIA%20(15-18TH%20CENTURY).pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_07_GUNPOWDER ARTILLERY AND MILITARY ARCHITECTURE IN SOUTH INDIA (15-18TH CENTURY).pdf`
  - `ijhs/Vol4_2005_07_GUNPOWDER%20ARTILLERY%20AND%20MILITARY%20ARCHITECTURE%20IN%20SOUTH%20INDIA%20(15-18TH%20CENTURY).pdf`
- mapped variants:
  - `ijhs/Vol4_2005_07_GUNPOWDER%20ARTILLERY%20AND%20MILITARY%20ARCHITECTURE%20IN%20SOUTH%20INDIA%20(15-18TH%20CENTURY).pdf` -> doc_id=`Vol4_2005_07_GUNPOWDER%20ARTILLERY%20AND%20MILITARY%20ARCHITECTURE%20IN%20SOUTH%20INDIA%20(15-18TH%20CENTURY)`, asset_role=`primary_pdf`

### Pair 61
- canonical: `ijhs/Vol4_2005_08_FIREPOWER%20CENTRIC%20WARFARE%20IN%20INDIA%20AND%20MILITARY%20MODERNIZATION%20OF%20THE%20MARATHAS%201740-1.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_08_FIREPOWER CENTRIC WARFARE IN INDIA AND MILITARY MODERNIZATION OF THE MARATHAS 1740-1.pdf`
  - `ijhs/Vol4_2005_08_FIREPOWER%20CENTRIC%20WARFARE%20IN%20INDIA%20AND%20MILITARY%20MODERNIZATION%20OF%20THE%20MARATHAS%201740-1.pdf`
- mapped variants:
  - `ijhs/Vol4_2005_08_FIREPOWER%20CENTRIC%20WARFARE%20IN%20INDIA%20AND%20MILITARY%20MODERNIZATION%20OF%20THE%20MARATHAS%201740-1.pdf` -> doc_id=`Vol4_2005_08_FIREPOWER%20CENTRIC%20WARFARE%20IN%20INDIA%20AND%20MILITARY%20MODERNIZATION%20OF%20THE%20MARATHAS%201740-1`, asset_role=`primary_pdf`

### Pair 62
- canonical: `ijhs/Vol4_2005_09_ROCKETS%20UNDER%20HAIDAR%20ALI%20AND%20TIPU%20SULTAN'.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_09_ROCKETS UNDER HAIDAR ALI AND TIPU SULTAN'.pdf`
  - `ijhs/Vol4_2005_09_ROCKETS%20UNDER%20HAIDAR%20ALI%20AND%20TIPU%20SULTAN'.pdf`
- mapped variants:
  - `ijhs/Vol4_2005_09_ROCKETS%20UNDER%20HAIDAR%20ALI%20AND%20TIPU%20SULTAN'.pdf` -> doc_id=`Vol4_2005_09_ROCKETS%20UNDER%20HAIDAR%20ALI%20AND%20TIPU%20SULTAN'`, asset_role=`primary_pdf`

### Pair 63
- canonical: `ijhs/Vol4_2005_10_HISTORICAL%20NOTES_2.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_10_HISTORICAL NOTES_2.pdf`
  - `ijhs/Vol4_2005_10_HISTORICAL%20NOTES_2.pdf`
- mapped variants:
  - `ijhs/Vol4_2005_10_HISTORICAL%20NOTES_2.pdf` -> doc_id=`Vol4_2005_10_HISTORICAL%20NOTES_2`, asset_role=`primary_pdf`

### Pair 64
- canonical: `ijhs/Vol4_2005_10_HISTORICAL%20NOTES_3.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_10_HISTORICAL NOTES_3.pdf`
  - `ijhs/Vol4_2005_10_HISTORICAL%20NOTES_3.pdf`
- mapped variants:
  - `ijhs/Vol4_2005_10_HISTORICAL%20NOTES_3.pdf` -> doc_id=`Vol4_2005_10_HISTORICAL%20NOTES_3`, asset_role=`primary_pdf`

### Pair 65
- canonical: `ijhs/Vol4_2005_11_BOOK%20REVIEW.pdf`
- basis: `currently_mapped_in_canonical_build`
- variants:
  - `ijhs/Vol4_2005_11_BOOK REVIEW.pdf`
  - `ijhs/Vol4_2005_11_BOOK%20REVIEW.pdf`
- mapped variants:
  - `ijhs/Vol4_2005_11_BOOK%20REVIEW.pdf` -> doc_id=`Vol4_2005_11_BOOK%20REVIEW`, asset_role=`primary_pdf`
