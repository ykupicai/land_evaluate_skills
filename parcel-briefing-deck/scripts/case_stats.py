# -*- coding: utf-8 -*-
"""從地籍案件產物算出簡報要用的全部統計，輸出 JSON。版面怎麼排會變，這些數字怎麼來不會變。

用法:
  python case_stats.py --xls <tcdgis屬性.xls> [--gpkg <圖層.gpkg>] [--sites <sites_status.csv>] [-o stats.json]

輸出鍵:
  sections   每段筆數(段名已去 [代碼] 前綴)
  ownership  公私別筆數;public_parcels 列出每筆公有地(段/地號/管理者/使類/面積)
  area_m2 / area_ha  向量面積合計
  zoning     使用分區 {name: {筆數, 面積_ha}}
  landtype   使用地類別 {name: {筆數, 面積_ha}}
  functional 國土功能分區(基地 dissolve × 功能分區套疊) {zone: {面積_ha, 佔比}}
  road       sites_status.csv 原列(編號/臨路狀態/距離/註記)

簡報文字禁止用沒出現在這份 JSON 的數字——範本句(如「皆為私有地」)要以實算結果覆核,
官田案就抓到 144 私 + 1 公,照抄範本會寫錯。
"""
import argparse
import json
import re
import sys

import pandas as pd


def _fix(s):
    if isinstance(s, str) and any(0x80 <= ord(c) <= 0xff for c in s) \
            and not any(0x4e00 <= ord(c) <= 0x9fff for c in s):
        try:
            return s.encode("latin1").decode("big5")
        except Exception:
            return s
    return s


def load_xls(path):
    df = pd.read_excel(path)
    df.columns = [_fix(c) for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(_fix)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xls", required=True, help="tcdgis 匯出屬性 xls(含 向量面積/使用分區/使用地類別/公私別)")
    ap.add_argument("--gpkg", help="make_maps 圖層.gpkg(算國土功能分區套疊,選填)")
    ap.add_argument("--sites", help="fishpv sites_status.csv(臨路檢核,選填)")
    ap.add_argument("-o", "--out", default="stats.json")
    a = ap.parse_args()

    x = load_xls(a.xls)
    x["_seg"] = x["地段名稱"].map(lambda s: re.sub(r"^\[\d+\]", "", str(s)))
    x["_a"] = x["向量面積"].astype(float)

    out = {
        "total_parcels": len(x),
        "sections": x.groupby("_seg").size().to_dict(),
        "ownership": x["公私別"].value_counts().to_dict(),
        "public_parcels": x[x["公私別"] == "公"][["_seg", "地號", "所有權人", "管理者", "使用地類別", "向量面積"]]
                          .rename(columns={"_seg": "段"}).to_dict("records"),
        "area_m2": round(x["_a"].sum(), 2),
        "area_ha": round(x["_a"].sum() / 10000, 2),
        "zoning": {k: {"筆數": int(v["地號"]), "面積_ha": round(v["_a"] / 10000, 2)}
                   for k, v in x.groupby("使用分區").agg({"地號": "count", "_a": "sum"}).iterrows()},
        "landtype": {k: {"筆數": int(v["地號"]), "面積_ha": round(v["_a"] / 10000, 2)}
                     for k, v in x.groupby("使用地類別").agg({"地號": "count", "_a": "sum"}).iterrows()},
    }
    # 每段最小地號(封面「XX段NNN地號等N筆」用)
    def landkey(s):
        m = re.match(r"(\d+)(?:-(\d+))?", str(s))
        return (int(m.group(1)), int(m.group(2) or 0)) if m else (10**9, 0)
    out["first_landno"] = {seg: sorted(g["地號"].astype(str), key=landkey)[0]
                           for seg, g in x.groupby("_seg")}

    if a.gpkg:
        import geopandas as gpd
        from shapely import make_valid, union_all
        base = gpd.read_file(a.gpkg, layer="基地")
        zones = gpd.read_file(a.gpkg, layer="功能分區")
        b = make_valid(union_all([make_valid(g) for g in base.geometry]))
        tot = b.area
        fz = {}
        for _, z in zones.iterrows():
            inter = make_valid(z.geometry).intersection(b).area
            if inter > 1:
                fz[z["zone"]] = fz.get(z["zone"], 0) + inter
        out["functional"] = {k: {"面積_ha": round(v / 10000, 2), "佔比": f"{v / tot * 100:.1f}%"}
                             for k, v in sorted(fz.items(), key=lambda kv: -kv[1])}

    if a.sites:
        st = pd.read_csv(a.sites, encoding="utf-8-sig")
        out["road"] = st.to_dict("records")

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\n-> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
