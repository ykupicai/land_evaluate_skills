# COUNTYID 對照表 (COUNTY_MOI 內政部縣市界)

`run.py` 用 `--filter-field COUNTYID --filter-value <代碼>` 指定範圍（代碼為單一字母）。

| ID | 縣市 | ID | 縣市 |
|----|------|----|------|
| A | 臺北市 | N | 彰化縣 |
| B | 臺中市 | O | 新竹市 |
| C | 基隆市 | P | 雲林縣 |
| D | 臺南市 | Q | 嘉義縣 |
| E | 高雄市 | T | 屏東縣 |
| F | 新北市 | U | 花蓮縣 |
| G | 宜蘭縣 | V | 臺東縣 |
| H | 桃園市 | W | 金門縣 |
| I | 嘉義市 | X | 澎湖縣 |
| J | 新竹縣 | Z | 連江縣 |
| K | 苗栗縣 | | |
| M | 南投縣 | | |

備註:
- 若使用者只給中文縣市名，先用 `ogrinfo -al -so <shp>` 或開 SHP 確認可用欄位；
  COUNTYNAME 為 Big5/UTF-8 中文，直接用中文做 `-where` 容易因編碼出錯，
  建議優先用 ASCII 的 `COUNTYID` 或 `COUNTYCODE`。
- 不同年份的縣市界檔欄位名可能不同（COUNTYID / COUNTYCODE / COUNTY_ID）；
  可用 `--filter-field` 指定，例如 `--filter-field COUNTYCODE --filter-value 10020`。

## 範圍大小與時間 (z16 參考)
- 小範圍 (連江/澎湖/金門/嘉義市/基隆市/新竹市): 數百張圖磚，約 2–4 分鐘。
- 一般縣 (宜蘭/彰化/雲林…): 數千張，約 10–30 分鐘。
- 大直轄市 (臺中/高雄/臺南/桃園): 上萬張，可能 30 分鐘以上，建議先用 z15 或分區。
