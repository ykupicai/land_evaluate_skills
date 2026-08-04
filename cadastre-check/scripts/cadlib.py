# -*- coding: utf-8 -*-
"""
cadlib — 台灣地籍工具函式庫（座標、Shapefile 讀寫、內政部屬性、圖磚）

只依賴標準函式庫；都市計畫圖切片需要 Pillow。
座標系統：TWD97 TM2 (EPSG:3826) <-> WGS84 <-> Web Mercator 圖磚像素。

外部服務皆免費、免帳號：
  * 現況地籍屬性       https://api.nlsc.gov.tw/S09_Ralid/getLandInfo
  * 都市計畫圖 (URBAN) https://wmts.nlsc.gov.tw/wmts/URBAN/...   需 Referer

幾何不在這裡取——界址環走農業部地籍圖資，見 moa.py。原本的圖磚向量化、
ICP 配準與幾何分割（約 1200 行）已隨該管線一併退役。
"""

import base64
import json
import math
import os
import re
import struct
import sys
import urllib.parse
import urllib.request

__all__ = [
    "tm2_forward",
    "tm2_inverse",
    "tile_res",
    "lonlat_to_pixel",
    "lonlat_to_tile",
    "shoelace",
    "centroid",
    "DbfReader",
    "ShpReader",
    "write_shapefile",
    "get_land_info",
    "query_new_old",
    "fetch_tiles",
    "mosaic",
    "parse_landno",
    "format_landno",
    "roc_date",
]

# ────────────────────────────────────────────────────────────────────
#  1. 座標轉換
# ────────────────────────────────────────────────────────────────────
_A = 6378137.0
_F = 1 / 298.257222101
_E2 = _F * (2 - _F)
_EP2 = _E2 / (1 - _E2)
_E1 = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))
_K0 = 0.9999
_FE = 250000.0
_CM = math.radians(121.0)
_ORIG = 20037508.342789244   # Web Mercator 半週長
_R = 6378137.0


def tm2_forward(lon, lat):
    """WGS84 經緯度 -> TWD97 TM2 (EPSG:3826) 公尺。"""
    lo, la = math.radians(lon), math.radians(lat)
    n = _A / math.sqrt(1 - _E2 * math.sin(la) ** 2)
    t = math.tan(la) ** 2
    c = _EP2 * math.cos(la) ** 2
    a = (lo - _CM) * math.cos(la)
    m = _A * ((1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256) * la
              - (3 * _E2 / 8 + 3 * _E2 ** 2 / 32 + 45 * _E2 ** 3 / 1024) * math.sin(2 * la)
              + (15 * _E2 ** 2 / 256 + 45 * _E2 ** 3 / 1024) * math.sin(4 * la)
              - (35 * _E2 ** 3 / 3072) * math.sin(6 * la))
    e = _FE + _K0 * n * (a + (1 - t + c) * a ** 3 / 6
                         + (5 - 18 * t + t * t + 72 * c - 58 * _EP2) * a ** 5 / 120)
    nn = _K0 * (m + n * math.tan(la) * (a * a / 2
                + (5 - t + 9 * c + 4 * c * c) * a ** 4 / 24
                + (61 - 58 * t + t * t + 600 * c - 330 * _EP2) * a ** 6 / 720))
    return e, nn


def tm2_inverse(x, y):
    """TWD97 TM2 公尺 -> WGS84 (lon, lat)。"""
    m = y / _K0
    mu = m / (_A * (1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256))
    p1 = (mu + (3 * _E1 / 2 - 27 * _E1 ** 3 / 32) * math.sin(2 * mu)
          + (21 * _E1 ** 2 / 16 - 55 * _E1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * _E1 ** 3 / 96) * math.sin(6 * mu)
          + (1097 * _E1 ** 4 / 512) * math.sin(8 * mu))
    c1 = _EP2 * math.cos(p1) ** 2
    t1 = math.tan(p1) ** 2
    n1 = _A / math.sqrt(1 - _E2 * math.sin(p1) ** 2)
    r1 = _A * (1 - _E2) / (1 - _E2 * math.sin(p1) ** 2) ** 1.5
    d = (x - _FE) / (n1 * _K0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (
        d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * _EP2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * _EP2 - 3 * c1 * c1) * d ** 6 / 720)
    lon = _CM + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                 + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * _EP2 + 24 * t1 * t1) * d ** 5 / 120) / math.cos(p1)
    return math.degrees(lon), math.degrees(lat)


def tile_res(zoom, tile_size=256):
    return 2 * _ORIG / (tile_size * 2 ** zoom)


def lonlat_to_pixel(lon, lat, zoom, tx0, ty0, tile_size=256):
    """WGS84 -> 以 (tx0, ty0) 為左上角的拼接影像像素座標。"""
    res = tile_res(zoom, tile_size)
    minx = -_ORIG + tx0 * tile_size * res
    maxy = _ORIG - ty0 * tile_size * res
    mx = lon / 180.0 * _ORIG
    my = _R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return (mx - minx) / res, (maxy - my) / res


def lonlat_to_tile(lon, lat, zoom):
    n = 2 ** zoom
    x = (lon + 180) / 360 * n
    r = math.radians(lat)
    y = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n
    return x, y


# ────────────────────────────────────────────────────────────────────
#  2. 幾何工具
# ────────────────────────────────────────────────────────────────────
def shoelace(pts):
    """有號面積；正值為逆時針。

    與 centroid 同樣必須先平移到局部原點。TM2 的 x~2.6e5、y~2.5e6，交叉項
    達 6.5e11，而小宗地的總和只有幾十——雙精度在那個量級的解析度約 1e-4，
    比要求的精度還粗。實測台東市豐橋段 2-3（57.30 m²）人工切割後兩片合計與
    原面積差 6.1e-5 m²，純粹是雜訊，卻超過 1e-6 相對容差而被判定「面積不守恆」，
    使用者畫對的那一刀被整個丟掉。平移後同一組資料的誤差降到 1e-11 量級。
    """
    n = len(pts)
    if n < 3:
        return 0.0
    ox, oy = pts[0]
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += (x1 - ox) * (y2 - oy) - (x2 - ox) * (y1 - oy)
    return s / 2


def centroid(pts):
    # 必須先平移到局部原點再算。TM2 的 x~3e5、y~2.7e6，交叉項 x1*y2 達 8e11，
    # 而整個環的交叉項總和只有 6*面積（小宗地約 50），十位數的抵消會把
    # 中心座標打歪到公尺級——曾實測 8 m² 宗地的中心跑到環外 17 m。
    ox, oy = pts[0]
    pts = [(x - ox, y - oy) for x, y in pts]
    a = shoelace(pts)
    if not a:
        return (ox + sum(p[0] for p in pts) / len(pts),
                oy + sum(p[1] for p in pts) / len(pts))
    cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        cr = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cr
        cy += (y1 + y2) * cr
    return ox + cx / (6 * a), oy + cy / (6 * a)


class DbfReader:
    """最小可用 DBF 讀取器，支援 Big5 / UTF-8。"""

    def __init__(self, path, encoding="big5"):
        self.path = path
        self.encoding = encoding
        self.f = open(path, "rb")
        _, _, _, _, self.nrec, self.hlen, self.rlen = struct.unpack("<BBBBIHH", self.f.read(12))
        self.f.seek(32)
        self.fields = []
        while True:
            b = self.f.read(32)
            if b[0:1] in (b"\r", b""):
                break
            name = b[:11].split(b"\x00")[0].decode(encoding, "replace")
            self.fields.append((name, chr(b[11]), b[16]))
        self.offsets = {}
        pos = 1
        for name, _t, ln in self.fields:
            self.offsets[name] = (pos, ln)
            pos += ln

    def get(self, rec, name):
        if name not in self.offsets:
            return ""
        s, ln = self.offsets[name]
        return rec[s:s + ln].decode(self.encoding, "replace").strip()

    def read_row(self, index):
        self.f.seek(self.hlen + index * self.rlen)
        return self.f.read(self.rlen)

    def row_dict(self, index):
        rec = self.read_row(index)
        return {n: self.get(rec, n) for n, _t, _l in self.fields}

    def iter_rows(self, chunk_rows=4000):
        self.f.seek(self.hlen)
        seen = 0
        while seen < self.nrec:
            buf = self.f.read(self.rlen * chunk_rows)
            if not buf:
                break
            for i in range(0, len(buf) - self.rlen + 1, self.rlen):
                if seen >= self.nrec:
                    break
                yield seen, buf[i:i + self.rlen]
                seen += 1

    def close(self):
        self.f.close()


class ShpReader:
    """以 SHX 索引隨機存取 .shp 的多邊形記錄。"""

    def __init__(self, shp_path):
        self.shp_path = shp_path
        self.shx_path = os.path.splitext(shp_path)[0] + ".shx"

    def read(self, index):
        """回傳 [ring, ...]，每個 ring 為 [(x, y), ...] TWD97。"""
        with open(self.shx_path, "rb") as shx:
            shx.seek(100 + index * 8)
            off, _ln = struct.unpack(">II", shx.read(8))
        with open(self.shp_path, "rb") as shp:
            shp.seek(off * 2)
            _rn, rl = struct.unpack(">II", shp.read(8))
            data = shp.read(rl * 2)
        if len(data) < 44:
            return []
        nparts, npts = struct.unpack("<2I", data[36:44])
        parts = struct.unpack("<%dI" % nparts, data[44:44 + nparts * 4])
        base = 44 + nparts * 4
        pts = [struct.unpack("<2d", data[base + i * 16: base + i * 16 + 16]) for i in range(npts)]
        rings = []
        for i in range(nparts):
            s = parts[i]
            e = parts[i + 1] if i + 1 < nparts else npts
            rings.append(pts[s:e])
        return rings

    def iter_bbox(self, xmin, ymin, xmax, ymax):
        """循序掃描，回傳 bbox 相交的 (row_index, rings)。"""
        with open(self.shp_path, "rb") as f:
            f.seek(24)
            flen = struct.unpack(">I", f.read(4))[0] * 2
            f.seek(100)
            row = 0
            while f.tell() < flen:
                h = f.read(8)
                if len(h) < 8:
                    break
                _rn, rl = struct.unpack(">II", h)
                data = f.read(rl * 2)
                row += 1
                if len(data) < 44:
                    continue
                bx0, by0, bx1, by1 = struct.unpack("<4d", data[4:36])
                if bx1 < xmin or bx0 > xmax or by1 < ymin or by0 > ymax:
                    continue
                nparts, npts = struct.unpack("<2I", data[36:44])
                parts = struct.unpack("<%dI" % nparts, data[44:44 + nparts * 4])
                base = 44 + nparts * 4
                pts = [struct.unpack("<2d", data[base + i * 16: base + i * 16 + 16]) for i in range(npts)]
                rings = []
                for i in range(nparts):
                    s = parts[i]
                    e = parts[i + 1] if i + 1 < nparts else npts
                    rings.append(pts[s:e])
                yield row - 1, rings


def write_shapefile(out_base, features, fields, prj_source=None, encoding="big5"):
    """
    features: [{"ring": [(x,y)...], "attrs": {欄位名: 值}}]
    fields:   [(欄位名, "C"|"N", 長度)]  欄位名以 encoding 編碼後不得超過 10 bytes
    """
    recs = []
    for f in features:
        ring = [tuple(p) for p in f["ring"]]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        # Shapefile 外環須為順時針（shoelace 負值）。政府 2022 原始資料實測
        # 400/400 筆皆為順時針。此處曾寫反成強制逆時針——單環時多數 GIS 會
        # 自行容錯所以看不出來，但含內環（孔）時會被判成外環而破圖。
        if shoelace(ring[:-1]) > 0:
            ring = ring[::-1]
        recs.append({"ring": ring, "attrs": f["attrs"]})

    allpts = [p for r in recs for p in r["ring"]]
    bx = (min(p[0] for p in allpts), min(p[1] for p in allpts),
          max(p[0] for p in allpts), max(p[1] for p in allpts))

    def header(flen16):
        h = struct.pack(">i", 9994) + b"\x00" * 20 + struct.pack(">i", flen16)
        h += struct.pack("<ii", 1000, 5) + struct.pack("<4d", *bx) + struct.pack("<4d", 0, 0, 0, 0)
        return h

    shp = b""
    shx = b""
    off = 50
    for i, r in enumerate(recs):
        ring = r["ring"]
        bb = (min(p[0] for p in ring), min(p[1] for p in ring),
              max(p[0] for p in ring), max(p[1] for p in ring))
        c = struct.pack("<i", 5) + struct.pack("<4d", *bb)
        c += struct.pack("<ii", 1, len(ring)) + struct.pack("<i", 0)
        for x, y in ring:
            c += struct.pack("<2d", x, y)
        cl = len(c) // 2
        shp += struct.pack(">ii", i + 1, cl) + c
        shx += struct.pack(">ii", off, cl)
        off += 4 + cl

    with open(out_base + ".shp", "wb") as fh:
        fh.write(header(50 + len(shp) // 2) + shp)
    with open(out_base + ".shx", "wb") as fh:
        fh.write(header(50 + len(shx) // 2) + shx)

    rlen = 1 + sum(f[2] for f in fields)
    hlen = 32 + 32 * len(fields) + 1
    d = struct.pack("<BBBBIHH", 3, 26, 1, 1, len(recs), hlen, rlen) + b"\x00" * 20
    for name, typ, ln in fields:
        nb = name.encode(encoding, "replace")[:11].ljust(11, b"\x00")
        d += nb + typ.encode() + b"\x00" * 4 + bytes([ln]) + bytes([2 if typ == "N" else 0]) + b"\x00" * 14
    d += b"\x0d"
    for r in recs:
        row = b" "
        for name, typ, ln in fields:
            v = str(r["attrs"].get(name, ""))
            b = v.encode(encoding, "replace")
            row += b[:ln].rjust(ln, b" ") if typ == "N" else b[:ln].ljust(ln, b" ")
        d += row
    d += b"\x1a"
    with open(out_base + ".dbf", "wb") as fh:
        fh.write(d)

    prj = ('PROJCS["TWD_1997_TM_Taiwan",GEOGCS["GCS_TWD_1997",DATUM["D_TWD_1997",'
           'SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],'
           'UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
           'PARAMETER["False_Easting",250000.0],PARAMETER["False_Northing",0.0],'
           'PARAMETER["Central_Meridian",121.0],PARAMETER["Scale_Factor",0.9999],'
           'PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]')
    if prj_source and os.path.exists(prj_source):
        try:
            prj = open(prj_source, "r", encoding="utf-8", errors="replace").read()
        except Exception:
            pass
    with open(out_base + ".prj", "w", encoding="utf-8") as fh:
        fh.write(prj)
    with open(out_base + ".cpg", "w", encoding="ascii") as fh:
        fh.write("Big5" if encoding.lower() in ("big5", "cp950") else "UTF-8")
    return out_base


# ────────────────────────────────────────────────────────────────────
#  4. 2022 底圖索引（sqlite，首次建立後查詢即時）
# ────────────────────────────────────────────────────────────────────


_UA = "Mozilla/5.0 (compatible; cadastre-check/1.0)"
_TIMEOUT = 30


def _http(url, data=None, headers=None, referer=None, method=None, raw=False):
    hdr = {"User-Agent": _UA}
    if referer:
        hdr["Referer"] = referer
    if headers:
        hdr.update(headers)
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            if hdr.get("Content-Type", "").startswith("application/json"):
                body = json.dumps(data).encode("utf-8")
            else:
                body = urllib.parse.urlencode(data).encode("utf-8")
                hdr.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            body = data if isinstance(data, bytes) else str(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=hdr, method=method)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        blob = resp.read()
    return blob if raw else blob.decode("utf-8", "replace")


NLSC_REFERER = "https://maps.nlsc.gov.tw/"


RALID = "https://api.nlsc.gov.tw/S09_Ralid/getLandInfo"


def _b64(s):
    try:
        return base64.b64decode(s).decode("utf-8")
    except Exception:
        return s or ""


NEWOLD = "https://openapi.moi.gov.tw/WEBAPI/LandNewOldQuery/1.0/QueryLandNo"


def query_new_old(items):
    """新舊地號轉換（內政部，免費免驗證）。單次最多 25 筆。

    items: [{"UNIT": 事務所碼2, "SEC": 段碼4, "NO": 地號8碼, "TYPE": "N"|"O"}]
      TYPE=N 舊號查新號；TYPE=O 新號查舊號
    回傳原始 RESPONSE 陣列，後繼地號在每筆的 LANDSNCHANGE。

    這是重測改號後唯一可靠的對照來源。**不要拿農業部模糊比對的結果當後繼地號**
    ——實測四筆重測案，模糊比對給的 671／687／166／23-2 全部不是真後繼，
    正解是 641／1479／1067／179。採信模糊比對會四筆全錯。
    """
    out = []
    for i in range(0, len(items), 25):
        txt = _http(NEWOLD, data=items[i:i + 25],
                    headers={"Content-Type": "application/json"})
        out.extend((json.loads(txt) or {}).get("RESPONSE") or [])
    return out


def get_land_info(city_code, sec, landno8):
    """
    查現況地籍屬性（免費免驗證）。city_code 為單一字母縣市代碼。
    回傳 dict 或 None（查無）。
    """
    try:
        txt = _http(RALID, data={"city": city_code, "sect": sec, "landno": landno8},
                    referer=NLSC_REFERER)
    except Exception:
        return None
    if not txt.strip():
        return None
    try:
        j = json.loads(txt)
    except Exception:
        return None
    r = (j or {}).get("ralid")
    if not r or not r.get("AA49"):
        return None
    return {
        "縣市碼": r.get("AA45"), "鄉鎮碼": r.get("AA46"),
        "段碼": r.get("AA48"), "地號": r.get("AA49"),
        "登記日期": str(r.get("AA05") or ""), "登記原因碼": r.get("AA06"),
        "面積": r.get("AA10"), "使用分區": _b64(r.get("AA11")), "使用地類別": _b64(r.get("AA12")),
        "公告現值": r.get("AA16"), "公告地價": r.get("AA17"),
        "公告現值年月": r.get("AA27"),
    }


DMAPS = "https://landmaps.nlsc.gov.tw/S_Maps/wmts/DMAPS/default/EPSG:3857/{z}/{y}/{x}"
DMAPS_REFERER = "https://easymap.moi.gov.tw/"
# 都市計畫圖。都市計畫區土地在 getLandInfo 的使用分區／使用地類別是空的
# （實測苗栗縣頭份市文化段 1020 即為如此），這一層是唯一能看到分區的來源。
# 與 DMAPS 一樣需要帶 Referer，不帶會拿到 0 bytes。
URBAN = "https://wmts.nlsc.gov.tw/wmts/URBAN/default/EPSG:3857/{z}/{y}/{x}"


URBAN_MAX_ZOOM = 19          # z=20 實測無內容
MAX_ZOOM = 20


def fetch_tiles(zoom, tx0, tx1, ty0, ty1, cache_dir, progress=None,
                url_tpl=DMAPS, referer=DMAPS_REFERER, prefix=""):
    """下載圖磚到 cache_dir，回傳成功張數。DMAPS 與 URBAN 都需要 Referer。

    prefix 用來區隔不同圖層的快取檔名，否則第二個圖層會讀到第一個的圖。"""
    os.makedirs(cache_dir, exist_ok=True)
    ok = 0
    total = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    done = 0
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            fn = os.path.join(cache_dir, "%s%d_%d_%d.png" % (prefix, zoom, tx, ty))
            if not os.path.exists(fn) or os.path.getsize(fn) == 0:
                try:
                    blob = _http(url_tpl.format(z=zoom, y=ty, x=tx), referer=referer, raw=True)
                    if blob:
                        with open(fn, "wb") as fh:
                            fh.write(blob)
                except Exception:
                    pass
            if os.path.exists(fn) and os.path.getsize(fn) > 0:
                ok += 1
            done += 1
            if progress:
                progress(done, total)
    return ok


def mosaic(zoom, tx0, tx1, ty0, ty1, cache_dir, tile_size=256, prefix=""):
    from PIL import Image
    nx, ny = tx1 - tx0 + 1, ty1 - ty0 + 1
    im = Image.new("RGBA", (nx * tile_size, ny * tile_size), (0, 0, 0, 0))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            fn = os.path.join(cache_dir, "%s%d_%d_%d.png" % (prefix, zoom, tx, ty))
            if os.path.exists(fn) and os.path.getsize(fn) > 0:
                try:
                    im.alpha_composite(Image.open(fn).convert("RGBA"),
                                       ((tx - tx0) * tile_size, (ty - ty0) * tile_size))
                except Exception:
                    pass
    return im


# ────────────────────────────────────────────────────────────────────
#  6. 向量化 / 配準 / 分割
# ────────────────────────────────────────────────────────────────────


def parse_landno(text):
    """「306-1」/「306」/「03060001」 -> 8 碼字串。"""
    t = str(text).strip()
    if re.fullmatch(r"\d{8}", t):
        return t
    m = re.fullmatch(r"(\d{1,4})\s*-\s*(\d{1,4})", t)
    if m:
        return "%04d%04d" % (int(m.group(1)), int(m.group(2)))
    m = re.fullmatch(r"(\d{1,4})", t)
    if m:
        return "%04d0000" % int(m.group(1))
    raise ValueError("無法解析地號：%s" % text)


def format_landno(no8):
    """8 碼 -> 「306-1」或「306」。"""
    no8 = str(no8).zfill(8)
    mo, zi = int(no8[:4]), int(no8[4:])
    return "%d-%d" % (mo, zi) if zi else "%d" % mo


def roc_date(d):
    d = str(d or "").strip()
    if len(d) == 7 and d.isdigit():
        return "民國%d年%s月%s日" % (int(d[:3]), d[3:5], d[5:7])
    return d or "--"
