---
name: landmark-to-parcel
description: Use when you have a Google Maps URL, short link (maps.app.goo.gl), or WGS84 lat/lon and need the current 地段地號 (administrative district + cadastral section + parcel number) it falls on — reverse cadastral lookup, coordinate-to-parcel, 座標反查地籍, 地標查地號, 網址查地號. Taiwan only.
---

# landmark-to-parcel（地標／座標 → 現行地段地號反查）

## Overview

跟一般地籍查詢方向相反：別的工具是「地號→幾何」正查，這支是「**點→地號**」反查。
把 Google Maps 地標點位反查成 **行政區＋地段（含小段）＋地號**，並附使分/使類/面積與可信度旗標。

權威分工：**本機地籍快照只當「候選來源」，現行地號一律以農業部即時查詢為準。**

## When to Use

- 有 Google Maps 網址／短網址（maps.app.goo.gl），或一組經緯度，要知道落在哪筆地。
- 反查結果可直接寫 `基地.shp` 餵 `make_maps --trust-shp` 出圖（都市計畫／空照套疊等）。

**不適用**：只給地標「名稱」不給網址／座標（需地理編碼、有查錯地方風險，本 skill 不做）；
台灣以外。

## Quick Reference（引擎在本專案，非 skill 內）

```bash
# 大量圖資轉換工具/ 專案根目錄下，用 QGIS python（PyQGIS，PowerShell 呼叫）
.\scripts\qgis_python.ps1 scripts/latlon_to_parcel.py "<Google Maps 網址>"
.\scripts\qgis_python.ps1 scripts/latlon_to_parcel.py --lat 22.924 --lon 120.347
# 順便寫基地.shp（可接出圖）：加 --out outputs/<案>/cadastre
# JSON 輸出：加 --json ；其餘旗標見 --help

# 一鍵接產線（反查→基地→周邊地籍→出圖，單點單筆，--case 必填）：
.\scripts\qgis_python.ps1 scripts/run_case.py --latlon "<網址>" --case <案名>
```

引擎流程：展開網址抓地標座標 → WGS84→EPSG:3826 → 農業部 identify 定縣市 →
本機快照點面相交出候選 → **段名先驗** → 農業部確認候選 → 需要時**收斂式子號探測**。

## 三個守門機制（都是踩坑後補的，看到別拿掉）

1. **座標要抓對那一組**：google maps 網址有兩組座標——`!3d<緯>!4d<經>` 是地標本身（取這組），
   `@<緯>,<經>` 是地圖視角中心（會偏移）。引擎優先取前者，只剩後者時標警告。

2. **段名一定要含小段**：農業部只認「新化段**王公廟小段**」，不認裸「新化段」。本機快照的
   `段`/`小段` 是兩欄，漏了小段會**整筆查無**，並被下游誤判成「分割」。（三子寵物天堂案實踩）

3. **段名先驗，排在探測之前**：先 `moa.resolve` 確認農業部認得這個段名。段名對不上 →
   直接判「段名問題」，**不可**讓子號探測把它誤報成「跨母號分割」。

## 可信度判讀（交付前必看）

- **點距邊界 <5m** → 引擎標「近界、建議人工確認相鄰筆」。Google 地標點常有 5~15m 誤差，
  靠邊時可能其實是隔壁那筆；界內數十公尺才篤定。
- **使分/使類空白** → 屬**都市土地或未登錄地**，身分待查證。交付文件**不可逕寫「都市土地」**
  （getLandInfo 對兩者回傳相同、無法區分）。都市土地的分區另查都市計畫圖（見專案 make_maps
  `使用分區` 主題會疊都市計畫 Color1）。
- 農業部即時值與本機快照不一致時，**以農業部為準**（本機是 111年2月舊快照）。

## 分割與死角（收斂探測）

本機快照裡的宗地在 111年2月後可能被**分割**：候選地號的現行幾何已縮小、不再含這個點
（關廟案：780-10 已分割，點實際落在 780-44）。引擎會：候選不含點 → 探同母號子號、
**探到含點即停、連續 15 筆查無才止**（不預設固定上限；曾因手寫範圍太小漏掉 780-44）。

**唯一死角**：分割後新地號掛到**別的母號**或**重測改號**（都市土地常見）→ 子號探測會落空，
引擎回 `FAIL_CROSS_MOTHER`，明確要求**退線上空間反查**（NLSC 地籍圖，尚未接掛），
**不會硬掰一個地號**。遇到這狀態就是該案需人工上地籍圖台查。

## 依賴

- 本專案 `大量圖資轉換工具/scripts/latlon_to_parcel.py`（引擎）與 `地籍圖資/<縣市>.shp`（本機快照）。
- skill `cadastre-check` 的 `api`/`moa` 模組（農業部 coagis 正查＋縣市界 identify；免登入）。
- 出圖接 `make_maps.py --trust-shp <基地.shp>`（見 skill `cadastral-map-pipeline`）。

## 已驗證

臺南關廟（分割→780-44，探測 44 次）、臺南新化（含小段 1230-3，1 次）、
嘉義東石（特定專用區 25，1 次）三案端到端通過（2026-08-21）。
