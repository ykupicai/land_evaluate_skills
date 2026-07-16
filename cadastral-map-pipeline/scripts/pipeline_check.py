# -*- coding: utf-8 -*-
"""地籍出圖產線硬閘門:每段交接跑一個子命令,數字不對=非零退出+可行動訊息。
降級模型(Opus/Sonnet)執行產線時,**每道閘門必須通過才准進下一段**;失敗時照訊息處理,
處理不了就停下回報,禁止繞過。

  python pipeline_check.py geometry <shp> --expect N          # ①後:筆數+重複幾何
  python pipeline_check.py join <joined.shp>                  # ②後:join 完整性+trust欄
  python pipeline_check.py sitemap <joined.shp> --sitemap <csv>  # ③前:段+地號全命中
  python pipeline_check.py spatial <joined.shp> --repo <大量圖資轉換工具路徑> [--sample N]
                                                              # ②後(選用,強烈建議):質心點對本機地籍
                                                              # 交叉驗證地號,抓面積join錯接
  python pipeline_check.py sheets <案outputs目錄> --cases N [--themes 使用分區,...]
                                                              # ③後:05清單成功數+檔案存在

exit code: 0=通過, 2=閘門失敗(訊息含原因與處置), 3=輸入錯誤
"""
import argparse
import sys
from pathlib import Path


def fail(msg):
    print("[GATE FAIL] " + msg)
    sys.exit(2)


def ok(msg):
    print("[GATE OK] " + msg)


def cmd_geometry(a):
    import geopandas as gpd
    g = gpd.read_file(a.path)
    n = len(g)
    keys = g.geometry.apply(lambda x: (round(x.area, 3), round(x.centroid.x, 2), round(x.centroid.y, 2)))
    dup = n - keys.nunique()
    if dup > 0:
        fail(f"幾何 {n} 筆中有 {dup} 筆重複(常因重複「加入主題」)。處置:本機以(面積,質心)去重後重驗,"
             f"不必重跑平台:g['__k']=...(見 tcdgis skill「下載後必驗筆數」)")
    if a.expect is not None and n != a.expect:
        fail(f"幾何 {n} 筆 ≠ 平台清單 {a.expect} 筆。處置:回平台核對選取清單筆數/查無清單;"
             f"若差額=查無地號數則屬正常,改 --expect 為實際加入數再驗")
    if g.crs is None:
        print("[warn] 無 CRS(平台 shp 常缺 .prj)——後續一律 set_crs(3826)")
    ok(f"geometry:{n} 筆、無重複" + (f"、符合預期 {a.expect}" if a.expect is not None else ""))


def cmd_join(a):
    import geopandas as gpd
    g = gpd.read_file(a.path)
    n = len(g)
    if "地號" not in g.columns:
        fail("join 輸出缺「地號」欄——area-join 未成功或讀錯檔")
    miss = int(g["地號"].isna().sum())
    if miss:
        fail(f"{miss}/{n} 筆未 join 到屬性。處置:提高 --tol 重跑 area_join(勿超過 1.0),或核對 xls 是否同批匯出")
    for c in ("20251201_4", "20251201_6", "20251201_7"):
        if c not in g.columns:
            fail(f"缺 trust 欄 {c}——area_join 未帶 --trust-fields,重跑加上該旗標")
    # 等面積組會讓 nearest-join 重複配對:同(段,地號) 出現兩次=有 xls 列沒人領(2026-07-16 東石實案)
    segcol = "地段名稱" if "地段名稱" in g.columns else "20251201_3"
    dup = g[g.duplicated([segcol, "地號"], keep=False)]
    if len(dup):
        pairs = dup.groupby([segcol, "地號"]).size()
        fail(f"{len(dup)} 筆重複地號指派(等面積宗地 join 撞號):\n{pairs.to_string()}\n"
             f"處置:對等面積組用平台 CADA 圖徵服務查真實質心改派(登入態下,"
             f"見 shp-xls-area-join skill「等面積宗地」章節),不要用 tol 硬調")
    ok(f"join:{n}/{n} 全數帶屬性,trust 欄齊,地號無重複指派")


def cmd_sitemap(a):
    import geopandas as gpd, csv, re
    sys.path.insert(0, str(Path(a.repo) / "scripts") if a.repo else "")
    try:
        from shp_trust_utils import norm_seg, normalize_landno
    except ImportError:
        def norm_seg(s):
            s = re.sub(r"^\[\w+\]", "", str(s or "").strip())
            return s.replace("小段", "").replace("段", "").replace(" ", "")
        def normalize_landno(s):
            s = str(s or "").strip()
            m = re.match(r"(\d+)(?:-(\d+))?$", s)
            return f"{int(m.group(1))}-{int(m.group(2) or 0)}" if m else s
    keys = set()
    for r in csv.DictReader(open(a.sitemap, encoding="utf-8-sig")):
        keys.add(f"{norm_seg(str(r.get('段','') or '')+str(r.get('小段','') or ''))}|{normalize_landno(r['地號'])}")
    g = gpd.read_file(a.path)
    misses = []
    for _, row in g.iterrows():
        k = f"{norm_seg(str(row['20251201_3']))}|{normalize_landno(str(row['20251201_4']))}"
        if k not in keys:
            misses.append(f"{row['20251201_3']}/{row['20251201_4']}")
    if misses:
        fail(f"{len(misses)} 筆基地在 sitemap 查無(會被歸「未對應」不出圖):{'、'.join(misses[:10])}"
             f"{'…' if len(misses)>10 else ''}。處置:多為段名異體字(台/臺、茄/加)或重測改段名——"
             f"修 sitemap 該列段名對齊平台段名(勿改地號),重驗")
    ok(f"sitemap:{len(g)}/{len(g)} 段+地號全命中")


def cmd_spatial(a):
    """代表點 × 本機縣市地籍(舊快照當驗證基準)交叉驗證地號——抓面積 join 錯接。
    ⚠️ 必須用 representative_point(保證在多邊形內);centroid 在凹形宗地會掉進鄰地
    造成假陽性(2026-07-16 清潔隊 60 抽 5 錯全是此因,join 本身無誤)。"""
    import geopandas as gpd, yaml, re
    repo = Path(a.repo)
    reg = yaml.safe_load((repo / "config" / "county_registry.yaml").read_text(encoding="utf-8"))
    g = gpd.read_file(a.path)
    if g.crs is None:
        g = g.set_crs(3826)
    g["_cty"] = g["20251201_1"].astype(str).str.replace("巿", "市").str.replace("台", "臺")
    if a.sample and a.sample < len(g):
        g = g.sample(a.sample, random_state=1)
    bad, checked, skipped = [], 0, []
    for cty, grp in g.groupby("_cty"):
        cad = reg["counties"].get(cty, {}).get("cadastral")
        if not cad or not (repo / cad).exists():
            skipped.append(cty); continue
        cents = grp.geometry.representative_point()
        bbox = (cents.x.min() - 50, cents.y.min() - 50, cents.x.max() + 50, cents.y.max() + 50)
        ref = gpd.read_file(repo / cad, bbox=bbox)
        if ref.crs is None:
            ref = ref.set_crs(3826)
        si = ref.sindex
        for idx, row in grp.iterrows():
            c = row.geometry.representative_point()
            cand = ref.iloc[list(si.query(c, predicate="within"))] if hasattr(si, "query") else ref[ref.contains(c)]
            checked += 1
            if not len(cand):
                continue  # 舊快照可能無此新宗地,不當錯
            r0 = cand.iloc[0]
            try:
                m, ch = int(str(r0.get("宗地母", "0")) or 0), int(str(r0.get("宗地子", "0")) or 0)
                ref_no = f"{m}-{ch}" if ch else f"{m}"
            except Exception:
                continue
            no = re.match(r"(\d+)(?:-(\d+))?", str(row["20251201_4"]))
            join_no = f"{int(no.group(1))}-{int(no.group(2))}" if no and no.group(2) else (f"{int(no.group(1))}" if no else "?")
            if ref_no != join_no:
                bad.append(f"{row['20251201_3']}{row['20251201_4']} 質心落在舊圖 {ref_no}")
    if skipped:
        print(f"[warn] 無本機地籍可驗的縣市:{'、'.join(skipped)}")
    thresh = max(1, int(checked * 0.02))
    if len(bad) > thresh:
        fail(f"空間交叉驗證 {checked} 筆中 {len(bad)} 筆地號不符(>2%容許,含地籍異動誤差):"
             f"{'; '.join(bad[:8])}…。處置:面積 join 可能錯接——檢查 area_join 模糊列報告、"
             f"縮小 --tol 重跑,或人工核對列出的宗地")
    ok(f"spatial:驗 {checked} 筆,{len(bad)} 筆不符(≤容許值 {thresh},多為地籍異動)")


def cmd_sheets(a):
    import csv
    case = Path(a.path)
    f05 = case / "05_出圖清單_maxmap.csv"
    if not f05.exists():
        f05 = case / "05_出圖清單.csv"
    if not f05.exists():
        fail(f"找不到 05 出圖清單於 {case}")
    rows = list(csv.DictReader(open(f05, encoding="utf-8-sig")))
    st = {}
    for r in rows:
        st[r["狀態"]] = st.get(r["狀態"], 0) + 1
    n_fail = st.get("失敗", 0)
    themes = [t for t in (a.themes.split(",") if a.themes else []) if t]
    if themes and a.cases:
        expect = a.cases * len(themes)
        got = sum(1 for r in rows if r["主題"] in themes and r["狀態"] == "成功")
        if got < expect:
            fail(f"指定主題成功數 {got} < 預期 {expect}(案場{a.cases}×主題{len(themes)})。"
                 f"狀態統計:{st}。處置:對 05 清單失敗列逐筆看備註,--cases= 補跑失敗案場")
    if n_fail:
        fail(f"05 清單有 {n_fail} 筆失敗:{st}。處置:看備註欄原因,--cases= 補跑;WMTS 逾時類重跑即過")
    missing = [r["檔名"] for r in rows if r["狀態"] == "成功" and r["檔名"] and
               not ((case / "圖檔_maxmap" / r["檔名"]).exists() or (case / "圖檔" / r["檔名"]).exists()
                    or any(case.glob(f"出圖成果*/**/{r['檔名']}")) or any(case.glob(f"出圖成果*/**/*{r['主題']}.png")))]
    if missing:
        fail(f"{len(missing)} 筆記成功但找不到圖檔(可能被移動未更新清單):{missing[:5]}…")
    ok(f"sheets:{st},檔案齊全")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("geometry"); p.add_argument("path"); p.add_argument("--expect", type=int)
    p = sub.add_parser("join"); p.add_argument("path")
    p = sub.add_parser("sitemap"); p.add_argument("path"); p.add_argument("--sitemap", required=True); p.add_argument("--repo", default=r"C:\Users\user\Documents\Claude\Projects\大量圖資轉換工具")
    p = sub.add_parser("spatial"); p.add_argument("path"); p.add_argument("--repo", default=r"C:\Users\user\Documents\Claude\Projects\大量圖資轉換工具"); p.add_argument("--sample", type=int, default=0)
    p = sub.add_parser("sheets"); p.add_argument("path"); p.add_argument("--cases", type=int); p.add_argument("--themes", default="")
    a = ap.parse_args()
    {"geometry": cmd_geometry, "join": cmd_join, "sitemap": cmd_sitemap,
     "spatial": cmd_spatial, "sheets": cmd_sheets}[a.cmd](a)


if __name__ == "__main__":
    main()
