# -*- coding: utf-8 -*-
"""案例回歸測試（需網路）。改動 moa/check 後跑這支，確認行為沒被弄壞。

用 --json-only 取結果，不依賴畫面文字。

  python scripts/regress.py            全部
  python scripts/regress.py -k 豐橋     只跑名稱含「豐橋」的
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "check.py")
# 一定要指定 --out-dir。即使加了 --no-shp，check.py 仍會寫 report_*.json，
# 不指定就會把幾十個測試報告倒進 config.json 設定的正式成果目錄，混在真成果裡。
# （這個坑踩過兩次：舊管線修過一次，重寫 regress 時又漏掉。）
REG_OUT = os.path.join(tempfile.gettempdir(), "cadastre_regress_out")
sys.path.insert(0, HERE)
import config as CFG

CFG.use_utf8_console()

# (縣市, 鄉鎮, 段名, 地號, 預期 verdict, 對登面積偏差上限 %；None = 不檢查)
#
# 幾何精度的期望值是實測值加一點餘裕。農業部圖資是圖解法數化成果，
# 小宗地的偏差本來就大——2-3（21 m²）實測 −3.3%，不是錯誤。
CASES = [
    # 一般都市土地，精度最好
    ("高雄市", "路竹區", "保安段", "711-3", "OK", 1.0),
    # 台北市精華區的畸零子號。這兩筆是圖磚時代怎麼切都切不出來的案子，
    # 曾經耗掉整輪人工對位平台的開發，現在直接拿到真界址。
    ("台北市", "中山區", "長春段二小段", "748", "OK", 1.0),
    ("台北市", "中山區", "長春段二小段", "748-1", "OK", 1.0),
    # 鐵路旁畸零地：1.92 m²、圖磚上寬僅 7 像素，舊管線完全成不了形
    ("臺東縣", "臺東市", "豐橋段", "2-2", "OK", 1.0),
    # 最細的一筆，圖解法誤差最大，釘住「小宗地偏差大是常態」
    ("臺東縣", "臺東市", "豐橋段", "2-3", "OK", 5.0),
    ("臺東縣", "臺東市", "豐橋段", "3-1", "OK", 1.0),
    # 使用者寫「臺東市」而官方是「台東市」——釘住臺／台正規化
    ("臺東縣", "台東市", "豐橋段", "3", "OK", 1.0),
    ("嘉義縣", "布袋鎮", "考試潭段鹿寮小段", "306", "OK", None),
    # ── 重測追蹤：舊地號 -> 內政部新舊對照 -> 新段名 -> 農業部幾何 ──
    # 重測後的地籍是數值法成果，幾何與登記面積吻合到 ±0.00%，比一般圖解法段還準。
    #
    # 段名已消失型（要回舊版次的段清單拿舊段碼才能送對照）
    ("新北市", "林口區", "小南灣段下福小段", "788", "RESURVEYED", 0.1),
    ("宜蘭縣", "大同鄉", "松羅一段", "95-91", "RESURVEYED", 0.1),
    # 段名還在但地號重編型（先被 14 碼閘門擋下，再走對照追回）
    # ★ 絕不可拿閘門攔下的那筆當後繼地號：實測 20-13 的模糊比對給 23-2，
    #   真後繼是溫泉東段 179，四筆重測案的模糊比對結果全部是錯的。
    ("屏東縣", "車城鄉", "四重溪段", "20-13", "RESURVEYED", 0.1),
    ("嘉義縣", "義竹鄉", "龍蛟潭段", "621-149", "RESURVEYED", 0.1),
    ("嘉義縣", "番路鄉", "內甕段", "681-4", "RESURVEYED", 0.1),
    ("嘉義縣", "大林鎮", "北勢段", "115", "RESURVEYED", 0.1),
    # 不存在的地號。預期是 MISMATCH 而不是 NOT_FOUND —— 這支 API 幾乎不會誠實
    # 回查無，實測查 9999 回的是同段 347 地號，靠 14 碼閘門擋下。
    # （這條原本我寫成 NOT_FOUND，是預期值算錯，程式是對的。）
    ("嘉義縣", "布袋鎮", "考試潭段鹿寮小段", "9999", "MISMATCH", None),
    # 離島：段清單完整（馬公市 53 段）但界址環一律回空。這是 NOT_FOUND 分支
    # 唯一的真實案例——本島連隨手查地號 1 都拿得到幾何，離島則全空。
    ("澎湖縣", "馬公市", "馬公段", "1", "NOT_FOUND", None),
]


def run(city, town, sec, no):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, CHECK, "--json-only", "--no-shp",
                        "--out-dir", REG_OUT, city, town, sec, no],
                       capture_output=True, env=env)
    txt = p.stdout.decode("utf-8", "replace")
    try:
        return json.loads(txt)[0]
    except Exception:
        return {"_parse_error": (txt[-300:] or
                                 p.stderr.decode("utf-8", "replace")[-300:])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", help="只跑名稱含此字串的案例")
    a = ap.parse_args()
    cases = [c for c in CASES if not a.k or a.k in "".join(c[:4])]
    print("回歸測試：%d 個案例（需網路）\n" % len(cases))
    print("%-8s %-16s %-8s %-12s %s" % ("鄉鎮", "段", "地號", "verdict", "備註"))
    bad = 0
    for city, town, sec, no, want_v, tol in cases:
        r = run(city, town, sec, no)
        if "_parse_error" in r:
            print("%-8s %-16s %-8s %-12s ✖ %s" % (town, sec, no, "解析失敗",
                                                  r["_parse_error"][:60]))
            bad += 1
            continue
        got = r.get("verdict")
        ok = got == want_v
        note = ""
        # 容差對 OK 與 RESURVEYED 都要檢查。原本只檢查 OK，害 RESURVEYED 那六筆
        # 的 0.1% 容差形同虛設——設了卻不驗，比沒設更糟。
        if ok and tol is not None and got in ("OK", "RESURVEYED"):
            dev = (r.get("幾何") or {}).get("對登面積偏差%")
            if dev is None:
                note = "無登記面積可比"
            elif abs(dev) > tol:
                ok = False
                note = "偏差 %+.2f%% 超過 %.1f%%" % (dev, tol)
            else:
                note = "偏差 %+.2f%%" % dev
        elif got == "MISMATCH":
            m = r.get("回傳不符") or {}
            note = "已擋下（得 %s）" % m.get("得", "?")
        elif got == "ERROR":
            note = (r.get("說明") or [""])[0][:40]
        print("%-8s %-16s %-8s %-12s %s %s"
              % (town, sec, no, got, "✔" if ok else "✖ 應為 " + want_v, note))
        if not ok:
            bad += 1
    print("\n%d/%d 通過" % (len(cases) - bad, len(cases)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
