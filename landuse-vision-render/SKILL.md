---
name: landuse-vision-render
description: 把土地使用計畫平面配置(SHP/DXF面+高度表)做成3D開發願景圖時使用。當使用者提到「願景圖」「開發示意圖」「量體模擬」「配置圖轉3D」「土地開發3D渲染」「blender+comfyui出願景」,或給配置面圖層+各分區高度要出鳥瞰渲染圖時,務必使用此skill——即使只說「幫這個案子做願景圖」也適用。不適用於單棟建築細部渲染(需真實建築設計)或純2D配置上色。
---

# 土地開發願景圖產線（Blender幾何 + ComfyUI拋光 + 空照合成）

## 核心原則
**幾何歸 Blender（確定性），AI 只做拋光。** 位置/數量/高度永遠來自計畫資料，AI 不得負責。成品是「概念願景圖」，對外必標註「AI 生成示意圖，實際以後續設計成果為準」。

## 首案範本（先讀）
屏東太空中心案＝完整可跑的範本。**接手先讀** `C:\Users\user\Documents\Claude\Projects\願景圖繪製\CLAUDE.md`（產線細節＋14條雷區）；腳本備份於 NAS 案件資料夾 `願景圖\產線腳本\`。

## 輸入檢核（缺一不可）
1. **配置面圖層**：SHP/GPKG 分區面，屬性含使用類別（DXF 只有線→先轉面；TWD97 EPSG:3826）
2. **高度表**：各使用類別的建物高度＋建築面積（如 landuse.xlsx）
3. **空照**：QGIS 匯出基地周邊 NLSC 正射＋bounds JSON（直連 NLSC 會被憑證/SSL 擋）

## 產線五步（腳本在範本專案 `工作/`）
| 步驟 | 腳本 | 說明 |
|---|---|---|
| ① 帶高度圖層 | geopandas | SHP+高度表 → `配置_含高度.gpkg`(use/height欄) |
| ② 佈局導出 | `export_scene_json.py` | 量體/樹/車/標線/池岸/**耳切三角化**, seed=42 |
| ③ 3D渲染 | `blender_scene.py` | 4視角×5通道(rgb/depth/mask/bmask/silh)。`USE_CYCLES=1 CYCLES_DEVICE=OPTIX` 上GPU |
| ④ AI拋光 | `comfy_auto.py` | ComfyUI API：tiled 3x(denoise 0.30) → bmask立面重繪(0.55)。改HOST為pod網址 |
| ⑤ 空照合成 | `blender_bg.py`+`composite_aerial.py` | 同相機空照背景×(1−silh alpha)＋成品×silh |

## 環境
- 本機無獨顯可跑（EEVEE快跑/Cycles CPU 3分鐘一視角）；RunPod 4090 用 OptiX 秒級
- **pod 容器 Blender 必用 4.2 LTS**（5.2 會 futex crash）＋ `apt-get install -y libsm6 libice6`
- ComfyUI 模型：RealVisXL_V5.0 / controlnet-depth+tile-sdxl / 4x-UltraSharp / UltimateSDUpscale node

## 判斷準則（收斂後定案，勿重新摸索）
- AI 小物件糊 → 提高 tiled `upscale_by`（每磚內物件要夠大），**不是**提高 denoise
- 高去噪全圖重繪＝毀真陰影＋生幻覺 → 只允許 tiled 輕拋光＋遮罩式局部重繪
- 凹多邊形（L形基地）任何填面/Boolean → 一律先耳切三角化
- 合成遮罩＝場景透明底渲染的 **alpha 剪影**（代理幾何會有破洞）
- 驗收：材質在成品視距看、遮罩要看形狀不能只看白色比例

## 常見錯誤
| 症狀 | 原因/解法 |
|---|---|
| 場景遠處被裁 | Blender 相機 clip_end 預設1000m → 設100000 |
| 大地面材質看不出紋理 | Noise 預設 Generated 座標 → 接 Object 座標 |
| ComfyUI API 400 | 看 response 的 node_errors（如 UltimateSDUpscale 要 batch_size） |
| 中文路徑檔案壞掉 | 用 python shutil/PowerShell，禁 Bash cp/mv |
