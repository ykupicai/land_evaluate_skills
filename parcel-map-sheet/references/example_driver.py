# -*- coding: utf-8 -*-
"""最小可跑範例：從一個含「基地」「周邊地籍」表的 gpkg，出一張最大化地圖版面的
「使用分區」主題 PNG。用 QGIS 內建 python 執行：

  & "C:\\Program Files\\QGIS 3.40.12\\bin\\python-qgis-ltr.bat" example_driver.py

這是**版面**範例，符號化用簡化 categorized（正式出圖請套 styles/使用分區.qml）。多主題就
換圖層/樣式後重複呼叫 build_sheet_layout。已在真實官田資料驗證：1/6000、四角淨空、
疊圖零遮基地、周邊無 label、涵蓋地號收合為「番子渡頭段 122 等 145 筆」。
"""
import shutil
import sys
from pathlib import Path

# --- 依你的環境改這幾行 ---------------------------------------------------------
QGIS_PREFIX = r"C:\Program Files\QGIS 3.40.12\apps\qgis-ltr"
SKILL_SCRIPTS = Path(r"C:\Users\user\.claude\skills\parcel-map-sheet\scripts")
GPKG = Path(r"...\圖層.gpkg")          # 含「基地」「周邊地籍」表（shp-xls-area-join 或參考案產出）
OUT_DIR = Path(r"...\圖檔")
LOCATION = "臺南市官田區"
PARCEL_SECTION, PARCEL_FIRST, PARCEL_TOTAL = "番子渡頭段", "122", 145
# ------------------------------------------------------------------------------

sys.path.insert(0, str(SKILL_SCRIPTS))
from qgis.core import (QgsApplication, QgsVectorLayer, QgsProject, QgsGeometry,
                       QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsFillSymbol,
                       QgsLayoutExporter, QgsCoordinateReferenceSystem,
                       QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
                       QgsVectorLayerSimpleLabeling)
from qgis.PyQt.QtGui import QColor, QFont
import build_layout as bl

QgsApplication.setPrefixPath(QGIS_PREFIX, True)
app = QgsApplication([], False)
app.initQgis()
proj = QgsProject.instance()
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 每個表各一份獨立複本，避開同 gpkg 跨表 SQLite 並發問題（見 usage.md）
cN = OUT_DIR / "_neigh.gpkg"; shutil.copyfile(GPKG, cN)
cB = OUT_DIR / "_base.gpkg";  shutil.copyfile(GPKG, cB)
neigh = QgsVectorLayer(f"{cN}|layername=周邊地籍", "使用分區", "ogr")
base = QgsVectorLayer(f"{cB}|layername=基地", "基地地籍", "ogr")  # 圖例照層名顯示
for l in (neigh, base):
    assert l.isValid(), l.name()
    if not l.crs().isValid():
        l.setCrs(QgsCoordinateReferenceSystem("EPSG:3826"))

# 周邊：依「使分」上色（正式版改 neigh.loadNamedStyle('styles/使用分區.qml')）；不上 label
vals = sorted({(f["使分"] or "") for f in neigh.getFeatures()})
pal_rgb = [(255, 190, 120), (200, 230, 150), (150, 200, 240), (230, 200, 230),
           (250, 230, 150), (200, 200, 200)]
cats = [QgsRendererCategory(v, QgsFillSymbol.createSimple(
    {"color": f"{pal_rgb[i % len(pal_rgb)][0]},{pal_rgb[i % len(pal_rgb)][1]},{pal_rgb[i % len(pal_rgb)][2]},255",
     "outline_style": "no"}), v or "（空白）")   # 周邊只留填色不畫邊線（使用者定案）
        for i, v in enumerate(vals)]
neigh.setRenderer(QgsCategorizedSymbolRenderer("使分", cats))
neigh.setLabelsEnabled(False)   # ← 周邊不上地號

# 基地：紅框（寬 0.5，使用者定案的細框）+ 地號 label（正式版改 loadNamedStyle('styles/基地紅框.qml')）
base.renderer().setSymbol(QgsFillSymbol.createSimple(
    {"color": "0,0,0,0", "style": "no", "outline_color": "255,0,0,255", "outline_width": "0.5"}))
pl = QgsPalLayerSettings(); pl.fieldName = "地號"
fmt = QgsTextFormat(); fmt.setFont(QFont("Microsoft JhengHei")); fmt.setSize(9)
buf = QgsTextBufferSettings(); buf.setEnabled(True); buf.setSize(1.0); buf.setColor(QColor(255, 255, 255))
fmt.setBuffer(buf); pl.setFormat(fmt)
base.setLabeling(QgsVectorLayerSimpleLabeling(pl)); base.setLabelsEnabled(True)

proj.addMapLayer(neigh, False); proj.addMapLayer(base, False)

# 基地 dissolve 幾何（供避讓）＋ bbox：先 makeValid 再 union；bbox 用 layer.extent()
g = QgsGeometry.unaryUnion([f.geometry().makeValid() for f in base.getFeatures()])
e = base.extent()
bbox = (e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum())

keep = []
layout, placement = bl.build_sheet_layout(
    proj, "使用分區",
    layers=[base, neigh], legend_layers=[neigh, base], legend_hide_title=set(),
    base_geom=g, bbox=bbox, location=LOCATION,
    parcel_note_text=bl.parcel_note(PARCEL_SECTION, PARCEL_FIRST, PARCEL_TOTAL),
    keep_alive=keep)
print(f"1/{placement.scale} assign={placement.assign} "
      f"zoomed={placement.zoomed_out} outside={placement.outside}")

settings = QgsLayoutExporter.ImageExportSettings(); settings.dpi = 300
out_png = OUT_DIR / "使用分區.png"
if out_png.exists():
    out_png.unlink()
QgsLayoutExporter(layout).exportToImage(str(out_png), settings)
print("->", out_png)
app.exitQgis()
