# -*- coding: utf-8 -*-
"""依段代碼+地號批次查「國土功能分區圖公開展示系統」(nluz.nlma.gov.tw) 的權威報部版分區。

輸出欄位:國土功能分區 / 原使用分區 / 原使用地 / 使用地(新編定) + 查詢狀態。
支援中斷續跑(checkpoint):已查過的地號不重查。

用法:
  python nluz_query.py sections --county 臺南市 --town 官田區
  python nluz_query.py query --roster <清冊.xls> --county 臺南市 -o <out.csv>
  python nluz_query.py query --roster <清冊.xls> --county 臺南市 -o <out.csv> --limit 10
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ⚠ 沒帶瀏覽器 User-Agent → ex_data 會回 404
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
BASE = "https://nluz.nlma.gov.tw/ex3smap"
THROTTLE = 5.5          # 平台限制 5 秒;5.5 實測穩定
MAX_RETRY = 2


class NluzClient:
    def __init__(self, county, version="報部版"):
        self.county = county
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})
        q = urllib.parse.urlencode({"CN": county, "version": version})
        self.page_url = f"{BASE}/default.aspx?{q}"
        html = self.s.get(self.page_url, timeout=40, verify=False).text
        m = re.search(r"layerToken\s*=\s*'([^']+)'", html)
        if not m:
            raise RuntimeError(f"取不到 layerToken(縣市名可能錯誤或系統改版):{county}")
        self.token = m.group(1)
        self.headers = {
            "Referer": self.page_url,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

    def post(self, cmd, data=None):
        url = f"{BASE}/ex_data?CMD={cmd}&TOKEN={self.token}"
        r = self.s.post(url, headers=self.headers, data=data or {}, timeout=60, verify=False)
        if r.status_code != 200:
            raise RuntimeError(f"{cmd} HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError:
            raise RuntimeError(f"{cmd} 非 JSON 回應(前200字):{r.text[:200]}")

    def towns(self):
        return [x["town"] for x in self.post("GETTOWNNAME")]

    def sections(self, town):
        """回 {段名: 段代碼},段代碼形如 DF4342。"""
        return {x["section"]: x["sec"] for x in self.post("GETSECNAME", {"VAL1": town})}

    def search_cada(self, sec_code, landno8):
        """單筆查詢。回 (status, attrs|msg)。status: 1=有資料 0=查無 9=限流 -1=其他"""
        d = self.post("SEARCHCADA", {"VAL1": sec_code, "VAL2": landno8})
        st = d.get("STATUS")
        if st == 1:
            feats = d.get("features") or []
            if feats:
                a = dict(feats[0].get("attributes") or {})
                g = feats[0].get("geometry") or {}
                a["_x3857"], a["_y3857"] = g.get("x"), g.get("y")
                return 1, a
            return 0, "STATUS=1 但無 features"
        return (st if st in (0, 9) else -1), d.get("MESSAGE", json.dumps(d, ensure_ascii=False))


def pad_landno(no):
    """地號 → 8 碼(母號4+子號4 零埋)。389-1 → 03890001;389 → 03890000"""
    s = str(no).strip()
    if not s:
        return None
    if "-" in s:
        a, b = s.split("-", 1)
    else:
        a, b = s, "0"
    a = re.sub(r"\D", "", a)
    b = re.sub(r"\D", "", b)
    if not a:
        return None
    return a.zfill(4) + (b or "0").zfill(4)


def norm_secname(name):
    """去掉 [4342] 前綴與空白。"""
    return re.sub(r"^\[\d+\]", "", str(name)).strip()


def sec_digits(name):
    """從 [4342]社子段 取 4342;取不到回 None。"""
    m = re.match(r"^\[(\d+)\]", str(name))
    return m.group(1) if m else None


def read_roster(path):
    """讀清冊,回 list of dict(鄉鎮市區, 地段名稱, 地號)。支援 xls/xlsx/csv。"""
    import pandas as pd
    if str(path).lower().endswith(".csv"):
        df = pd.read_csv(path, dtype=str)
    else:
        df = pd.read_excel(path, dtype=str)
    cols = {c: c for c in df.columns}

    def pick(*cands):
        for c in df.columns:
            for k in cands:
                if k in str(c):
                    return c
        return None

    c_town = pick("鄉鎮市區", "鄉鎮區", "鄉鎮")
    c_sec = pick("地段名稱", "地段", "段名")
    c_no = pick("地號")
    missing = [n for n, c in [("鄉鎮", c_town), ("地段", c_sec), ("地號", c_no)] if not c]
    if missing:
        raise RuntimeError(f"清冊缺欄位:{missing};實際欄位={list(df.columns)}")
    out = []
    for _, r in df.iterrows():
        out.append({"鄉鎮市區": str(r[c_town]).strip(),
                    "地段名稱": str(r[c_sec]).strip(),
                    "地號": str(r[c_no]).strip()})
    return out


def cmd_sections(args):
    cli = NluzClient(args.county)
    if args.town:
        secs = cli.sections(args.town)
        for name, code in sorted(secs.items()):
            print(f"{code}\t{name}")
        print(f"\n共 {len(secs)} 段", file=sys.stderr)
    else:
        for t in cli.towns():
            print(t)


FIELDS = ["鄉鎮市區", "地段名稱", "地號", "段代碼", "地號8碼", "查詢狀態",
          "國土功能分區", "原使用分區", "原使用地", "使用地", "備註"]


def cmd_query(args):
    rows = read_roster(args.roster)
    if args.limit:
        rows = rows[: args.limit]
    print(f"清冊 {len(rows)} 筆", file=sys.stderr)

    # checkpoint:讀既有輸出,已成功的不重查
    done = {}
    if os.path.exists(args.out) and not args.overwrite:
        with open(args.out, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("查詢狀態") in ("有資料", "查無"):
                    done[(r["地段名稱"], r["地號"])] = r
        print(f"checkpoint:已完成 {len(done)} 筆,續跑剩餘", file=sys.stderr)

    cli = NluzClient(args.county)
    sec_cache = {}
    results = []
    todo = [r for r in rows if (r["地段名稱"], r["地號"]) not in done]
    print(f"待查 {len(todo)} 筆,預估 {len(todo)*THROTTLE/60:.1f} 分鐘", file=sys.stderr)

    def flush():
        with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for r in rows:
                k = (r["地段名稱"], r["地號"])
                w.writerow(done.get(k, {"鄉鎮市區": r["鄉鎮市區"], "地段名稱": r["地段名稱"],
                                        "地號": r["地號"], "查詢狀態": "未查"}))

    for i, r in enumerate(todo, 1):
        town, secname_raw, no = r["鄉鎮市區"], r["地段名稱"], r["地號"]
        rec = {"鄉鎮市區": town, "地段名稱": secname_raw, "地號": no,
               "段代碼": "", "地號8碼": "", "查詢狀態": "", "國土功能分區": "",
               "原使用分區": "", "原使用地": "", "使用地": "", "備註": ""}

        # 段代碼:優先用清冊 [4342] 的 4 碼比對,否則用段名
        if town not in sec_cache:
            try:
                sec_cache[town] = cli.sections(town)
            except Exception as e:
                sec_cache[town] = {}
                rec.update(查詢狀態="失敗", 備註=f"取段清單失敗:{e}")
        secs = sec_cache[town]
        code = None
        dig = sec_digits(secname_raw)
        if dig:
            for nm, cd in secs.items():
                if cd.endswith(dig):
                    code = cd
                    break
        if not code:
            code = secs.get(norm_secname(secname_raw))
        no8 = pad_landno(no)
        rec["段代碼"], rec["地號8碼"] = code or "", no8 or ""

        if not code:
            rec.update(查詢狀態="失敗", 備註=f"段名對不到段代碼(平台 {town} 有 {len(secs)} 段)")
        elif not no8:
            rec.update(查詢狀態="失敗", 備註="地號格式無法轉 8 碼")
        else:
            for attempt in range(MAX_RETRY + 1):
                try:
                    st, payload = cli.search_cada(code, no8)
                except Exception as e:
                    st, payload = -1, str(e)
                if st == 9:  # 限流 → 這是唯一允許重試的狀況
                    rec["備註"] = f"限流重試{attempt+1}"
                    time.sleep(THROTTLE * 2)
                    continue
                if st == 1:
                    rec.update(查詢狀態="有資料",
                               國土功能分區=str(payload.get("國土功能分區", "")).strip(),
                               原使用分區=str(payload.get("原使用分區", "")).strip(),
                               原使用地=str(payload.get("原使用地", "")).strip(),
                               使用地=str(payload.get("使用地", "")).strip())
                elif st == 0:
                    rec.update(查詢狀態="查無", 備註=str(payload))
                else:
                    rec.update(查詢狀態="失敗", 備註=str(payload))
                break
            else:
                rec.update(查詢狀態="失敗", 備註="限流重試仍失敗")
            time.sleep(THROTTLE)

        done[(secname_raw, no)] = rec
        results.append(rec)
        if i % 5 == 0 or i == len(todo):
            flush()
            ok = sum(1 for x in done.values() if x.get("查詢狀態") == "有資料")
            print(f"  {i}/{len(todo)}  有資料累計 {ok}", file=sys.stderr, flush=True)

    flush()
    # 摘要
    from collections import Counter
    st_c = Counter(x.get("查詢狀態") for x in done.values())
    zone_c = Counter(x.get("國土功能分區") for x in done.values() if x.get("國土功能分區"))
    print("\n=== 摘要 ===", file=sys.stderr)
    print("狀態:", dict(st_c), file=sys.stderr)
    print("國土功能分區:", dict(zone_c), file=sys.stderr)
    print(f"輸出:{args.out}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="國土功能分區逐筆查詢(nluz.nlma.gov.tw 報部版)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("sections", help="列鄉鎮或某鄉鎮的段名↔段代碼")
    ps.add_argument("--county", required=True)
    ps.add_argument("--town")
    ps.set_defaults(func=cmd_sections)

    pq = sub.add_parser("query", help="依清冊批次查分區")
    pq.add_argument("--roster", required=True, help="清冊 xls/xlsx/csv(需含 鄉鎮市區/地段名稱/地號)")
    pq.add_argument("--county", required=True)
    pq.add_argument("-o", "--out", required=True)
    pq.add_argument("--limit", type=int, help="只查前 N 筆(試跑)")
    pq.add_argument("--overwrite", action="store_true", help="忽略既有輸出重查全部")
    pq.set_defaults(func=cmd_query)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
