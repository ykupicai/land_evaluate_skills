---
name: parcel-map-sheet
description: 以 QGIS 產出地籍/宗地案場的 A4 橫式主題成品圖(出圖),採「最大化地圖＋自動避讓角落疊圖＋右欄只留圖例」版面:比例尺/指北針與位置/涵蓋地號做成地圖角落半透明疊圖並自動挑選不遮基地的角落,基地疊粗紅框並標地號、周邊宗地不上 label,涵蓋地號收合為「段 第一筆 等 N 筆」。當使用者要把基地/周邊地籍圖層排版成列印地圖、做地籍出圖、宗地套繪成果圖、A4 出圖、依出圖清單批次出圖、或延續 shp-xls-area-join 的帶屬性 shp 產出地圖時,務必使用此 skill——即使只說「幫這個案場出圖」「把這批基地做成地圖」「排版成 A4 成果圖」也適用。不適用於單純的資料轉檔(shp/xls/dxf 轉換另有 skill)或不需排版的圖層檢視。
---

# 地籍案場主題出圖(A4 橫式，最大化地圖版面)

把「基地＋周邊地籍(＋功能分區/影像等)」排版成 A4 橫式主題成品圖。本 skill 專責**版面**,
是 `tcdgis-parcels-to-shp` → `shp-xls-area-join` 之後的最後一段:清冊 → 帶屬性 shp → **出圖**。

版面幾何核心 `scripts/overlay_placement.py`(純幾何、已單元測試)＋ QGIS 組裝
`scripts/build_layout.py`(已在真實官田資料端到端算圖驗證)。**用 QGIS 內建 python 執行**:

```powershell
& "C:\Program Files\QGIS 3.40.12\bin\python-qgis-ltr.bat" your_driver.py
```

## 版面規格(定案)

A4 橫式 297×210mm、EPSG:3826、匯出 300 DPI:

- **不放案名/圖名標題列**(使用者定案):圖名由檔名與 `05_出圖清單` 承載,地圖上緣直接
  頂到頁邊。
- **地圖框最大化**:`5,5,240,199` mm(佔頁寬約 81%)。比例尺就近取整(500…5000,超出進位千位)。
- **右欄只留圖例**:`247,5,45,199` mm,依地圖範圍動態過濾(`setLegendFilterByMapEnabled`),
  長標籤依「／」換行。基地層圖層名用「**基地地籍**」(圖例照層名顯示,使用者定案)。
- **角落疊圖，自動避讓基地**(關鍵):
  - 右下疊圖群 = 指北針＋比例尺文字＋比例尺(66×26mm);
  - 左下疊圖群 = 位置＋涵蓋地號(95×20mm);
  - 皆畫在**半透明白底**上,並由 `overlay_placement.place_overlays()` 依右下→左下→右上→左上
    優先序,挑**第一個與基地 dissolve 幾何不相交**的角落。四角皆會遮基地時**退一級比例尺**
    (基地略縮、範圍變大以挪出留白)重試;仍不行才回報 `outside`,交呼叫端**退回右欄底部**外置,
    絕不強行蓋住基地。
- **基地**:疊紅框(**寬 0.5**,使用者定案的細框)並標「地號」label;**周邊宗地不上 label**。
- **周邊地籍/功能分區只留填色、不畫宗地邊線**(使用者定案):套 QML 後對 renderer 把
  SimpleFill 邊線設 NoPen(參考 make_maps 的 `strip_outlines`),灰色地籍界線層不上圖。
- **涵蓋地號收合**:`段 第一筆 等 N 筆`(跨段補「(跨M段)」),用 `build_layout.parcel_note()`;
  完整清單留在 `05_出圖清單`。

「保證基地不被疊圖遮住」不是靠固定角落,而是靠上述**避讓＋必要時退比例尺**——已用真實官田
(四角淨空、1/6000)與合成「基地填滿圖框」(退到 1/9000 才淨空)、極端案(回報 outside)三案驗證。

## 主題與資料來源

主題圖名對照(`THEME_TITLES`,沿用參考案):

| 主題 | 圖名 | 額外資料需求 |
|---|---|---|
| 使用分區 | 非都市土地使用分區及都市計畫土地使用分區圖 | 只需 基地＋周邊(含使分) |
| 使用地編定 | 非都市土地使用地變更編定及都市計畫土地使用分區圖 | 只需 基地＋周邊(含使類) |
| 國土功能分區 | 國土功能分區圖 | 縣市功能分區 shp |
| 正射套疊 | 正射影像及通用電子地圖套疊圖 | NLSC WMTS(PHOTO2＋EMAP) |
| 國土利用調查 | 國土利用調查圖 | LUIMAP 色碼表＋分類結果 |
| 臨路判定 | 臨路判定圖 | 臨路狀態 csv；maxmap 另疊 EMAP2＋外擴圖框 |

**臨路判定(maxmap 定案)**:與其他主題不同,圖框**外擴 `ROAD_MARGIN_M`(預設 700m)**放大,
並疊**臺灣通用電子地圖 EMAP2**(圖層代碼 EMAP2、透明 0.9)於正射上,讓圖面同時看見基地
最近的區道/市道/縣道/鄉道與省道/國道交流道;宗基地仍依臨路狀態上色(綠=臨路、紅=不臨路)、
疊 fishpv 道路。make_maps 為此主題單獨建外擴底圖(`{cid}_臨路PHOTO2/EMAP2.tif`)並以外擴
bbox 出圖(避讓仍以基地計)。要調外擴幅度改 `ROAD_MARGIN_M`。

**使用分區／使用地編定**只靠 `shp-xls-area-join` 的帶屬性基地＋周邊地籍即可出;其餘主題各需
額外圖層。這幾層的抽取、CRS 修正、樣式、動態圖例合成,參考案
`大量圖資轉換工具/scripts/make_maps.py` 已完整實作,出圖時沿用其資料側,版面側換成本 skill。

## 工作流程

1. **備妥圖層**:基地(欄:案場ID/案場名稱/地號/使分/使類)、周邊地籍(欄:地號/使分/使類/是否基地)、
   視主題另備功能分區等。可直接用 `shp-xls-area-join` 的輸出,或參考案的 `圖層.gpkg`。
2. **套樣式**:`styles/*.qml`(使用分區/使用地編定/國土功能分區/周邊地籍/基地紅框/都市計畫)。
   基地紅框層開 地號 label;**周邊層 `setLabelsEnabled(False)`**。
3. **算基地 dissolve 幾何**(`QgsGeometry.unaryUnion`,先 `makeValid()` 每個要素,否則含無效幾何
   會靜默回空、比例尺誤縮到 1/500)＋ 用 `layer.extent()` 取 bbox。
4. **每主題呼叫** `build_layout.build_sheet_layout(...)` 產一個 Layout,`QgsLayoutExporter` 匯出 PNG。
5. **寫 `05_出圖清單`**:`案場ID,案場名稱,主題,檔名,比例尺,涵蓋地號,產出時間,狀態,備註`,
   單張失敗記備註續跑。

可執行的最小範例見 [references/example_driver.py](references/example_driver.py);參數、疑難排解、
與參考案資料側的接法見 [references/usage.md](references/usage.md)。

## 批次出圖（已整合進參考案 make_maps.py）

`大量圖資轉換工具/scripts/make_maps.py` 已加 **`--layout maxmap`** 開關,直接用本版面對整批
案場 × 6 主題批次出圖(沿用它的資料抽取＋WMTS/LUIMAP/臨路下載),並把主題免責說明寫入
`05_出圖清單` 備註欄。`overlay_placement.py`／`build_layout.py` 已 vendor 到該案 `scripts/`。

```powershell
& "C:\Program Files\QGIS 3.40.12\bin\python-qgis-ltr.bat" scripts\make_maps.py <案名> --layout maxmap
```

非破壞:maxmap 成果另存 `圖檔_maxmap/`、`05_出圖清單_maxmap.*`、`<案名>_maxmap.qgz`,不動原
compact 成果;`--layout compact`(預設)維持舊右欄版面可回退。整條「清冊→出圖」端到端流程見
`cadastral-map-pipeline` skill。

## 常見錯誤

- **比例尺莫名變 1/500**:基地含無效幾何,`unaryUnion` 靜默回空 → 先 `makeValid()`,bbox 用 `layer.extent()`。
- **同一 `.gpkg` 跨表讀取整層填色消失**:GDAL 在同 process 對同檔不同表共用連線會壞;每個表格
  各複製一份獨立實體檔再開(參考案 `make_table_copies` 詳述)。
- **基地被角落疊圖遮**:別寫死角落;一定要傳 `base_geom` 給 `build_sheet_layout` 讓它避讓。
- **周邊冒出地號**:周邊層樣式可能自帶 label,載入後務必 `setLabelsEnabled(False)`。
