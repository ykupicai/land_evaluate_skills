---
name: dxf-atlas
description: 把 DXF/DWG 差異範圍或標註以「紅色虛線外框」等註記層套疊到既有 CAD 大圖圖框、出成 PDF/PNG 成果圖時使用。當使用者說「差異範圍套疊出圖」「紅色虛線疊到細計/底圖」「用既有大圖圖框排版出 PNG」「DXF 出圖冊」「比對成果疊圖出圖」，或要在 progeCAD/ODA 出圖流程上加註記層時，務必使用此 skill——即使只說「幫我把差異疊到這張圖出圖」也適用。它封裝了 ODA 底圖 + matplotlib 紙面座標疊圖的已驗證作法，避開 SORTENTSTABLE／MTEXT／paper-space 等踩過的雷。不適用於 DXF→SHP 轉檔（用 dxf-to-shp）或 QGIS 版面出圖（用 parcel-map-sheet）。
---

# DXF 大圖套疊出圖（紅線／註記層）

把差異範圍或標註套疊到既有 CAD 大圖圖框並出 PDF/PNG 的**已驗證產線**。核心心法：
**註記本體寫進 DXF model space（受視埠裁切、跟著底圖），最終可見性靠 matplotlib 以「紙面座標」在 ODA 底圖上重畫一次（永遠在最上、完全不受 CAD draworder 影響）。**

已驗證黃金範例：`references/overlay_golden.py`（善化圳西段，2026-08 實際交付）。新案照它改路徑與分類規則即可。

## 產線五步
1. **重算幾何**（shapely）：讀來源 DXF、依圖層分類、`make_valid`+`buffer(0)` 清理、`partition` 依優先序切不重疊、求差異 dissolve。
2. **寫紅虛線進 model space**：`add_lwpolyline(..., linetype="DASHED", ltscale=大值, lineweight=160)`；設 `$LWDISPLAY=1`。
3. **圖例補列**：畫在 **paper space（配置「大圖」）**，MTEXT 沿用既有 `style`、用 `attachment_point`+`set_location`。
4. **轉檔出圖**：`OdCopyEx` DXF→DWG(ACAD2013) → `OdPdfExportEx` DWG→PDF。
5. **matplotlib 疊圖保命**：PyMuPDF 取面積最大頁（＝大圖 A1）render 成影像 → 以紙面 mm 為軸鋪底 → 用視埠參數 `to_paper()` 把差異外框換到紙面座標、`zorder=10` 重畫紅虛線 → 存 PNG。

## DO / DON'T（每條都是踩過的雷）

- **DON'T 全表重寫 SORTENTSTABLE 去改 draworder** → ODA 出圖時地圖區會變空白（排序鍵與真實 handle 空間衝突，解析錯亂）。
  **DO** 讓 diff 最後 append 靠自然順序在上；真正的可見性交給第 5 步 matplotlib overlay。
- **DON'T 想自動向量化/抽取紅箭頭** → 不可靠（會出「破掉的巨大箭頭」）。
  **DO** 需要箭頭/註記就在 matplotlib overlay 手動畫。
- **DON'T 把紅線只畫在 paper space** 期待蓋住地圖 → 會被視埠(viewport)遮住。
  **DO** 註記本體畫 model space（進視埠）、圖例線畫 paper space。
- **DON'T 忘記 `$LWDISPLAY=1`** → 線寬在出圖不生效。
- **model space 用公尺座標時 `ltscale` 要放大**（範例 `MLTSCALE=8.0`，dash≈6m），否則虛線看起來像實線。
- **`OdPdfExportEx` flags 不設第 1 bit（值=1）** → 只出 active layout（大圖），不會把所有配置都吐出來。範例用 `2|8|128|256|512`。
- **選頁：取面積最大的 PDF 頁** 當大圖 A1，別假設 page0。
- **視埠→紙面換算**：`s = vp.height/vp.view_height`；`to_paper(c)=(OX+(cx-XC)*s, OY+(cy-YC)*s)`（範例假設 twist=0、1:1000）。
- **字型** rcParams 加 `Microsoft JhengHei` fallback，否則中文變框框。
- 中文路徑檔案操作一律 PowerShell、寫檔 UTF-8（同全域準則）。

## 驗收
- 產出 PNG 後**目視確認紅虛線在地圖區可見**（不是只在圖例）。
- 建議留一張 golden PNG 對照，之後回歸時肉眼可比。
- 差異總面積與占比印出、dissolve 後塊數合理。

## 環境
- ODA/progeCAD 工具：`C:\Program Files\PSOFT\progeCAD 2025 Professional CHT\BimConverter`（`OdCopyEx.exe`、`OdPdfExportEx.exe`）。
- 套件：`ezdxf shapely pymupdf(fitz) matplotlib numpy`。
