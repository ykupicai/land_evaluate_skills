# -*- coding: utf-8 -*-
"""
env-sensitivity-check 對外程式介面。

串接三層：
  1. cadastre-check  -> 取得基地界址環幾何 (EPSG:3826) 與登記資料
  2. eland 應免查範圍 -> 自動查詢 46 項環境敏感項目之應查/免查
  3. TGOS/主管機關圖資 -> 對「應查」項目，若有向量圖資則實際做空間相交判斷

用法：
    import sys
    sys.path.insert(0, r"C:\\Users\\USER\\.claude\\skills\\env-sensitivity-check\\scripts")
    from api import run
    result = run("高雄市", "路竹區", "保安段", ["711-3"])
"""
from __future__ import annotations
import sys
import os
import importlib.util

_THIS_DIR = os.path.dirname(__file__)
sys.path.insert(0, _THIS_DIR)

from eland import ElandSession  # noqa: E402
from tgos_layers import find_layer  # noqa: E402
from overlay import check_intersection  # noqa: E402

SCHEMA = 1

CADASTRE_API_PATH = r"C:\Users\USER\.claude\skills\cadastre-check\scripts\api.py"


def _load_cadastre_api():
    """以獨立模組名稱載入 cadastre-check 的 api.py，避免與本檔（同名 api）互相覆蓋。"""
    if "cadastre_check_api" in sys.modules:
        return sys.modules["cadastre_check_api"]
    cadastre_scripts_dir = os.path.dirname(CADASTRE_API_PATH)
    if cadastre_scripts_dir not in sys.path:
        sys.path.insert(0, cadastre_scripts_dir)
    spec = importlib.util.spec_from_file_location("cadastre_check_api", CADASTRE_API_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cadastre_check_api"] = mod
    spec.loader.exec_module(mod)
    return mod


def run(city: str, town: str, section: str, landnos: list[str], village: str | None = None):
    cadastre_api = _load_cadastre_api()

    cad = cadastre_api.query(city, town, section, landnos)

    ok_records = [r for r in cad["records"] if r["ok"]]
    if not ok_records:
        return {
            "schema": SCHEMA,
            "cadastre": cad,
            "error": "地籍查詢全部失敗，無法取得基地幾何，請先確認地段地號是否正確",
        }

    es = ElandSession()
    eland_res = es.query(city, town, section_name=section, village_name=village)

    findings = []
    for item in eland_res["items"]:
        entry = {
            "level": item["level"],
            "item_no": item["item_no"],
            "question": item["question"],
            "sub_name": item["sub_name"],
            "eland_status": item["status"],
            "authority": item["authority"],
        }
        if item["status"] == "免查":
            entry["action"] = "免查，無需進一步比對"
            entry["overlay"] = None
        elif item["status"] == "無法判定":
            entry["action"] = "eland 判定所需的村里/地段條件不足，建議補齊後重查，或逕洽主管機關"
            entry["overlay"] = None
        else:  # 應查
            layer = find_layer(item["level"], item["item_no"], item["sub_name"])
            if layer is None or layer["kind"] == "none":
                entry["action"] = f"應查，TGOS 查無對應圖資，需逕洽主管機關（{item['authority'] or '見 eland 查復機關欄'}）或至 eland 正式申請"
                entry["overlay"] = None
            elif layer["kind"] == "zone_attribute":
                per_parcel = []
                any_hit = False
                any_unknown = False
                for rec in ok_records:
                    zone = rec["registry"].get("zone")
                    landno = rec["parcel"]["landno"]
                    if zone is None:
                        per_parcel.append({"landno": landno, "zone": None, "matched": None})
                        any_unknown = True
                    else:
                        matched = zone in layer["zone_match"]
                        per_parcel.append({"landno": landno, "zone": zone, "matched": matched})
                        if matched:
                            any_hit = True
                entry["overlay"] = {"layer": layer["name"], "agency": layer["agency"],
                                     "kind": "zone_attribute", "per_parcel": per_parcel}
                zone_label = "／".join(layer["zone_match"])
                if any_hit:
                    entry["action"] = f"應查 → 登記使用分區屬於「{zone_label}」，判定為屬於該項目"
                elif any_unknown:
                    entry["action"] = "應查，基地為都市土地（登記資料無使用分區欄位，此規則僅適用非都市土地），無法用使用分區判斷，請參考都市計畫圖或逕洽地政機關"
                else:
                    entry["action"] = f"應查 → 登記使用分區非「{zone_label}」，初步排除（仍建議正式查復確認）"
            elif layer["kind"] == "vector":
                per_parcel = []
                any_hit = False
                any_error = False
                for rec in ok_records:
                    r = check_intersection(rec["geometry"], layer, county=city, town=town)
                    per_parcel.append({"landno": rec["parcel"]["landno"], **r})
                    if r.get("error"):
                        any_error = True
                    elif r.get("intersects"):
                        any_hit = True
                entry["overlay"] = {"layer": layer["name"], "agency": layer["agency"],
                                     "kind": "vector", "per_parcel": per_parcel}
                if any_error:
                    entry["action"] = "應查，TGOS 圖資套疊時發生錯誤，需人工確認，不可視為已排除"
                elif any_hit:
                    entry["action"] = "應查 → TGOS 圖資套疊判斷：有交集，很可能落入該敏感區"
                else:
                    entry["action"] = "應查 → TGOS 圖資套疊判斷：無交集（初步排除，仍建議正式查復確認）"
            else:  # wms
                entry["overlay"] = {"layer": layer["name"], "agency": layer["agency"],
                                     "kind": "wms", "wms_url": layer["url"]}
                entry["action"] = "應查，TGOS 僅提供 WMS 影像圖資，需人工目視套疊比對（無法自動判斷相交）"
        findings.append(entry)

    summary = {
        "免查": sum(1 for f in findings if f["eland_status"] == "免查"),
        "應查_自動排除": sum(1 for f in findings if f["overlay"] and f["overlay"].get("kind") == "vector"
                          and f["overlay"]["per_parcel"] and not any(p["intersects"] for p in f["overlay"]["per_parcel"])),
        "應查_有交集": sum(1 for f in findings if f["overlay"] and f["overlay"].get("kind") == "vector"
                        and any(p["intersects"] for p in f["overlay"]["per_parcel"])),
        "應查_使用分區判斷_屬於": sum(1 for f in findings if f["overlay"] and f["overlay"].get("kind") == "zone_attribute"
                              and any(p.get("matched") for p in f["overlay"]["per_parcel"])),
        "應查_使用分區判斷_不屬於": sum(1 for f in findings if f["overlay"] and f["overlay"].get("kind") == "zone_attribute"
                               and not any(p.get("matched") for p in f["overlay"]["per_parcel"])
                               and not any(p.get("zone") is None for p in f["overlay"]["per_parcel"])),
        "應查_使用分區無法判斷(都市土地)": sum(1 for f in findings if f["overlay"] and f["overlay"].get("kind") == "zone_attribute"
                                   and any(p.get("zone") is None for p in f["overlay"]["per_parcel"])),
        "應查_需人工WMS比對": sum(1 for f in findings if f["overlay"] and f["overlay"].get("kind") == "wms"),
        "應查_需洽主管機關": sum(1 for f in findings if f["eland_status"] == "應查" and f["overlay"] is None),
        "無法判定": sum(1 for f in findings if f["eland_status"] == "無法判定"),
    }

    return {
        "schema": SCHEMA,
        "cadastre": cad,
        "eland": {"county_code": eland_res["county_code"], "town_code": eland_res["town_code"],
                  "section_matched": eland_res["section_matched"]},
        "findings": findings,
        "summary": summary,
    }
