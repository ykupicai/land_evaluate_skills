#!/usr/bin/env python3
"""Convert selected DXF layers to UTF-8 Shapefiles with INSERT expansion."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import ezdxf
    import geopandas as gpd
    from ezdxf.path import from_hatch, make_path
    from shapely.geometry import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Run: python -m pip install ezdxf geopandas shapely pyogrio\n"
        f"Original error: {exc}"
    )


SIDE_EXTENSIONS = (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".fix")


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "_", value).strip(" .")
    return value or "layer"


def xyz2(value) -> tuple[float, float]:
    return float(value[0]), float(value[1])


def entity_base(entity, layer: str, etype: str | None = None) -> dict:
    dxf = entity.dxf
    return {
        "CAD_LAYER": layer,
        "ETYPE": etype or entity.dxftype(),
        "HANDLE": str(getattr(dxf, "handle", "") or ""),
        "BLOCK": "",
        "ROTATION": None,
        "SCALE_X": None,
        "SCALE_Y": None,
        "TEXT": "",
        "HEIGHT": None,
        "SOURCE": "NATIVE",
    }


def path_line(entity, tolerance: float):
    path = make_path(entity)
    pts = [xyz2(v) for v in path.flattening(distance=tolerance, segments=8)]
    if len(pts) < 2:
        return None
    clean = [pts[0]]
    for pt in pts[1:]:
        if pt != clean[-1]:
            clean.append(pt)
    return LineString(clean) if len(clean) >= 2 else None


def text_value(entity) -> str:
    kind = entity.dxftype()
    if kind == "TEXT":
        return str(entity.dxf.text)
    if kind == "MTEXT":
        try:
            return entity.plain_text()
        except Exception:
            return str(entity.text)
    return ""


def primitive_geometry(entity, layer: str, tolerance: float):
    """Return (family, geometry, attributes) or None."""
    kind = entity.dxftype()
    attrs = entity_base(entity, layer)
    try:
        if kind == "POINT":
            return "point", Point(xyz2(entity.dxf.location)), attrs
        if kind == "LINE":
            geom = LineString([xyz2(entity.dxf.start), xyz2(entity.dxf.end)])
            return "line", geom, attrs
        if kind in {"LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "HELIX"}:
            geom = path_line(entity, tolerance)
            return ("line", geom, attrs) if geom is not None else None
        if kind in {"TEXT", "MTEXT"}:
            pos = entity.dxf.insert
            attrs["TEXT"] = text_value(entity)
            attrs["ROTATION"] = float(getattr(entity.dxf, "rotation", 0.0) or 0.0)
            attrs["HEIGHT"] = float(
                getattr(entity.dxf, "height", getattr(entity.dxf, "char_height", 0.0)) or 0.0
            )
            return "text", Point(xyz2(pos)), attrs
        if kind in {"HATCH", "MPOLYGON"}:
            polygons = []
            for boundary in from_hatch(entity):
                pts = [xyz2(v) for v in boundary.flattening(distance=tolerance, segments=8)]
                if len(pts) >= 3:
                    if pts[0] != pts[-1]:
                        pts.append(pts[0])
                    polygon = Polygon(pts)
                    if not polygon.is_empty and polygon.is_valid and polygon.area > 0:
                        polygons.append(polygon)
            if not polygons:
                return None
            geom = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
            return "polygon", geom, attrs
        if kind in {"3DFACE", "SOLID", "TRACE"}:
            pts = []
            for name in ("vtx0", "vtx1", "vtx2", "vtx3"):
                if hasattr(entity.dxf, name):
                    pt = xyz2(getattr(entity.dxf, name))
                    if not pts or pt != pts[-1]:
                        pts.append(pt)
            if len(pts) > 2 and pts[-1] == pts[0]:
                pts.pop()
            return ("polygon", Polygon(pts), attrs) if len(set(pts)) >= 3 else None
    except Exception:
        return None
    return None


def block_attributes(insert, layer: str) -> dict:
    attrs = entity_base(insert, layer, "INSERT")
    attrs.update(
        {
            "BLOCK": str(insert.dxf.name),
            "ROTATION": float(getattr(insert.dxf, "rotation", 0.0) or 0.0),
            "SCALE_X": float(getattr(insert.dxf, "xscale", 1.0) or 1.0),
            "SCALE_Y": float(getattr(insert.dxf, "yscale", 1.0) or 1.0),
            "SOURCE": "BLOCK",
        }
    )
    return attrs


def collect_virtual(entity, effective_layer: str, tolerance: float, skipped: Counter, depth: int = 0):
    if depth > 20:
        skipped["INSERT_RECURSION_LIMIT"] += 1
        return []
    results = []
    if entity.dxftype() == "INSERT":
        try:
            children = list(entity.virtual_entities())
        except Exception:
            skipped["INSERT_EXPANSION_ERROR"] += 1
            return results
        for child in children:
            child_layer = str(getattr(child.dxf, "layer", "0") or "0")
            layer = effective_layer if child_layer == "0" else child_layer
            results.extend(collect_virtual(child, layer, tolerance, skipped, depth + 1))
        return results
    item = primitive_geometry(entity, effective_layer, tolerance)
    if item is None:
        skipped[entity.dxftype()] += 1
    else:
        results.append(item)
    return results


def group_geometries(items, family: str):
    geoms = [geom for fam, geom, _ in items if fam == family and geom is not None and not geom.is_empty]
    if not geoms:
        return None
    if len(geoms) == 1:
        return geoms[0]
    if family == "line":
        parts = []
        for geom in geoms:
            parts.extend(list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom])
        return MultiLineString(parts)
    if family == "polygon":
        parts = []
        for geom in geoms:
            parts.extend(list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom])
        return MultiPolygon(parts)
    if family == "point":
        return MultiPoint(geoms)
    return None


def remove_old_shapefile(path: Path):
    for ext in SIDE_EXTENSIONS:
        candidate = path.with_suffix(ext)
        if candidate.exists():
            candidate.unlink()


def write_family(records: list[dict], output: Path, crs: str | None, prj_from: Path | None):
    remove_old_shapefile(output)
    frame = gpd.GeoDataFrame(records, geometry="geometry", crs=crs)
    frame.to_file(output, driver="ESRI Shapefile", encoding="UTF-8", index=False)
    output.with_suffix(".cpg").write_text("UTF-8", encoding="ascii")
    if prj_from:
        shutil.copyfile(prj_from, output.with_suffix(".prj"))
    bounds = [float(v) for v in frame.total_bounds]
    return {"path": str(output), "features": len(frame), "bounds": bounds}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input DXF file")
    select = parser.add_mutually_exclusive_group()
    select.add_argument("--layers", nargs="+", help="CAD layer names")
    select.add_argument("--all-layers", action="store_true", help="Convert every nonzero layer")
    parser.add_argument("--output-dir", type=Path, default=Path("dxf_shp_output"))
    parser.add_argument("--epsg", type=int, help="Assign EPSG code without reprojecting coordinates")
    parser.add_argument("--prj-from", type=Path, help="Copy a trusted .prj to every output")
    parser.add_argument("--curve-tolerance", type=float, default=0.05)
    parser.add_argument("--explode-block-parts", action="store_true")
    parser.add_argument("--insert-only", action="store_true", help="Omit non-INSERT modelspace entities")
    parser.add_argument("--list-layers", action="store_true")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input not found: {args.input}")
    if args.prj_from and not args.prj_from.is_file():
        parser.error(f"Projection file not found: {args.prj_from}")
    if args.curve_tolerance <= 0:
        parser.error("--curve-tolerance must be positive")

    doc = ezdxf.readfile(args.input)
    modelspace = doc.modelspace()
    source_counts = Counter(str(e.dxf.layer) for e in modelspace)
    insert_counts = Counter(str(e.dxf.layer) for e in modelspace if e.dxftype() == "INSERT")
    if args.list_layers:
        for name in sorted(source_counts, key=str.casefold):
            print(f"{name}\tentities={source_counts[name]}\tinserts={insert_counts[name]}")
        return 0

    available = {name.casefold(): name for name in source_counts}
    if args.all_layers:
        selected = [name for name in source_counts if name != "0"]
    elif args.layers:
        missing = [name for name in args.layers if name.casefold() not in available]
        if missing:
            parser.error("Layer(s) not found: " + ", ".join(missing))
        selected = [available[name.casefold()] for name in args.layers]
    else:
        parser.error("Use --layers, --all-layers, or --list-layers")

    selected_fold = {name.casefold(): name for name in selected}
    records = defaultdict(lambda: defaultdict(list))
    skipped = Counter()

    for entity in modelspace:
        source_layer = str(entity.dxf.layer)
        if source_layer.casefold() not in selected_fold:
            continue
        layer = selected_fold[source_layer.casefold()]
        if entity.dxftype() != "INSERT":
            if args.insert_only:
                continue
            item = primitive_geometry(entity, layer, args.curve_tolerance)
            if item is None:
                skipped[entity.dxftype()] += 1
            else:
                family, geom, attrs = item
                records[layer][family].append({**attrs, "geometry": geom})
            continue

        attrs = block_attributes(entity, layer)
        insert_point = Point(xyz2(entity.dxf.insert))
        point_attrs = {**attrs, "SOURCE": "INSERT_PT"}
        records[layer]["point"].append({**point_attrs, "geometry": insert_point})
        parts = collect_virtual(entity, layer, args.curve_tolerance, skipped)
        if args.explode_block_parts:
            for family, geom, _child_attrs in parts:
                if family == "text":
                    child_attrs = _child_attrs
                    child_attrs.update({k: attrs[k] for k in ("BLOCK", "SCALE_X", "SCALE_Y")})
                    child_attrs["SOURCE"] = "BLOCK_TEXT"
                    records[layer][family].append({**child_attrs, "geometry": geom})
                else:
                    records[layer][family].append({**attrs, "geometry": geom})
        else:
            for family in ("line", "polygon"):
                geom = group_geometries(parts, family)
                if geom is not None:
                    records[layer][family].append({**attrs, "geometry": geom})
            for family, geom, child_attrs in parts:
                if family == "text":
                    child_attrs.update({k: attrs[k] for k in ("BLOCK", "SCALE_X", "SCALE_Y")})
                    child_attrs["SOURCE"] = "BLOCK_TEXT"
                    records[layer]["text"].append({**child_attrs, "geometry": geom})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    crs = f"EPSG:{args.epsg}" if args.epsg else None
    report = {
        "input": str(args.input.resolve()),
        "selected_layers": selected,
        "source_entity_counts": {name: source_counts[name] for name in selected},
        "source_insert_counts": {name: insert_counts[name] for name in selected},
        "grouped_blocks": not args.explode_block_parts,
        "insert_only": args.insert_only,
        "curve_tolerance": args.curve_tolerance,
        "crs": crs or (str(args.prj_from) if args.prj_from else None),
        "outputs": {},
        "skipped_entity_types": dict(skipped),
        "warnings": [],
    }
    for layer in selected:
        report["outputs"][layer] = {}
        stem = safe_name(layer)
        for family in ("point", "line", "polygon", "text"):
            family_records = records[layer][family]
            if not family_records:
                continue
            output = args.output_dir / f"{stem}_{family}.shp"
            report["outputs"][layer][family] = write_family(
                family_records, output, crs, args.prj_from
            )
        if insert_counts[layer] and not args.explode_block_parts:
            line_count = sum(1 for row in records[layer]["line"] if row.get("SOURCE") == "BLOCK")
            if line_count not in (0, insert_counts[layer]):
                report["warnings"].append(
                    f"{layer}: {insert_counts[layer]} INSERTs but {line_count} block-derived line features"
                )
    if skipped:
        report["warnings"].append("Some entity types could not be converted; review skipped_entity_types.")
    report_path = args.output_dir / "conversion_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
