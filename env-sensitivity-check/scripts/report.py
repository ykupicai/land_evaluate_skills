# -*- coding: utf-8 -*-
"""將 api.run() 的結果轉成 Markdown 法令分析報告，以及套疊示意圖 (PNG)。"""
from __future__ import annotations
import os
from shapely.geometry import shape


def to_markdown(result: dict) -> str:
    if result.get("error"):
        return f"# 查詢失敗\n\n{result['error']}\n"

    cad = result["cadastre"]
    findings = result["findings"]
    summary = result["summary"]

    lines = []
    lines.append(f"# 開發基地環境敏感地區初步評估報告\n")
    lines.append(f"地籍版次：{cad.get('version')}｜座標系統：{cad.get('crs')}\n")

    lines.append("## 基地資料\n")
    lines.append("| 地號 | 登記面積(m²) | 使用分區 | 使用地類別 |")
    lines.append("|---|---|---|---|")
    for rec in cad["records"]:
        if not rec["ok"]:
            lines.append(f"| {rec['query']['landno']} | 查詢失敗：{rec['status']} | - | - |")
            continue
        reg = rec["registry"]
        lines.append(f"| {rec['parcel']['landno']} | {reg['area']} | {reg.get('zone') or '(都市土地，見都計圖)'} | {reg.get('land_type') or '-'} |")
    lines.append("")

    lines.append("## 總覽\n")
    lines.append(f"- 免查：{summary['免查']} 項")
    lines.append(f"- 應查，TGOS 圖資套疊後**無交集**（初步排除）：{summary['應查_自動排除']} 項")
    lines.append(f"- 應查，TGOS 圖資套疊後**有交集**（需留意）：{summary['應查_有交集']} 項")
    lines.append(f"- 應查，依登記使用分區判斷**屬於**該項目：{summary.get('應查_使用分區判斷_屬於', 0)} 項")
    lines.append(f"- 應查，依登記使用分區判斷**不屬於**該項目（初步排除）：{summary.get('應查_使用分區判斷_不屬於', 0)} 項")
    lines.append(f"- 應查，都市土地無使用分區欄位、無法用此規則判斷：{summary.get('應查_使用分區無法判斷(都市土地)', 0)} 項")
    lines.append(f"- 應查，僅有 WMS 影像，需人工比對：{summary['應查_需人工WMS比對']} 項")
    lines.append(f"- 應查，TGOS 查無圖資，需逕洽主管機關：{summary['應查_需洽主管機關']} 項")
    lines.append(f"- 無法判定（缺村里/地段資料）：{summary['無法判定']} 項\n")

    hit = [f for f in findings if f["overlay"] and f["overlay"].get("kind") == "vector"
           and any(p.get("intersects") for p in f["overlay"]["per_parcel"])]
    zone_hit = [f for f in findings if f["overlay"] and f["overlay"].get("kind") == "zone_attribute"
                and any(p.get("matched") for p in f["overlay"]["per_parcel"])]
    if hit or zone_hit:
        lines.append("## ⚠️ 判定為屬於該敏感項目（優先確認）\n")
        for f in hit:
            lines.append(f"- **{f['question']}**（{f['sub_name'] or ''}）→ 圖資套疊有交集：{f['overlay']['layer']}，主管機關：{f['authority'] or '見查復機關'}")
        for f in zone_hit:
            zone = next((p.get("zone") for p in f["overlay"]["per_parcel"] if p.get("matched")), "")
            lines.append(f"- **{f['question']}**（{f['sub_name'] or ''}）→ 登記使用分區為「{zone}」，主管機關：{f['authority'] or '見查復機關'}")
        lines.append("")

    zone_unknown = [f for f in findings if f["overlay"] and f["overlay"].get("kind") == "zone_attribute"
                     and any(p.get("zone") is None for p in f["overlay"]["per_parcel"])]
    if zone_unknown:
        lines.append("## 都市土地：使用分區規則不適用項目\n")
        for f in zone_unknown:
            lines.append(f"- {f['question']}（{f['sub_name'] or ''}）→ 請參考都市計畫圖或逕洽 {f['authority'] or '主管機關'}")
        lines.append("")

    need_agency = [f for f in findings if f["eland_status"] == "應查" and f["overlay"] is None]
    if need_agency:
        lines.append("## 需逕洽主管機關 / 無 TGOS 圖資可自行比對項目\n")
        lines.append("| 項目 | 主管機關 |")
        lines.append("|---|---|")
        for f in need_agency:
            lines.append(f"| {f['question']}{'（'+f['sub_name']+'）' if f['sub_name'] else ''} | {f['authority'] or '-'} |")
        lines.append("")

    wms_only = [f for f in findings if f["overlay"] and f["overlay"].get("kind") == "wms"]
    if wms_only:
        lines.append("## 需人工目視 WMS 套疊項目\n")
        for f in wms_only:
            lines.append(f"- {f['question']}（{f['overlay']['layer']}，{f['overlay']['agency']}）")
        lines.append("")

    lines.append("## 免查項目（無需進一步處理）\n")
    exempt = [f for f in findings if f["eland_status"] == "免查"]
    lines.append(f"共 {len(exempt)} 項，明細略（見附帶 JSON 完整結果）。\n")

    lines.append("---")
    lines.append("**重要提醒**：本報告為初步自我篩檢，套疊比對所用圖資之精度與時效以來源機關公告為準；"
                  "正式法定用途（環評、雜項執照等）仍須以「環境敏感地區單一窗口查詢平台」之正式行文查復結果為準。")
    return "\n".join(lines)


def draw_map(result: dict, out_path: str):
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["font.family"] = "Microsoft JhengHei"
    matplotlib.rcParams["axes.unicode_minus"] = False
    import matplotlib.pyplot as plt
    import geopandas as gpd
    from overlay import load_layer_gdf

    cad = result["cadastre"]
    parcel_geoms = [shape(rec["geometry"]) for rec in cad["records"] if rec["ok"]]
    if not parcel_geoms:
        return None
    parcel_gdf = gpd.GeoDataFrame(geometry=parcel_geoms, crs="EPSG:3826")

    fig, ax = plt.subplots(figsize=(8, 8))

    minx, miny, maxx, maxy = parcel_gdf.total_bounds
    pad = max(maxx - minx, maxy - miny, 200) * 3
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    view = (cx - pad, cx + pad, cy - pad, cy + pad)

    drawn_layers = set()
    for f in result["findings"]:
        ov = f.get("overlay")
        if not ov or ov.get("kind") != "vector":
            continue
        layer_name = ov["layer"]
        if layer_name in drawn_layers:
            continue
        drawn_layers.add(layer_name)
        from tgos_layers import LAYERS
        layer_cfg = next((l for l in LAYERS if l["name"] == layer_name), None)
        if not layer_cfg:
            continue
        try:
            gdf = load_layer_gdf(layer_cfg)
            gdf_clip = gdf.cx[view[0]:view[1], view[2]:view[3]]
            hit = any(p.get("intersects") for p in ov["per_parcel"])
            color = "#e53e3e" if hit else "#a0aec0"
            if len(gdf_clip):
                geom_type = gdf_clip.geom_type.iloc[0]
                if geom_type in ("Polygon", "MultiPolygon"):
                    gdf_clip.boundary.plot(ax=ax, color=color, linewidth=1, label=layer_name)
                else:
                    gdf_clip.plot(ax=ax, color=color, linewidth=1, label=layer_name)
        except Exception:
            continue

    parcel_gdf.boundary.plot(ax=ax, color="#1a202c", linewidth=2.5, label="開發基地")
    ax.set_xlim(view[0], view[1])
    ax.set_ylim(view[2], view[3])
    ax.set_title("開發基地環境敏感圖資套疊示意圖 (EPSG:3826)")
    ax.set_aspect("equal")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
