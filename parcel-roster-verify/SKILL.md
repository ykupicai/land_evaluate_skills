---
name: parcel-roster-verify
description: 土地清冊地號健檢:上 TCDGIS 多重地籍選取批次驗證每筆地號是否存在,查無者走內政部新舊地號 API(MOI_API_011)換算修正並回填清冊。當使用者說「確認清冊哪些地號有問題」「清冊地號驗證/健檢」「查無地號修正」「新舊地號查詢修正」「比對平台缺漏」,或拿到一份新清冊要進地籍出圖產線之前,務必先用此 skill。是 cadastral-map-pipeline 的第⓪步(tcdgis-parcels-to-shp 之前)。不適用於單純格式檢查(直接 pandas 檢查即可)、或已驗證過的清冊重跑。
---

# 土地清冊地號健檢(TCDGIS 批次驗證 + 新舊地號修正)

## Overview

把「縣市/鄉鎮區/段/小段/地號」清冊逐段批次加入 TCDGIS 多重地籍選取——**平台即時驗證每筆
地號存在性**;查無者用 MOI 新舊地號 API 換算成現行地號,回填修正後清冊。產出:①修正後
清冊(備註寫明依據+日期) ②平台匯出的完整屬性 Excel ③已含全部地號的平台選取清單
(可直接接 tcdgis-parcels-to-shp 的加入主題→下載 shp)。

2026-07-16 以清潔隊清冊 107 段 324 筆實測走通(6 筆修正、比對 0 缺漏)。

## 流程

1. **本機預檢+分批**:`python scripts/verify_roster.py batches <清冊.xlsx> <out.json>`
   ——欄位格式、母子號一致、重複地號,並 groupby(縣市/鄉鎮區/段/小段) 產批次 JSON(地號逗號串、去重)。
2. **登入與進圖台**:**REQUIRED SUB-SKILL: `tcdgis-parcels-to-shp`** 的前置與元件章節
   (使用者本人登入 → TCDEntrySys.aspx?Sys=4 → 同意地籍 modal → 開多重地籍選取;
   元件 id:`COUNTY_/TOWN_/SECTOR_SKINDA3` 下拉、`#CADANO_SKINDA3` 地號欄、
   `#btnCADANO_SKINDA3` 加入鈕;後綴 `_SKINDA3` 會變,找不到就
   `dijit.registry.filter(w=>/^COUNTY_/.test(w.id))` 重列)。
3. **批次加入(頁內注入 async driver,一次跑完全部批次)**:見下方〈Driver 要點〉。
4. **跑完立刻** `zoomtoCADAAll('SKINDA3')` → `BatchCADAToExcelMS('SKINDA3')` 匯出
   `Downloads\多重地籍選取結果表.xls`(重複匯出會存成 ` (1).xls`,**取 LastWriteTime 最新**)。
   **清單是前端狀態,跳轉/逾時即消失,絕不留隔夜**。
5. **比對**:`python scripts/verify_roster.py compare <清冊.xlsx> <結果表.xls>` → 缺漏清單。
6. **缺漏走新舊地號 API**(見下),換算出新段/新號後回平台補加入(舊號那筆若已誤加要先刪)。
7. **回填清冊**:原檔先備份,修正 段/地號/宗地母/宗地子,備註追加「XX段NN經新舊地號查詢
   (民國YY年重測)換算為ZZ段MM,已於TCDGIS驗證存在(日期)」。

## Driver 要點(bug 與時間陷阱,皆 2026-07-16 實測)

- **元件是 `dijit.form.Select`**:選項在 `.options`(`[{value,label}]`),**不是** store.data
  (舊筆記寫 FilteringSelect+store,版本已變;先讀 `dijit.byId(id).declaredClass` 判斷)。
  設值仍用 `.set('value',v)` 觸發縣市→鄉鎮→地段連動。
- **等待一律「輪詢目標出現」不是固定 sleep**:每 500ms 檢查 options 是否含目標段名,
  最多 10-12s;縣市/鄉鎮相同就不要重設(省連動等待)。
- **⚠️ 平台限流:連續「加入/查詢」動作間隔須 ≥10 秒**,太快會彈
  「請勿連續進行查詢動作!請10秒後再進行查詢」且該批加入 0 筆(2026-07-16 實測,
  5s 間隔連續 27 批全滅)。**每批加入之間固定睡 10.5s**;看到此訊息=限流非查無,
  該批等 10s 後**可重試一次**(這是唯一允許重試的訊息,勿與「查無地號」混淆)。
- 加入後的結果輪詢本身 ≤5s 即可(break=筆數增量≥本批 或 alertify 出現),
  但下一批仍要等滿 10.5s 節流間隔。百批全程約 20 分鐘,這是平台下限,快不了。
- **alertify 會排隊積壓**:舊訊息卡住會誤判成本批結果。每批結束把佇列清空:
  迴圈點 `.alertify-button-ok`(訊息在 `.alertify-message`)直到不可見。
- **「查無地號: X」= 即時最終回覆,不重試**(使用者鐵律 2026-07-16)。記入缺漏,直接走 API。
- **段名比對**:去掉 `[代碼]` 前綴後精確比對優先;有小段組成 `段名段+小段名小段`。
  注意異體字(頂**茄**芝來→平台為頂**加**芝來;臺/台)——找不到就列出該鄉鎮全部段名人工看。
- **其他查詢開新分頁**,TCDGIS 分頁絕不 navigate(前端清單會消失,實測痛過)。

## 新舊地號 API(MOI_API_011,免認證,實測可用)

```js
// POST 陣列,單次 ≤25 筆;瀏覽器 fetch 或 curl 皆可
fetch('https://openapi.moi.gov.tw/WEBAPI/LandNewOldQuery/1.0/QueryLandNo',{
  method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify([{UNIT:'GB',SEC:'0381',NO:'03090001',TYPE:'N'}])})
// UNIT=地政事務所代碼2碼=縣市代碼1碼+所序A,B,C…(縣市代碼=TCDGIS縣市下拉的value,
//   如宜蘭G→GA,GB…;不確定哪個所就 GA~GK 全帶一起丟,回 null 的就不是)
// SEC=段代碼4碼(直接抄 TCDGIS 地段下拉的 [xxxx] 前綴)
// NO=8碼:母號4碼+子號4碼零埋(309-1→03090001)
// TYPE='N' 舊查新 / 'O' 新查舊
// 回應 LANDSNCHANGE:[{SEC:新段代碼, NO:新8碼, RECEIVEYEAR:重測年, ...}] 或 null(無異動紀錄)
```
- 新段代碼查名稱:回 TCDGIS 該鄉鎮地段下拉找 `[新代碼]`;或 LISP 段名 API:
  `lisp.land.moi.gov.tw/MMS/Handle/QueryHandler.ashx?type=query&CountyCode=<縣碼>&Keyword=<段名>`
  (免 UI,回 JSON;縣碼=同 TCDGIS 縣市下拉 value 的 A-Z 一碼;LotCode=縣1+鄉2+段4)。
- **API 回 null=無異動紀錄**:地號真的不存在(分割註銷/合併)。依清冊慣例以母號示意出圖並備註,不硬湊。

## 銜接:清冊驗好之後

- 下一步是 `tcdgis-parcels-to-shp`(①,**同一次登入直接接**,勿登出)。
- 驗好的清冊(或①匯出的屬性 Excel)可另外餵 `nluz-landzone-query` 補
  **國土功能分區/原使用分區/原使用地/使用地** 四欄——不佔登入、可事後補跑,
  非都市土地開發評估案建議做(簡報第5頁的權威來源)。

## ⚠️ 最重要的陷阱:重測後相近段名,同號≠同宗地

礁溪「民權段327」在「民權一段」也有地號327——**但那是別人的地**。正解:民權段327
→(113年重測)→民權一段**368**。凡清冊段名查無、而鄉鎮內有相近段名(民權/民權一、
東振/東振新):**一律先走 API 換算,嚴禁直接在相近段名試同號**;試中了更危險(靜默錯地)。

## Quick Reference

| 目標 | 作法 |
|---|---|
| 分批/比對腳本 | `scripts/verify_roster.py batches\|compare` |
| 清單筆數 | `$('#tabCadalayer_SKINDA3').dataTable().fnGetNodes().length` |
| 刪清單某筆 | `dt.fnDeleteRow(node)`;node=fnGetNodes() 比對 cells[0] 的 14 碼鍵(地所2+段4+母4+子4,如 GB101003270000) |
| 清 alertify 佇列 | loop click `.alertify-button-ok`;訊息 `.alertify-message` |
| 匯出屬性 Excel | `BatchCADAToExcelMS('SKINDA3')` → Downloads\多重地籍選取結果表.xls |
| 新舊地號 API | openapi.moi.gov.tw/WEBAPI/LandNewOldQuery/1.0/QueryLandNo |
| 段名存在(免UI) | MMS QueryHandler.ashx?type=query&CountyCode=X&Keyword=段名 |
| 段名↔段代碼(免UI,免登入) | `nluz-landzone-query` 的 `nluz_query.py sections --county <縣市> --town <鄉鎮>` |
| 全國段名代碼批次 CSV | `lisp.land.moi.gov.tw/MMS/Handle/DownloadQuerySection.ashx?DownloadType=csv&CountyCode=<縣碼字母>`(乾淨 CSV:段/小段/代碼/所區碼/縣市/鄉鎮/事務所) |

## Common Mistakes

| 錯誤 | 真相 |
|---|---|
| 用 store.data 讀選項 | 現版是 dijit.form.Select,用 `.options` |
| 固定 sleep 等連動/驗證 | 輪詢+提早 break;加入驗證 ≤5s 即回 |
| 查無地號重試/換段猜號 | 即時最終回覆;查無=走 API,相近段名同號是別人的地 |
| alertify 訊息當本批結果 | 佇列會積壓,先清空再讀 |
| 加完慢慢做別的再匯出 | 前端清單跳轉即失,跑完立即定位+匯出 |
| API 回 null 當失敗重打 | null=無異動紀錄,母號示意+備註 |
| 直接覆寫原清冊 | 先備份;修正處備註寫依據與日期 |
