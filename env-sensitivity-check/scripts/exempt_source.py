# -*- coding: utf-8 -*-
"""環境敏感「應免查範圍」離線初篩來源（2026-08-05 建，取代線上 eland 查詢）。

輸入＝`parse_exempt_pdf.py` 由官方 PDF（『匯出全部項目』）產出的
`config/環敏應免查範圍.json`。給定基地縣市/鄉鎮(/段)，逐項判「應查/免查」，
輸出與線上 eland（eland.py）**相同結構**的 items，讓 api.run 下游套疊邏輯不必改。

為什麼改用 PDF：離線、權威、有版本日期（v4.7、115/07/31）、不受 eland SSL／
快取污染坑影響。使用者定案 2026-08-05：PDF 完全取代線上查詢，每月從平台重下更新。
可攜性：本檔只在給了 json 路徑時啟用；api.run 未拿到路徑仍回退線上 eland。

判定語意（見 parse_exempt_pdf.py 檔頭；已用龍崎案對線上 eland 逐項驗證 77/77 一致）：
  清單列的是「該狀態」的行政區，基地命中 → 該狀態；未命中 → 相反狀態。
  粒度三種並存（縣市／縣市鄉鎮／縣市鄉鎮段），基地任一層級 ∈ 清單即命中。

★ PDF 缺項補充（SUPPLEMENT）：官方「應免查範圍」表**不以行政區表列**的少數項目——
  森林系（國有林/保安林/林業試驗林/大專實驗林）、莫拉克特定區域，以及以使用分區判定的
  森林區/優良農地——PDF 查無。這些一律給「應查」，交第二階段（图资套疊或使用分區判定）決定，
  **絕不因 PDF 未列而靜默判免查**（安全方向：寧可多查一項，不可漏查）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_LEVEL_OUT = {"第一級": "第一級", "第二級": "第二級", "第三級": "海岸管理法"}
# ↑ PDF 第三級（近岸海域/潮間帶/海岸保護區…）＝ tgos_layers 的「海岸管理法」層，
#   輸出時對映，讓 find_layer 的 level 子字串比對接得上。


def _opp(status: str) -> str:
    return "免查" if status == "應查" else "應查"


def _base_keys(county: str, town: str, sections=None):
    """基地的行政區鍵集合：縣市／縣市+鄉鎮／縣市+鄉鎮+段（臺/台變體都放）。"""
    def variants(s):
        out = {s}
        if "臺" in s:
            out.add(s.replace("臺", "台"))
        if "台" in s:
            out.add(s.replace("台", "臺"))
        return out
    keys = set()
    for c in variants(county):
        keys.add(c)
        for t in variants(town or ""):
            if t:
                keys.add(c + t)
                for sec in (sections or []):
                    keys.add(c + t + sec)
    return keys


# PDF 未以行政區表列、須一律應查者（結構性缺項，與 PDF 版本無關）
SUPPLEMENT = [
    {"level": "第一級", "item_no": "23", "sub_name": "國有林事業區"},
    {"level": "第一級", "item_no": "23", "sub_name": "保安林"},
    {"level": "第一級", "item_no": "23", "sub_name": "林業試驗林地"},
    {"level": "第一級", "item_no": "23", "sub_name": "大專院校實驗林地"},
    {"level": "第一級", "item_no": "23", "sub_name": "森林區"},
    {"level": "第一級", "item_no": "26", "sub_name": "優良農地"},
    {"level": "第二級", "item_no": "8",
     "sub_name": "莫拉克颱風災後重建特別條例劃定公告之特定區域"},
]


def load(json_path) -> dict:
    return json.loads(Path(json_path).read_text(encoding="utf-8"))


def query(county: str, town: str, sections=None, json_path=None, data: dict = None):
    """回傳與 eland.py 相同結構的 items（level/item_no/sub_name/question/status/authority）。

    命中判定：基地 base_keys 與該項 regions 有交集 → applies。
    effective_status ＝ applies? item.status : 相反。
    另附 SUPPLEMENT（PDF 缺列項一律應查）。
    """
    if data is None:
        data = load(json_path)
    keys = _base_keys(county, town, sections)
    items = []
    for it in data["items"]:
        applies = any(r in keys for r in it["regions"])
        status = it["status"] if applies else _opp(it["status"])
        items.append({
            "level": _LEVEL_OUT.get(it["level"], it["level"]),
            "item_no": it["item_no"],
            "sub_name": it["name"],
            "question": it["name"],
            "status": status,
            "authority": None,
            "source": "pdf",
            "_applies": applies,
        })
    for sup in SUPPLEMENT:
        items.append({
            "level": sup["level"], "item_no": sup["item_no"],
            "sub_name": sup["sub_name"], "question": sup["sub_name"],
            "status": "應查", "authority": None, "source": "supplement",
            "_applies": None,
        })
    return {
        "version": data.get("version"),
        "source": f"環敏應免查範圍 PDF（{data.get('version')}）＋缺項補充",
        "items": items,
    }
