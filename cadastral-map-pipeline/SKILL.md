---
name: cadastral-map-pipeline
description: 地籍案場「土地清冊 → 官方地籍圖資 → 帶屬性 shp → A4 主題成果圖」的端到端工作流總控。把 parcel-roster-verify（清冊地號健檢與新舊地號修正）、tcdgis-parcels-to-shp（上國土規劃平台批次定位下載）、shp-xls-area-join（依向量面積把屬性接回 shp）、parcel-map-sheet／make_maps --layout maxmap（最大化版面批次出圖）依序串起來。當使用者說「跑整條產線」「從地號清冊一路做到成果地圖」「幫我把這批地號上平台、帶屬性、出圖」「端到端地籍出圖」「清冊到出圖」時,務必用此 skill 統籌;它會在每個交接點呼叫對應的子 skill。不適用於只做其中單一步驟(那直接用對應子 skill)。
---

# 地籍出圖端到端工作流（清冊 → 成果圖）

把三支子 skill 依序串成一條產線。**本 skill 只做統籌與交接**,每一段的細節在各子 skill。
遇到該段就呼叫該子 skill,不要在這裡重造流程。

## ⚠️ 執行紀律(所有模型適用;Opus/Sonnet 接手時尤其不可違反)

1. **硬閘門必過**:每段交接跑 `scripts/pipeline_check.py` 對應子命令(下方各段標註),
   **exit≠0 就照訊息處置;處置不了→停下回報使用者,禁止繞過或憑感覺續跑**。
2. **瀏覽器操作用現成 driver,不要重寫**:批次選取=tcdgis `scripts/batch_driver.js`、
   收尾下載=`scripts/finalize_download.js`(注入→輪詢狀態即可)。driver 內的節流/重試/
   取消規則是實測傷痕,**嚴禁「優化」**(例:縮短 10.5s 節流、對「查無地號」重試、
   多按一次「確定」)。
3. **遇到 skill 未記載的平台行為**(新彈窗、新元件、新錯誤訊息)→ 截圖+記錄現象,
   **停下回報,不要即興修復**。新版式清冊/平台改版的首跑交給高階模型。
4. **數字只能來自實算**:任何要交付的數量/面積,必須能指出來源腳本輸出;對不上=停。
5. 唯二允許自行重試:WMTS 逾時(make_maps 內建)、平台限流訊息(driver 內建一次)。

```
土地清冊（縣市/鄉鎮/地段/地號）
  │  ⓪ parcel-roster-verify         地號健檢（★需你本人登入,與①同一次登入）
  ▼     修正後清冊 ＋ 平台已含全部地號的選取清單
  │  ① tcdgis-parcels-to-shp        瀏覽器自動化（沿用⓪的登入與清單）
  ▼     官方地籍 shp(zip) ＋ 屬性 Excel（含 向量面積）
  │  ⓪c nluz-landzone-query         國土功能分區逐筆查（選用,可與②③並行）
  ▼     國土功能分區.csv（分區/原使用分區/原使用地/使用地）→ 餵④第5頁
  │  ② shp-xls-area-join            本機腳本（--trust-fields）
  ▼     帶屬性基地 shp（地號/使分/使類/所有權人…）
  │  ③ make_maps --layout maxmap    QGIS（沿用 parcel-map-sheet 版面）
  ▼     圖檔_maxmap/ 六主題 A4 成果圖 ＋ 05_出圖清單_maxmap
  │  ③b 存 QGZ（★簡報前必做）      <案名>_maxmap.qgz：全部圖層＋每主題 Layout
  ▼     使用者可在 QGIS 開啟修編任一張圖再匯出
  │  ④ parcel-briefing-deck         簡報產製（v1 定案 9 頁）
  ▼     光電開發評估簡報 .pptx
```

## 需要人工/環境的兩個點（先講清楚,不要假裝全自動）

- **①的登入**:`ngis.nlma.gov.tw` 帳密＋圖形驗證碼**由使用者本人輸入**(安全規則:agent
  不可代填、不可解驗證碼)。開好登入頁請使用者完成,回覆「好了」再續。
- **③的環境**:出圖須用 **QGIS 內建 python**(`python-qgis-ltr.bat`);正射套疊/國土利用
  需連 NLSC WMTS(未快取時)、臨路判定需 fishpv 臨路評估產物。缺資料的主題單張標失敗續跑。

其餘全自動。

## 逐段交接

### ⓪ 清冊地號健檢 → 用 `parcel-roster-verify`(新清冊一律先跑)
清冊逐段批次加入 TCDGIS 多重地籍選取=平台即時驗證每筆地號;「查無地號」不重試,
走 MOI 新舊地號 API(免認證)換算現行段/地號後補加入並回填清冊(原檔備份+備註依據)。
**交接約定**:⓪跑完平台清單已含全部(修正後)地號且已全範圍定位——**同一 session 直接
接①的加入主題→下載 shp 與匯出 Excel,不要登出重來**(前端清單跳轉即失)。
陷阱備忘:重測後相近段名同號≠同宗地,禁止在相近段名直接試同號(詳該 skill)。

### ① 取官方地籍 → 用 `tcdgis-parcels-to-shp`(⚠️ 一律走這步,無例外)
**使用者鐵律(2026-07-15):任何案子(含清冊模式/多案場批次)基地幾何一律上平台登入
下載「最新」官方 shp。** 不可改走 `大量圖資轉換工具` 舊手冊的本機地籍比對
(match_parcels)取幾何——本機 `地籍圖資/` 是舊快照,僅供③擷取周邊地籍/功能分區。
多案場清冊:選取分組=(縣市/鄉鎮/段/小段),下載後建**段+地號複合鍵** sitemap
(跨縣市清冊同地號會跨案場,純地號鍵會分錯家;`load_sitemap` 支援 段/小段 欄)。
**⚠️ sitemap 必含「段」欄(2026-07-16 東石實錯)**:同一鄉鎮跨段重複地號(魚塭區常見)
會讓 load_sitemap 移除衝突純地號鍵;csv 無段欄=複合鍵建不出→該地號分派失敗,
單筆案場會**整案無聲消失**(引擎只緩衝一句警告,05 清單看不到)。清冊無分基地欄時
一律走 ②b 的 `build_sites_sitemap.py`(產出即帶段欄);歷史案的無段欄 sitemap 可用
`rebuild_sitemap_spatial.py` 以既有 sites.shp 為權威補救。**sitemap 閘門必須驗「實際
餵給 make_maps 的那一份檔案」**——驗過≠餵入的那份(東石事故:後置步驟覆寫了驗過的檔)。
多重地籍選取(=`batch_driver.js`)→ 收尾(=`finalize_download.js`:定位→匯Excel→建主題
→加入一次→下載)。
**交接約定**:把下載的 zip 與匯出的 Excel **存成同一個 basename**(下一段靠同檔名自動配對)。
**🚧 閘門**:`pipeline_check.py geometry <解壓後shp> --expect <清單筆數>`(抓重複插入/筆數不符)。

### ①b 環境敏感地區套疊分析(選用,同一次登入順手做)
下載 shp 後、**趁地籍選取/定位還在**,開 規劃模組→環境敏感地區套疊分析→「地籍範圍」
→勾統計面積→開始查詢,scrape 結果表存 `環境敏感套疊.csv`(詳 `tcdgis-parcels-to-shp`
的環敏章節)。這份 csv 餵簡報第6頁(環境敏感地),沒查就只能(待補)。

### ⓪c 國土功能分區逐筆查 → 用 `nluz-landzone-query`（選用,但簡報第5頁強烈建議）
拿①匯出的屬性 Excel（欄位天生齊全）直接餵,查 nluz 報部版逐筆分區,產
`國土功能分區.csv`（國土功能分區/原使用分區/原使用地/使用地）。
**不佔登入、不動平台清單**——可與②③並行或事後補跑,不阻塞產線。
`python <skills>/nluz-landzone-query/scripts/nluz_query.py query --roster <①的Excel> --county <縣市> -o <案>\國土功能分區.csv`
⚠️ **平台限流 5 秒**(145 筆約 13 分鐘,腳本每 5 筆 checkpoint、中斷可續跑);
**都市計畫區/國家公園區回「查無」是正常**,非錯誤;版本是**報部版草案**,交付口徑需寫「以縣市政府認定為準」。
向量面拿不到(平台擋),面圖層仍走本機 `國土功能分區/` 圖資。

### ② 屬性接回 → 用 `shp-xls-area-join`
```powershell
python <skills>/shp-xls-area-join/scripts/area_join_shp.py <資料夾或 zip> --xls <Excel> --out-dir output --trust-fields
```
產出帶 地號/使分/使類/所有權人… 的基地 shp(BIG5, EPSG:3826),`--trust-fields` 同時帶
`20251201_*` 別名可直接餵 make_maps --trust-shp。這就是出圖的基地層來源。
**🚧 閘門**:`pipeline_check.py join <joined.shp>`;多案場再加
`pipeline_check.py sitemap <joined.shp> --sitemap <csv>`(段+地號 100% 命中才准進③);
全國性清冊強烈建議 `pipeline_check.py spatial <joined.shp>`(質心×本機地籍抓 join 錯接)。

### ②b 案場定義(多案場清冊必做;2026-07-16 縮編定案)
**案場定義權在產線,不在 fishpv。** fishpv 只當純臨路計算器(吃逐案 shp、吐臨路狀態),
不再自己聚類定義案場、不再產 sitemap——避免「聚類真相在外部工具、產線拿到失真副本」
(東石 S012 整案消失的結構性根因)。

- 清冊**有**分基地欄(如清潔隊):照舊從清冊建帶段欄 sitemap。
- 清冊**無**分基地欄(如東石,一份清冊=一堆相鄰宗地群):
  ```powershell
  python scripts\build_sites_sitemap.py --joined <②joined.shp> --out-dir <案>\案場定義
  ```
  相鄰宗地連通分量聚類(--gap 預設 0=須相鄰),產 `案場定義/sitemap.csv`(帶段欄)+
  `sites.shp`;編號北→南確定性(重跑不變),`--match-sites` 可沿用歷史編號。
- **先過 sitemap 閘門**(對 案場定義/sitemap.csv),再拆逐案 shp 餵 fishpv:
  ```powershell
  python scripts\split_shp_persite.py --joined <joined.shp> --sitemap <案>\案場定義\sitemap.csv --out-dir <案>\臨路評估_percase
  .\scripts\run_fishpv_percase.ps1 -Base <案>\臨路評估_percase   # 合併:merge_fishpv_percase.py
  ```
- run_case 的 digest 會**優先複製 案場定義/sitemap.csv** 給出圖;無案場定義且成果.xlsx
  反推出跨案場重複地號時會硬停並指路本步驟(不再無聲寫出無段欄 sitemap)。

### ③ 批次出圖 → 用 `parcel-map-sheet`（經 make_maps --layout maxmap）
**單一案場含臨路判定的標準走法**:`run_case.py --shp <②的joined.shp> --case <案名>`
(首跑:fishpv 臨路→總區位圖→停點)→ 再加 `--mode single --layout maxmap` 出六主題。
⚠️ **`--shp` 一律給絕對路徑**——fishpv 在漁電專案 cwd 下執行,相對路徑會 No such file
(2026-07-16 實踩)。fishpv 失敗會降級續跑(圖6標失敗、其餘照出),先排除再重跑 `--from fishpv`。

**臨路判定外擴——使用者口語→參數對照**(2026-07-16 定案):
- 使用者沒提 → 預設:single 外擴700m、persite 不外擴(都仍疊 EMAP2 見周邊路名)
- 「臨路要外擴」「外擴N公尺」 → `--road-margin=700`(或N)
- 「臨路不用外擴」 → `--road-margin=0`
(make_maps 與 run_case 皆吃此旗標;run_case 透傳。)
在 `大量圖資轉換工具/` 下,把基地(＋周邊/功能分區)備進案場結構後:
```powershell
& "C:\Program Files\QGIS 3.40.12\bin\python-qgis-ltr.bat" scripts\make_maps.py <案名> --layout maxmap
```
- 版面固定為**最大化地圖＋自動避讓角落疊圖＋右欄只留圖例**;周邊不上 label;涵蓋地號收合為
  「段 第一筆 等 N 筆」;主題免責說明寫入 `05_出圖清單_maxmap` 備註欄。
- 非破壞:另存 `圖檔_maxmap/`、`05_出圖清單_maxmap.*`、`<案名>_maxmap.qgz`;`--layout compact`
  可回退舊右欄版面。
- 常用旗標:`--themes=使用分區,使用地編定,國土功能分區`(只出本機可出、免連網的主題)、
  `--cases=<id>`、`--skip-extract`(重用既有 圖層.gpkg)。
- **清冊有分基地別時(重要,使用者定案)**:像清潔隊那種「一份清冊、多個案場/基地」的清冊,
  **必須對應回原清冊的基地分組、依各宗基地各出一組圖**,不可全部併成一案出一張。作法:
  從原清冊建 `sitemap.csv`(欄位:`地號,案場ID,案場名稱`),出圖時加
  `--sitemap <csv>`(persite 模式,`load_sitemap` 以正規化地號比對)。每宗基地會各自
  重算比例尺/範圍/角落避讓,`05_出圖清單` 逐基地列出;sitemap 查無的地號會歸
  「未對應」案場並警告,不會靜默混入其他基地——出圖前先檢查警告清單。
  **同段同地號列在多個案場=各案場都出**(2026-07-16 支援,使用者定案):sitemap 值為
  多對 (案場ID,名稱),基地列/幾何在每個案場都收一份,兩邊各自出圖。
- **成品圖依案場分資料夾**(使用者定案 2026-07-16):多案場清冊出圖後把 `圖檔_maxmap/`
  重整為 `<案場ID>_<案場名稱>/<主題>.png` 並同步改寫 05 清單檔名欄——跑
  `python scripts\reorg_sheets_persite.py <案outputs目錄>`(make_maps 本身仍寫攤平檔,
  出圖完跑重整;2026-07-16 起吃參數、案場ID 支援英數如 S012,不必再改腳本)。
- **多案場批次的臨路判定/正射時間帳**:臨路判定每案要外擴 700m 抓 PHOTO2+EMAP2,
  面積是案場框的十餘倍,105 案場約 7hr;純正射(PHOTO2+EMAP)約 1-1.5hr。趕時間先出
  正射、臨路後補(fishpv 成果與合併檔備妥即可隨時單獨補跑)。fishpv 多案場一律
  **逐案場拆 shp 再跑**(一次餵全清冊會把全國外框當畫布,記憶體爆炸)——拆檔/驅動/
  合併走 ②b 的三支腳本;make_maps 圖6 已支援依案場範圍過濾宗基地。

六主題:使用分區、使用地編定、國土功能分區、正射套疊、國土利用調查、臨路判定。前三張只需
②的基地＋周邊即可;後三張各需 NLSC WMTS／LUIMAP／fishpv 臨路資料。
**🚧 閘門**:`pipeline_check.py sheets <案outputs目錄> --cases <案場數> [--themes ...]`
(05 清單成功數與圖檔存在性;失敗列照備註 `--cases=` 補跑)。

### ③b 存 QGZ 供修編(★產簡報前必做,使用者定案)
出圖時**不要帶 `--no-qgz`**(預設就會寫),完成後即產 `<案名>_maxmap.qgz`——內含全部
圖層(gpkg 複本/底圖 tif)與**每主題一個 Layout**,使用者可在 QGIS 開啟手動修編再匯出。
若先前為求快帶過 `--no-qgz`,產簡報前補跑一次
`make_maps <案名> --trust-shp ... --skip-extract --layout maxmap`(重用 gpkg 與底圖快取,
只重算圖與寫 qgz)。**確認 qgz 存在且可開(層/Layout 齊)才進 ④**。

### ④ 簡報產製 → 用 `parcel-briefing-deck`
出圖完成後,以 ①的屬性 Excel＋③的 圖層.gpkg/圖檔_maxmap(＋fishpv 臨路成果,若有)產
評估案簡報:先 `case_stats.py` 實算統計(數字只能來自這份 JSON,範本敘述句要覆核,
不可照抄),再依 **v1 定案格式(9 頁)** 組 pptx 並跑 validate＋逐頁目視 QA。

## 銜接備忘

- 三支子 skill 已互相加交叉指引;本 skill 是它們的上層總控。
- ②→③:基地 shp 需含 地號/使分/使類欄;出圖前若走參考案抽取,會再撈周邊地籍與功能分區。
- 版面決定(定案):最大化地圖、角落疊圖自動避讓基地(必要時退比例尺)、周邊無 label、
  地號收合、caveat→備註。要改版面去 `parcel-map-sheet`。
