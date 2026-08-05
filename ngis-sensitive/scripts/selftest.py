"""
回歸測試：兩組已通過真實案件驗證的基準。

  python selftest.py

任何一項數字對不上就代表改壞了。改程式後務必跑過。
基準值來自使用者實際執行過的案子（西港案已由使用者確認完全相符）。
"""
import sys
import time

import geo
import ngis
import overlay

TOL = 0.005          # 面積容差 0.5%
CADASTRE = '~/.claude/skills/cadastre-check/scripts'

CASES = [
    {
        'name': '臺南市龍崎區番社段56-4（山區・功能正確性）',
        'parcel': ('臺南市', '龍崎區', '番社段', '00560004'),
        'site_area': 1515.29,
        'expect': [('2-06山坡地', 1515.29), ('2-01-2地質敏感區-山崩與地滑', 1162.56)],
        'union': 1515.29,
    },
    {
        'name': '臺南市西港區州海段214,215,216（平原・效能壓力）',
        'parcels': [('臺南市', '西港區', '州海段', n)
                    for n in ('02140000', '02150000', '02160000')],
        'site_area': 3243.97,
        'expect': [('2-05淹水潛勢', 1906.49), ('2-05淹水潛勢', 805.25)],
        'union': 2711.74,
        'max_seconds': 30,          # 曾因兩萬多個環卡死 >120s，這裡設上限防退步
    },
    {
        'name': '嘉義縣布袋鎮考試潭段鹿寮小段306（沿海・上游亂碼欄位）',
        'parcel': ('嘉義縣', '布袋鎮', '考試潭段鹿寮小段', '03060000'),
        'site_area': 2507.56,
        'expect': [('2-03嚴重地層下陷地區', 2507.56)],
        'union': 2507.56,
        # 這筆的 COUNTYNAME/TOWNNAME/NAME 在上游就是亂碼，須被 _looks_mojibake 濾掉
        'no_mojibake': True,
    },
    {
        # 168 頂點的大宗地：GET 會因查詢字串過長回 HTTP 404，必須 POST。
        # 也是唯一命中「一級」敏感地區、且含 <0.5% 微小部分重疊的基準。
        'name': '高雄市旗山區北勢段291-100（大宗地・一級敏感・POST 路徑）',
        'parcel': ('高雄市', '旗山區', '北勢段', '02910100'),
        'site_area': 43955.37,
        'expect': [
            ('1-21水庫集水區 (供家用或供公共給水)', 43955.37),
            ('2-06山坡地', 43955.37),
            ('2-20自來水水質水量保護區', 43955.37),
            ('2-01-2地質敏感區-山崩與地滑', 169.48),
            ('2-01-2地質敏感區-山崩與地滑', 141.90),
        ],
        'union': 43955.37,
    },
]


def _rings(case):
    import os
    p = os.path.expanduser(CADASTRE)
    if p not in sys.path:
        sys.path.insert(0, p)
    import moa
    specs = case.get('parcels') or [case['parcel']]
    out = []
    for city, town, sec, no8 in specs:
        r = moa.parcel(city, town, sec, no8)
        if not isinstance(r, dict) or 'ring' not in r:
            raise RuntimeError(f'取環失敗 {city}{town}{sec}{no8} -> {r}')
        out.append(r['ring'])
    return out


def _close(a, b, tol=TOL):
    return abs(a - b) <= max(abs(b) * tol, 0.05)


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    token = ngis.fetch_token()
    print(f'token 取得成功（長度 {len(token)}）\n')
    failed = 0

    for c in CASES:
        print(f'=== {c["name"]} ===')
        t0 = time.time()
        try:
            rings = _rings(c)
            res = overlay.analyze(rings, token=token)
        except Exception as e:
            print(f'  ❌ 執行失敗：{e!r}\n')
            failed += 1
            continue
        dt = time.time() - t0

        ok = True
        if not _close(res['site_area'], c['site_area']):
            print(f'  ❌ 基地面積 {res["site_area"]:,.2f}（預期 {c["site_area"]:,.2f}）')
            ok = False
        else:
            print(f'  ✅ 基地面積 {res["site_area"]:,.2f} m²')

        got = sorted(((h['layerName'], h['overlap_area']) for h in res['hits']),
                     key=lambda x: -x[1])
        exp = sorted(c['expect'], key=lambda x: -x[1])
        if len(got) != len(exp):
            print(f'  ❌ 命中項數 {len(got)}（預期 {len(exp)}）：{[g[0] for g in got]}')
            ok = False
        else:
            for (gn, ga), (en, ea) in zip(got, exp):
                if gn != en or not _close(ga, ea):
                    print(f'  ❌ {gn} {ga:,.2f}（預期 {en} {ea:,.2f}）')
                    ok = False
                else:
                    print(f'  ✅ {gn} {ga:,.2f} m²')

        if not _close(res['total_overlap_area'], c['union']):
            print(f'  ❌ 聯集 {res["total_overlap_area"]:,.2f}（預期 {c["union"]:,.2f}）')
            ok = False
        else:
            print(f'  ✅ 聯集 {res["total_overlap_area"]:,.2f} m²')

        if c.get('no_mojibake'):
            bad = [(h['layerName'], k, v) for h in res['hits']
                   for k, v in h['attributes'].items() if ngis._looks_mojibake(v)]
            if bad:
                print(f'  ❌ 仍有亂碼屬性未濾除：{bad[:3]}')
                ok = False
            else:
                print('  ✅ 上游亂碼屬性已濾除')

        lim = c.get('max_seconds')
        if lim and dt > lim:
            print(f'  ❌ 耗時 {dt:.1f}s 超過上限 {lim}s（效能退步，檢查 clip_bbox 是否失效）')
            ok = False
        else:
            print(f'  ⏱  {dt:.1f}s')

        print('  ' + ('全部通過' if ok else '有項目失敗') + '\n')
        failed += 0 if ok else 1

    print('=' * 50)
    print('全部通過' if failed == 0 else f'{failed} 組失敗')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
