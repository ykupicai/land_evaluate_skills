---
name: dxf-to-shp
description: Convert ASCII or binary DXF CAD layers into UTF-8 ESRI Shapefiles for QGIS, including recursive INSERT block expansion, point/line/polygon/text separation, curve approximation, CRS assignment, Chinese attribute preservation, and feature-count validation. Use when asked to convert DXF layers to SHP, extract a named CAD layer, fix missing block geometry, preserve Traditional Chinese CAD text, or prepare CAD data for GIS/QGIS. 當使用者提到「DXF 轉 SHP」「CAD 圖層轉 shapefile」「把 DXF 某圖層抽出來」「CAD 圖塊(INSERT)不見了」「保留 CAD 中文字/文字註記」「CAD 轉 GIS/QGIS」時,務必使用此 skill——即使只說「幫我把這個 dxf 轉成 shp」也適用。
---

# DXF to SHP

Use `scripts/dxf_to_shp.py` for deterministic conversion. Prefer it over ad-hoc parsing.

## Workflow

1. Inspect the source and list layers when the requested layer name is uncertain:

   ```powershell
   python scripts/dxf_to_shp.py input.dxf --list-layers
   ```

2. Confirm the coordinate system. Do not guess when spatial alignment matters. Use `--epsg` or copy an existing `.prj` with `--prj-from`.
3. Convert selected layers. Quote paths and layer names containing spaces or Chinese characters:

   ```powershell
   python scripts/dxf_to_shp.py input.dxf --layers "F_水車" --output-dir output --epsg 3826
   ```

4. Keep block grouping enabled by default. Each top-level `INSERT` becomes one multipart feature per geometry type, so the SHP feature count can match the CAD block count. Add `--explode-block-parts` only when every primitive inside each block must become a separate feature.
   Use `--insert-only` when standalone geometry is merely a block-definition sample and the requested result must contain only placed block instances.
5. Review `conversion_report.json`. Compare source entity counts, insert counts, output feature counts, skipped entity types, bounding boxes, and warnings.
6. Open the output in QGIS when available and visually verify location, rotation, scale, text, and completeness.

## Output rules

- Write separate Shapefiles for points, lines, polygons, and text because SHP cannot mix geometry families.
- Write UTF-8 `.cpg` files and preserve Traditional Chinese attributes.
- Expand nested blocks recursively and apply insertion position, X/Y scale, and rotation.
- Store CAD text as point geometry with `TEXT`, `ROTATION`, and `HEIGHT` fields.
- Approximate arcs, circles, ellipses, and splines using `--curve-tolerance`; reduce the value for denser curves.
- Never claim that a conversion is complete when the report contains skipped geometry or a suspicious insert/output count mismatch.

## Common commands

Read [references/usage.md](references/usage.md) when advanced options, dependency setup, field definitions, or troubleshooting are needed.
