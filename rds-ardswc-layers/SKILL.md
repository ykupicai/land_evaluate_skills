---
name: rds-ardswc-layers
description: 從農村發展及水土保持署「農村決策空間圖台」(rds.ardswc.gov.tw)批次擷取圖層成 shp/GeoJSON。當使用者提到「農村決策空間圖台」「rds.ardswc.gov.tw」「農村規劃決策輔助資源系統」「ardswc 圖資」,或要抓該圖台的農村再生/農村輔導/農地利用/農村文化/農村安全/國土功能分區等圖層時,務必使用此 skill——即使只說「幫我撈這個圖台的圖資」也適用。不適用於 NLSC 圖磚、TCDGIS 地籍(用 tcdgis-parcels-to-shp)、或其他機關圖台。
---

# 農村決策空間圖台(RDS)圖層擷取

## Overview

圖台前端是 SvelteKit SPA,底層為 **ArcGIS Server**(capabilities=`Map,Query,Data`,查詢開放)。
**直連 ArcGIS 主機會被 WAF 擋(403)**,唯一路徑是登入後走同源 `/api/proxy?<url>` 並帶
`X-CSRF-TOKEN`。token 由 `/api/auth/knock` 動態發放。分頁 2000 筆/次即可完整取出向量。

2026-07-30 實測:36 層、約 87 萬筆要素(最大單層 449,544 面)全數擷取成功。

## 流程

1. **使用者本人登入** `https://rds.ardswc.gov.tw/app/`(帳密+圖形驗證碼,或單簽登入 SSO)。
   **agent 不可代填帳密、不可解驗證碼**;開好頁面請使用者完成,回覆後再續。
2. **注入擷取器**:把 `scripts/browser_extract.js` 全文用 javascript_tool 注入該分頁
   (回傳 `__rds` 物件)。頁面若重新載入(如重新登入)注入即失效,重注即可,已下載檔案不受影響。
3. **查清單/筆數**:圖層 id 見 `references/layer_catalog.csv`(4 服務 341 層,含群組結構);
   或 `await __rds.count(id)` / `__rds.meta(id)` 即時查。
4. **擷取**:`__rds.batch([[id,count],...])` 背景批次,檔案落到
   `C:\Users\<user>\Downloads\rds_<id>.geojson`。**首次批次瀏覽器會跳「允許多個檔案下載」,
   要按允許**,否則只存到第一個檔就靜默停止。
5. **轉檔部署**:先寫 `map.csv`(欄位 `id,group,name`;`group` 留空=不分群組,
   範本見 `references/map_example_tainan36.csv`),再跑:
   ```
   python scripts/geojson_to_shp.py --dest <輸出根目錄> --map map.csv [--src <geojson目錄>] [--ids 89,91]
   ```
   `--src` 預設 `~/Downloads`;已存在同名 shp 者略過(可安全重跑續補);有層尚未下載會非零離開。
6. **驗收**:`await __rds.verify([id,...])` 逐層比對伺服器 count 與已抓筆數
   (回 `OK`/`MISMATCH`/`未抓`)。**MISMATCH = 缺頁,重抓該層**——缺頁不會報錯,不比對就發現不了。

## 關鍵事實(踩過的坑)

- **群組層不可抓**:`layer_catalog.csv` 的 `type=群組` 只是目錄節點,無要素;抓其下 `圖層`。
- **分類子層是重複資料**:如「各分區獨立顯示」「設施分類」底下各層,是母層依屬性拆分,
  抓母層即涵蓋全部,別重複抓(白費數倍時間)。
- **403 = token 過期,不是沒權限**:刷新 `/api/auth/knock` 後重試一次即可(腳本已內建)。
  真沒權限是「登入前」才會遇到。
- **PAGE 固定 2000**:等於服務 `maxRecordCount`,調高會被伺服器靜默截斷、造成缺資料。
- **工具呼叫 30 秒逾時 ≠ 任務失敗**:頁面內非同步批次仍在跑,查 `__rds.state`
  (`running:false` 且 `cur:null` 才是跑完)。逾時後**別重跑同一批**——先看 Downloads
  已有哪些 id,只把缺的組成新清單續跑:
  ```powershell
  ls ~/Downloads/rds_*.geojson | % { $_.BaseName -replace 'rds_','' } | sort
  ```
- **切換服務**:預設 `ardswc_map_114`;要抓 `ardswc_analysis_114`(148 層)等,先
  `__rds.setService('ardswc_analysis_114')`。**不同服務的同名圖層 id 不同**
  (如「54區特定水土保持區範圍圖」在 map_114 是 43、analysis_114 是 66),
  務必以該服務的 catalog 列為準,抓前用 `__rds.meta(id)` 確認 name 對得上。
- **大層記憶體**:`extract` 會把整層累積在記憶體再一次序列化,45 萬筆約數百 MB。
  單層抓即可(實測 449,544 筆可行),但**別同時併發多個大層**。
- **輸出併存 shp + geojson**:shp 的 DBF 欄名上限 10 bytes,中文長欄名(如「歷年跨域產業」
  那層 33 欄)會被截斷;**屬性分析請用 geojson,出圖用 shp**。
- **座標**:查詢帶 `outSR=3826` 直接取 TWD97 TM2,免事後轉換。

## Quick Reference

| 目標 | 作法 |
|---|---|
| 服務清單 | `/api/proxy?https://rds.ardswc.gov.tw/server/rest/services/ardswc?f=json` |
| 主服務 | `ardswc_map_114`(128 層,主力);另有 `ardswc_analysis_114`(148 層)、`ardswc_map_public_114`、`ardswc_cadastral_113` |
| 圖層目錄 | `references/layer_catalog.csv`(service,layer_id,parent_id,type,name) |
| 常用層範本 | `references/map_example_tainan36.csv`(2026-07-30 為臺南農再案抓的 36 層,可直接當 map.csv 用) |
| 取 token | `GET /api/auth/knock` → `{csrfToken}` |
| 查筆數 | `<layer>/query?where=1=1&returnCountOnly=true&f=json` |
| 拉向量 | `<layer>/query?where=1=1&outFields=*&outSR=3826&resultOffset=N&resultRecordCount=2000&f=geojson` |
| 大圖層估時 | 45 萬筆(225 頁)約 20-40 分;先跑小層驗證管線再跑大戶 |

## Common Mistakes

| 錯誤 | 真相 |
|---|---|
| 用 Python/curl 直連 ArcGIS 主機 | WAF 擋 403;必須走登入分頁的 `/api/proxy` |
| 把 403 當權限不足而放棄 | 多半是 token 計時過期,knock 一次就好 |
| 抓群組層或分類子層 | 群組無要素;分類子層與母層重複 |
| PAGE 調成 5000 求快 | 超過 maxRecordCount 會被截斷,資料缺漏且無警告 |
| 工具逾時就整批重跑 | 頁面內仍在跑;先查 `__rds.state` 與 Downloads 現有檔案 |
| 只交付 shp | 中文欄名被截斷;務必併存 geojson |
| 抓完不比對筆數 | 缺頁不會報錯;跑 `__rds.verify([...])` 才算完成 |
| 批次只下載到第一個檔 | 瀏覽器擋多重下載;首次要按「允許多個檔案下載」 |
| 跨服務沿用同一組 layer id | 各服務 id 各自編號,同名層 id 不同;抓前 `meta(id)` 確認 name |
