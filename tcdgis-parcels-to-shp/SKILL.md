---
name: tcdgis-parcels-to-shp
description: 在內政部國土規劃地理資訊系統(TCDGIS/NGIS,nsp.nlma.gov.tw)用「多重地籍選取」把土地清冊批次定位並下載 shapefile 時使用。凡是使用者提到「上國土規劃平台定位」「多重地籍選取」「全範圍定位」「批次地籍定位」「加入主題下載shp」「TCDGIS」「ngis.nlma.gov.tw」,或給一份地號清冊要在政府圖台選取/下載官方地籍範圍時,務必使用此 skill——即使只說「幫我把這批地號上平台跑一次」也適用。不適用於 NLSC 圖磚(用 landuse-wmts-to-shp)或本機地籍 shp 比對。
---

# TCDGIS 多重地籍選取 → 全範圍定位 → 下載 shp

## Overview

把「縣市/鄉鎮/地段/地號」清冊在國土規劃地理資訊圖台批次選取、定位、寫入繪圖主題、下載成 shapefile 的完整瀏覽器自動化流程。2026-07-13 以官田 145 筆(跨 2 地段)實測走通。

**核心事實:圖台是 dojo dijit 應用,不是普通表單。** 用 `dijit.byId(...).set('value',...)` 操作,不要猜 ASP.NET id、不要用 jQuery val() 設下拉。

## 前置(不可省略)

1. **登入由使用者本人完成**:開 https://ngis.nlma.gov.tw/TCDLogin.aspx,請使用者輸入帳密+圖形驗證碼(agent 依安全規則不可代填、不可解驗證碼),等回覆「好了」再繼續。
2. **入口必須走 SSO**:登入後導向 `https://ngis.nlma.gov.tw/TCDEntrySys.aspx?Sys=4` 進圖台。
   - ⚠️ **直接開 nsp.nlma.gov.tw/TCDGIS 或 /ngis/ 會拿到訪客版**——選單裡沒有「規劃模組」,看起來像功能不存在,其實是沒帶到登入態。Sys=1 是分區查詢、Sys=6 是圖資上傳,都不是圖台。
3. 視窗寬度 <768 會變行動版選單,先 resize 到 ≥1280。
4. 首次開地籍功能會彈「※ 地籍圖使用注意事項 ※」modal,**擋所有點擊**,先按「我完全同意及瞭解了」(用 JS 找按鈕文字點,座標常會點偏)。

## ⚡ 標準做法:注入現成 driver(不要每次重寫 JS)

批次選取與收尾下載已固化成兩支腳本(2026-07-15/16 實測邏輯),**任何模型一律注入使用**:

1. `javascript_exec`:`window.__QG = [ {c,t,s,ss,nos:[...]}, ... ]`(分組資料)
2. `javascript_exec`:貼上 [scripts/batch_driver.js](scripts/batch_driver.js) 全文(自動啟動)
   → 輪詢 `window.__BATCH`(i/total/added/errors/noFound/rateHits/done)
3. 完成後:`window.__FIN={theme:'主題名'}` → 貼上
   [scripts/finalize_download.js](scripts/finalize_download.js) 全文
   → 輪詢 `window.__FINST`(step/done/log)→ 去 Downloads 撿 zip+xls
4. **🚧 下載後必跑閘門**:`cadastral-map-pipeline/scripts/pipeline_check.py geometry <shp> --expect <清單筆數>`

driver 內建的節流(10.5s)/限流重試一次/「查無地號」不重試/confirm 只按一次+多餘取消/
alertify display 判斷,全是實測傷痕——**嚴禁改動這些參數與規則**。driver 故障或平台改版
(元件找不到、行為不符)→ 停下回報,首跑修復交高階模型。

以下手動流程說明保留作為 driver 的原理文件與除錯參考:

## 操作流程(頁面 JS,已實測)

開功能:規劃模組 → 多重地籍選取(選單 hover 展開不可靠,直接 JS click):
```js
Array.from(document.querySelectorAll('a')).find(e=>e.textContent.trim()==='多重地籍選取').click()
```

### 1. 逐段加入地號(每個地段一批,多筆逗號隔開,上限 1000 筆/清單)

⚠️ 同頁還有一組 `selLISP2County/Town/LandSec` + `txtLISP2LandNum`——**那是別的功能,設了沒用**。多重地籍選取用的是 dijit 元件,後綴 `_SKINDA3`(2026-07 實測值;此類後綴可能隨版本/帳號變動,若 `dijit.byId('COUNTY_SKINDA3')` 回 undefined,先用
`dijit.registry.filter(w=>/^COUNTY_/.test(w.id)).map(w=>w.id)` 重新找出實際後綴,以下所有 `_SKINDA3` 一律替換):

三層下拉的代碼都**不用背**,一律用中文名從選項查(縣市/鄉鎮/地段同一招)。
⚠️ **2026-07-16 實測:元件是 `dijit.form.Select`,選項在 `.options`([{value,label}]),
`store.data` 已不存在**(舊版是 FilteringSelect+store;先讀 `declaredClass` 判斷,兩招擇一):
```js
dijit.byId('COUNTY_SKINDA3').options.filter(o=>/臺南/.test(o.label))  // → {value:'D',...}
dijit.byId('COUNTY_SKINDA3').set('value','D');        // 設值觸發連動
// 等待用「輪詢 options 出現目標」(每500ms,上限10-12s),不要固定 sleep:
dijit.byId('TOWN_SKINDA3').options.filter(o=>/官田/.test(o.label))
dijit.byId('TOWN_SKINDA3').set('value','D,18');
dijit.byId('SECTOR_SKINDA3').options.filter(o=>/社子/.test(o.label))  // label 帶[代碼]前綴
dijit.byId('SECTOR_SKINDA3').set('value','DF4342');
$('#CADANO_SKINDA3').val('389,389-1,390');            // 地號格式 11 或 11-2,逗號隔開
document.getElementById('btnCADANO_SKINDA3').click(); // 加入(onclick=addCADAToTable)
```
- 換地段時只需改 SECTOR + 地號再按加入,清單會**累積**。
- 驗證筆數:`$('#tabCadalayer_SKINDA3').dataTable().fnGetNodes().length` 應等於清冊總筆數。
- 錯誤訊息走 alertify 彈窗(「請選擇地段」「格式不正確」「總筆數超過1000筆」「查無地號: X」),
  訊息在 `.alertify-message`、按 `.alertify-button-ok` 關閉。⚠️ **alertify 會排隊積壓**——
  舊訊息卡住會被誤讀成本批結果,每批加入後迴圈清空佇列再判讀。
- **「查無地號」是即時最終回覆,不重試**(使用者鐵律 2026-07-16)。加入驗證輪詢 ≤5s 即可
  (筆數增量≥本批 或 alertify 出現就 break)。查無的地號走 `parcel-roster-verify` 的
  新舊地號 API 換算修正,嚴禁在相近段名直接試同號(重測後同號≠同宗地)。
- **⚠️ 平台限流:連續加入/查詢動作間隔 ≥10 秒**,太快彈「請勿連續進行查詢動作!
  請10秒後再進行查詢」且該批 0 筆——此訊息=限流(等 10s 可重試一次),非查無。
  批次迴圈每批之間固定睡 10.5s,百批約 20 分鐘是平台下限。
- **前端清單跳轉即失**:批次跑完立刻全範圍定位＋加入主題/匯出Excel;其他查詢開新分頁,本分頁絕不 navigate。

### 2. 全範圍定位

```js
// onclick=zoomtoCADAAll('SKINDA3')
Array.from(document.querySelectorAll('button')).find(e=>/全範圍定位/.test(e.textContent)).click()
```
截圖確認地圖已縮放到全部宗地(藍框)。要看清地圖可暫時 `dlg.style.visibility='hidden'` 藏對話框,看完恢復。

### 3. 建主題並加入(下載的前置,順序不能反)

直接按「加入主題」會被 alertify 擋:「請先使用繪圖工具選出主題」。正確順序:
1. 按「開啟繪圖工具視窗」→ `dijit.byId('btnaddtheme').onClick()`(新增主題)→ alertify prompt 出現,填 `.alertify-text` 主題名(如 `20260713官田`)→ 按確定。確認 `dijit.byId('cmbtheme').get('displayedValue')` 已是新主題。
2. 回多重地籍視窗按「加入主題」(onclick=`btnInsertCADA('SKINDA3')`)→ 彈「確定將…地籍新增至主題 X?」→ 按確定。等 10 秒(伺服器把宗地寫入主題)。

### 4. 下載 shp(兩段式)

繪圖工具視窗內:
1. 點 `document.getElementById('下載')` (工具鈕,id 就叫「下載」)。
2. 點「ShapeFile檔案下載」dijit 按鈕(或直接呼叫全域 `downloadallshp()`)。
   內部流程:POST `GetShape.ashx` {TYPE:'ALL',UNAME:主題碼,NAME:escape(主題名)} 產 zip → GET `GetShape.ashx?type=DOWNLOAD&NAME=escape(名)` 觸發下載。**名稱編碼是舊式 `escape()`(%uXXXX),不是 encodeURIComponent**。

## 建主題/加入主題的實測坑(2026-07-15 清潔隊案)

- **alertify 可見性判斷**:alertify 是 `position:fixed`,`offsetParent` 永遠 null——
  用它判斷「可見」會讓清佇列迴圈空轉、一則都點不掉。**一律用
  `getComputedStyle(el).display!=='none'`** 判斷。
- **btnInsertCADA 只准呼叫一次**:它的 confirm 會進 alertify 佇列排隊;多呼叫幾次+
  把佇列裡的 confirm 都按「確定」=**重複插入主題,幾何加倍**(實測 313 筆變 626)。
  多餘的「確定將…新增至主題?」一律按**取消**。
- **下載後必驗筆數**:features 數 ≠ 選取清單數(尤其成倍)=重複插入。本機以
  (面積,質心) 去重即可,**不必回平台重做**:
  `g['__k']=g.geometry.apply(lambda x:(round(x.area,3),round(x.centroid.x,2),round(x.centroid.y,2))); g.drop_duplicates('__k')`
- **建主題 prompt 卡死的 fallback**:`addnewtheme()` 靠 alertify.prompt;佇列壞掉時
  prompt 永不出現。可直接打它內部的 AJAX 建主題(名稱不可與既有重複):
  `$.post("ws_data.ashx?CMD=INSERTNEWTHEME&TOKEN="+layerToken,{VAL:"主題名"},...).always(()=>GetThemebyUID("主題名"))`

## 判斷下載成功(最容易誤判的一步)

**network log 出現 `GetShape.ashx?type=DOWNLOAD... → 200 [FAILED: net::ERR_ABORTED]` = 下載成功**。那是 Chrome 把導航轉交下載管理器的正常訊號,不是失敗。**直接去 `%USERPROFILE%\Downloads` 找 `<主題名>_<日期>.zip`**,不要浪費時間在頁面內 fetch blob 搬運(base64 轉錄極易損毀)。

若 Downloads 真的沒有:重按一次下載鈕;POST 回 `ERROR` 表示主題是空的(加入主題那步沒成功)。

## 下載後處理

```python
# zip 內檔名是 Big5(zipfile 以 cp437 顯示成亂碼),解壓要轉檔名:
real = info.filename.encode('cp437').decode('big5')
```
- 內容物:`<主題名>_POLYGON.SHP/.SHX/.DBF/.CPG/.prj`,EPSG:3826。
- ⚠️ **屬性只有繪圖屬性**(NAME/RGB/TITLE/DESCRIBE=公私別),**沒有地號/使分/使類**。要完整屬性:在多重地籍視窗按「匯出Excel」(onclick=`BatchCADAToExcelMS('SKINDA3')`),或用來源清冊依幾何併回。
- 驗證:geopandas 讀取,筆數=清冊筆數、CRS=EPSG:3826、總面積量級合理。

## 下一步:把屬性接回圖面(接棒 shp-xls-area-join)

匯出的 Excel 帶 `向量面積` 欄與完整地籍屬性(地號/所有權人/使用分區/使用地類別/公告現值…),但 shp 只有繪圖屬性——兩者唯一的共同鍵是**面積**。接著用 **`shp-xls-area-join`** skill 依向量面積 nearest-join,生成帶完整屬性的新 shp:

```powershell
python <skills>/shp-xls-area-join/scripts/area_join_shp.py <主題名>_<日期>.zip --xls <匯出的Excel>.xls --out-dir output
```

- **把下載 zip 與匯出 Excel 存成同一個 basename**,`shp-xls-area-join` 才能在資料夾模式自動配對;否則就用上面單檔模式以 `--xls` 明確指定。
- 這條 `tcdgis-parcels-to-shp`(取範圍)→ `shp-xls-area-join`(帶屬性)是一條完整工作流:清冊 → 官方地籍 shp+屬性 Excel → 帶屬性 shp。

## ★ 同一次登入把「緊鄰宗地」一併查（2026-08-02 使用者定案）

**變更編定／容許使用等需判斷留設義務的案子，選取時就把緊鄰基地的宗地一併加入**，
匯出 Excel＋下載 shp，另存為 `<案>/鄰地/`。成本只多一批（10.5 秒節流）。

- **為什麼**：隔離綠帶「應留設側」取決於鄰地的**現行使用地類別**，而本機地籍是舊快照
  （Ver 111年2月）。布袋306 實例：南側 306-1 已於 112 年變更為特定目的事業用地
  （免留設），快照仍記農牧用地 → 用快照會多留 44 公尺綠帶。
- **鄰地地號怎麼來**：先用本機快照或圖台圖面「探勘」出可能相鄰的地號，再上平台查權威值。
  ⚠ 探勘完做**周界覆蓋檢查**——把查回的鄰地幾何併起來看有沒有包滿基地周界，
  缺口段就是快照裡沒有的新宗地（如分割後的 306-1），回平台補查。
- **下游**：`greenbelt_ratio --neighbours <鄰地_面積join.shp>`（見 `cadastral-map-pipeline` Ⓒ）。
- 大批次清冊（數十案場）不必每場都查，只對需要綠帶／周邊使用地分析的案場做。

## 環境敏感地區套疊分析(選用,接在下載 shp 之後)

依官方手冊 p39-41(大量圖資轉換工具/**docs/TCDGIS平台官方手冊HELP.pdf**,2026-07-30
自專案根目錄移入 docs/):分析「多重地籍選取定位後的
地籍範圍」與環境敏感地區各圖層是否套疊及套疊面積。**前置=本 skill 主流程已做完的事**
(多重地籍選取＋全範圍定位),所以下載 shp 後順手就能查。功能標示「僅供相關權限人員
使用」——本帳號有(選單看得到)。

流程(2026-07-15 官田 145 筆實測走通;此對話框後綴 `_SKINDA2`,規則同 `_SKINDA3`——
版本/帳號可能變,找不到就依 `chkAreaIntersect` 前綴重新列舉):

1. 先完成本 skill 主流程的多重地籍選取＋`zoomtoCADAAll`(分析吃「定位後的地籍範圍」),再開:
   ```js
   Array.from(document.querySelectorAll('a')).find(e=>e.textContent.trim()==='環境敏感地區套疊分析').click()
   ```
2. 對話框三個手風琴分頁,元件成對編號:**01=自訂範圍(預設展開)、02=地籍範圍、03=現有繪圖主題**。
   點文字「地籍範圍」的標題展開 02(直接勾 01 的 checkbox 是錯的——可見的那顆
   `chkAreaIntersect_SKINDA2` 屬自訂範圍)。
3. 勾 `chkAreaIntersect02_SKINDA2`(統計面積)→ 呼叫 `btnIntersect02('SKINDA2')`(開始查詢)。
   確認展開成功:該 checkbox `offsetParent!==null` 才動作。
4. 等 ~10 秒,等到含「圖層名稱」表頭的可見 table 出現。結果表頭:
   `圖層名稱|疊套面積(㎡)|說明|載入圖層`(注意是「疊套」不是「套疊」),共 53 項敏感圖層
   一次列出,有套疊者面積欄有值。
5. JS scrape 全表(逐 tr 取 td 文字)→ 存 `outputs/<案>/環境敏感套疊.csv`
   (欄:圖層名稱,套疊面積_m2,查詢日期,查詢方式;**無套疊者也要存**,證明「查過且無套疊」)。
6. 需要圖面時,結果列的「載入圖層」可把該敏感圖層載入地圖(後續出圖用)。

官田實測結果(驗證基準):53 項中 2 項套疊——公路兩側禁建限建地區(高速公路)153,008.94 m²
(基地緊鄰國道3號,合理交叉驗證)、淹水潛勢圖_24hr500mm 1,240.84 m²。

下游:`parcel-briefing-deck` 簡報第6頁(環境敏感地)以這份 csv 填表——有套疊列面積、
全無套疊則寫「經查詢均無套疊」,取代(待補)。

## Quick Reference

| 目標 | 元素/呼叫 |
|---|---|
| 圖台入口(登入版) | `ngis.nlma.gov.tw/TCDEntrySys.aspx?Sys=4` |
| 縣市/鄉鎮/地段 | `dijit.byId('COUNTY_SKINDA3'/'TOWN_SKINDA3'/'SECTOR_SKINDA3').set('value',…)` |
| 地號欄/加入 | `#CADANO_SKINDA3` / `#btnCADANO_SKINDA3` |
| 清單筆數 | `$('#tabCadalayer_SKINDA3').dataTable().fnGetNodes().length` |
| 全範圍定位 | 按鈕 onclick=`zoomtoCADAAll('SKINDA3')` |
| 新增主題/主題下拉 | `dijit.byId('btnaddtheme')` / `dijit.byId('cmbtheme')` |
| 加入主題 | onclick=`btnInsertCADA('SKINDA3')` → alertify 確定 |
| 下載 | `#下載` 工具鈕 → `downloadallshp()` |
| 匯出屬性 Excel | `BatchCADAToExcelMS('SKINDA3')` |

## Common Mistakes

| 錯誤 | 真相 |
|---|---|
| 直連 nsp 圖台找不到「規劃模組」 | 訪客版。走 `TCDEntrySys.aspx?Sys=4` |
| 設 `selLISP2*`/`txtLISP2LandNum` 沒反應 | 那是別的功能;用 `_SKINDA3` dijit 元件 |
| 猜要分批 30-50 筆 | 上限 1000 筆,一段 133 筆一次貼沒問題 |
| ERR_ABORTED 以為下載失敗 | 是成功交接訊號,去 Downloads 找 zip |
| 頁內 fetch+base64 搬檔案 | 轉錄必損毀;檔案本來就在 Downloads |
| 解壓後找不到中文檔名 | zip 檔名 Big5,cp437→big5 轉 |
| 以為 shp 帶地號屬性 | 只有繪圖屬性,屬性用「匯出Excel」 |
| 加入主題跳「請先使用繪圖工具選出主題」 | 先開繪圖工具新增/選定主題 |
| 點擊沒反應 | 「地籍圖使用注意事項」modal 還開著,先按同意 |
