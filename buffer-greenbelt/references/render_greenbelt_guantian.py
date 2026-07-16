# -*- coding: utf-8 -*-
"""官田 10m 緩衝綠帶出圖:正射為底、綠帶填綠、基地紅框,套 maxmap 版面。"""
import sys
from pathlib import Path

PROJ = Path(r"C:\Users\user\Documents\Claude\Projects\大量圖資轉換工具")
CASE = PROJ / "outputs" / "20260707官田maxmap"
sys.path.insert(0, str(PROJ / "scripts"))

from qgis.core import (QgsApplication, QgsVectorLayer, QgsRasterLayer, QgsProject,
                       QgsGeometry, QgsCoordinateReferenceSystem, QgsFillSymbol,
                       QgsLayoutExporter)
import build_layout as bl
import make_maps as mm

QgsApplication.setPrefixPath(r"C:\Program Files\QGIS 3.40.12\apps\qgis-ltr", True)
app = QgsApplication([], False); app.initQgis()
proj = QgsProject.instance()
proj.setCrs(QgsCoordinateReferenceSystem("EPSG:3826"))

# 圖層
photo = QgsRasterLayer(str(CASE / "底圖" / "001_PHOTO2.tif"), "正射影像(NLSC PHOTO2)")
emap = QgsRasterLayer(str(CASE / "底圖" / "001_EMAP2.tif"), "通用電子地圖(NLSC EMAP2)"); emap.setOpacity(0.85)
green = QgsVectorLayer(str(CASE / "緩衝綠帶" / "緩衝綠帶10m.shp"), "緩衝綠帶(寬10m)", "ogr")
base = QgsVectorLayer(f"{CASE / '圖層.gpkg'}|layername=基地", "基地地籍", "ogr")
for l in (photo, emap, green, base):
    assert l.isValid(), l.name()

# 樣式:綠帶=綠色填色無邊線;基地=紅細框+地號
green.renderer().setSymbol(QgsFillSymbol.createSimple(
    {"color": "56,168,0,255", "style": "solid", "outline_style": "no"}))
base.renderer().setSymbol(mm.outline_symbol())
base.setLabeling(mm.label_settings()); base.setLabelsEnabled(True)
for l in (photo, emap, green, base):
    proj.addMapLayer(l, False)

# 比例尺/範圍/角落避讓:以基地 dissolve 計
g = QgsGeometry.unaryUnion([f.geometry().makeValid() for f in base.getFeatures()])
e = base.extent()
bbox = (e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum())

keep = []
layout, pl = bl.build_sheet_layout(
    proj, "緩衝綠帶", [base, green, emap, photo], [green, base], set(),
    base_geom=g, bbox=bbox, location="臺南市官田區",
    parcel_note_text="社子段 389 等 145 筆（跨2段）", keep_alive=keep)
print(f"1/{pl.scale} assign={pl.assign} outside={pl.outside}")

s = QgsLayoutExporter.ImageExportSettings(); s.dpi = 300
out = CASE / "緩衝綠帶" / "001_20260707官田maxmap_緩衝綠帶10m.png"
if out.exists(): out.unlink()
QgsLayoutExporter(layout).exportToImage(str(out), s)
print("->", out)
app.exitQgis()
