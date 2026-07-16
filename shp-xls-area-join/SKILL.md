---
name: shp-xls-area-join
description: Join a geometry-only cadastral Shapefile to its companion XLS/XLSX by matching each polygon's vector area to the spreadsheet's 向量面積 column, then write a new BIG5 Shapefile carrying the parcel attributes (地號, 所有權人, 使用分區, 公告現值...). Use when a folder holds same-basename shp+xls (or zip+xls) pairs where the shp has geometry but no 地號, and the attributes live only in the spreadsheet. 當使用者提到「相同檔名的 shp 及 xls」「用向量面積 join」「把 xls 屬性接到 shp/圖面上」「地籍 shp 沒有地號要從 excel 帶屬性」「面積對應」「shp 與 excel 依面積合併生成新 shp」時,務必使用此 skill——即使只說「幫我把這資料夾的 shp 跟 xls 用面積 join」也適用。不適用於有共同地號/欄位可直接屬性 join 的情形(那用一般 table join 即可)。
---

# SHP × XLS Area Join

Use `scripts/area_join_shp.py` for the join. It is deterministic and handles the
tricky parts (BIG5 double-decode, zip-wrapped geometry, rounding-noise tolerance,
one-to-many parcels). Prefer it over writing ad-hoc pandas/geopandas each time.

## When this applies

A cadastral export arrives as two same-basename files:

- **geometry** — a Shapefile (often zipped) with polygon shapes but only styling
  attributes (`NAME`, `RGB`, `LINE_RGB`, a `公私別` `DESCRIBE` field). It has **no
  地號 and no owner**, so there is nothing to do a normal attribute join on.
- **attributes** — an `.xls`/`.xlsx` with the real parcel data (縣市名稱, 鄉鎮市區,
  地段名稱, 地號, 所有權人, 使用分區, 使用地類別, 公告現值...) plus a `向量面積`
  column holding each parcel's vectorized area in m².

The only key common to both is **area**. This skill matches polygon geometry area
to the `向量面積` column and writes the attributes onto the polygons.

**Common upstream: `tcdgis-parcels-to-shp`.** That skill drives the 國土規劃 圖台 to
turn a parcel list into exactly these two files — a `_POLYGON` shp zip (drawing
attributes only) plus a 匯出Excel with `向量面積` + full attributes. This skill is its
natural second half: `tcdgis-parcels-to-shp` (fetch geometry + attribute XLS) →
`shp-xls-area-join` (join them into an attributed shp). If the zip and Excel were saved
with the same basename, batch mode pairs them automatically; otherwise use single-pair
mode with `--xls`.

**Common downstream: `parcel-map-sheet`.** The attributed shp this skill produces (基地 +
使分/使類) is the input for A4 thematic map sheets. Full chain: `tcdgis-parcels-to-shp` →
`shp-xls-area-join` → `parcel-map-sheet` (出圖).

Add **`--trust-fields`** when the downstream is `make_maps --trust-shp`: it copies the tcdgis
Chinese columns to the `20251201_*` aliases (縣市→_1, 鄉鎮→_2, 地段→_3, 地號→_4, 使分→_6,
使類→_7) that trust mode reads, so the output feeds `make_maps --trust-shp` with no field
renaming. (段號 isn't in the export; trust mode allows it empty.)

## Workflow

1. **Look at the folder first.** Confirm the pairing before running. The pairing is
   by shared basename between the XLS and its geometry, where the geometry may be
   `<base>.shp`, `<base>.zip` (a shp inside), or a subfolder `<base>/`. Note that the
   `.shp` *inside* a zip often has an unrelated internal name (e.g. `..._POLYGON.shp`)
   — pairing is by the container name, not the inner name.

2. **Run the join over the whole folder:**

   ```powershell
   python scripts/area_join_shp.py "<folder>" --out-dir output
   ```

   Or one explicit pair (the geometry may be a `.shp` or a `.zip`):

   ```powershell
   python scripts/area_join_shp.py 周邊地籍.zip --xls 周邊地籍.xls --out-dir output
   ```

3. **Read the printed report.** For each pair it prints `matched N/N`. Aim for a full
   match. Anything unmatched is flagged `[WARN]`; the run exits non-zero so it is not
   silently "done". If polygons go unmatched, raise `--tol` slightly (see below).

4. **Verify in QGIS** (this project has a QGIS MCP). Open the output, confirm the
   Chinese attributes render, and spot-check that a parcel's 地號/所有權人 sits on the
   right polygon.

## Why *nearest* area, not exact equality

`向量面積` is stored rounded (usually 2 dp) while the geometry area is recomputed from
raw coordinates, so they differ by rounding noise — observed max ≈ 0.015 m². An exact
or 2-dp-equality join therefore **drops ~15–20 % of rows**. The script instead does a
nearest-value match within a small absolute tolerance (`--tol`, default **0.05 m²**),
which recovers 100 % while staying far below the area gap between genuinely different
parcels. Don't "fix" a low match rate by rounding both to integers — widen `--tol` a
little instead, and only as much as needed.

## Expected behaviours worth keeping in mind

- **One-to-many is normal.** A parcel split into several polygon features means more
  polygons than XLS rows (e.g. 1020 polygons ↔ 875 parcels). Every polygon still gets
  its parcel's attributes; that is correct, not an error.
- **Ambiguous equal-area parcels.** If two different 地號 share an area within the
  tolerance, an area join genuinely cannot tell them apart. The script prints a
  `[note]` counting such rows so you can disclose the caveat rather than overstate
  precision. There is no geometric key to resolve it — flag it to the user.
- **Empty 所有權人 is real data,** not a join miss — private parcels often leave the
  owner blank in the source XLS.

## 等面積宗地(漁電魚塭常見!)——面積 join 的原理性盲區

分割出的等面積宗地(如三塊厝新段 887-1/2/3 同為 2607.22 m²)nearest-join 會**重複配對**
(同地號指兩個 polygon、有 xls 列沒人領),且幾何面積 vs 向量面積的內部一致性檢查**驗不出來**。
2026-07-16 東石案實測:9 筆等面積中 4 筆被打亂。**唯一可靠解法=趁平台登入態查 CADA
圖徵服務真實幾何改派**:

```js
// TCDGIS 頁內(登入態):以 14 碼 ID(地所2+段4+母4+子4,如 QB145808870001)查真實幾何
var qt=new esri.tasks.QueryTask(responseObject.SearchLayers.CADA+'?token='+layerToken);
var q=new esri.tasks.Query(); q.returnGeometry=true; q.where="ID in ('QB145808870001','...')";
qt.execute(q, cb)  // cb 由 rings 算質心回傳 {id,cx,cy}
```
本機以「真值質心 contains 於哪個 polygon」改派地號。join 後一律跑
`cadastral-map-pipeline/scripts/pipeline_check.py join`(已含重複地號檢查)擋下此問題。

## Output rules

- Preserve the source CRS from its `.prj` (these files are TWD97 TM2 / EPSG:3826). If
  a source lacks a `.prj`, pass `--epsg`.
- Write a **BIG5** `.cpg` and BIG5-encoded DBF so QGIS/ArcGIS read the Chinese.
- Default output keeps the original shp columns **and** appends every XLS column
  (a name clash gets an `_xls` suffix). Use `--only-xls-cols` for geometry + XLS
  attributes only.
- Shapefile DBF field names are capped at 10 bytes (5 Chinese chars). If the XLS has
  longer headers they get truncated with a warning — switch to `--driver GPKG` to keep
  full names and UTF-8. Default stays Shapefile because that is what these jobs expect.
- Never report success while the run exited non-zero or left polygons unmatched.

## Options

Read [references/usage.md](references/usage.md) for the full flag list, dependency
setup, the encoding-repair details, and troubleshooting (wrong `--join-col`, mojibake,
CRS/area-unit mismatches, multi-shp zips).
