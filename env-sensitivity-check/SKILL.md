---
name: env-sensitivity-check
description: 台灣開發基地環境敏感地區自動化初步評估。輸入地段地號，自動串接地籍圖資、環境敏感地區單一窗口查詢平台(eland)應免查範圍、TGOS/主管機關圖資套疊，產出法令分析報告與示意圖。當使用者提到「環境敏感」「應查免查」「還敏對照」「開發基地評估」「環評前置作業」時使用。
---

# 開發基地環境敏感地區初步評估 env-sensitivity-check

輸入地段地號，自動跑完「兩層過濾」，輸出報告 + 套疊示意圖。

```
python scripts/check.py 高雄市 路竹區 保安段 711-3
```

> ★★ 2026-08-05 大改（大量圖資轉換工具產線接入）：
> - **第一層初篩改用官方『應免查範圍』離線 PDF**（`exempt_source.py` 讀
>   `parse_exempt_pdf.py` 產的 JSON），**取代線上 eland**：離線、權威、有版本、
>   不受 eland SSL／快取污染坑影響。線上 eland（`eland.py`）保留為未給 JSON 時的回退。
>   下游 `api.run(..., exempt_json=..., sections=..., env_root=...)` 三個新參數。
> - **單一登記表**：本檔的遠端 `LAYERS` 與本機 `LOCAL_LAYERS` 已合流到 `tgos_layers.py`
>   同檔（見該檔頭）；`overlay.py` 加 `fmt=local_shp` 吃本機圖資（山坡地/礦區等只有本機者，
>   由呼叫端注入 env_root）。大量圖資轉換工具的 `env_registry.py` 已成薄殼 re-export。
> - 判定語意與踩坑寫成大量圖資轉換工具 `tests/test_exempt_prescreen.py`。詳見該產線 CLAUDE.md「環敏」節。

## 兩層過濾邏輯（這是本 skill 存在的理由）

1. **第一層 — eland 應免查範圍過濾**：自動模擬瀏覽器送出
   `eland.nlma.gov.tw` 的「應免查範圍查詢」表單（縣市/鄉鎮市區/村里/地段連動下拉），
   取得 46 項全國區域計畫法環境敏感地區項目（含子項共 ~85 列）在該行政區的「應查／免查／無法判定」狀態。
   **免查的項目直接排除，不用進第二層。**
2. **第二層 — 圖資套疊 / 屬性判斷**：對「應查」的項目，查 `tgos_layers.py` 對照表：
   - `kind="vector"`：有向量圖資，下載（快取）後與 [cadastre-check](../cadastre-check/SKILL.md) 取得的基地界址環
     做真正的空間相交（`shapely.intersects`）判斷，給出「有交集」或「無交集（初步排除）」。
   - `kind="zone_attribute"`：像森林區／優良農地（特定農業區）／優良農地以外之農業用地（一般農業區）這幾項，
     其實不需要套疊任何圖資——這些名稱本身就是非都市土地的「使用分區」，cadastre-check 查地籍時已經把
     登記的使用分區帶回來了，直接字串比對即可。都市土地沒有使用分區欄位，會誠實回報「無法用此規則判斷」而
     不是誤判為排除。
   - 查無對應設定：標記「需逕洽主管機關」並附上 eland 提供的查復機關名稱。

## 為什麼要自己模擬表單，不能用官方 API？

eland 沒有公開 API，「應免查範圍查詢」是一般 ASP.NET Core 表單（含 antiforgery token）。
本 skill 用 `requests.Session()` 走一模一樣的流程：GET 首頁拿 token+cookie
→ POST `TownshipListJson`/`VillageListJson`/`LandSecListJson` 取得連動選單代碼
→ POST `QuerySEDataAdmin` 送出查詢 → 解析回傳 HTML 表格。
這與人工在瀏覽器操作是同一支公開查詢服務，只是省去手動點選的步驟。

## TGOS 圖資對照表現況

`scripts/tgos_layers.py` 目前收錄 **55 筆**設定（52 個真向量圖資 + 3 個使用分區屬性判斷），**沒有任何項目
停留在 WMS-only**。剩下仍查無可自動化來源、需逕洽主管機關或走 eland 正式申請者，多為**軍事／海岸管制區
（陸軍，機密）、交通兩側禁限建（高速公路／鐵路／捷運）、礦區（場）與地下礦坑、洪氾區、氣象／民航／
核子禁限建**等——這些不是「還沒接」，而是根本無公開向量資料（詳「還差哪些項目」一節）—— 完整 46 項逐一比對結果見專案資料夾內
`TGOS環境敏感圖資對照表.xlsx`（2026-08 查證版本，該檔案的 kind 欄位僅到第一輪查證，實際涵蓋範圍以本檔
與 `tgos_layers.py` 為準，後續持續擴充中）。

| eland 項目 | 來源 |
|---|---|
| 河川區域／區域排水設施範圍／水庫集水區／水庫蓄水範圍／海堤區域／自來水水質水量保護區 | 水利署 GIC 直接下載 `gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=X&filetype=SHP` |
| 自然保留區／野生動物保護區／野生動物重要棲息環境／自然保護區 | 林業署 SHP |
| 活動斷層兩側一定範圍／地質敏感區(地質遺跡)／地質敏感區(地下水補注)／地質敏感地區(山崩與地滑)／土石流潛勢溪流地區 | 地質雲開放 API |
| 森林（區域計畫劃定之森林區）／優良農地／優良農地以外之農業用地 | **使用分區屬性直接判斷**（不套疊圖資，見下） |
| 國家公園區內之特別景觀區、生態保護區／國家公園內之史蹟保存區／國家公園內之一般管制區及遊憩區／古蹟保存區／考古遺址／重要聚落建築群／重要文化景觀／飲用水水源水質保護區／飲用水取水口一定距離內之地區／國有林事業區／保安林／林業試驗林地／溫泉露頭及其一定範圍／水產動植物繁殖保育區／人工魚礁區及保護礁區／國際級重要濕地／地方級／國家級重要濕地核心保育區以外分區 | **內政部國家公園署海岸圖台 `vulnerable` 服務**（見下），一次接了 17 項 |
| 紀念建築／史蹟 | **文化部文化資產局 OpenData v2**（`data.boch.gov.tw`，點位＋地號，補 coastal 缺的兩類，見下） |
| 一級／二級海岸防護區 | 內政部國家公園署海岸圖台 `coastalDefend` 服務 |
| 一級海岸保護區（含海岸管理法特定區位版本） | 內政部國家公園署海岸圖台 `SeaSideProtection` 服務 layer 1（沿海自然保護區） |
| 二級海岸保護區（含海岸管理法特定區位版本） | 內政部國家公園署海岸圖台 `SeaSideProtection` 服務 layer 0（沿海一般保護區） |
| 淹水潛勢 | 內政部國家公園署海岸圖台 `others` 服務 layer 29（24小時降雨500mm標準情境） |

### 使用分區屬性判斷（不需套疊圖資）

使用者提醒：「森林區」「優良農地」「優良農地以外之農業用地」本身就是**非都市土地使用分區**的正式名稱
（森林區／特定農業區／一般農業區），不是要另外去找一張地圖來套疊——cadastre-check 查地籍時，內政部
NLSC API 已經把登記的使用分區帶回來了（`registry.zone`），直接字串比對即可：

```python
{"item_no": "23", "sub": "森林區", "kind": "zone_attribute", "zone_match": ["森林區"]}
```

都市土地沒有使用分區欄位（`registry.zone` 為 `None`），這種情況老實回報「都市土地無使用分區欄位、
無法用此規則判斷」，不會誤判為「不屬於」——都市土地要判斷優良農地類項目，得去看都市計畫圖或逕洽地政機關。

### 內政部國家公園署「國家公園濕地海岸整合資訊圖台」—— 一次補齊 17 項的大水庫

`https://coastal.nps.gov.tw/CoastalGIS/default` 背後是標準 **ArcGIS REST Server**
（`coastal.nps.gov.tw/coastal/rest/services/Ocean/...`），`vulnerable`（環境敏感）這個 MapServer
裡一次塞了 30 個圖層，把國家公園分區、文化資產、濕地、林業、飲用水等一大票原本查無圖資的項目都補齊了；
`coastalDefend` 這個 MapServer 則專門對應海岸管理法的一級/二級海岸防護區。這兩個服務**完全公開、
不需金鑰**，直接查詢即可：

```
GET https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer?f=json        # 列出所有圖層 id/名稱
GET https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer/3/query?where=1=1&outFields=*&f=geojson   # 取得該圖層全部圖徵
```

回傳標準 GeoJSON（WGS84 經緯度），`overlay.py` 的 `_load_arcgis_query`（`fmt="arcgis_query"`）直接呼叫
`.../<layer_id>/query` 取得，快取邏輯與其他 geojson 來源一致。

**`SeaSideProtection`／`others` 服務也已接上**（原本因為命名對不上、資料量大而遲疑，後經使用者確認對應
關係才補上）：
- `SeaSideProtection` layer 0「沿海一般保護區」= eland 的**二級**海岸保護區；layer 1「沿海自然保護區」=
  **一級**海岸保護區。這兩個項目在 eland 有兩處會問到（全國區域計畫法第一級/第二級，以及海岸管理法特定
  區位），已各接一次。
- `others` 服務裡淹水潛勢圖其實有 10 個降雨情境圖層（id 21-30，6小時/12小時/24小時三種降雨延時各配
  幾個雨量門檻）。**原本想全部 10 個一起查（`fmt="arcgis_query_multi"`），結果其中至少一個情境圖層資料量
  大到讓查詢卡了 5 分鐘以上跑不完，中途強制終止**。改成只查使用者確認的標準情境「24小時降雨500mm」
  （layer 29）單一圖層，改用 `fmt="arcgis_query"`，幾秒內就能查完。`overlay.py` 仍保留
  `_load_arcgis_query_multi`／`fmt="arcgis_query_multi"` 這個通用邏輯（目前沒有任何圖層在用），
  之後若要一次查多個圖層、且該服務資料量不大，才適合用它——**大圖層先用單一 `arcgis_query` 個別測過
  回應時間再決定要不要合併查詢**，別預設它跟其他小圖層一樣快。
- 同一台 ArcGIS Server 底下的 `coastalAreaSpecLocCase`（風場/太陽光電案件範圍）跟環境敏感無關，不用接。

### 水利署 GIC 平台（gic.wra.gov.tw）—— 也是不用金鑰的直接下載

`https://gic.wra.gov.tw/Gis/Page/GeoDataAndServices` 網頁上「SHP下載」按鈕背後其實是一支很單純的
固定網址規則，**英文名稱欄位直接就是查詢參數**：

```
GET https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=reservoir&filetype=SHP      # 水庫集水區
GET https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=ressub&filetype=SHP          # 水庫蓄水範圍
GET https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=SEAWALLZONE&filetype=SHP     # 一般性海堤區域
GET https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=TWQPROT&filetype=SHP         # 自來水水質水量保護區圖
GET https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=REGDAREA&filetype=SHP        # 中央管區域排水設施範圍
```

網頁上列出的每個資料集英文名稱（如 `RIVREGLN`／`GWREGION`／`gwconare` 等）理論上都能套這個規則直接下載，
之前 `河川區域` 用的 `RIVERL&filetype=KML` 也是同一支端點。這比先前接的 `maps.wra.gov.tw/arcgis/.../WMSServer`
（只給 WMS 影像、沒有明確 LAYERS 代碼）好用太多——**這支端點直接給向量 SHP，不用猜圖層代碼**。
之前判定為 `kind="wms"` 或 `kind="none"` 的水利署項目已全部改用這支下載。

#### ★ 完整代碼目錄怎麼拿（2026-08-04，使用者指路）

`https://gic.wra.gov.tw/Gis/Page/GeoDataAndServices` 是 SPA、抓不到清單；真正的**資料索引**在
**`https://gic.wra.gov.tw/Gis/Gic/DataIndex/Data/Main.aspx`**（SHP 206 筆／KML 125 筆，可搜尋）。
每筆下載鈕的 onclick 是 **`openDownloadPage('shp','2','<英文代碼>')`**，第三個參數就是
`DownLoad.aspx?fname=` 要用的代碼。頁面是 ASP.NET `__doPostBack` 分頁（21 頁），逐頁 POST
（保留 `__VIEWSTATE` 等 hidden 欄位、`__EVENTTARGET` 設 `...gvData_A$ctl13$ctlNN`）即可掃完，
一次得 140 個 SHP 圖層的「代碼→中文名」。與環敏相關的：

| eland 項目 | fname 代碼 |
|---|---|
| 中央管河川區域／區域排水設施範圍 | `RIVREGLN`／`REGDAREA` |
| 水庫集水區／水庫蓄水範圍 | `reservoir`／`ressub`（另有 `_insidearea`/`_outsidearea` 敏感區±0.5km） |
| 一般性海堤區域 | `SEAWALLZONE` |
| 自來水水質水量保護區 | `TWQPROT`（另有 ±0.5km 敏感區版本） |
| **地下水第一/二級管制區** | `gwconare`／`gwconare2`（★嚴重地層下陷以第一級 gwconare 替代判斷）|
| **淹水潛勢** | `flood_<雨量>mm_<時距>hr`：24hr500mm＝`flood_500mm_24hr`（標準情境）；另 6/12/24hr 各門檻共 10 個 |

⚠ **「地層下陷」在 GIC 只有各縣市「平均下陷速率／累積下陷量等值線」**（分縣市、分年度、
等值線非面範圍），**不是法定「嚴重地層下陷地區」界線** → 維持以地下水第一級管制區
（`gwconare`）作替代判斷，報告載明代理關係。

### 地質雲開放 API（www.geologycloud.tw）—— 比 TGOS 本身更好用的資料源

經濟部地質調查及礦業管理中心的「地質雲加值應用平臺」背後有一支**完全公開、不需金鑰**的 GeoJSON REST API，
直接回傳向量幾何（WGS84經緯度），比 TGOS 詮釋資料頁給的 WMS 影像好用很多：

```
GET https://www.geologycloud.tw/data/zh-tw/GeologicalSensitiveAreas?category=活動斷層&name=旗山斷層
GET https://www.geologycloud.tw/data/zh-tw/GeologicalSensitiveAreas?category=地質遺跡&name=大華壺穴
GET https://www.geologycloud.tw/data/zh-tw/GeologicalSensitiveAreas?category=地下水補注&name=臺北盆地
GET https://www.geologycloud.tw/data/zh-tw/GeologicalSensitiveAreas?category=山崩與地滑&name=南投縣&town=仁愛鄉&all=true
GET https://www.geologycloud.tw/data/zh-tw/ext_swcb_DebrisArea            # 全國土石流潛勢區，單次取得不用逐名查
```

- 斷層／地質遺跡／地下水補注沒有 `all=true` 批次查全部的參數（試過，回空），**只能逐名稱查**——所以
  `tgos_layers.py` 裡這幾項用 `fmt: "geojson_multi"` + `names` 清單（27 條斷層／19 處遺跡／6 大地下水分區），
  `overlay.py` 的 `_load_geojson_multi` 會逐一查詢、失敗的名稱寫進 `<cache>.failed.txt` 但不中斷整體流程。
- **`山崩與地滑`分類是用 `category=山崩與地滑&name=<縣市>&town=<鄉鎮>&all=true` 查（`name` 這裡放的是縣市而不是
  斷層名，命名跟其他分類不一致，是抓包瀏覽器選好縣市鄉鎮按「加入」後的實際 request 才找到的）。這個分類資料密度
  極高——單一鄉鎮就可能上萬筆圖徵、回應 60MB+ ——所以 `fmt: "geojson_town"` 不會像其他分類整批預先合併快取，
  而是 `overlay._load_geojson_town` 在查詢時才依基地當下的縣市/鄉鎮動態抓、以 `(category,county,town)` 為快取鍵。
  首次查某鄉鎮約 30 秒，同鄉鎮的後續查詢走快取約 3 秒。
- CORS 對這支 API 不是問題：`overlay.py` 用 Python `requests` 在伺服器端呼叫，CORS 只限制瀏覽器 JS，
  不影響後端腳本。

**要擴充圖資，就是在 `tgos_layers.py` 的 `LAYERS` list 多加一筆 dict**（`level`/`item_no`/`sub`/`name`/`agency`/`kind`/`fmt`/`url`或`url_template`+`names`），
`kind="vector"` 才會真正跑相交判斷，`kind="wms"` 只會在報告中提示人工比對。
TGOS 本身的下載網址／WMS 服務網址，可到該資料集詮釋資料頁按「下載」或「服務」按鈕取得
（`https://www.tgos.tw/tgos/NgdaMap` 搜尋 → 點資料集 → 頁面下方「圖資及服務資訊」表格）；
地質、水文類則優先檢查該主管機關自己的加值應用平台（如地質雲）是否有更好的開放 API，往往比 TGOS 詮釋資料頁列的 WMS 更完整。

### 文化部文化資產局 OpenData v2（data.boch.gov.tw）—— 補齊 coastal 缺的兩類文資

coastal 的 `vulnerable` 服務已涵蓋 **古蹟／歷史建築／聚落建築群／文化景觀／考古遺址**，
但**獨缺「紀念建築」與「史蹟」**。文資局有一組**免認證**的 OpenData v2，七類建造物資產全在：

```
GET https://data.boch.gov.tw/opendata/v2/assetsCase/1.4.json   # 紀念建築（全國 21 筆）
GET https://data.boch.gov.tw/opendata/v2/assetsCase/3.2.json   # 史蹟（全國 7 筆）
# 完整類碼：1.1古蹟 1.2歷史建築 1.3聚落建築群 1.4紀念建築 2.1考古遺址 3.1文化景觀 3.2史蹟
# OpenAPI 規格：GET https://data.boch.gov.tw/v3/api-docs/OpendataApi_v2
```

- **回傳是每筆一個 `longitude`/`latitude`（WGS84 代表點）＋ `landlotList`（坐落地號）**，
  不是面幾何。`tgos_layers.py` 用 `fmt="boch_asset"`＋`boch_code`＋`point_buffer_m`（預設 100m），
  `overlay._load_boch_asset` 把代表點緩衝成面再相交。
- ⚠ **命中僅代表「基地附近有此類文資」，實際坵塊須以回傳的「地號」欄（landlotList）人工核對**，
  非權威判定（正式仍以文資局查復為準）。因全國筆數極少、誤報成本近零，故採「寧可標出給人看」的初篩定位。
- ⚠ **無有效座標的筆數會被印出來、不納入空間篩檢**（實測 紀念建築 3 筆、史蹟 1 筆，多為金門資產），
  避免靜默漏成「無涉及」——那幾筆只能靠地號人工核對。
- ⚠ `/opendata/v2/assetsCase/geo/<類碼>.json`（理論上回**面幾何**）2026-08-04 實測伺服器
  回 **HTTP 500『系統異常』**，故先走非-geo 的點位版；該端點恢復後可改抓 geo 版取真實面界。
- 憑證同樣缺 SKI（見「踩過的坑」），已把 `data.boch.gov.tw` 加進 `govtls.GOV_HOSTS`。

**礦區（場）／地下礦坑仍無解**：礦業雲圖台（mine.geologycloud.tw）的後端
`geologyapi.gsmma.gov.tw/getlandsectionjson` 有礦業用地幾何，但**憑證根不受信任
（`SEC_E_UNTRUSTED_ROOT`，GCA 憑證鏈缺中繼，非 SKI 型）**；data.gov.tw 只有 CSV 無座標
（dataset 163035）。→ 需要時得掛政府 GCA CA bundle 才連得上，維持逕洽經濟部。

### ★ 來源取捨的優先順序（使用者 2026-08-04 定案）

**API 不好接、但有 SHP 可下載時，直接下載 SHP 當基礎圖資來判斷**，不要卡在 API 上、
也不要因此把該項退成「逕洽機關」。優先順序：

1. **直接下載 SHP／GeoJSON**（最好，可離線相交）：TGOS 詮釋資料頁「下載」鈕、
   主管機關開放資料頁、GIC `DownLoad.aspx?fname=X&filetype=SHP`、地質雲 GeoJSON。
   → 加 `kind="vector"`、`fmt="shp"`（給 `url`）或 `fmt="geojson"`。
2. **公開 ArcGIS REST**（`.../MapServer/<id>/query`）：大圖層記得設 `"bbox_query": True`。
3. 只有 WMS 影像、或自製圖台 API 猜不到（如 gis.ardswc.gov.tw 的 geoinfo_api，
   端點型式全 404）→ **先找該資料有沒有 SHP 版可下載**；真的都沒有，才標 `kind="wms"`／
   逕洽機關，並在報告寫明「無公開向量圖資、須逕洽」。
   ⚠ 不要在猜不到的自製 API 上反覆試探（產線紀律：遇未記載平台行為停下回報）。

## 輸出

```
env_check_out/
  env_result_<時間戳>.json   完整結構化結果（可程式化讀取）
  env_report_<時間戳>.md     法令分析報告（總覽 + 需洽機關清單 + 有交集警示）
  env_map_<時間戳>.png       套疊示意圖（黑線=基地，紅線=有交集圖層，灰線=無交集圖層）
```

## 串接其他專案

```python
import sys
sys.path.insert(0, r"C:\Users\USER\.claude\skills\env-sensitivity-check\scripts")
from api import run

result = run("高雄市", "路竹區", "保安段", ["711-3"])
result["summary"]      # {"免查": 66, "應查_自動排除": 1, "應查_有交集": 0, ...}
result["findings"]     # list[dict]，每項含 eland_status / overlay / action
```

`run()` 內部會自動載入 [cadastre-check](../cadastre-check/scripts/api.py) 的 `query()`（以獨立模組名稱
`cadastre_check_api` 載入，避免與本檔同名 `api.py`互相覆蓋——這是實作上唯一需要注意的坑）。

## 踩過的坑（2026-08-04，接進大量圖資轉換工具產線時實修）

- **政府網站憑證缺 Subject Key Identifier，Python 3.12+ 直接擋**：`ssl.create_default_context()`
  自 3.12 起預設帶 `VERIFY_X509_STRICT`，eland／coastal.nps.gov.tw／gic.wra.gov.tw 三站的憑證
  都缺這個 RFC 5280 擴充欄位 → `SSLCertVerificationError: Missing Subject Key Identifier`，
  在本機 Python 3.14 整支跑不起來（skill 原在 3.11 開發，那時沒這旗標）。
  修法集中在 **`govtls.py`**：只清 strict 旗標、**保留憑證鏈與主機名驗證**（絕不 `verify=False`）。
  ⚠ 用 `urllib.request`（走系統憑證庫）測起來是通的，`requests`（走 certifi）才會失敗——
  「我手動測過可以」不代表 skill 跑得動，一律用 requests 復測。
- **快取污染（★最陰險）**：這些政府端點在**參數錯誤／服務逾時**時回 **HTTP 200 + text/html
  錯誤頁**，`raise_for_status()` 過關、被當成 geojson/kml 寫進快取；之後每次都讀那份垃圾，
  **永遠不會自己好**，還會以「無交集」形式**靜默假陰性**（河川區域這個第一級項目實際踩到）。
  修法在 `overlay.py`：`_content_ok`/`_cache_valid`/`_fetch_validated` 三道——寫入前驗、
  讀取前也驗、不合格不寫快取。實測 GIC 對不存在的 `fname`（如 SUBSIDENCE）也是回 200+HTML。
- **大圖層 `where=1=1` 會逾時**：國有林／保安林／淹水潛勢用「撈全國」查詢會讓 coastal 內部
  逾時回 8,319 bytes 的 HTML。修法＝該層設 `"bbox_query": True`，`_load_arcgis_query` 改帶
  基地周邊 envelope（EPSG:3826，取整到 1km），payload 從全國縮到數百 KB、秒級完成，
  快取鍵含 bbox 讓鄰近案件重用。

## 與大量圖資轉換工具產線的接點（2026-08-04）

本 skill ＝該產線的 **⓪b 環敏免登入初篩**，插在 ⓪a（免登入取地籍）之後、①b（需登入的
TCDGIS 環敏 53 項）之前。橋接腳本 `scripts/env_prescreen.py`：
- 自 `outputs/<案>/cadastre/基地.shp`（⓪a 產出）讀行政區與地號，呼叫本 skill 的 `api.run`；
- 產 `環境敏感初篩.csv`／`.json`；
- 若案件已有 `環境敏感套疊.csv`（①b 平台結果），**自動逐項對帳**產 `環境敏感對帳.csv`，
  標出兩來源★不一致者——一律以平台／正式查復為準並寫進報告（NR23 前例：本機圖資較舊會
  出現方向相反的結論）。
- **嚴重地層下陷地區**在 eland 無單一窗口資料、水利署也無公開下陷區下載 → 使用者 2026-08-04
  定案**以「地下水管制區第一級」（GIC `fname=gwconare`）作替代判斷**，報告口徑須載明此代理關係。

### ★ eland「應免查範圍查詢」怎麼讀（使用者 2026-08-04 兩次糾正，最易誤解）

它回傳的成果是**「可免查的行政區清單」**。你的行政區**沒出現在成果**＝不在免查名單＝
該項「應查」；出現＝「免查」＝該行政區依法不涉及該敏感地。
→ 對某項目而言：**eland「免查」＝基地依法不涉及**。
  ❌ 不是「行政區層級、粒度較粗、不代表基地」——那是錯的理解。

**對帳時的鐵則**：`eland免查 × 平台套疊涉及` 是**真矛盾（★），不是粒度差異**，
不可淡化。一律以平台／正式查復為準，並把矛盾與可能原因（eland 未更新？平台圖層是
「潛勢」而非「已公告」？）寫進報告。`env_prescreen.py` 的 `reconcile()` 已照此判定。

## 限制

- **地段比對是文字比對**：cadastre-check（農業部命名）與 eland（地政司命名）的地段名稱偶有用字差異
  （如「小段」有無），`eland.py` 的 `find_section_code` 會先精確比對、失敗再做核心字模糊比對，
  仍失敗則地段欄位留空送出查詢——此時**依地段判定的 25 個項目會顯示「無法判定」**，不是查詢失敗。
- **kind="wms" 的項目不會自動判斷相交**（目前 `tgos_layers.py` 沒有任何項目停在這個狀態，但程式邏輯保留支援），
  只在報告中列出、附 WMS 網址，需人工開圖比對。
- **本工具的套疊結果是初步自我篩檢，不是正式判定。** 正式法定用途（環評、雜項執照）仍須以
  eland 正式行文查復結果為準——這點務必寫進每次產出的報告（`report.py` 已內建此提醒，不要移除）。
- **淹水潛勢圖**：水利署自己的 TGOS MAP API（ThemeMap）和 GIC 平台都把它列為限制/內部資料，猜不到開放
  下載網址；後來在 `coastal.nps.gov.tw` 的 `Ocean/others` MapServer 找到公開版本（10 個降雨情境圖層），
  已改用其中「24小時降雨500mm」單一情境（layer 29）接上——這是使用者確認的標準判定情境，其餘 9 個情境
  圖層目前沒接。eland 本身也註明水利署未提供這項的單一窗口應免查資料，所以這項永遠是「應查」，
  只是現在有向量圖資可以先自我篩檢了。
- 向量圖資快取在 `scripts/cache/`（`.zip`/`.kml`/`.geojson`），不會自動更新版本；若圖資已改版（如年度更新的
  土石流潛勢圖），需手動清快取重抓。
- `fmt="geojson_multi"` 的圖層若某個名稱查詢失敗，只會記到 `<快取檔>.failed.txt`，不會讓整體查詢失敗——
  但也代表那個名稱的區域**沒有被納入比對範圍**，要注意這個 silent partial failure。

## 檔案

```
scripts/
  api.py          ★ 對外介面：run(city, town, section, landnos, village=None)
  eland.py        eland 應免查範圍查詢自動化（session/token/連動選單/表格解析）
  tgos_layers.py  eland 項目 <-> 圖資對照表（擴充圖資改這裡；支援 shp/kml/geojson/geojson_multi/geojson_town/arcgis_query/zone_attribute）
  overlay.py      圖資下載快取 + shapely 空間相交判斷（含 zone_attribute 免套疊的使用分區比對邏輯在 api.py）
  report.py       結果轉 Markdown 報告 + matplotlib 套疊示意圖
  check.py        CLI 入口
  cache/          下載圖資快取（.zip/.kml）
```
