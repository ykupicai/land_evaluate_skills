---
name: buffer-greenbelt
description: 對地籍基地畫「等寬緩衝綠帶」並出圖:多宗基地 dissolve 後自邊界向內退縮 W 公尺(預設10m),以差集取得 W m 寬綠帶,輸出 綠帶shp+退縮後基地shp+面積統計,並以綠色填色套 maxmap 版面出成果圖。當使用者提到「緩衝綠帶」「基地向內退縮N公尺」「offset/內縮出一條綠帶」「退縮帶」「綠帶配置圖」「buffer -10」時,務必使用此 skill——即使只說「幫這個基地畫10米綠帶」也適用。獨立加值功能,不在 cadastral-map-pipeline 主流程內。不適用於一般 GIS buffer 分析(非基地綠帶情境)。
---

# 基地緩衝綠帶(dissolve → 內縮 → 差集)

用 `scripts/make_greenbelt.py` 算幾何,再套 `parcel-map-sheet` 的 maxmap 版面出圖。
作法為使用者定案(2026-07 官田案驗證):**dissolve → buffer(−W) → difference**。

## 1) 算綠帶

```powershell
python scripts/make_greenbelt.py --base <基地.shp|圖層.gpkg> [--layer 基地] --width 10 --out-dir 緩衝綠帶
```

輸出 `緩衝綠帶{W}m.shp` + `退縮後基地.shp`(BIG5,沿用來源 CRS),並印面積統計
(基地/退縮後/綠帶 ha 與佔比)——回報給使用者時引用這些實算數字。

**幾何行為(重要,都印在腳本輸出,不可靜默):**
- **預設含洞緣**:退縮自所有邊界為之,dissolve 區塊內部的洞(未圈入宗地/水路)洞緣也有
  綠帶。官田案使用者確認此為正確行為。只要外周長時加 `--outer-only`(先填洞再退縮,
  綠帶再與原範圍交集,避免落在洞內非基地土地)。
- **寬度不足 2W 的獨立區塊會整塊變綠帶**(退縮後消失)——腳本點名警告,務必轉告使用者。
- 幾何一律先 `make_valid` 再 union(地籍 shp 常含無效幾何,不修會靜默算錯)。
- CRS 須為公尺制(臺灣 EPSG:3826);非公尺制腳本會警告,退縮距離會失真。

## 2) 出圖

套 maxmap 版面(`build_sheet_layout`,QGIS python 執行),圖層由上而下:
**基地地籍(紅框0.5+地號 label) → 緩衝綠帶(綠色填色、無邊線) → EMAP(0.85) → 正射PHOTO2**;
圖例=[綠帶, 基地]。綠帶樣式:

```python
green.renderer().setSymbol(QgsFillSymbol.createSimple(
    {"color": "56,168,0,255", "style": "solid", "outline_style": "no"}))
```

可跑的官田完整範例:[references/render_greenbelt_guantian.py](references/render_greenbelt_guantian.py)
(依 `大量圖資轉換工具/scripts` 的 vendored `build_layout`/`make_maps` helper;新案改
CASE 路徑、位置與涵蓋地號字串即可)。比例尺/範圍/角落避讓照常以**基地 dissolve**計
(不是綠帶),與其他主題圖同範圍同比例。

## 官田參考值(驗證基準)

145 宗 → dissolve 4 區塊、全數存活;基地 59.67 ha、退縮後 53.91 ha、
**綠帶 5.75 ha(9.6%)**;`--outer-only` 則 5.70 ha。1/6000、疊圖 BR/BL。

## 回報格式

給使用者:綠帶面積與佔比、退縮後可配置面積、區塊存活數(有消失整塊要點名)、
shp 與 PNG 路徑;首次做該案時說明「含洞緣/僅外周長」的差異讓使用者選。
