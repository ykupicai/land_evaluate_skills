# -*- coding: utf-8 -*-
"""下載（快取）TGOS/主管機關向量圖資，並與基地幾何做空間相交判斷。"""
from __future__ import annotations
import os
import json
import hashlib
import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape, Point

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

UA = "Mozilla/5.0 env-sensitivity-check/1.0"

# 政府網站憑證缺 Subject Key Identifier，Python 3.12+ 的嚴格驗證會擋（詳 govtls.py）。
# 一律走這個已掛相容 adapter 的 session，別直接用 requests.get。
from govtls import gov_session  # noqa: E402

SESSION = gov_session()


def _cache_path(key: str, ext: str) -> str:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"{h}.{ext}")


# ── 快取內容驗證（★不可省略，2026-08-04 實踩）─────────────────────────────
# 症狀：`保安林` 與 `淹水潛勢` 兩個 .geojson 快取檔其實是 8,638 bytes 的 HTML 錯誤頁，
#      於是每次跑都報「套疊錯誤，需人工確認」，而且**永遠不會自己好**。
# 成因：這些政府端點在參數錯誤／服務異常時回 **HTTP 200 + text/html**，
#      `r.raise_for_status()` 因此過關，接著 `f.write(r.text)` 把 HTML 寫成 .geojson；
#      下一次 `os.path.exists(path)` 為真就直接讀那份垃圾。
#      實測 GIC 端點對不存在的 fname（如 SUBSIDENCE）同樣回 HTTP 200 + text/html。
# 修法：寫入前驗、讀取前也驗；不合格就**不要寫**／**視為沒有快取而重抓**。
#      （大量圖資轉換工具的 nlsc_wmts.py 圖磚快取踩過同一個坑，那邊用魔術位元組驗。）
def _content_ok(data, ext: str) -> bool:
    """粗驗內容型別：geojson 要能解析成 JSON、zip 要有 PK magic、kml 要像 XML。"""
    if ext in ("geojson", "json"):
        if isinstance(data, bytes):
            data = data.decode("utf-8", "replace")
        s = data.lstrip()
        if not s.startswith(("{", "[")):
            return False          # HTML 錯誤頁一律在這裡被擋掉
        try:
            obj = json.loads(s)
        except Exception:  # noqa: BLE001
            return False          # 截斷的 JSON 也擋掉
        if isinstance(obj, dict) and obj.get("error"):
            return False          # ArcGIS 的 JSON 形式錯誤回應
        return isinstance(obj, (dict, list))
    if ext == "zip":
        b = data if isinstance(data, bytes) else data.encode("utf-8", "replace")
        return b[:2] == b"PK"
    if ext == "kml":
        s = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
        return "<kml" in s[:4000].lower() or s.lstrip().startswith("<?xml")
    return bool(data)


def _cache_valid(path: str, ext: str) -> bool:
    """既有快取檔是否可用；不可用回 False 讓呼叫端重抓（不刪檔，留著給人查）。"""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    if ext == "zip":
        with open(path, "rb") as f:
            head = f.read(4096)
    else:
        # 大 geojson 不整檔讀：先看開頭像不像 JSON，再交給 json.loads 全檔驗
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if not f.read(2048).lstrip().startswith(("{", "[")):
                head = "<not json>"
            else:
                f.seek(0)
                head = f.read()
    if _content_ok(head, ext):
        return True
    print(f"    [快取失效] {os.path.basename(path)} 內容不是 {ext}"
          f"（很可能是 HTTP 200 的 HTML 錯誤頁）→ 重新下載")
    return False


def _fetch_validated(url: str, ext: str, params=None, timeout=90) -> bytes:
    """下載並驗內容；不合格丟 RuntimeError（**不寫入快取**，免得毒到下一次）。"""
    r = SESSION.get(url, params=params, timeout=timeout, headers={"User-Agent": UA})
    r.raise_for_status()
    body = r.content
    if not _content_ok(body, ext):
        ct = r.headers.get("Content-Type", "?")
        raise RuntimeError(
            f"回應不是 {ext}（HTTP {r.status_code}、Content-Type={ct}、"
            f"{len(body)} bytes）——常見於參數錯誤或服務異常時回 200+HTML；未寫入快取")
    return body


def _finalize_crs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    if gdf.crs.to_epsg() != 3826:
        gdf = gdf.to_crs("EPSG:3826")
    return gdf


def load_layer_gdf(layer: dict, bbox=None) -> gpd.GeoDataFrame:
    """下載並快取指定圖層，回傳 EPSG:3826 的 GeoDataFrame。
    bbox=(minx,miny,maxx,maxy) EPSG:3826，僅 `bbox_query` 圖層會用到（見 _load_arcgis_query）。"""
    fmt = layer.get("fmt", "shp")

    if fmt == "geojson":
        return _load_geojson_single(layer)
    if fmt == "geojson_multi":
        return _load_geojson_multi(layer)
    if fmt == "arcgis_query":
        return _load_arcgis_query(layer, bbox=bbox)
    if fmt == "arcgis_query_multi":
        return _load_arcgis_query_multi(layer)
    if fmt == "boch_asset":
        return _load_boch_asset(layer)
    if fmt == "local_shp":
        return _load_local_shp(layer)

    url = layer["url"]
    ext = "zip" if fmt == "shp" else fmt
    path = _cache_path(url, ext)
    if not _cache_valid(path, ext):
        with open(path, "wb") as f:
            f.write(_fetch_validated(url, ext, timeout=60))

    if fmt == "shp":
        # ⚠ zip 內的 .shp 可能在子目錄（GIC 下載檔就是 `Flood_500mm_24HR/xxx.shp`），
        #   `zip://path` 只看根目錄會 DataSourceError。找出 zip 內第一個 .shp 的相對路徑再讀。
        import zipfile  # noqa: PLC0415
        with zipfile.ZipFile(path) as zf:
            shps = [n for n in zf.namelist() if n.lower().endswith(".shp")]
        if not shps:
            raise ValueError(f"zip 內沒有 .shp：{path}")
        gdf = gpd.read_file(f"zip://{path}!{shps[0]}" if "/" in shps[0]
                            else f"zip://{path}")
    elif fmt == "kml":
        gdf = gpd.read_file(path, driver="KML")
    else:
        raise ValueError(f"未支援的格式: {fmt}")

    return _finalize_crs(gdf)


def _load_geojson_single(layer: dict) -> gpd.GeoDataFrame:
    url = layer["url"]
    path = _cache_path(url, "geojson")
    if not _cache_valid(path, "geojson"):
        with open(path, "wb") as f:
            f.write(_fetch_validated(url, "geojson", timeout=60))
    gdf = gpd.read_file(path)
    return _finalize_crs(gdf)


def _load_arcgis_query(layer: dict, bbox=None) -> gpd.GeoDataFrame:
    """layer['service_url'] 為 ArcGIS REST MapServer 網址，layer['layer_id'] 為圖層編號。
    呼叫 .../<layer_id>/query 取圖徵（公開服務，不需金鑰）。

    ★ 大圖層必須帶空間範圍（2026-08-04 實踩）：`where=1=1` 是「把全國圖徵一次撈回來」，
      國有林事業區／保安林／淹水潛勢這三個大圖層會讓伺服器內部逾時，
      回 **HTTP 200 + 8,319 bytes 的 HTML 錯誤頁**（不是 JSON，也不是 5xx）。
      在 tgos_layers 對該層設 `"bbox_query": True`，這裡就改帶 envelope 只取基地周邊，
      payload 從全國縮到數百 KB，秒級完成。
      快取鍵含 bbox（取整到 1 公里）——不同基地各自快取，同一帶的案子可重用。
    """
    url = f"{layer['service_url']}/{layer['layer_id']}/query"
    params = {"where": "1=1", "outFields": "*", "f": "geojson"}
    cache_key = url
    if layer.get("bbox_query") and bbox:
        # 取整到 1km 並外擴 1km，讓鄰近案件命中同一份快取
        x1, y1, x2, y2 = bbox
        g = 1000.0
        x1 = (int(x1 // g) - 1) * g; y1 = (int(y1 // g) - 1) * g
        x2 = (int(x2 // g) + 2) * g; y2 = (int(y2 // g) + 2) * g
        params.update({
            "geometry": f"{x1},{y1},{x2},{y2}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "3826",
            "spatialRel": "esriSpatialRelIntersects",
        })
        cache_key = f"{url}|bbox|{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}"
    path = _cache_path(cache_key, "geojson")
    if not _cache_valid(path, "geojson"):
        body = _fetch_validated(url, "geojson", params=params)
        with open(path, "wb") as f:
            f.write(body)
    gdf = gpd.read_file(path)
    return _finalize_crs(gdf)


def _load_arcgis_query_multi(layer: dict) -> gpd.GeoDataFrame:
    """layer['service_url'] + layer['layer_ids']（多個圖層編號），逐一查詢後合併成一個 GeoDataFrame。
    用於「符合任一情境即算」的情況，例如淹水潛勢圖的多種降雨情境圖層。"""
    cache_key = layer["service_url"] + "|" + ",".join(str(i) for i in layer["layer_ids"])
    path = _cache_path(cache_key, "geojson")
    if not _cache_valid(path, "geojson"):
        parts = []
        failed = []
        for lid in layer["layer_ids"]:
            url = f"{layer['service_url']}/{lid}/query"
            try:
                fc = json.loads(_fetch_validated(
                    url, "geojson",
                    params={"where": "1=1", "outFields": "*", "f": "geojson"}))
            except Exception:
                failed.append(str(lid))
                continue
            for feat in fc.get("features", []):
                feat.setdefault("properties", {})
                feat["properties"]["_layer_id"] = lid
                parts.append(feat)
        if failed:
            with open(path + ".failed.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(failed))
        combined = {"type": "FeatureCollection", "features": parts}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(combined, f, ensure_ascii=False)
    gdf = gpd.read_file(path)
    return _finalize_crs(gdf)


def _load_geojson_multi(layer: dict) -> gpd.GeoDataFrame:
    """layer['url_template'] 含 {name} 佔位符，layer['names'] 為要逐一查詢並合併的名稱清單。"""
    cache_key = layer["url_template"] + "|" + ",".join(layer["names"])
    path = _cache_path(cache_key, "geojson")
    if not _cache_valid(path, "geojson"):
        parts = []
        failed = []
        for name in layer["names"]:
            url = layer["url_template"].format(name=requests.utils.quote(name))
            try:
                fc = json.loads(_fetch_validated(url, "geojson", timeout=60))
            except Exception:
                failed.append(name)
                continue
            for feat in fc.get("features", []):
                feat.setdefault("properties", {})
                feat["properties"]["_query_name"] = name
                parts.append(feat)
        if failed:
            with open(path + ".failed.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(failed))
        combined = {"type": "FeatureCollection", "features": parts}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(combined, f, ensure_ascii=False)
    gdf = gpd.read_file(path)
    return _finalize_crs(gdf)


def _load_local_shp(layer: dict) -> gpd.GeoDataFrame:
    """本機環境敏感圖資（單一登記表 LOCAL_LAYERS 解析出的 shp）。

    layer 由 tgos_layers.resolve_by_name 產生的規則加上 `local_path` 組成：
      local_path : 已解析存在的絕對路徑（.shp/.geojson，含案件層 override）
      crs        : 無 .prj 時假定的 EPSG（本機山坡地 BOUNDARY.shp 就沒有 .prj）
      encoding   : dbf 編碼（地下水管制區為 big5）
    ⚠ 本機圖資多為 105~106 年快照，可能比平台舊（NR23 教訓）；此為免登入初篩用，
      交付仍以平台／主管機關查復為準。線圖層（河川/排水/煤礦坑道）以 intersects 判穿越，
      不緩衝——「線穿過基地」即為相交，符合套疊語意。"""
    path = str(layer["local_path"])
    kw = {}
    enc = layer.get("encoding")
    if enc:
        kw["encoding"] = enc
    gdf = gpd.read_file(path, **kw)
    if gdf.crs is None:
        gdf = gdf.set_crs(f"EPSG:{layer.get('crs', 3826)}")
    return _finalize_crs(gdf)


BOCH_BASE = "https://data.boch.gov.tw/opendata/v2/assetsCase"


def _load_boch_asset(layer: dict) -> gpd.GeoDataFrame:
    """文化部文化資產局 OpenData v2（免認證）：紀念建築(1.4)、史蹟(3.2)等建造物資產。
    每筆有 longitude/latitude（WGS84 代表點）與 landlotList（坐落地號）。

    ⚠ 幾何是**代表點非坵塊面**：以 layer['point_buffer_m']（預設 100m）緩衝成面後才做相交，
      命中僅代表『基地附近有此類文資』，實際坵塊須以回傳的『地號』欄（landlotList）人工核對，
      不可逕當權威判定（正式仍以文資局查復為準）。
    ⚠ /geo/ 端點（理論面幾何）2026-08-04 實測回 HTTP 500『系統異常』，故走非-geo 的點位版；
      該端點恢復後可改抓 geo 版取真實面界。"""
    code = layer["boch_code"]
    url = f"{BOCH_BASE}/{code}.json"
    path = _cache_path(url, "json")
    if not _cache_valid(path, "json"):
        with open(path, "wb") as f:
            f.write(_fetch_validated(url, "json", timeout=60))
    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    recs, dropped = [], []
    for r in rows:
        try:
            lon = float(r.get("longitude")); lat = float(r.get("latitude"))
        except (TypeError, ValueError):
            dropped.append(r.get("caseName")); continue
        if not (119 <= lon <= 123 and 21 <= lat <= 26):   # 台灣本島＋離島合理範圍，濾掉髒點
            dropped.append(r.get("caseName")); continue
        landnos = "、".join(
            f"{a.get('cityName', '')}{a.get('distName', '')}{a.get('landNo', '')}"
            for a in (r.get("landlotList") or []))
        recs.append({"名稱": r.get("caseName"), "caseId": r.get("caseId"),
                     "地號": landnos, "geometry": Point(lon, lat)})
    # ⚠ 無有效座標者無法做空間篩檢 → 一律印出，避免靜默漏成「無涉及」（本專案鐵律）。
    #   這幾筆只能靠 landlotList 地號人工核對是否落在基地所在鄉鎮。
    if dropped:
        print(f"    [boch {code}] ⚠ {len(dropped)} 筆無有效座標、未納入空間篩檢，"
              f"須以地號人工核對：{'、'.join(str(x) for x in dropped)}")
    gdf = gpd.GeoDataFrame(recs, geometry="geometry", crs="EPSG:4326")
    gdf = _finalize_crs(gdf)                                # → EPSG:3826（公尺）
    buf = layer.get("point_buffer_m", 100)
    if buf and len(gdf):
        gdf["geometry"] = gdf.geometry.buffer(buf)
    return gdf


def _load_geojson_town(layer: dict, county: str, town: str) -> gpd.GeoDataFrame:
    """
    地質雲『山崩與地滑』分類是逐縣市/鄉鎮查詢（單一鄉鎮即可能有上萬筆圖徵、數十MB），
    不適合像斷層/地質遺跡那樣整批快取，改成用到哪個鄉鎮才抓哪個鄉鎮，並以 (category,county,town) 為快取鍵。
    """
    cache_key = f"geojson_town|{layer['category']}|{county}|{town}"
    path = _cache_path(cache_key, "geojson")
    if not _cache_valid(path, "geojson"):
        params = {"category": layer["category"], "name": county, "town": town, "all": "true"}
        body = _fetch_validated("https://www.geologycloud.tw/data/zh-tw/GeologicalSensitiveAreas",
                                "geojson", params=params, timeout=120)
        with open(path, "wb") as f:
            f.write(body)
    gdf = gpd.read_file(path)
    return _finalize_crs(gdf)


def check_intersection(parcel_geometry_geojson: dict, layer: dict, county: str = None, town: str = None) -> dict:
    """
    parcel_geometry_geojson: cadastre-check 回傳的 GeoJSON geometry (EPSG:3826)
    county/town: 僅 fmt="geojson_town" 圖層需要，用於決定要抓哪個鄉鎮的資料
    回傳: {"intersects": bool, "matched_features": int, "feature_names": [...], "error": str|None}
    """
    try:
        parcel_geom = shape(parcel_geometry_geojson)
        if layer.get("fmt") == "geojson_town":
            if not county or not town:
                return {"intersects": None, "matched_features": 0, "feature_names": [],
                        "error": "geojson_town 圖層需要 county/town 參數"}
            gdf = _load_geojson_town(layer, county, town)
        else:
            gdf = load_layer_gdf(layer, bbox=parcel_geom.bounds)
        hits = gdf[gdf.intersects(parcel_geom)]
        name_cols = [c for c in ["NAME", "Name", "name", "c_name", "MC_NAME", "FILE_NAME", "_query_name", "Debrisno", "Gid",
                                  "個案名", "名稱", "NAME_1"] if c in gdf.columns]
        names = []
        if name_cols and len(hits):
            names = hits[name_cols[0]].astype(str).tolist()
        return {
            "intersects": len(hits) > 0,
            "matched_features": int(len(hits)),
            "feature_names": names[:10],
            "error": None,
        }
    except Exception as e:
        return {"intersects": None, "matched_features": 0, "feature_names": [], "error": str(e)}
