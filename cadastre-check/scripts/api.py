# -*- coding: utf-8 -*-
"""cadastre-check 對外程式介面 —— 給其他專案串接用。

    from api import query
    r = query("高雄市", "路竹區", "保安段", ["711-3", "711-4"])
    for rec in r["records"]:
        if rec["ok"]:
            rec["geometry"]        # GeoJSON Polygon，EPSG:3826
            rec["registry"]["area"]  # 官方登記面積 —— 面積請一律用這個

設計原則
--------
* **鍵名全部 ASCII**：中文鍵在跨語言／跨系統時容易出事（編碼、序列化、欄位名限制）。
  check.py 產的 report_*.json 保留中文鍵給人看；這裡是給機器用的。
* **結構固定**：不論成功失敗，每筆 record 的鍵都一樣，只有值不同。
  呼叫端只要看 `ok` 與 `status`，不必為每種結論寫不同的解析。
* **SCHEMA 版本號**：格式變動時 +1，呼叫端可以檢查。
* **面積分兩個欄位**：`registry.area` 是官方登記面積（權威），`map_area` 是幾何實算
  （僅供對照）。**絕不要拿 map_area 當面積用**——這份幾何是評估用途，不是界址。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cadlib as C
import check
import config as CFG
import moa

SCHEMA = 1

#: status 的所有可能值。ok=True 只有前兩種。
STATUSES = ("OK", "RESURVEYED", "MISMATCH", "NOT_FOUND", "ERROR")


def _geojson_ring(ring):
    """轉成 GeoJSON Polygon 的 coordinates。

    RFC 7946 規定外環為**逆時針**，與 Shapefile 的順時針慣例相反——
    兩邊都要對，所以這裡依規格轉向，不要沿用 SHP 的環向。
    首尾必須閉合。
    """
    r = list(ring)
    if C.shoelace(r) < 0:          # 負值＝順時針 -> 轉成逆時針
        r = r[::-1]
    r = [[round(x, 4), round(y, 4)] for x, y in r]
    if r[0] != r[-1]:
        r.append(r[0])
    return [r]


def _record(res):
    """把 check.check_one 的結果攤平成固定結構。"""
    st = res.get("verdict") or "ERROR"
    q = res.get("查詢") or {}
    code = res.get("代碼") or {}
    g = res.get("幾何") or {}
    info = res.get("現況") or {}
    tk = res.get("重測追蹤")
    bad = res.get("回傳不符")

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "ok": st in ("OK", "RESURVEYED"),
        "status": st,
        "message": res.get("結論", ""),
        "query": {"city": q.get("縣市"), "town": q.get("鄉鎮"),
                  "section": q.get("段"), "landno": q.get("地號")},
        "parcel": {
            "code14": code.get("14碼"),
            "office": code.get("事務所碼"), "sec": code.get("段碼"),
            "city_code": code.get("縣市碼"),
            "city": code.get("縣市"), "town": code.get("鄉鎮"),
            "section": code.get("段名"),
            "landno": C.format_landno(code["地號8碼"]) if code.get("地號8碼") else None,
            "landno8": code.get("地號8碼"),
        } if code else None,
        "geometry": ({"type": "Polygon", "coordinates": _geojson_ring(g["環"])}
                     if g.get("環") else None),
        "crs": "EPSG:3826",
        "map_area": g.get("圖面積"),
        "deviation_pct": g.get("對登面積偏差%"),
        "registry": {
            "area": num(info.get("面積")),
            "zone": info.get("使用分區") or None,
            "land_type": info.get("使用地類別") or None,
            "current_value": info.get("公告現值"),
            "land_value": info.get("公告地價"),
            "reg_date": info.get("登記日期") or None,
            "reg_reason": info.get("登記原因碼") or None,
        } if info else None,
        # 重測改號時，query 的地號與 parcel 的地號**不同**：parcel 是追蹤後的新地號。
        "resurveyed_from": ({"section": q.get("段"), "landno": q.get("地號"),
                             "landno8": code.get("原查詢地號8碼"),
                             "receive_year": tk.get("收件年"),
                             "reason": tk.get("原因碼")} if tk else None),
        # API 模糊比對回了別筆地時，保留被拒絕的內容供除錯（絕不可當成結果）
        "rejected": ({"wanted": bad["要"], "got": bad["得"],
                      "got_address": bad["得地址"]} if bad else None),
        "notes": list(res.get("說明") or []),
        "warnings": list(res.get("warnings") or []),
    }


def query(city, town, section, landnos, version=None, cache_dir=None):
    """查一組地號。回傳固定結構的 dict。

    landnos: 字串或字串陣列，"306" / "306-1" / "03060001" 皆可。
    version: 地籍版次，省略＝自動用最新（建議省略）。

    不產生任何檔案。要 SHP／都計圖請用 check.py 的 CLI。
    """
    if isinstance(landnos, str):
        landnos = [landnos]
    ver = version or moa.newest_version()
    ctx = {"ver": ver, "cache": cache_dir or CFG.cache_dir()}
    recs = []
    for no in landnos:
        try:
            res = check.check_one(city, town, section, no, ctx, quiet=True)
        except Exception as e:
            res = {"查詢": {"縣市": city, "鄉鎮": town, "段": section, "地號": no},
                   "verdict": "ERROR", "結論": "查詢失敗",
                   "說明": [str(e)], "warnings": []}
        recs.append(_record(res))
    return {"schema": SCHEMA, "version": ver, "crs": "EPSG:3826",
            "records": recs,
            "summary": {"total": len(recs),
                        "ok": sum(1 for r in recs if r["ok"]),
                        "failed": sum(1 for r in recs if not r["ok"])}}


def to_geojson(result):
    """把 query() 的結果轉成 GeoJSON FeatureCollection（只含查得到的）。

    座標是 TWD97 TM2／EPSG:3826，**不是**經緯度。GeoJSON 規格預設 WGS84，
    所以有些工具會誤判——匯入時請明確指定 EPSG:3826。
    """
    feats = []
    for r in result["records"]:
        if not r["ok"] or not r["geometry"]:
            continue
        p = r["parcel"] or {}
        reg = r["registry"] or {}
        feats.append({
            "type": "Feature",
            "geometry": r["geometry"],
            "properties": {
                "code14": p.get("code14"), "city": p.get("city"),
                "town": p.get("town"), "section": p.get("section"),
                "landno": p.get("landno"),
                "reg_area": reg.get("area"), "map_area": r.get("map_area"),
                "deviation_pct": r.get("deviation_pct"),
                "zone": reg.get("zone"), "land_type": reg.get("land_type"),
                "current_value": reg.get("current_value"),
                "land_value": reg.get("land_value"),
                "reg_date": reg.get("reg_date"),
                "cadastre_version": result["version"],
                "status": r["status"],
                "resurveyed_from": (r["resurveyed_from"] or {}).get("landno"),
                "source_geom": "MOA cadastre %s" % result["version"],
                "source_attr": "NLSC S09_Ralid getLandInfo",
                "note": "evaluation use only; not boundary survey",
            },
        })
    return {"type": "FeatureCollection",
            "crs": {"type": "name",
                    "properties": {"name": "urn:ogc:def:crs:EPSG::3826"}},
            "features": feats}
