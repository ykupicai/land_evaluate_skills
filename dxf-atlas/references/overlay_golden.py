# -*- coding: utf-8 -*-
"""
善化圳西段
把「原提會 vs 變更後細計」差異範圍以紅色虛線外框套疊到 20260330_細計確認 圖檔，
並用該檔既有的「大圖」圖框排版輸出 PNG。

流程：
  1. 由 比較\原提會.dxf、變更後細計.dxf 重算差異幾何（與 差異比對腳本_compare.py 同一套規則）
  2. 差異面 dissolve 後取外框，寫入 細計確認 模型空間新圖層（紅色 DASHED）
  3. 於「大圖」配置圖例第 4 欄補一列圖例
  4. 存 DXF → OdCopyEx 轉 DWG → OdPdfExportEx 出 PDF → PyMuPDF 轉 PNG
"""
import sys, io, os, subprocess
from collections import defaultdict, OrderedDict
import ezdxf
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union
from shapely import make_valid

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROP = r"D:\case\1. 辦理中\個人\1. 哲安\善化圳西段\03 計畫書件\20260828_內政部大會後提南市府主計大會提案單"
CMP = PROP + r"\比較"
SCRATCH = r"C:\Users\user\AppData\Local\Temp\claude\D--case-1---------1----------\24bff620-cf18-4235-bd0d-4ba2815c004b\scratchpad"
ODA = r"C:\Program Files\PSOFT\progeCAD 2025 Professional CHT\BimConverter"

SRC_DXF = SCRATCH + r"\細計確認.dxf"            # 由 20260330_細計確認.dwg 轉出
OUT_DXF = SCRATCH + r"\細計確認_套疊差異.dxf"
OUT_DWG = PROP + r"\20260330_細計確認_套疊差異範圍.dwg"
OUT_PDF = SCRATCH + r"\細計確認_套疊差異.pdf"
OUT_PNG = PROP + r"\20260330_細計確認_套疊差異範圍_大圖.png"

DIFF_LAYER = "差異範圍_原提會vs變更後細計"
CATS = ["住宅區", "綠地", "公園用地"]        # 優先序；理由見 差異比對腳本_compare.py
OTHER = "其他(道路等)"
MIN_AREA = 1.0

# ------------------------------------------------------------ 1. 重算差異幾何


def classify(layer):
    l = layer.replace(" ", "")
    if l == "BORDER":
        return "計畫範圍"
    if "地形標註" in l:
        return None
    for cat in ("住宅區", "公園用地", "停車場", "綠地"):
        if cat in l:
            return "公園用地" if cat == "停車場" else cat
    return None


def ring_to_poly(pts):
    if len(pts) < 3:
        return None
    p = Polygon(pts)
    if not p.is_valid:
        p = make_valid(p)
    return None if (p.is_empty or p.area < 1e-6) else p


def clean(g):
    if g is None or g.is_empty:
        return Polygon()
    g = make_valid(g).buffer(0)
    parts = []
    if isinstance(g, (MultiPolygon, GeometryCollection)):
        parts = [x for x in g.geoms if isinstance(x, Polygon) and x.area >= MIN_AREA]
    elif isinstance(g, Polygon) and g.area >= MIN_AREA:
        parts = [g]
    return unary_union(parts) if parts else Polygon()


def extract(path):
    doc = ezdxf.readfile(path)
    polys = defaultdict(list)
    for e in doc.modelspace():
        cat = classify(e.dxf.layer)
        if cat is None:
            continue
        if e.dxftype() == "LWPOLYLINE" and e.closed:
            p = ring_to_poly([(q[0], q[1]) for q in e.get_points("xy")])
            if p:
                polys[cat].append(p)
        elif e.dxftype() == "HATCH":
            for bp in e.paths:
                if not (bp.path_type_flags & 1):
                    continue
                pts = ([(v[0], v[1]) for v in bp.vertices] if hasattr(bp, "vertices")
                       else [(ed.start[0], ed.start[1]) for ed in bp.edges if hasattr(ed, "start")])
                p = ring_to_poly(pts)
                if p:
                    polys[cat].append(p)
    return polys


def partition(polys, border):
    part, used = OrderedDict(), Polygon()
    for cat in CATS:
        u = clean(clean(unary_union(polys.get(cat, []))).intersection(border).difference(used))
        part[cat] = u
        used = unary_union([used, u])
    part[OTHER] = clean(border.difference(used))
    return part


A, B = extract(CMP + r"\原提會.dxf"), extract(CMP + r"\變更後細計.dxf")
border = clean(unary_union(A["計畫範圍"]))
PA, PB = partition(A, border), partition(B, border)
allcats = CATS + [OTHER]

changes = []
for ca in allcats:
    for cb in allcats:
        if ca == cb:
            continue
        g = clean(PA[ca].intersection(PB[cb]))
        if g.area > MIN_AREA:
            changes.append((ca, cb, g))

diff = clean(unary_union([g for _, _, g in changes]))
parts = list(diff.geoms) if isinstance(diff, MultiPolygon) else [diff]
parts = [p for p in parts if not p.is_empty]
print(f"差異總面積 {diff.area:,.2f} m²（占計畫範圍 {diff.area / border.area * 100:.2f}%），"
      f"dissolve 後 {len(parts)} 塊")
for p in sorted(parts, key=lambda x: -x.area):
    print(f"   {p.area:10,.2f} m²  重心=({p.centroid.x:.1f},{p.centroid.y:.1f})  內環 {len(p.interiors)}")

# ------------------------------------------------------------ 2. 套疊到細計確認
doc = ezdxf.readfile(SRC_DXF)
doc.header["$LWDISPLAY"] = 1        # 讓線寬在出圖時生效
msp = doc.modelspace()

# 紅虛線畫在模型空間，套在既有底圖上；DASHED 段長 0.75 單位，公尺座標下需 ltscale。
# 加粗到 1.6 mm、長段虛線，並以 draw order 排到所有填色之上，才不被 solid hatch 蓋住。
LT = "DASHED"
MLTSCALE = 8.0        # 模型空間：dash ≈ 0.75×8 = 6 m（1:1000 → 6 mm 紙面）
MLW = 160             # 1.6 mm
if DIFF_LAYER in doc.layers:
    for e in list(msp.query(f'*[layer=="{DIFF_LAYER}"]')):
        msp.delete_entity(e)
    for e in list(doc.layouts.get("大圖").query(f'*[layer=="{DIFF_LAYER}"]')):
        doc.layouts.get("大圖").delete_entity(e)
    lay = doc.layers.get(DIFF_LAYER)
else:
    lay = doc.layers.add(DIFF_LAYER)
lay.dxf.color = 1                      # 紅
lay.dxf.linetype = LT
lay.dxf.lineweight = 50                # 0.50 mm
lay.on()
lay.thaw()
lay.unlock()

n = 0
diff_handles = []
for p in parts:
    rings = [list(p.exterior.coords)] + [list(r.coords) for r in p.interiors]
    for r in rings:
        e = msp.add_lwpolyline(r, close=True,
                               dxfattribs={"layer": DIFF_LAYER, "color": 1,
                                           "linetype": LT, "ltscale": MLTSCALE,
                                           "lineweight": MLW})
        diff_handles.append(e.dxf.handle)
        n += 1
print(f"寫入模型空間 {n} 條紅色虛線外框（{LT}, ltscale={MLTSCALE}, lw={MLW/100}mm）")

# draw order：不改動既有 SORTENTSTABLE（全表重寫會讓 ODA 出圖異常）；
# diff 為最後 append，靠自然順序 / handle 最大在上。PNG 另以 matplotlib 疊加保證可見。

# ------------------------------------------------------------ 3. 圖例補一列
sheet = doc.layouts.get("大圖")
# 沿用既有圖例文字樣式
style = "Standard"
for e in sheet.query('MTEXT[layer=="圖例"]'):
    style = e.dxf.style
    break
print("圖例文字樣式：", style)

# 圖例第 4 欄補一列（paper space；差異外框本體畫在 model space 見上）
LX0, LX1, LY = 371.03, 395.89, 67.70
sheet.add_lwpolyline([(LX0, LY), (LX1, LY)], close=False,
                     dxfattribs={"layer": DIFF_LAYER, "color": 1,
                                 "linetype": LT, "ltscale": 4.0, "lineweight": 160})
m = sheet.add_mtext("本次變更差異範圍",
                    dxfattribs={"layer": DIFF_LAYER, "char_height": 8.0,
                                "style": style, "color": 256, "attachment_point": 4})
m.set_location((LX1 + 5.0, LY))

doc.layouts.set_active_layout("大圖")
doc.saveas(OUT_DXF, encoding="utf-8")
print("\n寫出 DXF：", OUT_DXF)

# ------------------------------------------------------------ 4. 轉 DWG / 出 PDF / 出 PNG


def run(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", stdin=subprocess.DEVNULL)
    return (r.stdout or "") + (r.stderr or "")


print(run([ODA + r"\OdCopyEx.exe", OUT_DXF, OUT_DWG, "ACAD2013", "DWG"]).strip())
print("寫出 DWG：", OUT_DWG)

# exportflags: 2(hatch by vectorizer) + 8(other hatch vectorizer) + 256(SHX as geometry)
#              + 512(layer support) ；不設第 1 bit -> 只出 active layout(大圖)
flags = str(2 | 8 | 128 | 256 | 512)
print(run([ODA + r"\OdPdfExportEx.exe", OUT_DWG, OUT_PDF, flags]).strip()[:600])

import fitz
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams["font.family"] = ["Microsoft JhengHei", "DejaVu Sans"]

# 視埠參數（供紙面座標換算；twist=0，1:1000 → 紙面 mm = 實地 m）
vp = next(v for v in sheet.query("VIEWPORT") if abs(v.dxf.width - 550) < 5)
s = vp.dxf.height / vp.dxf.view_height
OX, OY = vp.dxf.center.x, vp.dxf.center.y
XC, YC = vp.dxf.view_center_point.x, vp.dxf.view_center_point.y


def to_paper(c):                                  # 實地 -> 紙面(mm, 從底)
    return (OX + (c[0] - XC) * s, OY + (c[1] - YC) * s)


pdf = fitz.open(OUT_PDF)
print(f"\nPDF 頁數 {pdf.page_count}")
best, best_i = None, 0
for i, pg in enumerate(pdf):
    r = pg.rect
    wmm, hmm = r.width / 72 * 25.4, r.height / 72 * 25.4
    print(f"  page{i}: {wmm:.1f} x {hmm:.1f} mm  area={wmm * hmm:,.0f}")
    if best is None or wmm * hmm > best:          # 「大圖」A1 是面積最大的頁
        best, best_i = wmm * hmm, i
print(f"選用 page{best_i}（大圖 A1）")
pg = pdf[best_i]
DPI = 300
pix = pg.get_pixmap(dpi=DPI, colorspace=fitz.csRGB, alpha=False)
img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
Wmm, Hmm = pg.rect.width / 72 * 25.4, pg.rect.height / 72 * 25.4
pdf.close()

# 以紙面座標為軸，將 ODA 底圖鋪滿，再疊畫地圖區紅虛線外框（保證在最上）
fig = plt.figure(figsize=(pix.width / DPI, pix.height / DPI), dpi=DPI)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, Wmm)
ax.set_ylim(0, Hmm)
ax.axis("off")
ax.imshow(img, extent=[0, Wmm, 0, Hmm], origin="upper", interpolation="lanczos", zorder=0)

# dash：6 mm 實線 + 3 mm 間隔；線寬 1.6 mm（換算 points）
mm2pt = 72.0 / 25.4
for p in parts:
    for r in [p.exterior] + list(p.interiors):
        xy = [to_paper(c) for c in r.coords]
        ax.plot([q[0] for q in xy], [q[1] for q in xy],
                color="#ff0000", linewidth=1.6 * mm2pt,
                linestyle=(0, (6 * mm2pt, 3 * mm2pt)),
                solid_capstyle="butt", zorder=10)

fig.savefig(OUT_PNG, dpi=DPI)
plt.close(fig)
print("寫出 PNG：", OUT_PNG, f"({pix.width}x{pix.height}px)")
