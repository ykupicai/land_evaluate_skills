# -*- coding: utf-8 -*-
"""
自動化查詢「環境敏感地區單一窗口查詢平台」(eland.nlma.gov.tw) 應免查範圍。

以真實瀏覽器行為（session cookie + antiforgery token + 連動下拉選單 JSON API）
模擬送出 /seportal/Web_SEData/QuerySEDataAdmin 表單，解析回傳的 46 項環境敏感
項目應查/免查結果表。
"""
from __future__ import annotations
import re
import requests
from bs4 import BeautifulSoup

from govtls import mount_gov_tls

BASE = "https://eland.nlma.gov.tw/seportal/Web_SEData/QuerySEDataAdmin"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) env-sensitivity-check/1.0"


class ElandSession:
    def __init__(self):
        self.s = mount_gov_tls(requests.Session())   # 見 govtls.py：政府憑證相容
        self.s.headers.update({"User-Agent": UA})
        self.token = None
        self.counties = []  # list of {value, text}
        self._bootstrap()

    def _bootstrap(self):
        r = self.s.get(BASE, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        tok_el = soup.select_one('input[name="__RequestVerificationToken"]')
        if not tok_el:
            raise RuntimeError("無法取得 __RequestVerificationToken，eland 頁面結構可能已變更")
        self.token = tok_el["value"]
        county_select = soup.select_one("#countycode")
        self.counties = [
            {"value": o.get("value"), "text": o.get_text(strip=True)}
            for o in county_select.select("option")
            if o.get("value")
        ]

    def _post_json(self, url, data):
        payload = dict(data)
        payload["__RequestVerificationToken"] = self.token
        r = self.s.post(url, data=payload, timeout=20)
        r.raise_for_status()
        return r.json()

    def find_county_code(self, county_name: str) -> str:
        county_name = county_name.strip().replace("台", "臺")
        for c in self.counties:
            if c["text"] == county_name:
                return c["value"]
        # fallback: substring match
        for c in self.counties:
            if county_name in c["text"] or c["text"] in county_name:
                return c["value"]
        raise ValueError(f"eland 縣市清單中找不到「{county_name}」")

    def get_towns(self, county_code: str):
        return self._post_json(
            "https://eland.nlma.gov.tw/seportal/Web_SEData/TownshipListJson",
            {"county": county_code},
        )

    def find_town_code(self, county_code: str, town_name: str) -> str:
        town_name = town_name.strip().replace("台", "臺")
        towns = self.get_towns(county_code)
        for t in towns:
            if t["text"] == town_name:
                return t["value"]
        for t in towns:
            if town_name in t["text"] or t["text"] in town_name:
                return t["value"]
        raise ValueError(f"eland 鄉鎮市區清單中找不到「{town_name}」（縣市代碼 {county_code}）")

    def get_villages(self, town_code: str):
        return self._post_json(
            "https://eland.nlma.gov.tw/seportal/Web_SEData/VillageListJson",
            {"township": town_code},
        )

    def get_sections(self, town_code: str):
        return self._post_json(
            "https://eland.nlma.gov.tw/seportal/Web_SEData/LandSecListJson",
            {"township": town_code},
        )

    def find_section_code(self, town_code: str, section_name: str) -> str | None:
        """盡力比對地段名稱；找不到就回傳 None（查詢時該欄留空，會導致依地段判定的項目顯示"無法判定"）。"""
        if not section_name:
            return None
        section_name = section_name.strip().replace("台", "臺")
        secs = self.get_sections(town_code)
        for sc in secs:
            if sc["text"] == section_name:
                return sc["value"]
        # normalize: eland 地段常見「OO段」，農業部可能是「OO段OO小段」或反之，取核心字比對
        core = re.sub(r"(小段|段)$", "", section_name)
        candidates = [sc for sc in secs if core and core in sc["text"]]
        if len(candidates) == 1:
            return candidates[0]["value"]
        return None

    def find_village_code(self, town_code: str, village_name: str | None) -> str:
        if not village_name:
            return ""
        villages = self.get_villages(town_code)
        for v in villages:
            if v["text"] == village_name.strip():
                return v["value"]
        return ""

    def query(self, county_name: str, town_name: str, section_name: str | None = None,
              village_name: str | None = None):
        """執行一次應免查範圍查詢，回傳 (查詢用行政區文字, parsed_items)。"""
        county_code = self.find_county_code(county_name)
        town_code = self.find_town_code(county_code, town_name)
        village_code = self.find_village_code(town_code, village_name)
        section_code = self.find_section_code(town_code, section_name) if section_name else None

        form = {
            "countycode": county_code,
            "towncode": town_code,
            "villageid": village_code or "",
            "seccode": section_code or "",
            "__RequestVerificationToken": self.token,
        }
        r = self.s.post(BASE, data=form, timeout=30)
        r.raise_for_status()
        items = parse_result_html(r.text)
        return {
            "county_code": county_code,
            "town_code": town_code,
            "village_code": village_code,
            "section_code": section_code,
            "section_matched": section_code is not None,
            "items": items,
        }


def parse_result_html(html: str):
    """解析查詢結果表格，回傳 list[dict]：status, level, question, sub_name, admin_level, admin_name, authority"""
    soup = BeautifulSoup(html, "lxml")
    tables = soup.select("table")
    target = None
    for t in tables:
        rows = t.select("tr")
        if len(rows) > 20:
            target = t
            break
    if target is None:
        return []

    items = []
    for row in target.select("tr"):
        cells = [c.get_text(strip=True) for c in row.select("td")]
        if len(cells) < 5:
            continue
        status, level, question, admin_level, admin_name = cells[0], cells[1], cells[2], cells[3], cells[4]
        authority = cells[5] if len(cells) > 5 else ""
        if status not in ("應查", "免查", "無法判定"):
            continue
        m = re.match(r"^(\d+(?:-\d+)?)[、.]?\s*(?:\d+-\d+\.)?(.*?)(?:【名稱[:：]\s*(.*?)】)?$", question)
        item_no = m.group(1) if m else ""
        sub_name = m.group(3) if m and m.group(3) else ""
        items.append({
            "status": status,
            "level": level,
            "item_no": item_no,
            "question": question,
            "sub_name": sub_name,
            "admin_level": admin_level,
            "admin_name": admin_name,
            "authority": authority,
        })
    return items
