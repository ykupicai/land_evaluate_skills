"""
基地 × 環境敏感地區 交集分析。

流程（順序不可換，見 SKILL.md「面積必須在 TM2 算」）：
  基地環(TM2) --> WebMercator --> ngis.query_polygon 面查詢
              --> 敏感區幾何(WebMercator) --> 轉回 TM2 --> shapely 交集

為什麼一定要轉回 TM2 才算面積：
  identify 回傳的是 WebMercator(3857)，該投影在緯度 φ 的面積失真為 1/cos²φ。
  台灣約 23°N 即 1.18 倍 —— 實測直接用 WebMercator 算會多 18.84%，
  轉 TM2 後與官方 Shape.STArea() 誤差 0.00%。
"""
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.validation import make_valid

import geo
import ngis


def _rings_to_tm2(rings_merc):
    """WebMercator 環清單 -> TM2 環清單。"""
    return [[geo.lonlat_to_tm2(*geo.merc_to_lonlat(x, y)) for x, y in ring]
            for ring in rings_merc]


def _signed_area(r):
    x0, y0 = r[0]
    return sum((r[i][0] - x0) * (r[i + 1][1] - y0) - (r[i + 1][0] - x0) * (r[i][1] - y0)
               for i in range(len(r) - 1)) / 2


def _assemble(outers, holes):
    polys = []
    for o in outers:
        op = Polygon(o)
        if not op.is_valid:
            op = make_valid(op)
        inner = []
        if op.geom_type == 'Polygon':
            for h in holes:
                try:
                    if Polygon(h).representative_point().within(op):
                        inner.append(h)
                except Exception:
                    pass
        try:
            polys.append(Polygon(o, inner) if inner else op)
        except Exception:
            polys.append(op)
    if not polys:
        return None
    g = unary_union([make_valid(p) if not p.is_valid else p for p in polys])
    return g if not g.is_empty else None


def _ring_bbox(r):
    xs = [p[0] for p in r]
    ys = [p[1] for p in r]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_hit(b, clip):
    return not (b[2] < clip[0] or b[0] > clip[2] or b[3] < clip[1] or b[1] > clip[3])


def _esri_rings_to_polygon(rings, clip_bbox=None):
    """
    ESRI rings -> shapely。ESRI 慣例：外環順時針、孔洞逆時針。
    座標系不限（在哪個平面座標系判方向都一致），但 y 必須向上。

    clip_bbox 是效能命脈，不是可有可無的優化：
    實測淹水潛勢單筆有 **21,787 個環**（189,605 頂點）。不先用邊界框篩掉
    離基地遠的環，孔洞歸屬會變成 21,435 外環 × 352 孔洞 ≈ 750 萬次
    幾何判斷而整個卡死。離基地很遠的環不可能有交集，直接丟掉。
    """
    outers, holes = [], []
    for r in rings:
        if len(r) < 4:
            continue
        if clip_bbox and not _bbox_hit(_ring_bbox(r), clip_bbox):
            continue
        (holes if _signed_area(r) > 0 else outers).append(r)
    if not outers:
        return None
    return _assemble(outers, holes)


def _site_rings_to_polygon(rings_tm2):
    """
    使用者提供的基地環 -> shapely。

    **不套用 ESRI 方位慣例** —— 外部來源（QGIS、手繪、DXF、其他 API）給的環
    方向不可預期，硬套慣例會把逆時針的單一外環誤判成孔洞而整個歸零。
    改用「面積最大者為外環，被其包含者為孔洞」，與方位無關。
    """
    valid = [r for r in rings_tm2 if len(r) >= 4]
    if not valid:
        return None
    if len(valid) == 1:
        p = Polygon(valid[0])
        return make_valid(p) if not p.is_valid else p
    ranked = sorted(valid, key=lambda r: abs(_signed_area(r)), reverse=True)
    outer = ranked[0]
    op = Polygon(outer)
    if not op.is_valid:
        op = make_valid(op)
    outers, holes = [outer], []
    for r in ranked[1:]:
        try:
            if Polygon(r).representative_point().within(op):
                holes.append(r)
            else:
                outers.append(r)
        except Exception:
            outers.append(r)
    return _assemble(outers, holes)


def analyze(site_rings_tm2, token=None, levels=('一級', '二級'), min_area=0.01):
    """
    基地與各環境敏感地區的交集分析。

    site_rings_tm2: 基地環清單，TWD97 TM2 座標 [[(x,y),...], ...]
    回傳 {
      'site_area': 基地面積 m2,
      'hits': [{'level','layerName','attributes','overlap_area','overlap_ratio'}...],
      'total_overlap_area', 'total_overlap_ratio'   # 各敏感區聯集，避免重複計算
    }
    """
    token = token or ngis.fetch_token()

    site_tm2 = _site_rings_to_polygon(site_rings_tm2)
    if site_tm2 is None or site_tm2.is_empty:
        raise ValueError('基地幾何無效')
    site_area = site_tm2.area

    rings_merc = [[geo.tm2_to_merc(x, y) for x, y in r] for r in site_rings_tm2]
    site_merc = _site_rings_to_polygon(rings_merc)
    # 邊界框外擴 1 m，避免浮點邊界把恰好相切的環誤篩掉
    b = site_merc.bounds
    site_bbox = (b[0] - 1, b[1] - 1, b[2] + 1, b[3] + 1)

    res = ngis.query_polygon(token, rings_merc, levels=levels, return_geometry=True)

    hits, inter_geoms = [], []
    for lv, items in res.items():
        for it in items:
            g = it.get('geometry') or {}
            rings = g.get('rings')
            if not rings:
                continue
            # 敏感區動輒十幾萬頂點（實測淹水潛勢單筆 189,605 點）。
            # 先在 WebMercator 裁切，只把「交集結果」轉 TM2 —— 若先整片轉座標
            # 再交集，會在純 Python 迴圈裡跑數十萬次投影換算而卡死。
            poly = _esri_rings_to_polygon(rings, clip_bbox=site_bbox)
            if poly is None:
                continue
            inter_merc = site_merc.intersection(poly)
            if inter_merc.is_empty:
                continue
            inter = _to_tm2(inter_merc)
            if inter is None or inter.is_empty or inter.area < min_area:
                continue
            inter_geoms.append(inter)
            hits.append({
                'level': lv,
                'layerName': it['layerName'],
                'attributes': it['attributes'],
                'overlap_area': inter.area,
                'overlap_ratio': inter.area / site_area,
            })

    hits.sort(key=lambda h: -h['overlap_area'])
    union_area = unary_union(inter_geoms).area if inter_geoms else 0.0
    return {
        'site_area': site_area,
        'hits': hits,
        'total_overlap_area': union_area,
        'total_overlap_ratio': union_area / site_area if site_area else 0.0,
    }


def _to_tm2(geom):
    """把（已裁切、頂點很少的）WebMercator 幾何轉成 TM2，供面積計算。"""
    def conv(poly):
        ext = [geo.lonlat_to_tm2(*geo.merc_to_lonlat(x, y)) for x, y in poly.exterior.coords]
        ins = [[geo.lonlat_to_tm2(*geo.merc_to_lonlat(x, y)) for x, y in r.coords]
               for r in poly.interiors]
        p = Polygon(ext, ins)
        return p if p.is_valid else make_valid(p)

    if geom.is_empty:
        return None
    if geom.geom_type == 'Polygon':
        return conv(geom)
    parts = [conv(g) for g in getattr(geom, 'geoms', []) if g.geom_type == 'Polygon']
    return unary_union(parts) if parts else None


def format_report(result):
    """把 analyze() 結果排成可讀文字。"""
    L = [f'基地面積：{result["site_area"]:,.2f} m²', '']
    if not result['hits']:
        L.append('未與任何環境敏感地區重疊。')
    else:
        L.append(f'命中 {len(result["hits"])} 項環境敏感地區：')
        L.append('')
        for h in result['hits']:
            L.append(f'● [{h["level"]}] {h["layerName"]}')
            L.append(f'    重疊面積：{h["overlap_area"]:,.2f} m²'
                     f'（占基地 {h["overlap_ratio"]*100:.2f}%）')
            for k, v in list(h['attributes'].items())[:6]:
                L.append(f'    {k}: {v}')
            L.append('')
        L.append(f'聯集重疊面積：{result["total_overlap_area"]:,.2f} m²'
                 f'（占基地 {result["total_overlap_ratio"]*100:.2f}%）')
        L.append('（聯集已扣除各敏感區彼此重疊部分，不等於逐項相加）')
    L.append('')
    L.append('本結果僅供初步評估，正式判定應以主管機關套繪為準。')
    return '\n'.join(L)
