#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Join a geometry-only Shapefile to its companion XLS by vector area.

Background
----------
Cadastral exports from Taiwan land-parcel tools often arrive as two files that
share a basename:

  * a Shapefile (sometimes wrapped in a .zip) that carries the polygon geometry
    but only styling attributes (RGB, LINE_RGB, a 公私別 DESCRIBE field, ...) --
    it has *no* 地號 or owner to join on; and
  * an .xls / .xlsx that carries the full parcel attributes (縣市, 地段, 地號,
    所有權人, 使用分區, 公告現值, ...) plus a `向量面積` column holding each
    parcel's vectorized area in m^2.

The only key common to both is area. This script computes each polygon's
geometry area and matches it to the XLS `向量面積` column, then writes a new
Shapefile carrying the joined attributes.

Why a *nearest* match, not an exact one
---------------------------------------
The stored `向量面積` is rounded (usually to 2 dp) while Shapely recomputes the
area from the raw coordinates, so the two differ by rounding noise (observed
max ~0.015 m^2). An exact or 2-dp-rounded equality join drops ~15-20% of rows;
a nearest-value match within a small absolute tolerance (default 0.05 m^2)
recovers 100% while staying far below any real area gap between distinct
parcels. One XLS parcel may match several polygons (a parcel split into
multiple polygon features) -- that one-to-many mapping is expected and fine.

Encoding
--------
These files are almost always BIG5. `.xls` read through xlrd frequently comes
back as BIG5 bytes mis-decoded as latin1; this script detects and repairs that.
Output is written with a BIG5 .cpg so QGIS/ArcGIS read the Chinese correctly.
"""

import argparse
import os
import sys
import tempfile
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Encoding helpers
# --------------------------------------------------------------------------- #
def _looks_mojibake(s):
    """True if the string carries latin1-range bytes but no CJK -- the classic
    signature of BIG5 text that xlrd decoded as latin1/cp1252."""
    if not isinstance(s, str) or not s:
        return False
    has_high = any(0x80 <= ord(c) <= 0xFF for c in s)
    has_cjk = any(0x4E00 <= ord(c) <= 0x9FFF for c in s)
    has_repl = "�" in s
    return (has_high or has_repl) and not has_cjk


def _fix_big5(s):
    """Recover BIG5 text that was decoded as latin1. Leaves already-correct
    (UTF-8 / real CJK) strings untouched."""
    if not _looks_mojibake(s):
        return s
    try:
        return s.encode("latin1").decode("big5")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def load_xls(path):
    """Read an .xls/.xlsx and repair BIG5 mojibake in headers and cells."""
    df = pd.read_excel(path)
    df.columns = [_fix_big5(c) for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(_fix_big5)
    return df


# --------------------------------------------------------------------------- #
# Pairing: find the geometry that goes with an XLS
# --------------------------------------------------------------------------- #
def _shp_inside_zip(zip_path, extract_root):
    """Extract a zip and return the path to the single .shp inside it."""
    dest = os.path.join(extract_root, os.path.splitext(os.path.basename(zip_path))[0])
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    shps = []
    for root, _dirs, files in os.walk(dest):
        for f in files:
            if f.lower().endswith(".shp"):
                shps.append(os.path.join(root, f))
    if not shps:
        raise FileNotFoundError(f"no .shp found inside {zip_path}")
    if len(shps) > 1:
        print(f"  [warn] {os.path.basename(zip_path)} holds {len(shps)} shp; using {os.path.basename(shps[0])}")
    return shps[0]


def find_geometry_for(xls_path, folder, extract_root):
    """Locate the Shapefile paired with an XLS by shared basename. Order:
    1. <base>.shp beside it, 2. <base>.zip beside it, 3. subfolder <base>/*.shp."""
    base = os.path.splitext(os.path.basename(xls_path))[0]
    direct = os.path.join(folder, base + ".shp")
    if os.path.isfile(direct):
        return direct
    zip_path = os.path.join(folder, base + ".zip")
    if os.path.isfile(zip_path):
        return _shp_inside_zip(zip_path, extract_root)
    subdir = os.path.join(folder, base)
    if os.path.isdir(subdir):
        for f in os.listdir(subdir):
            if f.lower().endswith(".shp"):
                return os.path.join(subdir, f)
    return None


# NLSC 國土測繪地籍欄位別名：make_maps 的 trust-shp 模式讀 20251201_* 欄名，而 tcdgis
# 匯出的屬性 Excel 用中文欄名。--trust-fields 時，依此把中文欄複製成 20251201_* 別名，
# 讓 shp-xls-area-join 的輸出可直接餵給 make_maps --trust-shp（段號不在 Excel，故從缺；
# trust 模式容許段號為空）。來源欄不存在就跳過該別名。
TRUST_ALIASES = {
    "20251201_1": "縣市名稱",
    "20251201_2": "鄉鎮市區",
    "20251201_3": "地段名稱",
    "20251201_4": "地號",
    "20251201_6": "使用分區",
    "20251201_7": "使用地類別",
}


# --------------------------------------------------------------------------- #
# The join
# --------------------------------------------------------------------------- #
def area_join(shp_path, xls_path, join_col="向量面積", tol=0.05,
              only_xls_cols=False, epsg=None, trust_fields=False):
    """Return a GeoDataFrame of the shp polygons with XLS attributes joined by
    nearest vector area, plus a stats dict."""
    g = gpd.read_file(shp_path)
    if g.crs is None and epsg is not None:
        g = g.set_crs(epsg=epsg)
    if g.crs is None:
        print("  [warn] source has no CRS; areas assume the coordinate units are metres")
    df = load_xls(xls_path)

    if join_col not in df.columns:
        raise KeyError(f"join column '{join_col}' not in XLS. Columns: {list(df.columns)}")

    g = g.reset_index(drop=True)
    g["__ord"] = np.arange(len(g))
    g["__area"] = g.geometry.area

    x = df.copy()
    x["__xarea"] = pd.to_numeric(x[join_col], errors="coerce").astype(float)
    x = x.dropna(subset=["__xarea"])

    # Warn about parcels that are indistinguishable by area (ambiguous matches).
    dup_area = x["__xarea"].round(2).duplicated(keep=False)
    n_ambig = int(dup_area.sum())

    left = g[["__ord", "__area"]].sort_values("__area")
    right = x.sort_values("__xarea")
    m = pd.merge_asof(left, right, left_on="__area", right_on="__xarea",
                      direction="nearest", tolerance=tol)
    m = m.sort_values("__ord").reset_index(drop=True)

    xls_cols = [c for c in df.columns]
    matched = int(m[join_col].notna().sum())

    out = g.sort_values("__ord").reset_index(drop=True).copy()
    for c in xls_cols:
        target = c if (only_xls_cols or c not in out.columns) else f"{c}_xls"
        out[target] = m[c].values

    drop = ["__ord", "__area"]
    if only_xls_cols:
        keep = [c for c in xls_cols if c in out.columns] + ["geometry"]
        out = out[keep]
    else:
        out = out.drop(columns=[d for d in drop if d in out.columns])

    if trust_fields:
        for alias, src in TRUST_ALIASES.items():
            if src in out.columns and alias not in out.columns:
                out[alias] = out[src].values

    out = gpd.GeoDataFrame(out, geometry="geometry", crs=g.crs)
    stats = {"polygons": len(g), "xls_rows": len(df), "matched": matched,
             "unmatched": len(g) - matched, "ambiguous_area_rows": n_ambig,
             "columns": [c for c in out.columns if c != "geometry"]}
    return out, stats


def write_output(gdf, out_path, driver="ESRI Shapefile"):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if driver == "ESRI Shapefile":
        gdf.to_file(out_path, encoding="big5")
        with open(os.path.splitext(out_path)[0] + ".cpg", "w") as f:
            f.write("BIG5")
    else:  # GPKG -- UTF-8, no 10-char field-name limit
        gdf.to_file(out_path, driver=driver)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def process_pair(shp_path, xls_path, out_path, args):
    print(f"- {os.path.basename(xls_path)}  x  {os.path.basename(shp_path)}")
    gdf, st = area_join(shp_path, xls_path, join_col=args.join_col, tol=args.tol,
                        only_xls_cols=args.only_xls_cols, epsg=args.epsg,
                        trust_fields=args.trust_fields)
    write_output(gdf, out_path, driver=args.driver)
    flag = "" if st["unmatched"] == 0 else f"  [WARN {st['unmatched']} unmatched]"
    print(f"    polygons {st['polygons']}, xls rows {st['xls_rows']}, "
          f"matched {st['matched']}/{st['polygons']} (tol {args.tol}){flag}")
    if st["ambiguous_area_rows"]:
        print(f"    [note] {st['ambiguous_area_rows']} XLS rows share an area within 0.01 m^2; "
              f"their polygons may take an equal-area neighbour's attributes")
    print(f"    -> {out_path}")
    return st


def main():
    ap = argparse.ArgumentParser(description="Join geometry-only SHP to its XLS by vector area.")
    ap.add_argument("target", help="a folder of paired files, or a single .shp/.zip")
    ap.add_argument("--xls", help="XLS path (required when target is a single .shp/.zip)")
    ap.add_argument("--out-dir", default="output", help="output directory (default: output)")
    ap.add_argument("--join-col", default="向量面積", help="XLS area column (default: 向量面積)")
    ap.add_argument("--tol", type=float, default=0.05,
                    help="absolute area match tolerance in m^2 (default: 0.05)")
    ap.add_argument("--only-xls-cols", action="store_true",
                    help="output geometry + XLS columns only (drop shp styling cols)")
    ap.add_argument("--driver", default="ESRI Shapefile",
                    choices=["ESRI Shapefile", "GPKG"],
                    help="output format; GPKG avoids the shapefile 10-byte field-name limit")
    ap.add_argument("--epsg", type=int, help="assign this EPSG if the source has no .prj")
    ap.add_argument("--suffix", default="_面積join", help="output basename suffix")
    ap.add_argument("--trust-fields", action="store_true",
                    help="add 20251201_* aliases (縣市/鄉鎮/地段/地號/使分/使類) so the output "
                         "feeds make_maps --trust-shp directly")
    args = ap.parse_args()

    ext = ".gpkg" if args.driver == "GPKG" else ".shp"
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        if os.path.isdir(args.target):
            folder = args.target
            xls_files = sorted(f for f in os.listdir(folder)
                               if f.lower().endswith((".xls", ".xlsx")) and not f.startswith("~$"))
            if not xls_files:
                print("No .xls/.xlsx files found in folder."); sys.exit(1)
            for xf in xls_files:
                xls_path = os.path.join(folder, xf)
                shp_path = find_geometry_for(xls_path, folder, tmp)
                if shp_path is None:
                    print(f"- {xf}: [skip] no matching .shp/.zip/subfolder found")
                    continue
                base = os.path.splitext(xf)[0]
                out_path = os.path.join(args.out_dir, base + args.suffix + ext)
                results.append(process_pair(shp_path, xls_path, out_path, args))
        else:
            if not args.xls:
                print("Single-file mode needs --xls."); sys.exit(1)
            t = args.target
            shp_path = _shp_inside_zip(t, tmp) if t.lower().endswith(".zip") else t
            base = os.path.splitext(os.path.basename(args.xls))[0]
            out_path = os.path.join(args.out_dir, base + args.suffix + ext)
            results.append(process_pair(shp_path, args.xls, out_path, args))

    total_unmatched = sum(r["unmatched"] for r in results)
    print(f"\nDone: {len(results)} pair(s).",
          "All polygons matched." if total_unmatched == 0
          else f"{total_unmatched} polygon(s) unmatched -- consider raising --tol.")
    if total_unmatched:
        sys.exit(2)


if __name__ == "__main__":
    main()
