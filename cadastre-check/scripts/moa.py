# -*- coding: utf-8 -*-
"""農業部地籍圖資查詢（map.moa.gov.tw / coagis.colife.org.tw）。

取代原本的「圖磚向量化＋ICP 配準＋幾何分割」整條管線：這支直接向官方要
界址環，回傳的就是真正的地籍多邊形，不需要重建、不需要比對舊底圖。

實測精度（對照內政部登記面積）：多數在 ±0.5% 內，最細的 21 m² 宗地 −3.3%。
連圖磚完全畫不出來的畸零地（1.92 m²、寬僅 7 像素）都拿得到真界址。

★ 安全要求：這支 API 會做模糊比對，查不到就回**別的地**，而且會跨縣市。
  實測查「新北市 林口區 小南灣段下福小段 788」回傳「臺南市永康區南灣段231地號」。
  因此 parcel() 一律驗證回傳的 14 碼與請求完全相同，不符即拒絕——
  沒有這道閘門，這支 API 會靜默產出錯誤幾何。
"""
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

CONFIG_URL = ("https://map.moa.gov.tw/farmland/configs/QueryLand/"
              "config_widgets_QueryLand_Widget_47.json")
REFERER = "https://map.moa.gov.tw/farmland/survey.html"
TIMEOUT = 30

# 這批服務的憑證鏈在部分環境下驗不過，但傳輸內容是公開圖資、且回傳值都會
# 經過 14 碼比對，不採信未驗證的內容，故關閉驗證換取可用性。
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_cfg = None
_cache = {}

# 版次有兩種寫法：早期 105Q2（季）、之後 114Dec（雙月）。排序要能同時處理。
_MON = {"Feb": 2, "Apr": 4, "Jun": 6, "Aug": 8, "Oct": 10, "Dec": 12,
        "Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12}


class MoaError(RuntimeError):
    pass


def _get(url, params=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Referer": REFERER,
        "Accept": "application/json, text/plain, */*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise MoaError("連線失敗：%s" % e)
    except ValueError as e:
        raise MoaError("回應不是合法 JSON：%s" % e)


def config(force=False):
    """取服務設定。token 放在公開靜態檔，免登入，但**會輪替**——
    每次執行重抓，不要寫死或長期快取。"""
    global _cfg
    if _cfg is None or force:
        c = _get(CONFIG_URL)
        if not c.get("cadastralSoeToken"):
            raise MoaError("設定檔沒有 token，服務可能已改版")
        _cfg = c
    return _cfg


def _list_url():
    return config()["cadastralListUrl"]


def _ring_url():
    return (config()["cadastralSoeUrl"] +
            "CadastralMap/SOE/MapServer/exts/CoaRESTSOE/LandAddressToLocation_ring")


def _other(name, params=None):
    j = _get(_list_url() + name, params)
    if not j.get("isSuccess"):
        raise MoaError("%s 失敗：%s" % (name, j.get("Msg") or "未知"))
    return j.get("other") or []


def _ver_key(v):
    m = re.match(r"^(\d+)(Q\d|[A-Za-z]{3})$", v or "")
    if not m:
        return (0, 0)
    return (int(m.group(1)), _MON.get(m.group(2), 0))


def versions():
    if "ver" not in _cache:
        rows = _other("GetVerList")
        _cache["ver"] = sorted((r["版次"] for r in rows), key=_ver_key)
    return _cache["ver"]


def newest_version():
    """清單中最新的版次。使用者要求一律走最新，所以每次執行動態解析，不寫死。"""
    v = versions()
    if not v:
        raise MoaError("取不到任何版次")
    return v[-1]


def _norm(s):
    """臺／台 與空白差異在各系統間不一致，比對前統一。"""
    return (s or "").replace("臺", "台").replace(" ", "").strip()


def _pick(names, want):
    """在官方清單中找出對應項目，回傳官方寫法（不是使用者輸入的寫法）。"""
    w = _norm(want)
    for n in names:
        if _norm(n) == w:
            return n
    return None


def counties():
    if "county" not in _cache:
        _cache["county"] = [r["County"] for r in _other("GetCountyList")]
    return _cache["county"]


def towns(county):
    k = ("town", county)
    if k not in _cache:
        _cache[k] = [r["Town"] for r in
                     _other("GetTownList", {"ver": newest_version(), "county": county})]
    return _cache[k]


def sections(county, town, ver=None):
    """回傳 {段名: 段碼}。段碼是 6 碼，例如 EJ2820（事務所 EJ + 段 2820）。"""
    ver = ver or newest_version()
    k = ("sect", ver, county, town)
    if k not in _cache:
        _cache[k] = {r["Sect"]: r["SectCode"] for r in
                     _other("GetSectionList", {"ver": ver, "county": county, "town": town})}
    return _cache[k]


def find_section_any_version(county, town, section, max_back=12):
    """段名在最新版次消失時，往回找哪個版次還有它。回傳 (版次, 段碼) 或 None。

    用途：段名消失通常代表整段重測改名，要送新舊地號轉換就得先有舊段碼。
    段碼不能猜——實測手猜松羅一段為 GD0179，轉換 API 回空；正確是 GA0895。

    只往回找 max_back 個版次：段清單每版一次查詢，全掃 57 版太慢，
    而重測改名後舊段通常在最近幾版還查得到（實測松羅一段、小南灣段下福小段
    都在往回第 2 版就找到）。
    """
    c = _pick(counties(), county)
    if not c:
        return None
    t = _pick(towns(c), town)
    if not t:
        return None
    for v in list(reversed(versions()))[:max_back]:
        try:
            secs = sections(c, t, v)
        except MoaError:
            continue
        s = _pick(list(secs.keys()), section)
        if s:
            return v, secs[s]
    return None


def section_name_of(county, town, sec4, ver=None):
    """由 4 碼段碼反查段名（最新版次）。轉換 API 只給段碼，但查幾何要段名。"""
    ver = ver or newest_version()
    c = _pick(counties(), county)
    t = _pick(towns(c or county), town) if c else None
    if not c or not t:
        return None
    for name, code in sections(c, t, ver).items():
        if code[2:] == sec4:
            return name
    return None


def resolve(county, town, section, ver=None):
    """把使用者輸入對到官方寫法。回傳 (縣市, 鄉鎮, 段名, 段碼) 或拋 MoaError。

    名稱體系與內政部不同，不能直接沿用：實測農業部用「台東市」不是「臺東市」，
    且嘉義市底下只有一個「嘉義市」而沒有東區／西區。
    """
    ver = ver or newest_version()
    c = _pick(counties(), county)
    if not c:
        raise MoaError("查無縣市「%s」" % county)
    t = _pick(towns(c), town)
    if not t:
        raise MoaError("「%s」底下查無鄉鎮「%s」（可選：%s）"
                       % (c, town, "、".join(towns(c)[:8])))
    secs = sections(c, t, ver)
    s = _pick(list(secs.keys()), section)
    if not s:
        raise MoaError("%s %s 在版次 %s 查無段「%s」（該鄉鎮共 %d 段）"
                       % (c, t, ver, section, len(secs)))
    return c, t, s, secs[s]


def parcel(county, town, section, no8, ver=None):
    """查單筆界址環。回傳 dict 或 None（查無／不符）。

    no8: 8 碼地號（母 4 + 子 4），例如 "07110003"。
    回傳 {"ring": [(x,y)...], "code": 14碼, "center": (x,y), "版次": ..., "地址": ...}

    ★ 回傳的 14 碼一定要與請求相符才採用。這支 API 查不到時會回「最接近」的
      別筆地而不是報錯，且會跨縣市。
    """
    ver = ver or newest_version()
    c, t, s, sectcode = resolve(county, town, section, ver)
    want = sectcode + no8
    addr = "%s %s %s %s-%s" % (c, t, s, no8[:4], no8[4:])
    j = _get(_ring_url(), {
        "token": config()["cadastralSoeToken"],
        "LandAddress": addr, "LandVersion": ver, "CodeVersion": ver,
        "SpatialRefZone": "本島", "SpatialRefOutput": "3826", "f": "json"})
    if j.get("error"):
        msg = j["error"].get("message", "")
        if "Token" in msg:
            config(force=True)          # token 輪替過，重抓一次再試
            j = _get(_ring_url(), {
                "token": config()["cadastralSoeToken"],
                "LandAddress": addr, "LandVersion": ver, "CodeVersion": ver,
                "SpatialRefZone": "本島", "SpatialRefOutput": "3826", "f": "json"})
        if j.get("error"):
            raise MoaError("查詢失敗：%s" % j["error"].get("message"))
    rows = j.get("ReturnResult") or []
    if not rows or not rows[0].get("ReturnPolygon"):
        return None
    r0 = rows[0]
    got = r0.get("Return14SecNo") or ""
    if got != want:
        # 模糊比對命中別筆地。這是這支 API 最危險的行為，一律拒絕。
        return {"mismatch": True, "want": want, "got": got,
                "got_addr": r0.get("ReturnLandAddress", "")}
    try:
        rings = json.loads(r0["ReturnPolygon"])["rings"]
    except (ValueError, KeyError) as e:
        raise MoaError("界址環解析失敗：%s" % e)
    ring = [tuple(p) for p in max(rings, key=len)]
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return None
    try:
        cen = (float(r0.get("ReturnCenterX")), float(r0.get("ReturnCenterY")))
    except (TypeError, ValueError):
        cen = None
    return {"ring": ring, "code": got, "center": cen, "版次": ver,
            "地址": r0.get("ReturnLandAddress", ""), "環數": len(rings),
            "縣市": c, "鄉鎮": t, "段名": s, "段碼": sectcode}
