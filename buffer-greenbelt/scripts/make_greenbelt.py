# -*- coding: utf-8 -*-
"""基地緩衝綠帶計算:dissolve → 向內退縮 W 公尺 → difference = 等寬 W m 綠帶。

用法:
  python make_greenbelt.py --base <基地.shp 或 圖層.gpkg> [--layer 基地] [--width 10]
                           [--out-dir 緩衝綠帶] [--outer-only]

輸出(BIG5 shp,沿用來源 CRS,需為公尺制投影如 EPSG:3826):
  緩衝綠帶{W}m.shp   綠帶範圍
  退縮後基地.shp      退縮後可配置範圍(配置設施用)
並印出統計:基地/退縮後/綠帶面積(ha)、區塊存活數。

幾何細節(2026-07 官田案與使用者確認之定案):
  * 退縮自「所有邊界」為之——含 dissolve 區塊內部的洞(未圈入的宗地/水路缺口),
    故洞緣亦有綠帶。此為預設行為。
  * 若只要沿外周長設帶(內部洞不設),加 --outer-only:先把每個區塊的洞填掉再退縮,
    綠帶再與原 dissolve 範圍取交集(避免綠帶落在洞內非基地土地上)。
  * 寬度不足 2W 的獨立區塊退縮後會完全消失=整塊納入綠帶;腳本會點名警告,不靜默。
  * 全部幾何先 make_valid 再 union——官田案實測含無效幾何,不修會靜默算錯(bbox 塌縮)。
"""
import argparse
import os

import geopandas as gpd
from shapely import make_valid, union_all
from shapely.geometry import Polygon, MultiPolygon


def parts_of(geom):
    if geom.is_empty:
        return []
    return list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]


def fill_holes(geom):
    return MultiPolygon([Polygon(p.exterior) for p in parts_of(geom)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="基地 shp,或含基地表的 gpkg")
    ap.add_argument("--layer", default=None, help="gpkg 圖層名(如 基地)")
    ap.add_argument("--width", type=float, default=10.0, help="綠帶寬(m),預設 10")
    ap.add_argument("--out-dir", default="緩衝綠帶")
    ap.add_argument("--outer-only", action="store_true",
                    help="只沿外周長設帶(內部洞不設);預設含洞緣")
    a = ap.parse_args()

    g = gpd.read_file(a.base, layer=a.layer) if a.layer else gpd.read_file(a.base)
    if g.crs is None or (g.crs.axis_info and g.crs.axis_info[0].unit_name.lower() not in ("metre", "meter")):
        print("[warn] 來源 CRS 非公尺制或缺 CRS,退縮距離將失真——請先確認(臺灣通常 EPSG:3826)")

    d = make_valid(union_all([make_valid(x) for x in g.geometry]))
    src = fill_holes(d) if a.outer_only else d
    inner = src.buffer(-a.width)
    green = src.difference(inner)
    if a.outer_only:
        green = green.intersection(d)   # 綠帶不落在洞內非基地土地
        inner = d.difference(green)     # 退縮後=基地扣綠帶(保留洞)

    blocks = parts_of(d)
    gone = [i for i, p in enumerate(blocks, 1) if not p.intersects(inner)]
    print(f"dissolve 區塊 {len(blocks)},退縮後存活 {len(blocks) - len(gone)}")
    if gone:
        print(f"[warn] {len(gone)} 個區塊寬度不足 {2 * a.width:.0f}m,退縮後完全消失=整塊納入綠帶"
              f"(區塊序 {gone});如非預期請確認基地範圍")
    print(f"基地 {d.area / 10000:.2f} ha | 退縮後 {inner.area / 10000:.2f} ha | "
          f"綠帶 {green.area / 10000:.2f} ha ({green.area / d.area * 100:.1f}%)")

    os.makedirs(a.out_dir, exist_ok=True)
    w = int(a.width) if a.width == int(a.width) else a.width
    p1 = os.path.join(a.out_dir, f"緩衝綠帶{w}m.shp")
    p2 = os.path.join(a.out_dir, "退縮後基地.shp")
    gpd.GeoDataFrame({"name": [f"緩衝綠帶({w}m)"]}, geometry=[green], crs=g.crs).to_file(p1, encoding="big5")
    gpd.GeoDataFrame({"name": [f"退縮後基地(-{w}m)"]}, geometry=[inner], crs=g.crs).to_file(p2, encoding="big5")
    print("->", p1)
    print("->", p2)


if __name__ == "__main__":
    main()
