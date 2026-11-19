# Measurement report 2026-11-10

**Environment:** Linux 6.6.87.2-microsoft-standard-WSL2 · x86_64 · 16 cores · 15.6 GB RAM · Python 3.12.3

**Repetitions per measurement:** 3 (median shown)

### Reading

| File | Kind | Pages | Words | Median | per page | Budget |
|---|---|--:|--:|--:|--:|:--:|
| `artikel_cp1252.csv` | sheet | 1 | 30 | 2.9 ms | 2.9 ms | ✓ |
| `artikel_utf8.csv` | sheet | 1 | 25 | 0.4 ms | 0.4 ms | ✓ |
| `empty_workbook.xlsx` | sheet | 1 | 0 | 2.7 ms | 2.7 ms | ✓ |
| `positionen.xlsx` | sheet | 3 | 38 | 4.7 ms | 1.6 ms | ✓ |
| `rechnung_din5008.pdf` | pdf | 1 | 100 | 26.6 ms | 26.6 ms | ✓ |
| `rechnung_mehrseitig.pdf` | pdf | 3 | 243 | 83.9 ms | 28.0 ms | ✓ |
| `rechnung_mehrseitig.tiff` | image | 2 | 200 | 4618.8 ms | 2309.4 ms | ❌ |
| `rechnung_scan_150dpi.png` | image | 1 | 100 | 1017.5 ms | 1017.5 ms | ❌ |
| `rechnung_scan_300dpi.png` | image | 1 | 100 | 1196.4 ms | 1196.4 ms | ❌ |
| `rotationen.pdf` | pdf | 4 | 16 | 7.2 ms | 1.8 ms | ✓ |

### Rendering

| File | Kind | Pages | Words | Median | per page | Budget |
|---|---|--:|--:|--:|--:|:--:|
| `rechnung_din5008.pdf (Rendern, 2×)` | render | 1 | 100 | 32.3 ms | 32.3 ms | ✓ |
| `rechnung_mehrseitig.pdf (Rendern, 2×)` | render | 1 | 243 | 26.4 ms | 26.4 ms | ✓ |
| `rotationen.pdf (Rendern, 2×)` | render | 1 | 16 | 23.9 ms | 23.9 ms | ✓ |

### Steps from file to reviewable result

| File | Text from | Kind | File stable (assumed) | Parse | OCR | Recognition | Extraction | Total |
|---|---|---|--:|--:|--:|--:|--:|--:|
| `both_policy_and_invoice.pdf` | text_layer | none | 1000 ms | 8.3 ms | 0.0 ms | 0.5 ms | 0.0 ms | 1008.8 ms |
| `contract_change_a_1.pdf` | text_layer | contract_change | 1000 ms | 26.2 ms | 0.0 ms | 0.9 ms | 7.7 ms | 1034.8 ms |
| `contract_change_a_1_scan300.png` | ocr | contract_change | 1000 ms | 65.6 ms | 1232.3 ms | 1.3 ms | 9.3 ms | 2308.4 ms |
| `contract_change_a_2.pdf` | text_layer | contract_change | 1000 ms | 26.2 ms | 0.0 ms | 1.2 ms | 8.7 ms | 1036.2 ms |
| `contract_change_a_2_scan150.png` | ocr | contract_change | 1000 ms | 12.0 ms | 944.1 ms | 1.1 ms | 7.5 ms | 1964.8 ms |
| `contract_change_a_3.pdf` | text_layer | contract_change | 1000 ms | 28.7 ms | 0.0 ms | 1.2 ms | 9.9 ms | 1039.8 ms |
| `contract_change_a_4.pdf` | text_layer | contract_change | 1000 ms | 26.3 ms | 0.0 ms | 1.3 ms | 8.3 ms | 1035.9 ms |
| `contract_change_b_1.pdf` | text_layer | contract_change | 1000 ms | 22.8 ms | 0.0 ms | 1.2 ms | 9.7 ms | 1033.7 ms |
| `contract_change_b_1_scan300.png` | ocr | contract_change | 1000 ms | 65.4 ms | 1190.6 ms | 1.0 ms | 11.6 ms | 2268.5 ms |
| `contract_change_b_2.pdf` | text_layer | contract_change | 1000 ms | 22.2 ms | 0.0 ms | 1.4 ms | 10.7 ms | 1034.2 ms |
| `contract_change_b_2_scan150.png` | ocr | contract_change | 1000 ms | 12.5 ms | 679.9 ms | 1.0 ms | 8.2 ms | 1701.5 ms |
| `contract_change_b_3.pdf` | text_layer | contract_change | 1000 ms | 14.7 ms | 0.0 ms | 0.8 ms | 8.4 ms | 1023.9 ms |
| `contract_change_b_4.pdf` | text_layer | contract_change | 1000 ms | 13.9 ms | 0.0 ms | 0.8 ms | 7.3 ms | 1021.9 ms |
| `contract_change_c_1.pdf` | text_layer | contract_change | 1000 ms | 13.9 ms | 0.0 ms | 0.7 ms | 4.7 ms | 1019.2 ms |
| `contract_change_c_1_scan300.png` | ocr | contract_change | 1000 ms | 57.8 ms | 918.7 ms | 0.9 ms | 5.6 ms | 1983.0 ms |
| `contract_change_c_2.pdf` | text_layer | contract_change | 1000 ms | 20.7 ms | 0.0 ms | 1.0 ms | 7.0 ms | 1028.7 ms |
| `contract_change_c_2_scan150.png` | ocr | contract_change | 1000 ms | 11.2 ms | 656.5 ms | 0.8 ms | 5.0 ms | 1673.4 ms |
| `contract_change_c_3.pdf` | text_layer | contract_change | 1000 ms | 14.1 ms | 0.0 ms | 0.7 ms | 4.9 ms | 1019.7 ms |
| `contract_change_c_4.pdf` | text_layer | contract_change | 1000 ms | 15.5 ms | 0.0 ms | 0.8 ms | 5.7 ms | 1022.0 ms |
| `contract_change_d_1.pdf` | text_layer | contract_change | 1000 ms | 19.0 ms | 0.0 ms | 1.0 ms | 9.6 ms | 1029.5 ms |
| `contract_change_d_1_scan300.png` | ocr | contract_change | 1000 ms | 61.8 ms | 1152.6 ms | 1.1 ms | 11.5 ms | 2227.0 ms |
| `contract_change_d_2.pdf` | text_layer | contract_change | 1000 ms | 16.2 ms | 0.0 ms | 0.8 ms | 7.7 ms | 1024.8 ms |
| `contract_change_d_2_scan150.png` | ocr | contract_change | 1000 ms | 11.2 ms | 807.8 ms | 0.9 ms | 8.6 ms | 1828.4 ms |
| `contract_change_d_3.pdf` | text_layer | contract_change | 1000 ms | 15.8 ms | 0.0 ms | 0.9 ms | 9.8 ms | 1026.5 ms |
| `contract_change_d_4.pdf` | text_layer | contract_change | 1000 ms | 18.8 ms | 0.0 ms | 0.8 ms | 10.3 ms | 1029.8 ms |
| `contract_change_e_1.pdf` | text_layer | contract_change | 1000 ms | 15.1 ms | 0.0 ms | 0.8 ms | 7.8 ms | 1023.7 ms |
| `contract_change_e_1_scan300.png` | ocr | none | 1000 ms | 58.8 ms | 851.1 ms | 0.8 ms | 0.0 ms | 1910.8 ms |
| `contract_change_e_2.pdf` | text_layer | contract_change | 1000 ms | 14.1 ms | 0.0 ms | 0.7 ms | 6.9 ms | 1021.7 ms |
| `contract_change_e_2_scan150.png` | ocr | contract_change | 1000 ms | 11.5 ms | 636.0 ms | 0.9 ms | 7.8 ms | 1656.1 ms |
| `contract_change_e_3.pdf` | text_layer | contract_change | 1000 ms | 16.3 ms | 0.0 ms | 0.8 ms | 8.9 ms | 1026.1 ms |
| `contract_change_e_4.pdf` | text_layer | contract_change | 1000 ms | 19.3 ms | 0.0 ms | 0.8 ms | 7.1 ms | 1027.2 ms |
| `neither_claim_report.pdf` | text_layer | none | 1000 ms | 5.7 ms | 0.0 ms | 0.4 ms | 0.0 ms | 1006.2 ms |
| `policy_a_1.pdf` | text_layer | policy | 1000 ms | 15.2 ms | 0.0 ms | 0.7 ms | 5.2 ms | 1021.1 ms |
| `policy_a_1_scan300.png` | ocr | policy | 1000 ms | 60.8 ms | 942.7 ms | 1.1 ms | 4.7 ms | 2009.2 ms |
| `policy_a_2.pdf` | text_layer | policy | 1000 ms | 16.8 ms | 0.0 ms | 0.8 ms | 4.8 ms | 1022.4 ms |
| `policy_a_2_scan150.png` | ocr | policy | 1000 ms | 11.7 ms | 759.9 ms | 0.8 ms | 8.1 ms | 1780.6 ms |
| `policy_a_3.pdf` | text_layer | policy | 1000 ms | 21.9 ms | 0.0 ms | 1.2 ms | 4.7 ms | 1027.8 ms |
| `policy_a_4.pdf` | text_layer | policy | 1000 ms | 21.1 ms | 0.0 ms | 0.8 ms | 5.6 ms | 1027.5 ms |
| `policy_b_1.pdf` | text_layer | policy | 1000 ms | 18.7 ms | 0.0 ms | 1.1 ms | 8.5 ms | 1028.3 ms |
| `policy_b_1_scan300.png` | ocr | policy | 1000 ms | 62.2 ms | 975.8 ms | 1.2 ms | 8.6 ms | 2047.9 ms |
| `policy_b_2.pdf` | text_layer | policy | 1000 ms | 15.6 ms | 0.0 ms | 0.8 ms | 6.9 ms | 1023.2 ms |
| `policy_b_2_scan150.png` | ocr | policy | 1000 ms | 13.2 ms | 736.0 ms | 1.3 ms | 8.9 ms | 1759.4 ms |
| `policy_b_3.pdf` | text_layer | policy | 1000 ms | 31.0 ms | 0.0 ms | 1.5 ms | 11.6 ms | 1044.1 ms |
| `policy_b_4.pdf` | text_layer | policy | 1000 ms | 24.7 ms | 0.0 ms | 1.2 ms | 9.3 ms | 1035.2 ms |
| `policy_c_1.pdf` | text_layer | policy | 1000 ms | 19.1 ms | 0.0 ms | 1.1 ms | 5.2 ms | 1025.4 ms |
| `policy_c_1_scan300.png` | ocr | policy | 1000 ms | 58.1 ms | 1076.9 ms | 1.1 ms | 4.0 ms | 2140.1 ms |
| `policy_c_2.pdf` | text_layer | policy | 1000 ms | 23.5 ms | 0.0 ms | 1.1 ms | 6.1 ms | 1030.7 ms |
| `policy_c_2_scan150.png` | ocr | policy | 1000 ms | 12.0 ms | 740.7 ms | 0.8 ms | 4.5 ms | 1758.1 ms |
| `policy_c_3.pdf` | text_layer | policy | 1000 ms | 16.7 ms | 0.0 ms | 0.8 ms | 4.6 ms | 1022.1 ms |
| `policy_c_4.pdf` | text_layer | policy | 1000 ms | 16.5 ms | 0.0 ms | 0.7 ms | 3.9 ms | 1021.2 ms |
| `policy_d_1.pdf` | text_layer | policy | 1000 ms | 18.7 ms | 0.0 ms | 0.9 ms | 8.6 ms | 1028.1 ms |
| `policy_d_1_scan300.png` | ocr | policy | 1000 ms | 55.9 ms | 1000.1 ms | 1.0 ms | 7.3 ms | 2064.3 ms |
| `policy_d_2.pdf` | text_layer | policy | 1000 ms | 16.5 ms | 0.0 ms | 0.8 ms | 7.3 ms | 1024.6 ms |
| `policy_d_2_scan150.png` | ocr | policy | 1000 ms | 12.2 ms | 961.4 ms | 0.9 ms | 8.1 ms | 1982.6 ms |
| `policy_d_3.pdf` | text_layer | policy | 1000 ms | 18.0 ms | 0.0 ms | 0.8 ms | 10.0 ms | 1028.9 ms |
| `policy_d_4.pdf` | text_layer | policy | 1000 ms | 23.8 ms | 0.0 ms | 1.4 ms | 9.5 ms | 1034.7 ms |
| `policy_e_1.pdf` | text_layer | policy | 1000 ms | 19.6 ms | 0.0 ms | 0.9 ms | 7.1 ms | 1027.6 ms |
| `policy_e_1_scan300.png` | ocr | policy | 1000 ms | 66.3 ms | 1055.0 ms | 1.2 ms | 7.4 ms | 2129.9 ms |
| `policy_e_2.pdf` | text_layer | policy | 1000 ms | 13.6 ms | 0.0 ms | 0.7 ms | 6.0 ms | 1020.4 ms |
| `policy_e_2_scan150.png` | ocr | policy | 1000 ms | 11.4 ms | 708.3 ms | 0.9 ms | 9.3 ms | 1729.9 ms |
| `policy_e_3.pdf` | text_layer | policy | 1000 ms | 21.2 ms | 0.0 ms | 0.8 ms | 7.6 ms | 1029.6 ms |
| `policy_e_4.pdf` | text_layer | policy | 1000 ms | 21.9 ms | 0.0 ms | 1.0 ms | 9.2 ms | 1032.2 ms |
| `premium_invoice_a_1.pdf` | text_layer | premium_invoice | 1000 ms | 29.1 ms | 0.0 ms | 1.1 ms | 10.7 ms | 1040.9 ms |
| `premium_invoice_a_1_scan300.png` | ocr | premium_invoice | 1000 ms | 60.4 ms | 1098.6 ms | 0.9 ms | 6.1 ms | 2165.9 ms |
| `premium_invoice_a_2.pdf` | text_layer | premium_invoice | 1000 ms | 18.4 ms | 0.0 ms | 0.8 ms | 5.2 ms | 1024.3 ms |
| `premium_invoice_a_2_scan150.png` | ocr | premium_invoice | 1000 ms | 11.9 ms | 680.3 ms | 0.8 ms | 5.5 ms | 1698.6 ms |
| `premium_invoice_a_3.pdf` | text_layer | premium_invoice | 1000 ms | 18.5 ms | 0.0 ms | 0.8 ms | 5.5 ms | 1024.8 ms |
| `premium_invoice_a_4.pdf` | text_layer | premium_invoice | 1000 ms | 14.8 ms | 0.0 ms | 0.7 ms | 5.1 ms | 1020.7 ms |
| `premium_invoice_b_1.pdf` | text_layer | premium_invoice | 1000 ms | 13.8 ms | 0.0 ms | 0.7 ms | 7.8 ms | 1022.3 ms |
| `premium_invoice_b_1_scan300.png` | ocr | premium_invoice | 1000 ms | 63.7 ms | 1002.3 ms | 1.1 ms | 10.4 ms | 2077.4 ms |
| `premium_invoice_b_2.pdf` | text_layer | premium_invoice | 1000 ms | 18.0 ms | 0.0 ms | 0.8 ms | 10.6 ms | 1029.4 ms |
| `premium_invoice_b_2_scan150.png` | ocr | premium_invoice | 1000 ms | 11.7 ms | 636.1 ms | 0.9 ms | 8.8 ms | 1657.5 ms |
| `premium_invoice_b_3.pdf` | text_layer | premium_invoice | 1000 ms | 20.9 ms | 0.0 ms | 1.1 ms | 10.5 ms | 1032.4 ms |
| `premium_invoice_b_4.pdf` | text_layer | premium_invoice | 1000 ms | 17.3 ms | 0.0 ms | 0.8 ms | 7.6 ms | 1025.7 ms |
| `premium_invoice_c_1.pdf` | text_layer | premium_invoice | 1000 ms | 22.8 ms | 0.0 ms | 0.8 ms | 6.4 ms | 1030.0 ms |
| `premium_invoice_c_1_scan300.png` | ocr | premium_invoice | 1000 ms | 55.2 ms | 1050.5 ms | 0.9 ms | 8.7 ms | 2115.3 ms |
| `premium_invoice_c_2.pdf` | text_layer | premium_invoice | 1000 ms | 17.6 ms | 0.0 ms | 0.8 ms | 6.2 ms | 1024.5 ms |
| `premium_invoice_c_2_scan150.png` | ocr | premium_invoice | 1000 ms | 11.2 ms | 692.1 ms | 1.0 ms | 6.5 ms | 1710.8 ms |
| `premium_invoice_c_3.pdf` | text_layer | premium_invoice | 1000 ms | 20.0 ms | 0.0 ms | 0.8 ms | 6.5 ms | 1027.4 ms |
| `premium_invoice_c_4.pdf` | text_layer | premium_invoice | 1000 ms | 21.3 ms | 0.0 ms | 1.2 ms | 7.5 ms | 1030.0 ms |
| `premium_invoice_d_1.pdf` | text_layer | premium_invoice | 1000 ms | 20.7 ms | 0.0 ms | 0.9 ms | 9.8 ms | 1031.4 ms |
| `premium_invoice_d_1_scan300.png` | ocr | premium_invoice | 1000 ms | 57.2 ms | 1215.1 ms | 1.2 ms | 13.3 ms | 2286.8 ms |
| `premium_invoice_d_2.pdf` | text_layer | premium_invoice | 1000 ms | 23.5 ms | 0.0 ms | 1.6 ms | 11.6 ms | 1036.7 ms |
| `premium_invoice_d_2_scan150.png` | ocr | premium_invoice | 1000 ms | 12.2 ms | 738.1 ms | 1.0 ms | 8.8 ms | 1760.1 ms |
| `premium_invoice_d_3.pdf` | text_layer | premium_invoice | 1000 ms | 17.4 ms | 0.0 ms | 0.9 ms | 8.7 ms | 1026.9 ms |
| `premium_invoice_d_4.pdf` | text_layer | premium_invoice | 1000 ms | 23.1 ms | 0.0 ms | 1.4 ms | 11.7 ms | 1036.2 ms |
| `premium_invoice_e_1.pdf` | text_layer | premium_invoice | 1000 ms | 21.0 ms | 0.0 ms | 1.2 ms | 10.1 ms | 1032.3 ms |
| `premium_invoice_e_1_scan300.png` | ocr | premium_invoice | 1000 ms | 57.0 ms | 939.8 ms | 0.9 ms | 8.8 ms | 2006.5 ms |
| `premium_invoice_e_2.pdf` | text_layer | premium_invoice | 1000 ms | 13.9 ms | 0.0 ms | 0.8 ms | 6.7 ms | 1021.4 ms |
| `premium_invoice_e_2_scan150.png` | ocr | premium_invoice | 1000 ms | 11.9 ms | 760.3 ms | 1.2 ms | 10.8 ms | 1784.1 ms |
| `premium_invoice_e_3.pdf` | text_layer | premium_invoice | 1000 ms | 16.9 ms | 0.0 ms | 0.9 ms | 7.4 ms | 1025.3 ms |
| `premium_invoice_e_4.pdf` | text_layer | premium_invoice | 1000 ms | 14.8 ms | 0.0 ms | 0.8 ms | 6.9 ms | 1022.5 ms |

- 62 one-page text-layer PDFs: median 1027 ms, slowest 1044 ms, 62 of 62 within 3000 ms.
- 30 one-page scans read by OCR: median 1974 ms, slowest 2308 ms, 30 of 30 within 3000 ms.
- Each total contains 1000 ms for “file stable”. That wait is an assumption until the folder watcher exists; the other steps are measured.

> Measured on the development machine. The target is a 16 GB laptop without a GPU and may be slower.
