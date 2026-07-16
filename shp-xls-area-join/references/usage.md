# area_join_shp.py — usage & troubleshooting

## Dependencies

```powershell
python -m pip install geopandas pandas numpy xlrd openpyxl
```

- `xlrd` is needed for legacy `.xls`; `openpyxl` for `.xlsx`.
- `geopandas` pulls in `fiona`/`pyogrio` + `shapely` for reading/writing SHP & GPKG.

## Command reference

```
python scripts/area_join_shp.py TARGET [--xls XLS] [options]
```

`TARGET` is either a **folder** (batch mode — every `.xls`/`.xlsx` in it is paired
and processed) or a **single `.shp`/`.zip`** (then `--xls` is required).

| Flag | Default | Meaning |
|------|---------|---------|
| `--xls PATH` | — | XLS/XLSX for single-file mode |
| `--out-dir DIR` | `output` | where new files are written |
| `--join-col NAME` | `向量面積` | XLS column holding the area to match |
| `--tol FLOAT` | `0.05` | absolute area match tolerance, m² |
| `--only-xls-cols` | off | output geometry + XLS columns only (drop shp styling) |
| `--driver NAME` | `ESRI Shapefile` | or `GPKG` (no 10-byte field-name limit, UTF-8) |
| `--epsg INT` | — | assign a CRS when the source has no `.prj` |
| `--suffix STR` | `_面積join` | appended to each output basename |

Exit code is non-zero if any polygon went unmatched, so a wrapping script won't
mistake a partial join for success.

## Pairing logic

For each XLS with basename `B`, geometry is resolved in this order:

1. `B.shp` in the same folder
2. `B.zip` in the same folder → extracted to a temp dir, the `.shp` inside is used
   (its internal name is ignored — a zip commonly holds `..._POLYGON.shp`)
3. subfolder `B/` containing a `.shp`

A zip with several `.shp` uses the first and warns.

## The join, precisely

1. Read the shp; if it has no CRS and `--epsg` was given, assign it.
2. Read the XLS and repair BIG5 mojibake (see below).
3. Compute `geometry.area` per polygon.
4. `pandas.merge_asof(direction="nearest", tolerance=tol)` on area ↔ `向量面積`.
   Nearest-value, so rounding noise (~0.01 m²) still matches while distinct parcels
   (metres² apart) never cross-match.
5. Attach every XLS column to the polygons; write with a BIG5 `.cpg`.

Multiple polygons matching one XLS row (one-to-many) is expected for split parcels.

## Encoding repair

`.xls` read through `xlrd` often returns BIG5 bytes that were decoded as latin1 —
column names and cells look like `¿ì¤½«Ç`. The script detects this (latin1-range or
`�` characters with no CJK present) and repairs it via
`s.encode("latin1").decode("big5")`. Strings that are already valid UTF-8/CJK are left
untouched, so the same code path is safe for `.xlsx` and for correctly-encoded files.

If you ever see mojibake in the output, read a couple of raw cells manually and confirm
the true encoding; adjust the decode target if a source is GBK/UTF-8 rather than BIG5.

## Troubleshooting

- **`join column '向量面積' not in XLS`** — the area column is named differently. List
  the columns (the error prints them) and pass `--join-col "<name>"`. Candidates seen
  in the wild: `向量面積`, `標示面積` (registered area — usually *not* the geometry
  area, so prefer 向量面積 when both exist).
- **Low match rate / `[WARN] N unmatched`** — first raise `--tol` to `0.1`, `0.5`.
  If large gaps remain, the shp and xls may be different datasets, the shp CRS may be
  geographic (degrees → tiny areas) rather than projected metres, or `--join-col` is
  the wrong column. Check `get_layer_crs` in QGIS; areas must be in m².
- **Chinese shows as `?` or boxes in QGIS** — confirm the `.cpg` next to the output
  says `BIG5`. The script writes it; some workflows overwrite it.
- **Truncated field names** — shapefile caps DBF names at 10 bytes. Use
  `--driver GPKG` to keep full Chinese headers.
- **Ambiguous equal-area parcels (`[note]`)** — inherent to an area-only join; there
  is no other shared key. Surface the count to the user instead of implying exactness.

## Reproducing the reference result

On the 圖資對應 sample folder the batch run yields, with no extra flags:

```
20260713_2026-07-13.xls  → 145 polygons, 145 rows, matched 145/145
周邊地籍.xls              → 1020 polygons, 875 rows, matched 1020/1020
```
