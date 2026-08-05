"""
套疊示意圖輸出：底圖 + 環境敏感圖層 + 基地範圍。

底圖走國土測繪中心 WMTS 圖磚，敏感圖層走 NGIS 的 export（Map 能力，
是這台伺服器上唯一沒被封鎖的能力，比 identify 穩）。基地範圍用向量描邊，
所以圖上的紅框是精確的，不受圖磚解析度影響。
"""
import io
import json
import math
import os
import urllib.parse
import urllib.request
import ssl

from PIL import Image, ImageDraw, ImageFont

import geo
import ngis

WMTS = {
    'EMAP': 'https://wmts.nlsc.gov.tw/wmts/EMAP/default/EPSG:3857/{z}/{y}/{x}',
    'PHOTO': 'https://wmts.nlsc.gov.tw/wmts/PHOTO2/default/EPSG:3857/{z}/{y}/{x}',
}
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# 疊圖顏色（RGBA）。與伺服器 export 的配色無關，這是我們自己畫的框線。
SITE_COLOR = (220, 30, 30, 255)

_FONT_CANDIDATES = [
    r'C:\Windows\Fonts\msjh.ttc',      # 微軟正黑體
    r'C:\Windows\Fonts\mingliu.ttc',   # 細明體
    r'C:\Windows\Fonts\simsun.ttc',
]


def _font(size):
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0', 'Referer': ngis.PORTAL})
    return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()


_legend_cache = {}


def legend_swatches(token, service):
    """
    取得伺服器實際符號色票 {layerId: PIL.Image(RGBA)}。

    圖例必須用這個，不能自己配色 —— 否則圖例顏色與圖面不符，
    報告會誤導。色票是 20x20 PNG，山坡地那類斜線填充也能正確呈現。
    """
    key = (token[:8], service)
    if key in _legend_cache:
        return _legend_cache[key]
    import base64
    url = f'{ngis.BASE}/{service}/MapServer/legend?f=json&token={token}'
    d = json.loads(_fetch(url).decode('utf-8', 'replace'))
    out = {}
    for L in d.get('layers', []):
        lg = L.get('legend') or []
        if not lg or not lg[0].get('imageData'):
            continue
        try:
            im = Image.open(io.BytesIO(base64.b64decode(lg[0]['imageData']))).convert('RGBA')
            out[L.get('layerId')] = im
        except Exception:
            pass
    _legend_cache[key] = out
    return out


def _lonlat_to_tilef(lon, lat, z):
    n = 2 ** z
    return ((lon + 180) / 360 * n,
            (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)


def _pick_zoom(pad_m, size_px, max_z=19):
    """挑出讓圖磚解析度略優於輸出解析度的 zoom。"""
    target = (pad_m * 2) / size_px           # 目標每像素公尺
    for z in range(max_z, 5, -1):
        res = 156543.03392804097 / (2 ** z)  # 赤道每像素公尺
        if res * math.cos(math.radians(23)) <= target:
            return z
    return 15


def _basemap(cx, cy, pad, size, kind='EMAP'):
    """依 WebMercator 中心與半徑抓底圖，回傳裁切好的 RGB 影像。"""
    lo0, la0 = geo.merc_to_lonlat(cx - pad, cy + pad)
    lo1, la1 = geo.merc_to_lonlat(cx + pad, cy - pad)
    z = _pick_zoom(pad, size)
    fx0, fy0 = _lonlat_to_tilef(lo0, la0, z)
    fx1, fy1 = _lonlat_to_tilef(lo1, la1, z)
    tx0, ty0, tx1, ty1 = int(fx0), int(fy0), int(fx1), int(fy1)
    W, H = (tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256
    canvas = Image.new('RGB', (W, H), (245, 245, 245))
    tpl = WMTS.get(kind, WMTS['EMAP'])
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            try:
                b = _fetch(tpl.format(z=z, x=tx, y=ty))
                canvas.paste(Image.open(io.BytesIO(b)).convert('RGB'),
                             ((tx - tx0) * 256, (ty - ty0) * 256))
            except Exception:
                pass
    box = (int((fx0 - tx0) * 256), int((fy0 - ty0) * 256),
           int((fx1 - tx0) * 256), int((fy1 - ty0) * 256))
    return canvas.crop(box).resize((size, size), Image.LANCZOS), z


def _layer_png(token, service, layer_ids, cx, cy, pad, size):
    q = {
        'bbox': f'{cx-pad},{cy-pad},{cx+pad},{cy+pad}',
        'bboxSR': '102100', 'imageSR': '102100',
        'size': f'{size},{size}',
        'layers': 'show:' + ','.join(str(i) for i in layer_ids),
        'transparent': 'true', 'format': 'png32', 'f': 'image', 'token': token,
    }
    url = f'{ngis.BASE}/{service}/MapServer/export?' + urllib.parse.urlencode(q)
    return Image.open(io.BytesIO(_fetch(url))).convert('RGBA')


def draw(site_rings_tm2, out_path, token=None, layer_spec=None,
         size=900, margin_ratio=1.8, basemap='EMAP', title=None, notes=None):
    """
    產出套疊示意圖。

    site_rings_tm2 : 基地環（TWD97 TM2）
    layer_spec     : [(service, [layer_id...], 圖例文字)]，None 則只畫底圖+基地
    margin_ratio   : 圖幅相對基地尺寸的倍率，越大看到越多周邊
    """
    token = token or ngis.fetch_token()

    pts_merc = [[geo.tm2_to_merc(x, y) for x, y in r] for r in site_rings_tm2]
    xs = [p[0] for r in pts_merc for p in r]
    ys = [p[1] for r in pts_merc for p in r]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    pad = max(span * margin_ratio / 2, 120.0)

    img, z = _basemap(cx, cy, pad, size, basemap)
    img = img.convert('RGBA')

    for service, ids, _label in (layer_spec or []):
        try:
            img = Image.alpha_composite(img, _layer_png(token, service, ids, cx, cy, pad, size))
        except Exception:
            pass

    # 基地範圍：向量描邊，精確不受圖磚解析度影響
    def to_px(mx, my):
        return ((mx - (cx - pad)) / (2 * pad) * size,
                ((cy + pad) - my) / (2 * pad) * size)

    ov = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for r in pts_merc:
        px = [to_px(x, y) for x, y in r]
        d.polygon(px, fill=(220, 30, 30, 45))
        d.line(px + [px[0]], fill=SITE_COLOR, width=3)
    img = Image.alpha_composite(img, ov).convert('RGB')

    # 圖例色票：一律取伺服器實際符號，不自己配色
    swatches = {}
    for service, ids, _lbl in (layer_spec or []):
        try:
            sw = legend_swatches(token, service)
            for i in ids:
                if i in sw:
                    swatches[(service, i)] = sw[i]
        except Exception:
            pass

    _decorate(img, pad, size, layer_spec, title, notes, swatches)
    img.save(out_path)
    return out_path


def _decorate(img, pad, size, layer_spec, title, notes, swatches=None):
    d = ImageDraw.Draw(img, 'RGBA')
    f_t, f_s, f_n = _font(22), _font(15), _font(13)

    if title:
        d.rectangle([0, 0, size, 38], fill=(255, 255, 255, 225))
        d.text((12, 9), title, fill=(20, 20, 20), font=f_t)

    # 比例尺：取一個好看的整數公尺長度
    mpp = (pad * 2) / size * math.cos(math.radians(23))
    for target in (500, 200, 100, 50, 20, 10):
        bar_px = target / mpp
        if 90 <= bar_px <= size * 0.35:
            break
    x0, y0 = 18, size - 30
    d.rectangle([x0 - 8, y0 - 22, x0 + bar_px + 12, y0 + 14], fill=(255, 255, 255, 215))
    d.line([(x0, y0), (x0 + bar_px, y0)], fill=(0, 0, 0), width=3)
    for xx in (x0, x0 + bar_px):
        d.line([(xx, y0 - 6), (xx, y0 + 6)], fill=(0, 0, 0), width=3)
    d.text((x0, y0 - 20), f'{target} m', fill=(0, 0, 0), font=f_s)

    # 指北針
    nx, ny = size - 38, 62
    d.ellipse([nx - 22, ny - 30, nx + 22, ny + 22], fill=(255, 255, 255, 215))
    d.polygon([(nx, ny - 26), (nx - 8, ny + 8), (nx, ny + 1), (nx + 8, ny + 8)], fill=(30, 30, 30))
    d.text((nx - 6, ny + 6), 'N', fill=(20, 20, 20), font=f_s)

    # 圖例：基地用自訂紅框，敏感圖層一律貼伺服器實際色票
    swatches = swatches or {}
    items = [('基地範圍', None)]
    for service, ids, lbl in (layer_spec or []):
        items.append((lbl, swatches.get((service, ids[0]))))
    if items:
        lh = 24
        w = max(150, 56 + max(len(t) for t, _ in items) * 13)
        y = 48 if title else 12
        d.rectangle([10, y, 10 + w, y + lh * len(items) + 12], fill=(255, 255, 255, 232))
        for i, (lbl, sw) in enumerate(items):
            yy = y + 8 + i * lh
            box = (18, yy + 2, 38, yy + 18)
            if sw is None and i == 0:
                d.rectangle(box, outline=SITE_COLOR, width=3, fill=(220, 30, 30, 45))
            elif sw is not None:
                img.paste(sw.resize((20, 16), Image.NEAREST), (box[0], box[1]), sw.resize((20, 16), Image.NEAREST))
                d.rectangle(box, outline=(120, 120, 120), width=1)
            else:
                d.rectangle(box, outline=(120, 120, 120), width=1, fill=(200, 200, 200, 140))
            d.text((46, yy + 1), lbl, fill=(20, 20, 20), font=f_n)

    foot = '底圖：內政部國土測繪中心｜敏感圖層：內政部國土管理署 NGIS｜僅供初步評估參考'
    if notes:
        foot = notes + '｜' + foot
    d.rectangle([0, size - 17, size, size], fill=(255, 255, 255, 220))
    d.text((8, size - 15), foot, fill=(70, 70, 70), font=_font(11))
