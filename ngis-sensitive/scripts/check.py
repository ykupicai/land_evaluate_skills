"""
CLI：查詢座標落在哪些環境敏感地區。

  python check.py --tm2 261302 2519564
  python check.py --lonlat 121.13 24.03
  python check.py --tm2 261302 2519564 --json out.json
  python check.py --list-layers
"""
import argparse
import json
import os
import sys

import geo
import ngis


def _utf8_console():
    """cp950 主控台印中文會直接 crash，先轉 UTF-8。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


CADASTRE = os.path.expanduser('~/.claude/skills/cadastre-check/scripts')


def _parse_no8(s):
    """'56-4' / '0056-0004' / '00560004' -> 8 碼。"""
    s = s.strip()
    if '-' in s:
        a, b = s.split('-', 1)
    else:
        a, b = (s[:-4], s[-4:]) if len(s) == 8 else (s, '0')
    return f'{int(a):04d}{int(b):04d}'


def _run_parcel(a, token):
    """地段地號 -> 界址環 -> 交集分析 -> （可選）出圖。需要 cadastre-check。"""
    if CADASTRE not in sys.path:
        sys.path.insert(0, CADASTRE)
    try:
        import moa
    except ImportError:
        print('需要 cadastre-check skill 才能用 --parcel（找不到 moa 模組）', file=sys.stderr)
        return 4

    if len(a.parcel) < 4:
        print('--parcel 需要至少 4 個參數：縣市 鄉鎮 段 地號…', file=sys.stderr)
        return 6
    city, town, sec = a.parcel[:3]
    nos = a.parcel[3:]

    try:
        import cadlib
    except ImportError:
        cadlib = None

    rings, parcels, reg_total = [], [], 0.0
    for no in nos:
        no8 = _parse_no8(no)
        p = moa.parcel(city, town, sec, no8)
        if not isinstance(p, dict) or 'ring' not in p:
            got = p.get('got_addr') if isinstance(p, dict) else None
            print(f'查無 {city}{town}{sec}{no}'
                  + (f'（API 回傳別筆地「{got}」，已被 14 碼閘門擋下）' if got else ''),
                  file=sys.stderr)
            return 5
        rings.append(p['ring'])
        line = f'{p["地址"]}｜{p["code"]}｜{len(p["ring"])} 頂點'
        if cadlib:
            try:
                info = cadlib.get_land_info(p['段碼'][0], p['段碼'][2:], no8) or {}
                if info.get('面積'):
                    reg_total += float(info['面積'])
                    line += f'｜登記 {info["面積"]} m²'
                    if info.get('使用分區'):
                        line += f'｜{info["使用分區"]}／{info.get("使用地類別","")}'
            except Exception:
                pass
        print(line)
        parcels.append({k: v for k, v in p.items() if k != 'ring'})

    p = {'地址': f'{city}{town}{sec}' + '、'.join(nos) + '地號' if len(nos) > 1
         else parcels[0].get('地址', '')}

    import overlay
    res = overlay.analyze(rings, token=token,
                          levels=('一級', '二級') if a.level == '全部' else (a.level,))
    if len(nos) > 1:
        print(f'\n合併基地：{len(nos)} 筆，圖面積合計 {res["site_area"]:,.2f} m²'
              + (f'｜登記合計 {reg_total:,.2f} m²' if reg_total else ''))
    ring = rings[0] if len(rings) == 1 else None
    print()
    print(overlay.format_report(res))

    if a.map:
        import mapdraw
        spec, seen = [], set()
        for h in res['hits']:
            nm = h['layerName']
            svc = ngis.SERVICES[h['level']]
            key = (svc, nm)
            if key in seen:
                continue
            seen.add(key)
            for lid, lname in ngis.list_layers(token, h['level']):
                if lname == nm:
                    spec.append((svc, [lid], nm))
                    break
        mapdraw.draw(rings, a.map, token=token, layer_spec=spec,
                     basemap=a.basemap, title=f'{p["地址"]} 環境敏感地區套疊',
                     notes=f'基地 {res["site_area"]:,.1f} m²'
                           f'｜重疊 {res["total_overlap_ratio"]*100:.2f}%')
        print(f'\n已輸出套疊圖：{a.map}')

    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump({'parcels': parcels, 'rings_tm2': rings, 'analysis': res},
                      f, ensure_ascii=False, indent=2, default=str)
        print(f'已寫出 {a.json}')
    return 0


def main():
    _utf8_console()
    ap = argparse.ArgumentParser(description='NGIS 環境敏感地區查詢')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--tm2', nargs=2, type=float, metavar=('X', 'Y'),
                   help='TWD97 TM2 座標 (EPSG:3826)')
    g.add_argument('--lonlat', nargs=2, type=float, metavar=('LON', 'LAT'),
                   help='WGS84 經緯度')
    ap.add_argument('--parcel', nargs='+', metavar='縣市 鄉鎮 段 地號…',
                    help='用地段地號查（需 cadastre-check skill）。可給多筆地號合併為單一基地，'
                         '例：--parcel 臺南市 西港區 州海段 214 215 216')
    ap.add_argument('--level', choices=['一級', '二級', '全部'], default='全部')
    ap.add_argument('--json', metavar='PATH', help='輸出 JSON 檔')
    ap.add_argument('--map', metavar='PATH', help='輸出套疊示意圖 PNG（需 --parcel 或環）')
    ap.add_argument('--basemap', choices=['EMAP', 'PHOTO'], default='EMAP')
    ap.add_argument('--list-layers', action='store_true', help='列出所有圖層後結束')
    a = ap.parse_args()

    try:
        token = ngis.fetch_token()
    except Exception as e:
        print(f'取得 token 失敗：{e}', file=sys.stderr)
        return 2

    if a.list_layers:
        for lv in ('一級', '二級'):
            print(f'\n=== {lv}環境敏感地區 ===')
            for lid, name in ngis.list_layers(token, lv):
                print(f'  [{lid:2d}] {name}')
        return 0

    if a.parcel:
        return _run_parcel(a, token)

    if not (a.tm2 or a.lonlat):
        ap.error('需要 --tm2 / --lonlat / --parcel（或用 --list-layers）')

    if a.tm2:
        tm2x, tm2y = a.tm2
        lon, lat = geo.tm2_to_lonlat(tm2x, tm2y)
    else:
        lon, lat = a.lonlat
        tm2x, tm2y = geo.lonlat_to_tm2(lon, lat)
    mx, my = geo.lonlat_to_merc(lon, lat)

    levels = ('一級', '二級') if a.level == '全部' else (a.level,)
    try:
        res = ngis.query_point(token, mx, my, levels=levels)
    except Exception as e:
        print(f'查詢失敗：{e}', file=sys.stderr)
        return 3

    print(f'查詢點  TM2({tm2x:.2f}, {tm2y:.2f})  經緯度({lon:.6f}, {lat:.6f})')
    total = 0
    for lv in levels:
        hits = res.get(lv, [])
        total += len(hits)
        print(f'\n=== {lv}環境敏感地區：{len(hits)} 項 ===')
        if not hits:
            print('  （無）')
        for h in hits:
            print(f'  ● {h["layerName"]}')
            for k, v in h['attributes'].items():
                print(f'      {k}: {v}')
    print(f'\n合計命中 {total} 項')
    print('本結果僅供初步評估參考，正式判定應以主管機關套繪為準。')

    if a.json:
        payload = {
            'query': {'tm2': [tm2x, tm2y], 'lonlat': [lon, lat]},
            'results': res,
            'note': '僅供初步評估參考，非正式套繪結果',
        }
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f'已寫出 {a.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
