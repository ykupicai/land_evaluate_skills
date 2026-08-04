# -*- coding: utf-8 -*-
"""純邏輯自我測試（不連網、不需外部資料）。

跑法：python scripts/selftest.py
"""
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadlib as C
import config as CFG
import moa

FAILS = []


def check(name, ok, detail=""):
    print("  %s %s%s" % ("✔" if ok else "✖", name, ("  " + detail) if detail else ""))
    if not ok:
        FAILS.append(name)


def t_area():
    print("\n[面積]")
    sq = [(308620.0, 2727900.0), (308630.0, 2727900.0),
          (308630.0, 2727910.0), (308620.0, 2727910.0)]
    check("100 m² 正方形", abs(abs(C.shoelace(sq)) - 100.0) < 1e-6,
          "得 %.6f" % abs(C.shoelace(sq)))
    check("環向不影響面積絕對值",
          abs(abs(C.shoelace(sq)) - abs(C.shoelace(list(reversed(sq))))) < 1e-9)
    # 平移不變性：釘住「shoelace 要先平移到局部原點」。TM2 大座標下雙精度的
    # 面積解析度約 1e-4，未修正前 57 m² 宗地的切割會因 6.1e-5 的雜訊被誤判不守恆。
    tiny = [(261299.237, 2519569.937), (261316.261, 2519559.991),
            (261311.989, 2519556.651), (261302.620, 2519565.219),
            (261302.550, 2519565.310)]
    ox, oy = tiny[0]
    d = abs(abs(C.shoelace(tiny)) -
            abs(C.shoelace([(x - ox, y - oy) for x, y in tiny])))
    check("面積具平移不變性（TM2 大座標下不失真）", d < 1e-9, "差 %.2e m²" % d)


def t_winding():
    print("\n[環向]")
    # cadlib 慣例：shoelace 正值 = 逆時針。ESRI 外環要順時針（負值）。
    # 政府原始圖資實測 400/400 環都是順時針，別憑直覺寫反。
    ccw = [(0, 0), (10, 0), (10, 10), (0, 10)]
    check("正值代表逆時針", C.shoelace(ccw) > 0, "得 %+.1f" % C.shoelace(ccw))
    check("反轉後為順時針（負值）", C.shoelace(ccw[::-1]) < 0)


def t_landno():
    print("\n[地號解析]")
    cases = [("306", "03060000"), ("306-1", "03060001"),
             ("03060001", "03060001"), ("711-3", "07110003")]
    ok = True
    for given, want in cases:
        got = C.parse_landno(given)
        if got != want:
            ok = False
            print("     %s -> %s（應為 %s）" % (given, got, want))
    check("地號轉 8 碼", ok)
    check("8 碼轉顯示格式", C.format_landno("07110003") == "711-3" and
          C.format_landno("03060000") == "306")


def t_coords():
    print("\n[座標轉換往返]")
    worst = 0.0
    for x, y in ((308626.0, 2727906.0), (170000.0, 2540000.0), (250000.0, 2600000.0)):
        lon, lat = C.tm2_inverse(x, y)
        bx, by = C.tm2_forward(lon, lat)
        worst = max(worst, math.hypot(bx - x, by - y))
    check("TM2 <-> WGS84 往返", worst < 1e-3, "最大 %.2e m" % worst)


def t_moa_version_sort():
    print("\n[農業部版次排序]")
    # 版次有兩種寫法：早期 105Q2（季）、之後 114Dec（雙月）。排序要能同時處理，
    # 因為「一律用最新版次」是靠排序決定的，排錯會靜默拿到舊資料。
    vs = ["105Q2", "105Q4", "107Feb", "107Dec", "114Oct", "114Dec", "115Feb", "115Apr"]
    got = sorted(vs, key=moa._ver_key)
    check("季與雙月混排正確", got == vs, "得 %s" % "、".join(got[-3:]))
    check("115Apr 排在 114Dec 之後", moa._ver_key("115Apr") > moa._ver_key("114Dec"))
    check("無法解析的版次不會炸", moa._ver_key("亂寫") == (0, 0))


def t_moa_norm():
    print("\n[臺／台 正規化]")
    # 農業部與內政部的名稱體系不同：實測農業部用「台東市」不是「臺東市」，
    # 且嘉義市底下只有一個「嘉義市」而沒有東區／西區。比對前一定要正規化。
    check("臺=台", moa._norm("臺東縣") == moa._norm("台東縣"))
    check("忽略空白", moa._norm(" 長春段 二小段 ") == moa._norm("長春段二小段"))
    names = ["台東市", "卑南鄉"]
    check("_pick 回官方寫法", moa._pick(names, "臺東市") == "台東市")
    check("_pick 找不到回 None", moa._pick(names, "不存在鄉") is None)


def t_cadlib_intact():
    """cadlib 的內部相依是否完整。

    清理死碼時我把 `_UA` / `_TIMEOUT` 兩個常數刪掉了——它們只被底線開頭的
    私有函式 `_http` 使用，相依分析漏掉了私有函式。後果很陰險：`get_land_info`
    把例外吞成 `return None`，畫面只顯示「內政部查無屬性」，看起來像 API 掛了，
    完全不會指向真正的原因。所以用機器檢查每個公開函式的自由變數都有定義。
    """
    print("\n[cadlib 內部相依]")
    import ast
    import builtins
    import inspect
    src = inspect.getsource(C)
    tree = ast.parse(src)
    top = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            top.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    top.add(t.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                top.add((a.asname or a.name).split(".")[0])
    bi = set(dir(builtins))
    missing = set()
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        local = set(a.arg for a in fn.args.args)
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                local.add(sub.id)
            elif isinstance(sub, ast.ExceptHandler) and sub.name:
                local.add(sub.name)
            elif isinstance(sub, (ast.Import, ast.ImportFrom)):
                for a in sub.names:
                    local.add((a.asname or a.name).split(".")[0])
            elif isinstance(sub, ast.arg):
                local.add(sub.arg)
            elif isinstance(sub, (ast.FunctionDef, ast.ClassDef)) and sub is not fn:
                local.add(sub.name)      # 巢狀 def／class，例如 write_shapefile 裡的 header
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                if sub.id not in local and sub.id not in top and sub.id not in bi:
                    missing.add("%s -> %s" % (fn.name, sub.id))
    if missing:
        for m in sorted(missing):
            print("     %s" % m)
    check("每個函式引用的名稱都有定義", not missing)
    # 直接確認關鍵常數還在——這兩個被刪掉時不會有任何錯誤訊息
    check("_UA / _TIMEOUT 存在",
          hasattr(C, "_UA") and hasattr(C, "_TIMEOUT"))


def t_no_convert_rgb_on_mosaic():
    """禁止對 mosaic 的輸出直接 .convert("RGB")。

    mosaic 回傳 RGBA、透明底。`.convert("RGB")` 會把透明變成**黑色**，
    產出的圖底色全黑、內容幾乎看不出來，而且不會有任何錯誤訊息——只能靠人眼發現。
    這個坑今天犯了三次（對位平台底圖兩次、都計圖切片一次），所以改用機器擋：
    要壓白底就 Image.new + paste(mask=alpha)。
    """
    import re
    print("\n[禁止 mosaic 直接 convert RGB]")
    d = os.path.dirname(os.path.abspath(__file__))
    bad = []
    for fn in ("check.py", "moa.py"):
        p = os.path.join(d, fn)
        if not os.path.exists(p):
            continue
        for i, line in enumerate(io.open(p, encoding="utf-8").read().split("\n"), 1):
            if re.search(r'mosaic\([^)]*\)\s*\.convert\(\s*["\']RGB["\']\s*\)', line):
                bad.append("%s:%d" % (fn, i))
    if bad:
        for b in bad:
            print("     %s" % b)
    check("沒有 mosaic(...).convert('RGB') 的寫法", not bad)


def t_api_contract():
    """串接契約：鍵名全 ASCII、結構不隨結論變動、GeoJSON 環向符合 RFC 7946。

    這些是外部專案會直接依賴的東西，改壞了對方會在自己那邊炸，而且不容易
    追回是這裡的問題，所以用機器釘住。
    """
    import api
    print("\n[串接契約]")
    # 用假的 res 走 _record，不連網
    fake_ok = {"查詢": {"縣市": "高雄市", "鄉鎮": "路竹區", "段": "保安段", "地號": "711-3"},
               "verdict": "OK", "結論": "查得到",
               "幾何": {"環": [(0, 0), (10, 0), (10, 10)], "圖面積": 50.0},
               "代碼": {"14碼": "EJ282007110003", "事務所碼": "EJ", "段碼": "2820",
                        "縣市碼": "E", "段名": "保安段", "縣市": "高雄市",
                        "鄉鎮": "路竹區", "地號8碼": "07110003"},
               "現況": {"面積": 49.9}, "說明": [], "warnings": []}
    fake_bad = {"查詢": {"縣市": "X", "鄉鎮": "Y", "段": "Z", "地號": "1"},
                "verdict": "ERROR", "結論": "查詢失敗", "說明": ["x"], "warnings": []}
    a, b = api._record(fake_ok), api._record(fake_bad)
    check("成功與失敗的鍵完全相同", set(a.keys()) == set(b.keys()),
          "差異 %s" % (set(a) ^ set(b) or "無"))

    def all_keys(o, out):
        if isinstance(o, dict):
            for k, v in o.items():
                out.add(k)
                all_keys(v, out)
        elif isinstance(o, list):
            for v in o:
                all_keys(v, out)
    ks = set()
    all_keys(a, ks)
    bad = [k for k in ks if any(ord(c) > 127 for c in k)]
    check("鍵名全為 ASCII", not bad, "非 ASCII：%s" % (bad or "無"))
    check("status 在列舉值內", a["status"] in api.STATUSES and b["status"] in api.STATUSES)
    check("失敗時 ok=False 且 geometry=None",
          b["ok"] is False and b["geometry"] is None)
    # GeoJSON 外環須逆時針（RFC 7946），與 Shapefile 的順時針相反
    cw = [(0, 0), (0, 10), (10, 10), (10, 0)]          # 順時針
    ring = api._geojson_ring(cw)[0]
    s = 0.0
    for i in range(len(ring) - 1):
        s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    check("GeoJSON 外環轉為逆時針", s > 0, "shoelace %+.1f" % (s / 2))
    check("GeoJSON 環首尾閉合", ring[0] == ring[-1])


def main():
    print("cadastre-check 自我測試（不連網）")
    t_cadlib_intact()
    t_no_convert_rgb_on_mosaic()
    t_api_contract()
    t_area()
    t_winding()
    t_landno()
    t_coords()
    t_moa_version_sort()
    t_moa_norm()
    print("\n%s" % ("全部通過" if not FAILS
                    else "失敗 %d 項：%s" % (len(FAILS), "、".join(FAILS))))
    return 1 if FAILS else 0


if __name__ == "__main__":
    CFG.use_utf8_console()
    sys.exit(main())
