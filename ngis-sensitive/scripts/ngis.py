"""
國土規劃地理資訊系統（NGIS）環境敏感地區查詢。

資料源：內政部國土管理署城鄉發展分署
  圖台  https://nsp.nlma.gov.tw/ngis/       （只用來取 token，不渲染）
  服務  https://giss.nlma.gov.tw/tcdmap/rest/services/TCDGIS/
        SENSITIVEAREA_1_2017  一級環境敏感地區（25 圖層）
        SENSITIVEAREA_2_2017  二級環境敏感地區（29 圖層）

三個缺一不可的條件（見 SKILL.md「踩過的坑」）：
  1. token 每次執行重抓，且必須排除被 // 註解掉的舊值
  2. 每個請求都要帶 Referer: https://nsp.nlma.gov.tw/ngis/
  3. 只能用 identify，query 一律被拒（服務謊報支援 Query）
"""
import json
import re
import ssl
import urllib.parse
import urllib.request

PORTAL = 'https://nsp.nlma.gov.tw/ngis/'
BASE = 'https://giss.nlma.gov.tw/tcdmap/rest/services/TCDGIS'
SERVICES = {
    '一級': 'SENSITIVEAREA_1_2017',
    '二級': 'SENSITIVEAREA_2_2017',
}
UA = 'Mozilla/5.0'
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


class NgisError(RuntimeError):
    pass


def _http(url, timeout=45, data=None):
    """
    data 不為 None 時改用 POST。

    大宗地的環會把 URL 撐爆：實測旗山區北勢段291-100（168 頂點）用 GET
    直接回 HTTP 404——不是查無，是查詢字串過長被伺服器擋掉。
    識別度低又難查，所以帶幾何的請求一律走 POST。
    """
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    headers = {'User-Agent': UA, 'Referer': PORTAL}
    if body is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    req = urllib.request.Request(url, data=body, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read().decode('utf-8', 'replace')


def fetch_token(timeout=45):
    """
    取得 layerToken。

    頁面同一行有兩個 `var layerToken = "..."`，第一個被 // 註解掉且已失效。
    只認前方 4 字元內沒有 // 的那一個 —— 拿錯會一路 Invalid Token。
    """
    html = _http(PORTAL, timeout=timeout)
    live = [m.group(1)
            for m in re.finditer(r'var\s+layerToken\s*=\s*"([A-Za-z0-9_\-]{40,90})"', html)
            if '//' not in html[max(0, m.start() - 4):m.start()]]
    if not live:
        raise NgisError('頁面中找不到生效的 layerToken；圖台版型可能已改，需重新確認取法')
    return live[0]


def list_layers(token, level='二級', timeout=45):
    """回傳 [(圖層id, 圖層名)]。名稱可能帶尾端空白，比對前務必 strip。"""
    svc = SERVICES[level]
    d = json.loads(_http(f'{BASE}/{svc}/MapServer?f=json&token={token}', timeout))
    if 'error' in d:
        raise NgisError(f"{level} 圖層清單取得失敗：{d['error'].get('message')}")
    return [(L['id'], (L.get('name') or '').strip()) for L in d.get('layers', [])]


def _identify(token, level, geometry, geom_type, extent, tolerance=3,
              image_px=1000, return_geometry=False, layers='all', timeout=60):
    svc = SERVICES[level]
    xmin, ymin, xmax, ymax = extent
    q = {
        'geometry': json.dumps(geometry),
        'geometryType': geom_type,
        'sr': '102100',
        'layers': layers,
        'tolerance': str(tolerance),
        'mapExtent': f'{xmin},{ymin},{xmax},{ymax}',
        'imageDisplay': f'{image_px},{image_px},96',
        'returnGeometry': 'true' if return_geometry else 'false',
        'f': 'json',
        'token': token,
    }
    # 幾何可能很大，一律 POST（見 _http 的說明）
    raw = _http(f'{BASE}/{svc}/MapServer/identify', timeout, data=q)
    d = json.loads(raw)
    if 'error' in d:
        raise NgisError(f"{level} identify 失敗：{d['error'].get('message')}")
    return d.get('results', [])


def query_point(token, merc_x, merc_y, levels=('一級', '二級'),
                pad=300.0, tolerance=3, return_geometry=False):
    """
    單點查詢。座標須為 WebMercator(3857)；用 geo.tm2_to_merc / lonlat_to_merc 轉換。

    pad 決定 mapExtent 大小，與 image_px 一起換算出每像素地面距離：
    預設 pad=300、1000px → 每像素 0.6 m，tolerance=3px ≈ 1.8 m 吸附範圍。
    """
    geom = {'x': merc_x, 'y': merc_y, 'spatialReference': {'wkid': 102100}}
    extent = (merc_x - pad, merc_y - pad, merc_x + pad, merc_y + pad)
    out = {}
    for lv in levels:
        res = _identify(token, lv, geom, 'esriGeometryPoint', extent,
                        tolerance=tolerance, return_geometry=return_geometry)
        out[lv] = [_clean(r) for r in res]
    return out


def query_polygon(token, rings_merc, levels=('一級', '二級'),
                  tolerance=1, return_geometry=False):
    """
    面查詢（宗地範圍與敏感區的實際交集）。rings_merc 為 WebMercator 環清單。

    面查詢比點查詢正確 —— 宗地可能只有一角落在敏感區內，點查詢會漏判。
    """
    xs = [p[0] for r in rings_merc for p in r]
    ys = [p[1] for r in rings_merc for p in r]
    pad = max(50.0, max(max(xs) - min(xs), max(ys) - min(ys)) * 0.2)
    extent = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    geom = {'rings': rings_merc, 'spatialReference': {'wkid': 102100}}
    out = {}
    for lv in levels:
        res = _identify(token, lv, geom, 'esriGeometryPolygon', extent,
                        tolerance=tolerance, return_geometry=return_geometry)
        out[lv] = [_clean(r) for r in res]
    return out


_DROP = ('Shape', 'Shape.STArea()', 'Shape.STLength()', 'OBJECTID')


def _looks_mojibake(v):
    """
    偵測上游資料的亂碼屬性值。

    NGIS 部分圖層的描述性欄位在資料庫裡就是壞的（非傳輸或解碼問題）：
    實測 2-03嚴重地層下陷地區 的 COUNTYNAME 是 b'\\xc5\\xb8q\\xdb\\xb6m'，
    用 UTF-8/Big5/CP950/GBK 都解不出中文；同一回應的欄位「名稱」中文卻正常，
    同欄位在 2-06山坡地 也正常顯示「臺南市」。2-05淹水潛勢的 city 亦同。

    判定本身（重疊面積、比例、圖層名）不受影響，但這些值不可寫進報告。

    **限制：只抓得到含高位字元的亂碼。** 純 ASCII 的壞值（實測 2-05淹水潛勢
    的 city='0O3n~0'）與合法代碼（kind='24h500r'）在字元組成上無從區分，
    硬猜只會誤刪正常值。因此描述性欄位一律不可盡信，需人工核對。
    """
    if not isinstance(v, str) or not v.strip():
        return False
    s = v.strip()
    # CJK 與全形標點以外的高位字元佔比過高即視為亂碼
    susp = sum(1 for c in s if ord(c) > 0x7F and not (
        0x3000 <= ord(c) <= 0x303F or 0x4E00 <= ord(c) <= 0x9FFF
        or 0xFF00 <= ord(c) <= 0xFFEF))
    return susp >= 1 and susp / len(s) >= 0.2


def _clean(result):
    """整理 identify 結果：去掉幾何雜訊欄位、空值與上游亂碼值，圖層名 strip。"""
    attrs = {k: v for k, v in (result.get('attributes') or {}).items()
             if k not in _DROP and v not in (None, '', ' ', 'Null')
             and not _looks_mojibake(v)}
    item = {
        'layerId': result.get('layerId'),
        'layerName': (result.get('layerName') or '').strip(),
        'attributes': attrs,
    }
    if result.get('geometry'):
        item['geometry'] = result['geometry']
    return item
