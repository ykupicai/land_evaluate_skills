# nluz.nlma.gov.tw 端點細節（2026-07-26 實測）

系統：直轄市、縣（市）國土功能分區圖公開展示資訊查詢系統。ArcGIS JS API 4.25 + ASP.NET。
入口：`https://nluz.nlma.gov.tw/ex3smap/default.aspx?CN=<縣市>&version=<版本>`
（`CN`/`version` 需 urlencode；version 例：`報部版`）

## 取 token

token 直接寫在入口頁 HTML：`const layerToken = 'wFq-...';`
用 regex `layerToken\s*=\s*'([^']+)'` 取出。綁 ASP.NET session（cookie `ASP.NET_SessionId`），
且呼叫時需 `Referer` 指向入口頁。同一 session 內可重複使用。

## ex_data（主要資料端點，POST）

`POST https://nluz.nlma.gov.tw/ex3smap/ex_data?CMD=<命令>&TOKEN=<token>`
表頭：`Referer`（入口頁）、`X-Requested-With: XMLHttpRequest`、
`Content-Type: application/x-www-form-urlencoded; charset=UTF-8`、
**`User-Agent` 必須是瀏覽器字串（缺 → 404，這點最容易誤判為路徑錯）**。

| CMD | 參數 | 回傳 |
|---|---|---|
| `GETTOWNNAME` | — | `[{town:"七股區"}, ...]` 該縣市全鄉鎮 |
| `GETSECNAME` | `VAL1`=鄉鎮 | `[{sec:"DF4342", section:"社子段"}, ...]` 段名↔段代碼 |
| `SEARCHCADA` | `VAL1`=**段代碼**、`VAL2`=**8碼地號** | 見下 |
| `SEARCHBYXY` | `VAL1`=lon、`VAL2`=lat | 依座標查（未細測） |
| `SEARCHADDRESS` | `VAL1`=地址 | 依地址查（未細測） |
| `GETPOINTOFINTERSEST` | `VAL1`,`VAL2`,`VAL3` | POI（未細測） |

`SEARCHCADA` 成功回：
```json
{"STATUS":1,"features":[{"attributes":{
  "鄉鎮市區":"官田區","地段":"社子段","地號":"389",
  "國土功能分區":"農業發展地區第二類","使用地":" ",
  "原使用分區":"一般農業區","原使用地":"農牧用地"},
  "geometry":{"x":13397679.95,"y":2653173.24}}]}   // 質心, EPSG:3857
```
`STATUS`：`1`=有資料、`0`=查無（`MESSAGE:"沒有符合條件的地籍資料。"`）、
`9`=限流（`MESSAGE:"請勿連續進行查詢動作!請5秒後再進行查詢。"`，**唯一該重試的狀態**）。

`VAL1` 給段**名**會回 STATUS=0。必須給段代碼。

## ArcGIS 服務（能拿到的有限）

`https://nluz.nlma.gov.tw/nluzmap/rest/services/`

| 服務 | 狀態 |
|---|---|
| `BASELAYER/MapServer` | **公開免 token**。layer 0=縣市、1=鄉鎮、2=村里；可 query |
| `Exhibition/Exhibition_NLURange/MapServer/<0~21>` | token+Referer 可 query。各縣市**分區圖範圍外框**，1 筆/縣市，原生 wkid 102443 = **EPSG:3826** |
| `Exhibition/Exhibition_NLU_/MapServer` | **子圖層全部拿不到**（見下） |

`Exhibition_NLU_`（真正的分區面）：
- 直連 REST + token + Referer → `User does not have permissions to access 'exhibition/exhibition_nlu_.mapserver'`
- 經 `https://nluz.nlma.gov.tw/ex3smap/mapproxy?<完整URL>&token=<token>`（需瀏覽器 session）
  → **只放行** `MapServer?f=json` 與 `MapServer/legend?f=json`；
  `/<id>/query`、`/identify`、`/export` 一律 `400 錯誤的要求`
- 圖層清單含**全 22 縣市**：0 雲林、1 南投、2 新竹縣、3 臺中、4 新北、5 金門、6 新竹市、
  7 嘉義縣、**8 臺南**、9 苗栗、10 高雄、11 屏東、12 連江、13 基隆、14 嘉義市、15 宜蘭、
  16 澎湖、17 花蓮、18 臺東、19 彰化、20 桃園、21 臺北。`maxRecordCount` 2000、SR 3857。

`legend` 回 20 類分區碼＋色票（A10~A50/A4T、C10~C40、M11~M13/M20/M30、U10/U21~U23/U30）。

## 其他

- SSL 憑證有問題（同 up.tainan.gov.tw）→ `verify=False`。
- `up.aino.com.tw/upmap/rest/services` 在 m_main.js 有註冊 token，但實測 404，是死參考。
- 前端 JS：`ex3smap/js/config.js`、`ex3smap/js/m_main.js`（minified，token/命令都在裡面）。
- config.js 明載限制：「屬實施都市計畫或國家公園計畫之土地，無須製作使用地土地清冊電子檔，
  因此本系統無法提供查詢結果」。
