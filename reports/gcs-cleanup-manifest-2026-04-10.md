# GCS Cleanup Manifest

- bucket root: `gs://cahcblr-pdfs/assets`
- duplicate pair count: 65
- pairs with both variants in GCS: 65
- pairs with only canonical in GCS: 0
- pairs with partial/missing variant state in GCS: 0
- pending uploads: 2

## Duplicate Cleanup

| # | Canonical | Delete From GCS | Basis |
|---|---|---|---|
| 1 | `gs://cahcblr-pdfs/assets/ijhs/13-Books%20Received%20for%20Review.pdf` | `gs://cahcblr-pdfs/assets/ijhs/13-Books Received for Review.pdf` | `currently_mapped_in_canonical_build` |
| 2 | `gs://cahcblr-pdfs/assets/ijhs/1_PM%20Dolas.pdf` | `gs://cahcblr-pdfs/assets/ijhs/1_PM Dolas.pdf` | `currently_mapped_in_canonical_build` |
| 3 | `gs://cahcblr-pdfs/assets/ijhs/2_NC%20Shah.pdf` | `gs://cahcblr-pdfs/assets/ijhs/2_NC Shah.pdf` | `currently_mapped_in_canonical_build` |
| 4 | `gs://cahcblr-pdfs/assets/ijhs/3_F%20Di%20Giacomo.pdf` | `gs://cahcblr-pdfs/assets/ijhs/3_F Di Giacomo.pdf` | `currently_mapped_in_canonical_build` |
| 5 | `gs://cahcblr-pdfs/assets/ijhs/4_S%20Dasgupta.pdf` | `gs://cahcblr-pdfs/assets/ijhs/4_S Dasgupta.pdf` | `currently_mapped_in_canonical_build` |
| 6 | `gs://cahcblr-pdfs/assets/ijhs/5_P%20Sharma.pdf` | `gs://cahcblr-pdfs/assets/ijhs/5_P Sharma.pdf` | `currently_mapped_in_canonical_build` |
| 7 | `gs://cahcblr-pdfs/assets/ijhs/6_R%20Ghosh.pdf` | `gs://cahcblr-pdfs/assets/ijhs/6_R Ghosh.pdf` | `currently_mapped_in_canonical_build` |
| 8 | `gs://cahcblr-pdfs/assets/ijhs/6__Arnab%20Rai%20Choudhuri.pdf` | `gs://cahcblr-pdfs/assets/ijhs/6__Arnab Rai Choudhuri.pdf` | `currently_mapped_in_canonical_build` |
| 9 | `gs://cahcblr-pdfs/assets/ijhs/7_MA%20Wani.pdf` | `gs://cahcblr-pdfs/assets/ijhs/7_MA Wani.pdf` | `currently_mapped_in_canonical_build` |
| 10 | `gs://cahcblr-pdfs/assets/ijhs/8_S%20Kulangara.pdf` | `gs://cahcblr-pdfs/assets/ijhs/8_S Kulangara.pdf` | `currently_mapped_in_canonical_build` |
| 11 | `gs://cahcblr-pdfs/assets/ijhs/9_B%20Goswami.pdf` | `gs://cahcblr-pdfs/assets/ijhs/9_B Goswami.pdf` | `currently_mapped_in_canonical_build` |
| 12 | `gs://cahcblr-pdfs/assets/ijhs/Cumulative%20Index_58_ijhs.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Cumulative Index_58_ijhs.pdf` | `currently_mapped_in_canonical_build` |
| 13 | `gs://cahcblr-pdfs/assets/ijhs/IJHS_60_3_1.pdf` | `gs://cahcblr-pdfs/assets/ijhs/IJHS_60_3_1_mean_motions.pdf` | `currently_mapped_in_canonical_build_exact_duplicate` |
| 14 | `gs://cahcblr-pdfs/assets/ijhs/Pages%20from%20Vol4_2005_10_HISTORICAL%20NOTES_1.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Pages from Vol4_2005_10_HISTORICAL NOTES_1.pdf` | `currently_mapped_in_canonical_build` |
| 15 | `gs://cahcblr-pdfs/assets/ijhs/Vol1_2005_02_ENVIRONMENT%20AND%20ECOLOGY%20IN%20THE%20RAMAYANA.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol1_2005_02_ENVIRONMENT AND ECOLOGY IN THE RAMAYANA.pdf` | `currently_mapped_in_canonical_build` |
| 16 | `gs://cahcblr-pdfs/assets/ijhs/Vol1_2005_03_MYSTICAL%20MATHEMATICS%20IN%20ANCIENT%20PLANETS.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol1_2005_03_MYSTICAL MATHEMATICS IN ANCIENT PLANETS.pdf` | `currently_mapped_in_canonical_build` |
| 17 | `gs://cahcblr-pdfs/assets/ijhs/Vol1_2005_04_CONGRESS%20AND%20CONSERVATION.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol1_2005_04_CONGRESS AND CONSERVATION.pdf` | `currently_mapped_in_canonical_build` |
| 18 | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_02_MANAGEMENT%20OF%20FISTULA%20IN%20ANO%20IN%20ANCIENT%20GREEK%20AND%20AYURVEDIC%20MEDICINE%20A%20HISTORICAL%20AN.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_02_MANAGEMENT OF FISTULA IN ANO IN ANCIENT GREEK AND AYURVEDIC MEDICINE A HISTORICAL AN.pdf` | `currently_mapped_in_canonical_build` |
| 19 | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_03_HIPPARCHUS'S%203600%20BASED%20CHORD%20TABLE%20AND%20ITS%20PLACE%20IN%20THE%20HISTORY%20OF%20ANCIENT%20GREEK%20AN.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_03_HIPPARCHUS'S 3600 BASED CHORD TABLE AND ITS PLACE IN THE HISTORY OF ANCIENT GREEK AN.pdf` | `currently_mapped_in_canonical_build` |
| 20 | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_04_HINDUS%20SCIENTIFIC%20CONTRIBUTIONS%20IN%20INDO%20CALENDAR.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_04_HINDUS SCIENTIFIC CONTRIBUTIONS IN INDO CALENDAR.pdf` | `currently_mapped_in_canonical_build` |
| 21 | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_05_HISTORICAL%20NOTES_1.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_05_HISTORICAL NOTES_1.pdf` | `currently_mapped_in_canonical_build` |
| 22 | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_05_HISTORICAL%20NOTES_2.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_05_HISTORICAL NOTES_2.pdf` | `currently_mapped_in_canonical_build` |
| 23 | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_06_BOOK%20REVIEW.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol2_2005_06_BOOK REVIEW.pdf` | `currently_mapped_in_canonical_build` |
| 24 | `gs://cahcblr-pdfs/assets/ijhs/Vol31_1_8_SupplementBibliographyon%20MagneticStudies.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol31_1_8_SupplementBibliographyon MagneticStudies.pdf` | `currently_mapped_in_canonical_build` |
| 25 | `gs://cahcblr-pdfs/assets/ijhs/Vol37_1_9_Supplement%20ScientificPeriodicals.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol37_1_9_Supplement ScientificPeriodicals.pdf` | `currently_mapped_in_canonical_build` |
| 26 | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_01_THE%20FIRST%20CATALOGUE%20ON%20FORGE%20WELDED%20IRON%20CANNONS%20BY%20NEOGI.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_01_THE FIRST CATALOGUE ON FORGE WELDED IRON CANNONS BY NEOGI.pdf` | `currently_mapped_in_canonical_build` |
| 27 | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_02_RAJAGOPALA%20THE%20MASSIVE%20IRON%20CANNON%20AT%20THANJAVUR%20IN%20TAMIL%20NADU.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_02_RAJAGOPALA THE MASSIVE IRON CANNON AT THANJAVUR IN TAMIL NADU.pdf` | `currently_mapped_in_canonical_build` |
| 28 | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_03_DAL%20MARDAN%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BISHNUPUR.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_03_DAL MARDAN THE FORGE WELDED IRON CANNON AT BISHNUPUR.pdf` | `currently_mapped_in_canonical_build` |
| 29 | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_04_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20BADA%20BURJ%20OF%20GOLCONDA%20FORT%20RAMPART.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_04_THE FORGE WELDED IRON CANNON AT BADA BURJ OF GOLCONDA FORT RAMPART.pdf` | `currently_mapped_in_canonical_build` |
| 30 | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_05_THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20FATEH%20BURJ%20OF%20GOLCONDA%20FORST%20RAMPART.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_05_THE FORGE WELDED IRON CANNON AT FATEH BURJ OF GOLCONDA FORST RAMPART.pdf` | `currently_mapped_in_canonical_build` |
| 31 | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_06_BHAVANI%20SANKAR%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_06_BHAVANI SANKAR THE FORGE WELDED IRON CANNON AT JHANSI FORT.pdf` | `currently_mapped_in_canonical_build` |
| 32 | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_07_KADAK%20BIJLI%20THE%20FORGE%20WELDED%20IRON%20CANNON%20AT%20JHANSI%20FORT.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_07_KADAK BIJLI THE FORGE WELDED IRON CANNON AT JHANSI FORT.pdf` | `currently_mapped_in_canonical_build` |
| 33 | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_08_AZDAHA%20PAIKAR%20THE%20COMPOSITE%20IRON%20BROZE%20CANNON%20AT%20MUSA%20BURJ%20OF%20GOLCONDA%20FORT.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_08_AZDAHA PAIKAR THE COMPOSITE IRON BROZE CANNON AT MUSA BURJ OF GOLCONDA FORT.pdf` | `currently_mapped_in_canonical_build` |
| 34 | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_09_FATH%20RAIHBAR%20THE%20MASSIVE%20BRONZE%20CANNON%20AT%20PETLA%20BURJ%20OF%20GOLCONDA%20FORT.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_09_FATH RAIHBAR THE MASSIVE BRONZE CANNON AT PETLA BURJ OF GOLCONDA FORT.pdf` | `currently_mapped_in_canonical_build` |
| 35 | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_10_HISTORICAL%20NOTES.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol3_2005_10_HISTORICAL NOTES.pdf` | `currently_mapped_in_canonical_build` |
| 36 | `gs://cahcblr-pdfs/assets/ijhs/Vol41_1_8_Magic%20Square.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol41_1_8_Magic Square.pdf` | `currently_mapped_in_canonical_build` |
| 37 | `gs://cahcblr-pdfs/assets/ijhs/Vol42_3_15_Historical%20NoteRBalasubramaniam.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol42_3_15_Historical NoteRBalasubramaniam.pdf` | `currently_mapped_in_canonical_build` |
| 38 | `gs://cahcblr-pdfs/assets/ijhs/Vol44_1_6_Historical%20Notes.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol44_1_6_Historical Notes.pdf` | `currently_mapped_in_canonical_build` |
| 39 | `gs://cahcblr-pdfs/assets/ijhs/Vol44_1_9_Book%20Review.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol44_1_9_Book Review.pdf` | `currently_mapped_in_canonical_build` |
| 40 | `gs://cahcblr-pdfs/assets/ijhs/Vol44_2_5_PT%20Craddock.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol44_2_5_PT Craddock.pdf` | `currently_mapped_in_canonical_build` |
| 41 | `gs://cahcblr-pdfs/assets/ijhs/Vol44_3_5_Historical%20Notes.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol44_3_5_Historical Notes.pdf` | `currently_mapped_in_canonical_build` |
| 42 | `gs://cahcblr-pdfs/assets/ijhs/Vol44_4_6_Historical%20Notes.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol44_4_6_Historical Notes.pdf` | `currently_mapped_in_canonical_build` |
| 43 | `gs://cahcblr-pdfs/assets/ijhs/Vol46_1_10_Project%20reportAKSeth.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol46_1_10_Project reportAKSeth.pdf` | `currently_mapped_in_canonical_build` |
| 44 | `gs://cahcblr-pdfs/assets/ijhs/Vol46_1_11_Project%20reportSSen.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol46_1_11_Project reportSSen.pdf` | `currently_mapped_in_canonical_build` |
| 45 | `gs://cahcblr-pdfs/assets/ijhs/Vol48_1_13_Form%20IV.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol48_1_13_Form IV.pdf` | `currently_mapped_in_canonical_build` |
| 46 | `gs://cahcblr-pdfs/assets/ijhs/Vol48_3_9_Project%20Reports.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol48_3_9_Project Reports.pdf` | `currently_mapped_in_canonical_build` |
| 47 | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_10_ProjectReport_%20BKSen.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_10_ProjectReport_ BKSen.pdf` | `currently_mapped_in_canonical_build` |
| 48 | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_11_%20News.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_11_ News.pdf` | `currently_mapped_in_canonical_build` |
| 49 | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_3_%20AMSharan.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_3_ AMSharan.pdf` | `currently_mapped_in_canonical_build` |
| 50 | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_6_%20RCGupta.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_6_ RCGupta.pdf` | `currently_mapped_in_canonical_build` |
| 51 | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_8_Book%20Review.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_8_Book Review.pdf` | `currently_mapped_in_canonical_build` |
| 52 | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_9_Project%20Report_%20Jbhattacharyya.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol48_4_9_Project Report_ Jbhattacharyya.pdf` | `currently_mapped_in_canonical_build` |
| 53 | `gs://cahcblr-pdfs/assets/ijhs/Vol49_1_10_Book%20Review.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol49_1_10_Book Review.pdf` | `currently_mapped_in_canonical_build` |
| 54 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_01_IRON%20CANNONS%20OF%20CHINA.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_01_IRON CANNONS OF CHINA.pdf` | `currently_mapped_in_canonical_build` |
| 55 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_02_MONSTER%20CANNON%20WROUGHT%20IRON%20BOMBARDS%20OF%20EUROPE.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_02_MONSTER CANNON WROUGHT IRON BOMBARDS OF EUROPE.pdf` | `currently_mapped_in_canonical_build` |
| 56 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_03_CANNONS%20OF%20EASTERN%20INDIA.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_03_CANNONS OF EASTERN INDIA.pdf` | `currently_mapped_in_canonical_build` |
| 57 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_04_FORGE%20WELDED%20CANNONS%20IN%20THE%20FORTS%20OF%20KARIMNAGAR%20DISTRICT%20IN%20THE%20ANDHRA%20PRADESH.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_04_FORGE WELDED CANNONS IN THE FORTS OF KARIMNAGAR DISTRICT IN THE ANDHRA PRADESH.pdf` | `currently_mapped_in_canonical_build` |
| 58 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_05_DEVELOPMENT%20OF%20CANNON%20TECHNOLOGY%20IN%20INDIA.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_05_DEVELOPMENT OF CANNON TECHNOLOGY IN INDIA.pdf` | `currently_mapped_in_canonical_build` |
| 59 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_06_EPIC%20OF%20SALTPETRE%20TO%20GUNPOWDER.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_06_EPIC OF SALTPETRE TO GUNPOWDER.pdf` | `currently_mapped_in_canonical_build` |
| 60 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_07_GUNPOWDER%20ARTILLERY%20AND%20MILITARY%20ARCHITECTURE%20IN%20SOUTH%20INDIA%20(15-18TH%20CENTURY).pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_07_GUNPOWDER ARTILLERY AND MILITARY ARCHITECTURE IN SOUTH INDIA (15-18TH CENTURY).pdf` | `currently_mapped_in_canonical_build` |
| 61 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_08_FIREPOWER%20CENTRIC%20WARFARE%20IN%20INDIA%20AND%20MILITARY%20MODERNIZATION%20OF%20THE%20MARATHAS%201740-1.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_08_FIREPOWER CENTRIC WARFARE IN INDIA AND MILITARY MODERNIZATION OF THE MARATHAS 1740-1.pdf` | `currently_mapped_in_canonical_build` |
| 62 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_09_ROCKETS%20UNDER%20HAIDAR%20ALI%20AND%20TIPU%20SULTAN'.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_09_ROCKETS UNDER HAIDAR ALI AND TIPU SULTAN'.pdf` | `currently_mapped_in_canonical_build` |
| 63 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_10_HISTORICAL%20NOTES_2.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_10_HISTORICAL NOTES_2.pdf` | `currently_mapped_in_canonical_build` |
| 64 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_10_HISTORICAL%20NOTES_3.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_10_HISTORICAL NOTES_3.pdf` | `currently_mapped_in_canonical_build` |
| 65 | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_11_BOOK%20REVIEW.pdf` | `gs://cahcblr-pdfs/assets/ijhs/Vol4_2005_11_BOOK REVIEW.pdf` | `currently_mapped_in_canonical_build` |

## Pending Uploads

| # | GCS Object | Local Path | Present In GCS | Title |
|---|---|---|---|---|
| 1 | `gs://cahcblr-pdfs/assets/other/A_Comparitive_analysis_of_Kamsavadha_episode_in_Puranic_Texts.pdf` | `/Users/sunder/projects/patra-darpan/corpus/other/A_Comparitive_analysis_of_Kamsavadha_episode_in_Puranic_Texts.pdf` | `False` | A Comparative Analysis of the Kaṁsavadha Episode Across Various Purāṇic Texts |
| 2 | `gs://cahcblr-pdfs/assets/other/The_Scope_of_Ashtadashavarnana.pdf` | `/Users/sunder/projects/patra-darpan/corpus/other/The_Scope_of_Ashtadashavarnana.pdf` | `False` | The Scope of Aṣṭādaśavarṇana in the Mahākāvya Mathurābhyudaya |