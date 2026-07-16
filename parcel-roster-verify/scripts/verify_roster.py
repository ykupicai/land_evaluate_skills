# -*- coding: utf-8 -*-
"""土地清冊地號健檢工具
batches: 預檢 + 依(縣市/鄉鎮區/段/小段)分批產 JSON(餵 TCDGIS driver)
compare: 清冊 vs TCDGIS 匯出結果表,列缺漏

用法:
  python verify_roster.py batches 清冊.xlsx out.json
  python verify_roster.py compare 清冊.xlsx 多重地籍選取結果表.xls [--subs subs.json]

subs.json(選用): 修正對照 [{"from":[縣市,鄉鎮,段,小段,地號],"to":[縣市,鄉鎮,平台段名,地號]}]
"""
import sys, json, re
import pandas as pd

REQ = ['縣市', '鄉鎮區', '段', '地號']


def load_roster(path):
    df = pd.read_excel(path, header=0)
    miss = [c for c in REQ if c not in df.columns]
    assert not miss, f'清冊缺欄位: {miss}'
    if '小段' not in df.columns:
        df['小段'] = ''
    df['小段'] = df['小段'].fillna('')
    df['地號'] = df['地號'].astype(str).str.strip()
    return df


def precheck(df):
    probs = []
    for i, r in df.iterrows():
        dh = r['地號']
        if not re.fullmatch(r'\d{1,4}(-\d{1,3})?', dh):
            probs.append((i + 2, '地號格式異常', dh))
        if pd.isna(r['段']) or not str(r['段']).strip():
            probs.append((i + 2, '段空白', dh))
    dup = df[df.duplicated(subset=['縣市', '鄉鎮區', '段', '小段', '地號'], keep=False)]
    for i in dup.index:
        probs.append((i + 2, '重複地號(加入時自動去重)', df.loc[i, '地號']))
    return probs


def cmd_batches(roster, out):
    df = load_roster(roster)
    for row, kind, val in precheck(df):
        print(f'  [預檢] excel列{row}: {kind}: {val}')
    batches = []
    for (city, town, sec, ssec), g in df.groupby(['縣市', '鄉鎮區', '段', '小段'], sort=False):
        nums = list(dict.fromkeys(g['地號']))
        batches.append([city, town, sec, ssec, ','.join(nums)])
    json.dump(batches, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n = sum(len(b[4].split(',')) for b in batches)
    print(f'{len(batches)} 段, {n} 筆唯一地號 → {out}')


def cmd_compare(roster, export, subs_path=None):
    df = load_roster(roster)
    ex = pd.read_excel(export)
    ex['段名'] = ex['地段名稱'].astype(str).str.replace(r'^\[\d+\]', '', regex=True)
    got = {(r['縣市名稱'], r['鄉鎮市區'], r['段名'], str(r['地號'])) for _, r in ex.iterrows()}

    subs = {}
    if subs_path:
        for s in json.load(open(subs_path, encoding='utf-8')):
            subs[tuple(s['from'])] = tuple(s['to'])

    expected = {}
    for _, r in df.iterrows():
        key5 = (r['縣市'], r['鄉鎮區'], r['段'], r['小段'], r['地號'])
        if key5 in subs:
            c, t, s, n = subs[key5]
            expected[(c, t, s, n)] = '修正對照'
        else:
            sec = r['段'] + '段' + (r['小段'] + '小段' if r['小段'] else '')
            expected[(r['縣市'], r['鄉鎮區'], sec, r['地號'])] = ''

    missing = []
    for k, note in expected.items():
        if k in got:
            continue
        # 寬鬆比對:同縣市/鄉鎮/地號,段名字首互含(容 [代碼]、小段寫法、異體字以外的差異)
        if any(g[0] == k[0] and g[1] == k[1] and g[3] == k[3]
               and (k[2][:2] in g[2] or g[2][:2] in k[2]) for g in got):
            continue
        missing.append((k, note))

    print(f'清冊唯一 {len(expected)} 筆 / 匯出 {len(ex)} 筆 / 缺漏 {len(missing)} 筆')
    for k, note in missing:
        print('  MISSING:', k, note)
    return missing


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == 'batches':
        cmd_batches(sys.argv[2], sys.argv[3])
    elif cmd == 'compare':
        subs = sys.argv[sys.argv.index('--subs') + 1] if '--subs' in sys.argv else None
        cmd_compare(sys.argv[2], sys.argv[3], subs)
    else:
        print(__doc__)
        sys.exit(1)
