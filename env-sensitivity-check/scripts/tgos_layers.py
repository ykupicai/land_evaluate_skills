# -*- coding: utf-8 -*-
"""
eland 46 項環境敏感項目 <-> TGOS（或各主管機關）圖資對照表。

kind:
  "vector"         -> 有可下載之向量圖資（SHP/KML），可實際做空間相交判斷
  "wms"            -> 僅有 WMS 影像服務，只能視覺比對，無法自動判斷相交
  "zone_attribute" -> 不需套疊圖資，直接比對 cadastre-check 回傳的登記「使用分區」欄位即可判斷
                      （森林區/特定農業區/一般農業區本身就是非都市土地使用分區名稱）
  "none"           -> 查無公開圖資，需逕洽主管機關 / 走 eland 正式申請

match 用來比對 eland.py 解析出的 item：(level 關鍵字, item_no, sub_name 關鍵字或 None)
level 關鍵字只需是 "第一級"/"第二級"/"海岸管理法" 其中之一的子字串。
"""

LAYERS = [
    # ---- 第一級 ----
    {"level": "第一級", "item_no": "2", "sub": None,
     "name": "河川區域", "agency": "經濟部水利署", "kind": "vector",
     "url": "https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=RIVERL&filetype=KML",
     "fmt": "kml"},
    {"level": "第一級", "item_no": "4", "sub": None,
     "name": "區域排水設施範圍", "agency": "經濟部水利署", "kind": "vector",
     "url": "https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=REGDAREA&filetype=SHP",
     "fmt": "shp"},
    {"level": "第一級", "item_no": "5", "sub": None,
     "name": "活動斷層兩側一定範圍", "agency": "經濟部地質調查及礦業管理中心", "kind": "vector", "fmt": "geojson_multi",
     "url_template": "https://www.geologycloud.tw/data/zh-tw/GeologicalSensitiveAreas?category=%E6%B4%BB%E5%8B%95%E6%96%B7%E5%B1%A4&name={name}",
     "names": ["旗山斷層", "新竹斷層", "新城斷層", "新化斷層", "池上斷層", "車籠埔斷層", "大尖山斷層", "三義斷層",
               "九芎坑斷層", "鹿野斷層", "瑞穗斷層", "奇美斷層", "米崙斷層", "木屐寮斷層", "六甲斷層", "獅潭斷層",
               "屯子腳斷層", "嶺頂斷層", "梅山斷層", "大甲斷層", "小崗山斷層", "車瓜林斷層", "玉里斷層", "利吉斷層",
               "初鄉斷層", "大茅埔─雙冬斷層", "口宵里斷層"]},
    {"level": "第一級", "item_no": "7", "sub": None,
     "name": "自然保留區", "agency": "農業部林業及自然保育署", "kind": "vector",
     "url": "https://www.tgos.tw:443/MDE/VirtualDir_TC/Product/4fbee0f6-e2e2-4deb-93f3-eeefa6659d81/自然保留區1152_SHP.zip",
     "fmt": "shp"},
    {"level": "第一級", "item_no": "8", "sub": None,
     "name": "野生動物保護區", "agency": "農業部林業及自然保育署", "kind": "vector",
     "url": "https://www.tgos.tw:443/MDE/VirtualDir_TC/Product/54693a28-60f4-435d-9509-039f0b23dd94/mapdata202307040547.zip",
     "fmt": "shp"},
    {"level": "第一級", "item_no": "9", "sub": None,
     "name": "野生動物重要棲息環境", "agency": "農業部林業及自然保育署", "kind": "vector",
     "url": "https://www.tgos.tw:443/MDE/VirtualDir_TC/Product/2a45414e-619a-420c-8830-3b19f2f38ce7/陸域野生動物重要棲息環境1151_SHP.zip",
     "fmt": "shp"},
    {"level": "第一級", "item_no": "10", "sub": None,
     "name": "自然保護區", "agency": "農業部林業及自然保育署", "kind": "vector",
     "url": "https://www.tgos.tw:443/MDE/VirtualDir_TC/Product/69fdf5ae-434e-4e7a-b61b-568426f0b359/自然保護區1151_SHP.zip",
     "fmt": "shp"},
    {"level": "第一級", "item_no": "21", "sub": None,
     "name": "水庫集水區", "agency": "經濟部水利署", "kind": "vector",
     "url": "https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=reservoir&filetype=SHP",
     "fmt": "shp"},
    {"level": "第二級", "item_no": "19", "sub": None,
     "name": "水庫集水區（非供家用或非供公共給水）", "agency": "經濟部水利署", "kind": "vector",
     "url": "https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=reservoir&filetype=SHP",
     "fmt": "shp"},
    {"level": "第一級", "item_no": "22", "sub": None,
     "name": "水庫蓄水範圍", "agency": "經濟部水利署", "kind": "vector",
     "url": "https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=ressub&filetype=SHP",
     "fmt": "shp"},
    {"level": "第一級", "item_no": "6", "sub": None,
     "name": "國家公園區內之特別景觀區、生態保護區", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 23},
    {"level": "第一級", "item_no": "12", "sub": "國際級重要濕地",
     "name": "國際級重要濕地", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 26},
    {"level": "第一級", "item_no": "13", "sub": None,
     "name": "古蹟保存區", "agency": "文化部文化資產局／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 3},
    {"level": "第一級", "item_no": "14", "sub": None,
     "name": "考古遺址", "agency": "文化部文化資產局／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 5},
    {"level": "第一級", "item_no": "15", "sub": None,
     "name": "重要聚落建築群", "agency": "文化部文化資產局／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 2},
    {"level": "第一級", "item_no": "16", "sub": None,
     "name": "重要文化景觀", "agency": "文化部文化資產局／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 1},
    {"level": "第一級", "item_no": "19", "sub": None,
     "name": "國家公園內之史蹟保存區", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 22},
    {"level": "第一級", "item_no": "20", "sub": "飲用水水源水質保護區",
     "name": "飲用水水源水質保護區", "agency": "環境部／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 8},
    {"level": "第一級", "item_no": "20", "sub": "飲用水取水口一定距離內之地區",
     "name": "飲用水取水口一定距離內之地區", "agency": "環境部／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 7},
    {"level": "第一級", "item_no": "23", "sub": "國有林事業區",
     "name": "國有林事業區", "agency": "農業部林業及自然保育署／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 9, "bbox_query": True},
    {"level": "第一級", "item_no": "23", "sub": "保安林",
     "name": "保安林", "agency": "農業部林業及自然保育署／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 11, "bbox_query": True},
    {"level": "第一級", "item_no": "23", "sub": "林業試驗林地",
     "name": "林業試驗林地", "agency": "農業部林業及自然保育署／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 10},
    {"level": "第一級", "item_no": "24", "sub": None,
     "name": "溫泉露頭及其一定範圍", "agency": "經濟部／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 20},
    {"level": "第一級", "item_no": "25", "sub": None,
     "name": "水產動植物繁殖保育區", "agency": "農業部漁業署／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 15},
    {"level": "第一級", "item_no": "23", "sub": "森林區",
     "name": "非都市土地使用分區：森林區", "agency": "地政機關（依登記使用分區判定）", "kind": "zone_attribute",
     "zone_match": ["森林區"]},
    {"level": "第一級", "item_no": "26", "sub": None,
     "name": "優良農地（特定農業區）", "agency": "地政機關（依登記使用分區判定）", "kind": "zone_attribute",
     "zone_match": ["特定農業區"]},
    # ---- 第二級 ----
    {"level": "第二級", "item_no": "1", "sub": "山崩與地滑",
     "name": "山崩與地滑地質敏感區", "agency": "經濟部地質調查及礦業管理中心", "kind": "vector",
     "fmt": "geojson_town", "category": "山崩與地滑"},
    {"level": "第二級", "item_no": "1", "sub": "活動斷層",
     "name": "地質敏感地區（活動斷層）", "agency": "經濟部地質調查及礦業管理中心", "kind": "vector", "fmt": "geojson_multi",
     "url_template": "https://www.geologycloud.tw/data/zh-tw/GeologicalSensitiveAreas?category=%E6%B4%BB%E5%8B%95%E6%96%B7%E5%B1%A4&name={name}",
     "names": ["旗山斷層", "新竹斷層", "新城斷層", "新化斷層", "池上斷層", "車籠埔斷層", "大尖山斷層", "三義斷層",
               "九芎坑斷層", "鹿野斷層", "瑞穗斷層", "奇美斷層", "米崙斷層", "木屐寮斷層", "六甲斷層", "獅潭斷層",
               "屯子腳斷層", "嶺頂斷層", "梅山斷層", "大甲斷層", "小崗山斷層", "車瓜林斷層", "玉里斷層", "利吉斷層",
               "初鄉斷層", "大茅埔─雙冬斷層", "口宵里斷層"]},
    {"level": "第二級", "item_no": "1", "sub": "土石流",
     "name": "地質敏感地區（土石流）", "agency": "農業部農村發展及水土保持署", "kind": "vector", "fmt": "geojson",
     "url": "https://www.geologycloud.tw/data/zh-tw/ext_swcb_DebrisArea"},
    {"level": "第二級", "item_no": "4", "sub": None,
     "name": "海堤區域", "agency": "經濟部水利署", "kind": "vector",
     "url": "https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=SEAWALLZONE&filetype=SHP",
     "fmt": "shp"},
    {"level": "第二級", "item_no": "17", "sub": None,
     "name": "地質敏感區(地質遺跡)", "agency": "經濟部地質調查及礦業管理中心", "kind": "vector", "fmt": "geojson_multi",
     "url_template": "https://www.geologycloud.tw/data/zh-tw/GeologicalSensitiveAreas?category=%E5%9C%B0%E8%B3%AA%E9%81%BA%E8%B7%A1&name={name}",
     "names": ["大華壺穴", "暖暖壺穴", "十分瀑布", "萊萊火成岩脈", "桶盤嶼玄武岩", "七美嶼凝灰角礫岩", "過港貝化石層",
               "龜山島火山碎屑堆積層", "鼻頭角海蝕地形", "嘉義縣瑞里蝙蝠洞及燕子崖", "高雄市高中枕狀熔岩",
               "琉球嶼西南沿岸海蝕地形及崩崖", "南投縣武界褶皺構造與曲流峽谷", "秀姑巒溪八里灣層沉積岩及曲流",
               "臺東縣小野柳濁流岩", "利吉混同層及其蛇綠岩系外來岩塊", "花蓮縣石梯坪海階及凝灰岩",
               "高雄市雞冠山石灰岩", "屏東縣車城尖山外來岩塊"]},
    {"level": "第二級", "item_no": "20", "sub": None,
     "name": "自來水水質水量保護區", "agency": "經濟部水利署", "kind": "vector",
     "url": "https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=TWQPROT&filetype=SHP",
     "fmt": "shp"},
    {"level": "第二級", "item_no": "23", "sub": None,
     "name": "地質敏感區(地下水補注)", "agency": "經濟部地質調查及礦業管理中心", "kind": "vector", "fmt": "geojson_multi",
     "url_template": "https://www.geologycloud.tw/data/zh-tw/GeologicalSensitiveAreas?category=%E5%9C%B0%E4%B8%8B%E6%B0%B4%E8%A3%9C%E6%B3%A8&name={name}",
     "names": ["濁水溪沖積扇", "宜蘭平原", "臺北盆地", "嘉南平原", "臺中盆地", "屏東平原"]},
    {"level": "第二級", "item_no": "7", "sub": None,
     "name": "土石流潛勢溪流地區", "agency": "農業部農村發展及水土保持署", "kind": "vector", "fmt": "geojson",
     "url": "https://www.geologycloud.tw/data/zh-tw/ext_swcb_DebrisArea"},
    {"level": "第二級", "item_no": "21", "sub": None,
     "name": "優良農地以外之農業用地（一般農業區）", "agency": "地政機關（依登記使用分區判定）", "kind": "zone_attribute",
     "zone_match": ["一般農業區"]},
    {"level": "第二級", "item_no": "11", "sub": "地方級重要濕地核心保育區、生態復育區",
     "name": "地方級重要濕地核心保育區、生態復育區", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 24},
    {"level": "第二級", "item_no": "11", "sub": "國家級重要濕地核心保育區、生態復育區以外分區",
     "name": "國家級重要濕地核心保育區、生態復育區以外分區", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 25},
    {"level": "第二級", "item_no": "18", "sub": None,
     "name": "國家公園內之一般管制區及遊憩區", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 21},
    {"level": "第二級", "item_no": "24", "sub": None,
     "name": "人工魚礁區及保護礁區", "agency": "農業部漁業署／內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 14},
    {"level": "第二級", "item_no": "9", "sub": None,
     "name": "二級海岸保護區（沿海一般保護區）", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/SeaSideProtection/MapServer", "layer_id": 0},
    {"level": "第二級", "item_no": "5", "sub": None,
     "name": "淹水潛勢（24小時降雨500mm標準情境）", "agency": "經濟部水利署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/others/MapServer", "layer_id": 29, "bbox_query": True},
    # ---- 第一級（海岸保護區，補在後面避免影響前面既有比對）----
    {"level": "第一級", "item_no": "11", "sub": None,
     "name": "一級海岸保護區（沿海自然保護區）", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/SeaSideProtection/MapServer", "layer_id": 1},
    # ---- 海岸管理法特定區位 ----
    {"level": "海岸管理法", "item_no": "1", "sub": "一級海岸防護區",
     "name": "一級海岸防護區", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/coastalDefend/MapServer", "layer_id": 0},
    {"level": "海岸管理法", "item_no": "1", "sub": "二級海岸防護區",
     "name": "二級海岸防護區", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/coastalDefend/MapServer", "layer_id": 1},
    {"level": "海岸管理法", "item_no": "1", "sub": "一級海岸保護區",
     "name": "一級海岸保護區（沿海自然保護區）", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/SeaSideProtection/MapServer", "layer_id": 1},
    {"level": "海岸管理法", "item_no": "1", "sub": "二級海岸保護區",
     "name": "二級海岸保護區（沿海一般保護區）", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/SeaSideProtection/MapServer", "layer_id": 0},
    {"level": "海岸管理法", "item_no": "1", "sub": "近岸海域",
     "name": "近岸海域", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/coastalArea/MapServer", "layer_id": 5},
    {"level": "海岸管理法", "item_no": "1", "sub": "潮間帶",
     "name": "潮間帶", "agency": "內政部國家公園署", "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/coastalArea/MapServer", "layer_id": 11},

    # ══ 2026-08-04 新增（依使用者指定的三個來源逐一盤點後補上）══════════════
    # ★ 嚴重地層下陷地區 → 以「地下水管制區第一級」判斷（使用者 2026-08-04 定案）。
    #   理由：地層下陷的法定管制手段就是地下水管制；水利署本身沒有公開的下陷區下載
    #   （實測 fname=SUBSIDENCE 回 HTTP 200 + text/html 錯誤頁，不是圖資），
    #   而地下水第一級管制區有現成 SHP。
    #   ⚠ 報告口徑須寫明「以地下水管制區第一級作為地層下陷之替代判斷」，
    #     不可逕稱已判定嚴重地層下陷地區。
    #   另註：coastal 的 Ocean/others layer 31 也有「地下水第一級管制區」，可交叉核對。
    {"level": "第二級", "item_no": "3", "sub": None,
     "name": "嚴重地層下陷地區（以地下水管制區第一級判斷）", "agency": "經濟部水利署",
     "kind": "vector", "fmt": "shp",
     "url": "https://gic.wra.gov.tw/gis/gic/API/Google/DownLoad.aspx?fname=gwconare&filetype=SHP",
     "note": "替代判斷：地下水管制區第一級。報告須載明此代理關係。"},

    # 文化資產類：eland 一律要求逕洽地方文資機關，但 coastal 的 vulnerable 服務裡
    # 其實有現成向量圖層，可先自我篩檢（仍不取代正式查復）。
    {"level": "第二級", "item_no": "12", "sub": None,
     "name": "歷史建築", "agency": "文化部文化資產局／內政部國家公園署",
     "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 4},
    {"level": "第二級", "item_no": "13", "sub": None,
     "name": "聚落建築群（聚落保存區）", "agency": "文化部文化資產局／內政部國家公園署",
     "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 27},
    {"level": "第二級", "item_no": "14", "sub": None,
     "name": "文化景觀（文化景觀保存區）", "agency": "文化部文化資產局／內政部國家公園署",
     "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 0},
    # 礦業保留區：vulnerable layer 18「礦業保留地」。
    # ⚠ 同題號的「礦區（場）」與「地下礦坑分布地區」仍無公開向量來源，維持逕洽經濟部。
    {"level": "第二級", "item_no": "22", "sub": "礦業保留區",
     "name": "礦業保留區（礦業保留地）", "agency": "經濟部／內政部國家公園署",
     "kind": "vector", "fmt": "arcgis_query",
     "service_url": "https://coastal.nps.gov.tw/coastal/rest/services/Ocean/vulnerable/MapServer", "layer_id": 18},
]


def find_layer(level: str, item_no: str, sub_name: str = ""):
    """回傳最匹配的圖資設定；找不到回傳 None。"""
    best = None
    for ly in LAYERS:
        if ly["item_no"] != item_no:
            continue
        if ly["level"] not in level:
            continue
        if ly["sub"] is None:
            best = best or ly
        elif sub_name and ly["sub"] in sub_name:
            return ly
    return best
