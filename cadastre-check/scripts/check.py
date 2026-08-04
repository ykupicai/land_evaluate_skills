# -*- coding: utf-8 -*-
"""台灣地籍查詢：地段地號 -> 官方界址環 + 官方屬性 -> SHP。

資料來源分工（兩邊都是免費、免帳號）：
  幾何：農業部地籍圖資（moa.py）——直接回傳界址環，不重建、不比對舊底圖
  屬性：內政部 NLSC S09_Ralid getLandInfo——登記面積、使用分區、公告現值等

面積一律以內政部登記值為準；`圖面積` 欄僅供對照。實測農業部幾何與登記面積
多數差 ±0.5% 以內，最細的 21 m² 宗地 −3.3%——**這份幾何不是界址**，
是評估用途的相對正確形狀。
"""
import argparse
import datetime
import io
import json
import math
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cadlib as C
import config as CFG
import moa

VERDICTS = {
    "OK": "查得到",
    "RESURVEYED": "已重測改號（已追蹤到新地號）",
    "NOT_FOUND": "查無",
    # 這支 API 幾乎總會回「某筆地」而不是誠實地回查無：實測查不存在的
    # 考試潭段鹿寮小段 9999，回的是同段 347 地號。所以「此地號不存在」在
    # 實務上多半是以 MISMATCH 呈現，NOT_FOUND 很少觸發——用語要讓人看得懂。
    "MISMATCH": "查無此地號（API 回傳別筆地，已拒絕）",
    "ERROR": "查詢失敗",
}


def log(msg, quiet=False):
    if not quiet:
        print(msg)


def _fmt_area(x):
    try:
        return "%.2f" % float(x)
    except (TypeError, ValueError):
        return ""


def _track_resurvey(city, town, unit, sec4, no8, ctx, quiet=False):
    """舊地號 -> 內政部新舊對照 -> 新段名 -> 農業部幾何。

    回傳 (p, 追蹤資訊) 或 (None, 原因)。

    ★ 後繼地號一定要走內政部這支，不可拿農業部模糊比對的結果充當——
      實測四筆重測案，模糊比對給的全部不是真後繼（見 cadlib.query_new_old）。
    """
    try:
        rows = C.query_new_old([{"UNIT": unit, "SEC": sec4,
                                 "NO": no8, "TYPE": "N"}])
    except Exception as e:
        return None, "新舊地號對照查詢失敗：%s" % e
    ch = (rows[0].get("LANDSNCHANGE") if rows else None) or []
    if not ch:
        return None, "新舊地號對照無資料（可能未重測，或該筆已滅失）"
    for c in ch:
        nsec, nno = c.get("SEC"), c.get("NO")
        if not nsec or not nno:
            continue
        name = moa.section_name_of(city, town, nsec, ctx["ver"])
        if not name:
            continue
        try:
            p = moa.parcel(city, town, name, nno, ctx["ver"])
        except moa.MoaError:
            continue
        if p and not p.get("mismatch"):
            return p, {"新段碼": nsec, "新地號8碼": nno,
                       "新段名": name, "新地號": C.format_landno(nno),
                       "收件年": c.get("RECEIVEYEAR"), "原因碼": c.get("REASON")}
    return None, ("對照到新地號（%s）但農業部查不到其幾何"
                  % "、".join("%s-%s" % (c.get("SEC"), c.get("NO")) for c in ch[:3]))


def check_one(city, town, section, landno, ctx, quiet=False):
    """查一筆。回傳 res dict。"""
    res = {"查詢": {"縣市": city, "鄉鎮": town, "段": section, "地號": landno},
           "版次": ctx["ver"], "說明": [], "warnings": []}
    no8 = C.parse_landno(landno)
    if not no8:
        res["verdict"] = "ERROR"
        res["結論"] = VERDICTS["ERROR"]
        res["說明"].append("地號格式無法解析：%s" % landno)
        return res
    res["地號8碼"] = no8

    track = None
    try:
        p = moa.parcel(city, town, section, no8, ctx["ver"])
    except moa.MoaError as e:
        # 段名在最新版次查無 -> 多半是整段重測改名。往回找舊版次拿到舊段碼，
        # 就能送新舊地號對照追到後繼地號。
        p = None
        hit = None
        if "查無段" in str(e):
            log("  段名在 %s 已不存在，回舊版次查段碼…" % ctx["ver"], quiet)
            hit = moa.find_section_any_version(city, town, section)
        if not hit:
            res["verdict"] = "ERROR"
            res["結論"] = VERDICTS["ERROR"]
            res["說明"].append(str(e))
            log("  ✖ %s" % e, quiet)
            return res
        oldver, oldcode = hit
        log("  於版次 %s 找到舊段碼 %s，查新舊地號對照…" % (oldver, oldcode), quiet)
        p, track = _track_resurvey(city, town, oldcode[:2], oldcode[2:],
                                   no8, ctx, quiet)
        if p is None:
            res["verdict"] = "ERROR"
            res["結論"] = VERDICTS["ERROR"]
            res["說明"].append("%s；%s" % (e, track))
            log("  ✖ %s" % track, quiet)
            return res
        res["舊段碼"] = oldcode
        res["舊段版次"] = oldver

    if p is None:
        res["verdict"] = "NOT_FOUND"
        res["結論"] = VERDICTS["NOT_FOUND"]
        res["說明"].append("版次 %s 查無此地號。" % ctx["ver"])
        log("  查無此地號（版次 %s）" % ctx["ver"], quiet)
        return res

    if p.get("mismatch"):
        # 這支 API 查不到時會回「最接近」的別筆地，而且會跨縣市。一律拒絕。
        # 但「查不到」常常是因為重測改號，所以先走內政部新舊對照追一次——
        # 注意絕不能拿 p["got"] 當後繼地號，那只是模糊比對的產物，實測四筆全錯。
        bad = {"要": p["want"], "得": p["got"], "得地址": p["got_addr"]}
        log("  回傳不符（得 %s），改查新舊地號對照…" % p["got"], quiet)
        p2, track = _track_resurvey(city, town, p["want"][:2], p["want"][2:6],
                                    no8, ctx, quiet)
        if p2 is None:
            res["verdict"] = "MISMATCH"
            res["結論"] = VERDICTS["MISMATCH"]
            res["回傳不符"] = bad
            res["說明"].append("API 回傳的是別筆地（要 %s，得 %s ＝ %s），已拒絕採用。"
                               % (bad["要"], bad["得"], bad["得地址"]))
            res["說明"].append(str(track))
            res["warnings"].append("此地號在版次 %s 已不存在（重測、分割或段名變更）。"
                                   % ctx["ver"])
            log("  ✖ 已拒絕；%s" % track, quiet)
            return res
        res["回傳不符"] = bad
        p, = (p2,)

    res["verdict"] = "RESURVEYED" if track else "OK"
    res["結論"] = VERDICTS[res["verdict"]]
    if track:
        res["重測追蹤"] = track
        res["說明"].append(
            "原地號已重測改號 -> %s %s（收件 %s 年，原因碼 %s）；以下幾何與屬性均為新地號。"
            % (track["新段名"], track["新地號"],
               track.get("收件年") or "?", track.get("原因碼") or "?"))
        log("  ✔ 追蹤到新地號：%s %s" % (track["新段名"], track["新地號"]), quiet)
    res["幾何"] = {"環": p["ring"], "頂點數": len(p["ring"]),
                   "圖面積": round(abs(C.shoelace(p["ring"])), 4),
                   "中心": p["center"], "環數": p["環數"]}
    code = p["code"]
    # 重測追蹤成功時，往後所有事情（屬性查詢、SHP 欄位）都要用**新**地號，
    # 沿用查詢時輸入的舊地號會查不到屬性——實測四重溪段 20-13 追到溫泉東段 179，
    # 仍拿 00200013 去查 getLandInfo 只會得到「查無屬性」。
    cur_no8 = track["新地號8碼"] if track else no8
    res["代碼"] = {"14碼": code, "事務所碼": p["段碼"][:2], "段碼": p["段碼"][2:],
                   "縣市碼": p["段碼"][0], "段名": p["段名"],
                   "縣市": p["縣市"], "鄉鎮": p["鄉鎮"], "地號8碼": cur_no8}
    if track:
        res["代碼"]["原查詢地號8碼"] = no8
    log("  %s  %s" % (code, p["地址"]), quiet)
    log("  界址環：%d 頂點，圖面積 %.2f m²"
        % (len(p["ring"]), res["幾何"]["圖面積"]), quiet)

    # 屬性走內政部，農業部只給幾何
    try:
        info = C.get_land_info(p["段碼"][0], p["段碼"][2:], cur_no8) or {}
    except Exception as e:
        info = {}
        res["warnings"].append("屬性查詢失敗：%s" % e)
    res["現況"] = info
    if info:
        reg = info.get("面積")
        log("  登記：面積 %s m²，%s／%s，登記 %s"
            % (reg, info.get("使用分區") or "", info.get("使用地類別") or "",
               C.roc_date(info.get("登記日期"))), quiet)
        try:
            r = float(reg)
            d = (res["幾何"]["圖面積"] - r) / r * 100 if r else 0
            res["幾何"]["對登面積偏差%"] = round(d, 2)
            if abs(d) > 5:
                res["warnings"].append(
                    "圖面積與登記面積差 %+.1f%%，小宗地的圖解法數化誤差本就較大；"
                    "面積請以登記值為準。" % d)
        except (TypeError, ValueError):
            pass
    else:
        res["warnings"].append("內政部查無屬性；幾何仍可用，但面積等欄位從缺。")
        log("  ⚠ 內政部查無屬性", quiet)
    return res


# ────────────────────────────────────────────────────────────────
FIELDS = [("段號", "C", 14), ("縣市", "C", 10), ("鄉鎮", "C", 10), ("段", "C", 24),
          ("宗地母", "C", 4), ("宗地子", "C", 4), ("地號", "C", 12),
          ("登面積", "N", 18), ("圖面積", "N", 18),
          ("使分", "C", 20), ("使類", "C", 24),
          ("公告值", "N", 10), ("公告價", "N", 10), ("登日期", "C", 7),
          ("版次", "C", 8), ("幾何源", "C", 40), ("屬性源", "C", 40),
          ("品質", "C", 60)]


def build_shapefile(results, out_dir, stamp, quiet=False):
    """把查得到的每一筆寫成一份 SHP。"""
    qa = {"執行": False, "筆數": 0}
    feats = []
    for r in results:
        # RESURVEYED 也要出圖：幾何與屬性都是追蹤到的新地號，一樣可用
        if r.get("verdict") not in ("OK", "RESURVEYED"):
            continue
        code = r["代碼"]
        g = r["幾何"]
        info = r.get("現況") or {}
        no8 = code["地號8碼"]
        dev = g.get("對登面積偏差%")
        feats.append({"ring": g["環"], "attrs": {
            "段號": code["14碼"], "縣市": code["縣市"], "鄉鎮": code["鄉鎮"],
            "段": code["段名"], "宗地母": no8[:4], "宗地子": no8[4:],
            "地號": C.format_landno(no8),
            "登面積": _fmt_area(info.get("面積")),
            "圖面積": "%.2f" % g["圖面積"],
            "使分": info.get("使用分區", ""), "使類": info.get("使用地類別", ""),
            "公告值": str(info.get("公告現值") or ""),
            "公告價": str(info.get("公告地價") or ""),
            "登日期": info.get("登記日期", ""),
            "版次": r["版次"],
            "幾何源": "農業部地籍圖資 %s" % r["版次"],
            "屬性源": "NLSC S09_Ralid getLandInfo",
            "品質": "評估用途非界址;面積以登面積為準" +
                    (";圖面積偏差%+.1f%%" % dev if dev is not None else ""),
        }})
    if not feats:
        qa["原因"] = "沒有任何查得到的地號"
        return None, qa
    c0 = results[0].get("代碼") or {}
    tag = (C.format_landno(c0.get("地號8碼", "")).replace("-", "_")
           if len(feats) == 1 else "site")
    base = os.path.join(out_dir, "%s%s_%s_%s"
                        % (c0.get("事務所碼", ""), c0.get("段碼", ""), tag, stamp))
    C.write_shapefile(base, feats, FIELDS)
    qa.update({"執行": True, "輸出": base, "筆數": len(feats)})
    return base, qa


def build_urban_crop(items, ctx, out_dir, quiet=False, stamp=""):
    """使用分區為空 -> 多半是都市計畫區土地，抓都計圖切片供人工判讀。

    刻意不做自動判讀：分區以顏色與文字標註表示，判錯的代價太高。
    這一步對整組地號只做一次，不逐筆產圖——多筆基地各產一張會得到好幾張
    內容幾乎相同、而且紅框只有一筆的圖，實測會讓人把單筆的框當成整個基地。
    """
    from PIL import Image, ImageDraw
    qa = {"執行": False}
    parts = [(C.format_landno(r["代碼"]["地號8碼"]), r["幾何"]["環"]) for r in items]
    allpts = [p for _n, ring in parts for p in ring]
    if not allpts:
        qa["原因"] = "無幾何可定位"
        return None, qa
    xs = [p[0] for p in allpts]
    ys = [p[1] for p in allpts]
    pad = 60.0
    win = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    lls = [C.tm2_inverse(x, y) for x, y in
           ((win[0], win[1]), (win[2], win[3]), (win[0], win[3]), (win[2], win[1]))]
    lons = [a[0] for a in lls]
    lats = [a[1] for a in lls]
    zoom = min(C.URBAN_MAX_ZOOM, C.MAX_ZOOM)
    ax0, ay1 = C.lonlat_to_tile(min(lons), min(lats), zoom)
    ax1, ay0 = C.lonlat_to_tile(max(lons), max(lats), zoom)
    tx0, tx1, ty0, ty1 = int(ax0) - 1, int(ax1) + 1, int(ay0) - 1, int(ay1) + 1
    ok = C.fetch_tiles(zoom, tx0, tx1, ty0, ty1, ctx["cache"],
                       url_tpl=C.URBAN, referer="https://www.nlsc.gov.tw/",
                       prefix="urban_")
    if not ok:
        qa["原因"] = "都計圖磚全空（該區可能無都市計畫）"
        return None, qa
    # 一定要壓到白底，不能用 .convert("RGB")：mosaic 回傳的是 RGBA、透明底，
    # convert 會把透明變成**黑色**，整張圖底色全黑、分區色塊幾乎看不出來。
    # （同一個坑第三次了——對位平台的底圖也是這樣壞的。凡是 mosaic 的輸出
    #   要給人看，就先 alpha_composite 到白底。）
    _m = C.mosaic(zoom, tx0, tx1, ty0, ty1, ctx["cache"], prefix="urban_")
    if _m.mode == "RGBA":
        img = Image.new("RGB", _m.size, (255, 255, 255))
        img.paste(_m, mask=_m.split()[3])
    else:
        img = _m.convert("RGB")
    px = []
    for x, y in ((win[0], win[3]), (win[2], win[1])):
        lon, lat = C.tm2_inverse(x, y)
        px.append(C.lonlat_to_pixel(lon, lat, zoom, tx0, ty0))
    x0 = max(0, int(min(p[0] for p in px)))
    y0 = max(0, int(min(p[1] for p in px)))
    x1 = min(img.size[0], int(max(p[0] for p in px)))
    y1 = min(img.size[1], int(max(p[1] for p in px)))
    if x1 - x0 < 4 or y1 - y0 < 4:
        qa["原因"] = "範圍過小"
        return None, qa
    crop = img.crop((x0, y0, x1, y1))
    s = max(1, min(8, int(round(1200.0 / (x1 - x0)))))
    if s > 1:
        crop = crop.resize((crop.size[0] * s, crop.size[1] * s), 0)
    d = ImageDraw.Draw(crop)
    for name, ring in parts:
        pts = []
        for x, y in ring:
            lon, lat = C.tm2_inverse(x, y)
            p = C.lonlat_to_pixel(lon, lat, zoom, tx0, ty0)
            pts.append(((p[0] - x0) * s, (p[1] - y0) * s))
        d.line(pts + [pts[0]], fill=(198, 0, 60), width=max(2, s))
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        d.text((cx, cy), name, fill=(198, 0, 60))
    sfx = ("_" + stamp) if stamp else ""
    code = items[0]["代碼"]
    name = ("%s%s_site_urban%s.png" % (code["事務所碼"], code["段碼"], sfx)
            if len(parts) > 1 else
            "%s%s_%s_urban%s.png" % (code["事務所碼"], code["段碼"],
                                     code["地號8碼"][:4], sfx))
    out = os.path.join(out_dir, name)
    crop.save(out)
    qa.update({"執行": True, "輸出": out, "地號": [n for n, _r in parts],
               "縮放層級": zoom, "圖磚張數": ok})
    return out, qa


def main(argv=None):
    CFG.use_utf8_console()
    ap = argparse.ArgumentParser(description="台灣地籍查詢（農業部幾何＋內政部屬性）")
    ap.add_argument("city", nargs="?", help="縣市，如 高雄市")
    ap.add_argument("town", nargs="?", help="鄉鎮市區，如 路竹區")
    ap.add_argument("section", nargs="?", help="段名，如 保安段")
    ap.add_argument("landno", nargs="*", help="地號，可多筆，如 711-3 711-4")
    ap.add_argument("--out-dir", help="輸出目錄")
    ap.add_argument("--version", help="地籍版次（預設用最新的）")
    ap.add_argument("--no-shp", action="store_true", help="只查詢，不產生 SHP")
    ap.add_argument("--json-only", action="store_true",
                    help="只輸出 JSON（人看的中文鍵格式）")
    ap.add_argument("--api-json", action="store_true",
                    help="只輸出串接用 JSON（ASCII 鍵、結構固定，見 api.py）")
    ap.add_argument("--geojson", action="store_true",
                    help="只輸出 GeoJSON FeatureCollection（EPSG:3826）")
    ap.add_argument("--list-versions", action="store_true", help="列出所有版次後結束")
    ap.add_argument("--list-sections", action="store_true", help="列出該鄉鎮所有段名後結束")
    args = ap.parse_args(argv)
    quiet = args.json_only or args.api_json or args.geojson

    try:
        ver = args.version or moa.newest_version()
    except moa.MoaError as e:
        print("✖ 無法連線農業部地籍服務：%s" % e)
        return 2

    if args.list_versions:
        vs = moa.versions()
        print("共 %d 個版次，最新 %s：" % (len(vs), vs[-1]))
        print("  " + "、".join(vs[-12:]))
        return 0

    if not args.city or not args.town:
        ap.print_help()
        return 1

    if args.list_sections:
        try:
            c, t = args.city, args.town
            cc = moa._pick(moa.counties(), c) or c
            tt = moa._pick(moa.towns(cc), t) or t
            secs = moa.sections(cc, tt, ver)
        except moa.MoaError as e:
            print("✖ %s" % e)
            return 2
        print("%s %s（版次 %s）共 %d 段：" % (cc, tt, ver, len(secs)))
        for name, code in sorted(secs.items(), key=lambda kv: kv[1]):
            print("  %-6s %s" % (code, name))
        return 0

    if not args.section or not args.landno:
        ap.print_help()
        return 1

    out_dir = CFG.output_dir(args.out_dir)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    ctx = {"ver": ver, "cache": CFG.cache_dir()}

    log("地籍版次：%s（%s）" % (ver, "指定" if args.version else "最新"), quiet)
    log("幾何來源：農業部地籍圖資　屬性來源：內政部 NLSC", quiet)

    results = []
    for no in args.landno:
        log("\n" + "─" * 62, quiet)
        log("查詢：%s %s %s %s" % (args.city, args.town, args.section, no), quiet)
        log("─" * 62, quiet)
        try:
            r = check_one(args.city, args.town, args.section, no, ctx, quiet)
        except Exception as e:
            r = {"查詢": {"縣市": args.city, "鄉鎮": args.town,
                          "段": args.section, "地號": no},
                 "verdict": "ERROR", "結論": VERDICTS["ERROR"],
                 "說明": [str(e)], "warnings": [], "traceback": traceback.format_exc()}
            log("  ✖ 查詢失敗：%s" % e, quiet)
        log("\n  結論：【%s】" % r.get("結論", "?"), quiet)
        for s in r.get("說明", []):
            log("    · " + s, quiet)
        for w in r.get("warnings", []):
            log("    ⚠ " + w, quiet)
        results.append(r)

    oks = [r for r in results if r.get("verdict") in ("OK", "RESURVEYED")]

    # 使用分區為空 -> 都市計畫區土地，抓都計圖切片。對整組只做一次。
    urban = [r for r in oks if not str((r.get("現況") or {}).get("使用分區") or "").strip()]
    if urban and not args.no_shp:
        try:
            uo, uq = build_urban_crop(urban, ctx, out_dir, quiet, stamp)
            for r in urban:
                r["都計圖"] = uq
            if uo:
                log("\n  ℹ %d 筆使用分區為空（都市計畫區土地）-> 已輸出都計圖切片 %s"
                    % (len(urban), os.path.basename(uo)), quiet)
            else:
                log("\n  ℹ 使用分區為空，但未取得都計圖：%s" % uq.get("原因", "未知"), quiet)
        except Exception as e:
            log("\n  ✖ 都計圖切片產出失敗：%s" % e, quiet)

    if oks and not args.no_shp:
        try:
            so, sq = build_shapefile(results, out_dir, stamp, quiet)
            for r in oks:
                r["圖層"] = sq
            if so:
                log("\nSHP：%s.shp（%d 筆圖徵）" % (so, sq["筆數"]), quiet)
            else:
                log("\n✖ 未產出 SHP：%s" % sq.get("原因", "未知"), quiet)
        except Exception as e:
            log("\n✖ SHP 產出失敗：%s" % e, quiet)

    n_bad = len(results) - len(oks)
    if n_bad:
        log("\n查詢 %d 筆，成功 %d 筆，未取得 %d 筆。"
            % (len(results), len(oks), n_bad), quiet)

    report = os.path.join(out_dir, "report_%s.json" % stamp)
    with io.open(report, "w", encoding="utf-8") as f:
        f.write(json.dumps(results, ensure_ascii=False, indent=1))

    if args.api_json or args.geojson:
        import api
        payload = {"schema": api.SCHEMA, "version": ver, "crs": "EPSG:3826",
                   "records": [api._record(r) for r in results]}
        payload["summary"] = {
            "total": len(payload["records"]),
            "ok": sum(1 for r in payload["records"] if r["ok"]),
            "failed": sum(1 for r in payload["records"] if not r["ok"])}
        out = api.to_geojson(payload) if args.geojson else payload
        print(json.dumps(out, ensure_ascii=False, indent=1))
    elif args.json_only:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    else:
        log("報告：%s" % report)

    # 離開碼給呼叫端判斷：0 全部查到、1 部分失敗、2 全部失敗
    if not oks:
        return 2
    return 1 if len(oks) < len(results) else 0


if __name__ == "__main__":
    sys.exit(main())
