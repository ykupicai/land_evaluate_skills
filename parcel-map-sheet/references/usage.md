# parcel-map-sheet — 參數與疑難排解

## 執行環境

必須用 **QGIS 內建 python**(含 PyQGIS)，不是系統 python：

```powershell
$env:PYTHONNOUSERSITE=1; & "C:\Program Files\QGIS 3.40.12\bin\python-qgis-ltr.bat" your_driver.py
```

`scripts/overlay_placement.py` 是純幾何、無 QGIS 相依，可用系統 python + shapely 單獨測試
（`tests/test_overlay_placement.py`）。`scripts/build_layout.py` 需 PyQGIS。

## 版面常數（scripts/overlay_placement.py 開頭，mm）

| 常數 | 值 | 說明 |
|---|---|---|
| `PAGE_W, PAGE_H` | 297, 210 | A4 橫式 |
| `MAP_X, MAP_Y, MAP_W, MAP_H` | 5, 5, 240, 199 | 最大化地圖框(無標題列,頂到頁邊) |
| `LEGEND_X, LEGEND_Y, LEGEND_W, LEGEND_H` | 247, 5, 45, 199 | 右欄只留圖例 |
| `OVERLAY_SCALE_NORTH` | 66×26 | 指北針＋比例尺疊圖框 |
| `OVERLAY_LOC_PARCEL` | 95×20 | 位置＋涵蓋地號疊圖框 |
| `OVERLAY_INSET` | 2 | 疊圖距地圖內邊留白 |
| `SCALE_LEVELS` | 500…5000 | 比例尺階梯（超出進位千位） |
| `CORNER_PRIORITY` | BR,BL,TR,TL | 多角皆淨空時的擺放偏好 |

要「地圖大一點但資訊各歸各位」的保守版面（右欄放圖例＋比例尺＋註記、不用角落疊圖），
把 `MAP_W` 改回 ~214、`LEGEND_X` 改 ~222，並改用參考案 make_maps 的右欄擺法即可。

## 核心 API

`overlay_placement.place_overlays(intersect_area_fn, bbox, overlays=None, max_zoomout=6)`
→ `Placement(assign, scale, extent, zoomed_out, outside)`：
- `intersect_area_fn(x1,y1,x2,y2)`：回傳基地落在該地面矩形內的面積（呼叫端用 shapely 或
  QgsGeometry 實作）。
- 依 `CORNER_PRIORITY` 貪婪指派疊圖到「不壓基地」的角落；四角皆壓則退一級比例尺重試；
  仍不行回 `outside=True`。

`build_layout.build_sheet_layout(project, name, layers, legend_layers,
legend_hide_title, base_geom, bbox, location, parcel_note_text, keep_alive, map_overlay=None)`
→ `(layout, placement)`：組一張 A4 橫式版面（**不放案名/圖名標題列**，使用者定案）。`base_geom` 是基地 dissolve 的 QgsGeometry。
`legend_hide_title` 是要隱藏圖例小標題的圖層名集合。`map_overlay` 可放紅字橫幅（如
「都市土地無使用地編定」）於地圖上緣置中。

`build_layout.parcel_note(section, first_landno, total, extra_sections=0)`
→ `"番子渡頭段 122 等 145 筆"`（跨段補「(跨M段)」）。

## 圖層需求

| 圖層 | 必要欄位 | 樣式 | label |
|---|---|---|---|
| 基地 | 案場ID, 案場名稱, 地號, 使分, 使類 | 基地紅框.qml（紅粗框） | 地號 **開** |
| 周邊地籍 | 地號, 使分, 使類, 是否基地 | 使用分區.qml / 使用地編定.qml | **關**（`setLabelsEnabled(False)`） |
| 功能分區（選） | zone | 國土功能分區.qml | 關 |

樣式檔在參考案 `大量圖資轉換工具/styles/`；使用分區/使用地編定.qml 由該案
`build_legend_styles.py` 從使用者 QGIS 樣式庫產出（含紋理），不要手改。

## 疑難排解

- **比例尺變 1/500（地圖爆縮）**：基地含無效幾何，`QgsGeometry.unaryUnion` 靜默回空幾何、
  bbox 變 0。修法：union 前對每個要素 `makeValid()`，且 bbox 用 `layer.extent()` 而非
  union 的 boundingBox。
- **整層填色不見、只剩紅框/灰線**：同一 `.gpkg` 在同 process 對「不同表」共用 SQLite 連線導致
  crs()/extent() 讀回空值（參考案 Task8 查明，重試無效）。**每個表格各複製一份獨立實體檔**
  再開層。
- **基地被角落疊圖壓到**：務必傳 `base_geom`；`place_overlays` 會避讓，必要時退比例尺；四角
  皆不行才 `outside=True` 退回右欄底部（`build_sheet_layout` 已處理）。
- **周邊冒出地號**：載入 `使用分區.qml` 後樣式可能自帶 label → `neigh.setLabelsEnabled(False)`。
- **中文變方框**：字型用 `Microsoft JhengHei`（已內建於 build_layout）。
- **PNG 匯出報 `ERROR 6 ... update access`**：無害警告；匯出前把舊 png `unlink()` 即可消除。

## 與上游的接法

`tcdgis-parcels-to-shp`（取官方地籍 shp＋屬性 Excel）→ `shp-xls-area-join`（依向量面積 join 成
帶屬性基地 shp）→ **本 skill**（排版出圖）。使用分區/使用地編定兩張圖只需上游產出的基地＋
周邊即可；其餘主題的資料抽取沿用參考案 `大量圖資轉換工具/scripts/make_maps.py`。
