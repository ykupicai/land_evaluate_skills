# -*- coding: utf-8 -*-
"""overlay_placement 的純幾何驗證（一般 python + shapely，不需 QGIS）。

用真實官田基地證明四角淨空、疊圖零遮擋；再用「基地填滿圖框」的合成案證明
退比例尺 fallback 一定能挪出淨空角落（保證基地不被疊圖遮住）。
"""

import sys
from pathlib import Path

from shapely import make_valid, union_all
from shapely.geometry import box

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
import overlay_placement as op  # noqa: E402


def _intersect_fn(base_geom):
    return lambda x1, y1, x2, y2: base_geom.intersection(box(x1, y1, x2, y2)).area


def load_guantian_base():
    import geopandas as gpd
    gpkg = Path(r"C:\Users\user\Documents\Claude\Projects\大量圖資轉換工具"
                r"\outputs\20260707台南官田40MW\圖層_讀取_基地.gpkg")
    if not gpkg.exists():
        return None
    g = gpd.read_file(gpkg, layer="基地")
    return make_valid(union_all([make_valid(x) for x in g.geometry]))


def test_real_guantian_all_corners_clear():
    base = load_guantian_base()
    if base is None:
        print("SKIP 官田: gpkg 不在"); return
    p = op.place_overlays(_intersect_fn(base), base.bounds)
    assert not p.outside, "官田應能在角落擺放"
    assert not p.zoomed_out, "官田四角本就淨空，不該退比例尺"
    assert set(p.assign.values()) == {"BR", "BL"}, f"預期右下+左下，得 {p.assign}"
    # 逐一確認指派到的角落確實零遮擋
    for name, w, h in [op.OVERLAY_SCALE_NORTH, op.OVERLAY_LOC_PARCEL]:
        r = op.corner_rect_ground(p.assign[name], w, h, p.extent)
        assert base.intersection(box(*r)).area == 0
    print(f"PASS 官田: 1/{p.scale}, {p.assign}, 零遮擋")


def test_fill_frame_triggers_zoomout():
    """基地幾乎填滿初始圖框 → 起始四角全被壓 → 退比例尺後保證挪出淨空角落。"""
    base = box(0, 0, 1400, 1100)  # 大方塊，初始 1/7000 圖框約 1498x1337，四角都會被壓
    p = op.place_overlays(_intersect_fn(base), base.bounds)
    assert not p.outside, "退比例尺後應能擺放"
    assert p.zoomed_out, "填滿案應觸發退比例尺"
    for name, w, h in [op.OVERLAY_SCALE_NORTH, op.OVERLAY_LOC_PARCEL]:
        r = op.corner_rect_ground(p.assign[name], w, h, p.extent)
        assert base.intersection(box(*r)).area == 0, f"{name} 退階後仍壓基地"
    print(f"PASS 填滿案: 退到 1/{p.scale}, {p.assign}, 零遮擋")


def test_extreme_fill_falls_back_outside():
    """病態案：基地遠大於任何合理圖框（永遠填滿）→ outside=True，交呼叫端退右欄。"""
    base = box(0, 0, 500000, 500000)
    p = op.place_overlays(_intersect_fn(base), base.bounds, max_zoomout=3)
    assert p.outside, "極端填滿應回報 outside 讓呼叫端外置"
    print(f"PASS 極端案: outside={p.outside}（退回右欄，不強遮）")


if __name__ == "__main__":
    test_real_guantian_all_corners_clear()
    test_fill_frame_triggers_zoomout()
    test_extreme_fill_falls_back_outside()
    print("\n全部通過。")
