---
name: landuse-wmts-to-shp
description: >-
  把內政部國土測繪中心(NLSC)的「國土利用現況調查成果」WMTS(LUIMAP) 以指定縣市裁切、
  向量化成帶 RGB 與調查類別屬性的 Shapefile。當使用者提到「國土利用」「LUIMAP」
  「土地利用調查」「WMTS 轉 SHP」「把某縣市的國土利用下載/裁切/向量化」「國土利用色碼/類別」，
  或想把 NLSC 圖磚轉成可在 QGIS/ArcGIS 用的向量圖層時，務必使用此 skill。
  即使使用者只說「幫我做嘉義市的土地利用 SHP」「下載國土利用圖層轉向量」也適用。
  不適用於非 NLSC 的圖資、或單純瀏覽地圖而不需向量化的情境。
---

# 國土利用調查 WMTS → 行政區裁切向量化 SHP

把 NLSC 的 LUIMAP（已上色影像圖磚）以某縣市範圍下載、拼接、**最近色比對色碼表**還原調查類別、
向量化成 SHP，屬性表含 `lu_code / lu_name / R / G / B / std_RGB`。

## 重要前提與精度說明（先讓使用者知道）
- WMTS 給的是**已上色的點陣影像**，不是原始向量。本流程用「最近色比對」反推類別，
  邊界含 JPEG/PNG 壓縮雜訊與反鋸齒中間色 → 屬**近似成果**（實測單一縣市覆蓋率 ~99%）。
  若使用者要**精確界線**，應改取國土利用調查的**向量原始資料**，本 skill 不適用。
- 支援兩種行政區尺度，用**同一支** `run.py`、只差邊界 SHP 與篩選欄位：
  - **縣市**：內政部 `COUNTY_MOI_*`，篩選欄位 `COUNTYID`（單字母，如 `I`=嘉義市）。
  - **鄉鎮市區**：`鄉鎮界_97TM2`，篩選欄位 `townid`（8 碼，如 `10020001`=嘉義市東區）。
  鄉鎮尺度範圍更小、圖磚更少、更快，且裁切到精確鄉鎮界。
- 環境用 **QGIS 內建的 GDAL/Python**（透過 `scripts/env.bat`），不要用系統 Python
  另裝 gdal/rasterio（常因版本/wheel 失敗）。

## 需要的輸入
1. 行政區界 SHP：縣市界或鄉鎮界（依使用者要的尺度）。若沒提供，先問路徑。
2. 目標行政區的 **ASCII 代碼**：縣市用 `COUNTYID`、鄉鎮用 `townid`。
   - 使用者通常給**中文名稱**（如「嘉義市東區」「花蓮市」）。中文做 `-where` 易因 DBF 編碼
     出錯，所以**先用 `scripts/find_id.py` 把名稱對到 ASCII 代碼**，再餵 run.py：
     ```bat
     scripts\env.bat python scripts\find_id.py --shp "<鄉鎮SHP>" --query 嘉義市東區
     ```
     它會列出 `townid=...`，挑對的那筆。縣市對照另見 `references/countyid.md`。
   - 注意：鄉鎮界中部分離島鄉鎮(如東石鄉、澎湖各鄉)會有**多筆同 townid** 的多邊形，
     `--filter-value` 用該 townid 會一次涵蓋全部，正常。
3. 色碼表 CSV：預設用內附 `references/luimap_colortable.csv`（109 年版）。除非另給，用這份。
4. zoom 等級（預設 16）。

## 執行步驟
1. **確認環境**：執行 `scripts\env.bat gdalinfo --version`。若報錯找不到 QGIS，
   提醒使用者需安裝 QGIS 3.x（env.bat 會自動挑版本最高、含 `bin\o4w_env.bat` 的安裝）。
2. **解析代碼**：用 `find_id.py`（見上）把使用者給的中文行政區名對到 `COUNTYID`/`townid`。
   不確定欄位時可 `scripts\env.bat ogrinfo -al -so <SHP>` 看 schema。
3. **跑整條流程**（單一指令，內含 取界→抓圖→分類→向量化→裁切→輸出）：
   ```bat
   :: 縣市
   scripts\env.bat python scripts\run.py ^
     --boundary-shp "<縣市SHP>" --filter-field COUNTYID --filter-value I ^
     --zoom 16 --colortable "<skill>\references\luimap_colortable.csv" ^
     --out "output\<縣市>_landuse.shp"
   :: 鄉鎮市區
   scripts\env.bat python scripts\run.py ^
     --boundary-shp "<鄉鎮SHP>" --filter-field townid --filter-value 10020001 ^
     --zoom 16 --colortable "<skill>\references\luimap_colortable.csv" ^
     --out "output\<鄉鎮>_landuse.shp"
   ```
   大範圍（直轄市）會抓上萬張圖磚、需時較久，建議在背景執行並回報進度；
   必要時先用 `--zoom 15` 試跑。
4. **驗證**：用 `ogrinfo -al -so <out>` 確認 Feature Count 與欄位；
   可選擇把屬性 RGB 還原柵格化跟原始 WMTS 視覺比對（腳本見
   [references/verify_rgb.md](references/verify_rgb.md)），
   並列出各類別面積佔比做 sanity check（城市應以住宅/道路/農地為大宗）。

## 主要參數（run.py）
| 參數 | 說明 | 預設 |
|------|------|------|
| `--boundary-shp` | 行政區界 SHP（縣市界或鄉鎮界） | 必填 |
| `--filter-field` | 篩選欄位：縣市 `COUNTYID`、鄉鎮 `townid` | 必填 |
| `--filter-value` | 代碼值，如 `I` 或 `10020001`（用 find_id.py 查） | 必填 |
| `--zoom` | 圖磚等級（15 粗 / 16 平衡 / 17-18 細） | `16` |
| `--colortable` | 色碼表 CSV | 必填（用內附） |
| `--out` | 輸出 SHP 路徑 | 必填 |
| `--target-epsg` | 輸出座標系 | `3826`（TWD97/TM2） |
| `--sieve` | 去雜點門檻(像素)，調大→邊界碎面變少但犧牲細節 | `8` |
| `--workdir` | 中繼檔資料夾（圖磚快取於此，可續跑） | 暫存資料夾 |

## 輸出
- `output\<縣市>_landuse.shp`（EPSG:3826、UTF-8、含 .cpg）
- 屬性：`classid`(內部索引)、`lu_code`(保留前導零)、`lu_name`(中文)、`R`、`G`、`B`、
  `std_RGB`（格式 `R,G,B`，如 `166,205,233`）

## 疑難排解
- **找不到 osgeo / numpy**：沒透過 `env.bat` 跑，或 QGIS 沒裝。一律用 `scripts\env.bat python ...`。
- **`import inspect` 之類 stdlib 衝突**：別把工作腳本命名成 stdlib 同名（如 `inspect.py`）。
- **縣市篩不到**：欄位名不對，用 `--filter-field` 指定正確欄位；或值含前導零要用字串（如 `10020`）。
- **顏色對不上 / 類別怪**：色碼表 RGB 必須與 WMTS 算圖一致；不同年版色碼不同，
  確認用對年版的色碼表（內附為 109 年版）。
