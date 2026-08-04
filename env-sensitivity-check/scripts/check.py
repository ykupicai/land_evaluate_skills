# -*- coding: utf-8 -*-
"""
CLI: python check.py <縣市> <鄉鎮市區> <地段> <地號...> [--out-dir DIR] [--village 村里]

輸出：
  env_report_<時間戳>.md    法令分析報告
  env_result_<時間戳>.json  完整結構化結果
  env_map_<時間戳>.png      套疊示意圖
"""
import sys
import os
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from api import run  # noqa: E402
import report  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("city")
    p.add_argument("town")
    p.add_argument("section")
    p.add_argument("landnos", nargs="+")
    p.add_argument("--village", default=None)
    p.add_argument("--out-dir", default=None)
    args = p.parse_args()

    out_dir = args.out_dir or os.path.join(os.getcwd(), "env_check_out")
    os.makedirs(out_dir, exist_ok=True)

    result = run(args.city, args.town, args.section, args.landnos, village=args.village)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(out_dir, f"env_result_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    if result.get("error"):
        print("查詢失敗：", result["error"])
        sys.exit(2)

    md = report.to_markdown(result)
    md_path = os.path.join(out_dir, f"env_report_{ts}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    map_path = os.path.join(out_dir, f"env_map_{ts}.png")
    try:
        report.draw_map(result, map_path)
    except Exception as e:
        print("繪圖失敗（不影響報告本身）：", e)
        map_path = None

    print("完成：")
    print(" -", json_path)
    print(" -", md_path)
    if map_path:
        print(" -", map_path)


if __name__ == "__main__":
    main()
