# Usage reference

## Dependencies

Use Python 3.10+ with:

```powershell
python -m pip install ezdxf geopandas shapely pyogrio
```

`geopandas` may use Fiona instead of Pyogrio; either engine is acceptable when ESRI Shapefile writing works.

## Examples

List layer names and source counts:

```powershell
python scripts/dxf_to_shp.py "C:\data\drawing.dxf" --list-layers
```

Convert one layer and assign TWD97 / TM2 zone 121:

```powershell
python scripts/dxf_to_shp.py "C:\data\drawing.dxf" --layers "F_水車" --output-dir "C:\data\shp" --epsg 3826
```

Convert several layers and reuse a trusted projection file:

```powershell
python scripts/dxf_to_shp.py input.dxf --layers "W_進水" "W_排水" "W_進排水_TXT" --output-dir output --prj-from known.prj
```

Convert every nonzero layer:

```powershell
python scripts/dxf_to_shp.py input.dxf --all-layers --output-dir output
```

Explode every primitive from each block:

```powershell
python scripts/dxf_to_shp.py input.dxf --layers "F_水車" --output-dir output --explode-block-parts
```

Keep only placed block instances and omit standalone sample geometry:

```powershell
python scripts/dxf_to_shp.py input.dxf --layers "F_水車" --output-dir output --insert-only
```

## Output naming

For each selected CAD layer, the script may create:

- `<layer>_point.shp`: CAD POINT entities and INSERT locations.
- `<layer>_line.shp`: lines, polylines, curves, and grouped block linework.
- `<layer>_polygon.shp`: supported filled/face geometry.
- `<layer>_text.shp`: TEXT and MTEXT insertion points with readable attributes.
- `conversion_report.json`: counts, extents, skipped types, and warnings.

## Important fields

- `CAD_LAYER`: original or effective CAD layer.
- `ETYPE`: original entity type, or `INSERT` for grouped block output.
- `HANDLE`: DXF entity handle when present.
- `BLOCK`: block name for INSERT-derived output.
- `ROTATION`: CAD rotation in degrees.
- `SCALE_X`, `SCALE_Y`: block scale.
- `TEXT`: decoded text content.
- `HEIGHT`: CAD text height.
- `SOURCE`: `NATIVE`, `BLOCK`, `INSERT_PT`, or `BLOCK_TEXT`.

## Troubleshooting

- If line output shows only one symbol while point output contains many locations, the symbols are likely INSERT blocks. Keep default grouping enabled.
- If one extra unplaced symbol remains, it is often standalone sample geometry used to define/check the block. Use `--insert-only` after confirming this in the report or CAD.
- If coordinates are correct but QGIS places the data elsewhere, assign the correct CRS; reprojection and CRS assignment are different operations.
- If Chinese text is garbled before conversion, resave/export the DXF as UTF-8 or use the correct source code page. The script writes UTF-8 but cannot reliably infer every incorrectly decoded source string.
- If a DWG is supplied, convert it to DXF with CAD/ODA/QGIS tools first. This script intentionally reads DXF only.
- If curves look angular, reduce `--curve-tolerance`, for example from `0.05` to `0.01` drawing units.
