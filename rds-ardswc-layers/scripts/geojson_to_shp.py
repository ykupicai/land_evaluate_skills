# -*- coding: utf-8 -*-
"""Downloads/rds_<id>.geojson → 依圖層分資料夾的 shp + geojson,部署到目的地。

用法:
  python geojson_to_shp.py --dest "<輸出根目錄>" --map map.csv [--ids 89,91]

map.csv 欄位: id,group,name
  group 留空=不分群組(直接放輸出根目錄下)。可從 references/layer_catalog.csv 挑列改成。
已存在同名 shp 者略過(可安全重跑續補)。
"""
import argparse
import csv
import shutil
import sys
from pathlib import Path

import geopandas as gpd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dest', required=True, help='輸出根目錄(可為 NAS UNC 路徑)')
    ap.add_argument('--map', required=True, help='CSV: id,group,name')
    ap.add_argument('--src', default=str(Path.home() / 'Downloads'), help='geojson 來源目錄')
    ap.add_argument('--ids', default='', help='只處理這些 id(逗號分隔),預設全部')
    a = ap.parse_args()

    src, dest = Path(a.src), Path(a.dest)
    only = {int(x) for x in a.ids.split(',') if x.strip()} if a.ids else None

    rows = []
    with open(a.map, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            lid = int(r['id'])
            if only and lid not in only:
                continue
            name = r['name'].strip().replace('/', '_')
            grp = (r.get('group') or '').strip()
            gj = src / f'rds_{lid}.geojson'
            if not gj.exists():
                rows.append((lid, name, '尚未下載', ''))
                continue
            folder = (dest / grp / name) if grp else (dest / name)
            shp = folder / (name + '.shp')
            if shp.exists():
                rows.append((lid, name, '已存在', ''))
                continue
            folder.mkdir(parents=True, exist_ok=True)
            g = gpd.read_file(gj)
            # shp 的 DBF 欄名上限 10 bytes,中文長欄名會截斷 → 併存 geojson 保全欄名
            g.to_file(shp, encoding='utf-8')
            shutil.copy(gj, folder / (name + '.geojson'))
            rows.append((lid, name, len(g), str(g.geom_type.iloc[0]) if len(g) else ''))

    print(f'{"ID":<5}{"筆數":<10}{"幾何":<14}圖層')
    for lid, name, n, gt in rows:
        print(f'{lid:<5}{str(n):<10}{gt:<14}{name}')
    if any(r[2] == '尚未下載' for r in rows):
        sys.exit(1)   # 有缺漏 → 非零離開,不讓呼叫端誤判全部完成


if __name__ == '__main__':
    main()
