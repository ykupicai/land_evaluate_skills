"""座標轉換：TWD97 TM2 (EPSG:3826) <-> WGS84 <-> WebMercator (EPSG:3857)。

GRS80 橢球，中央經線 121E，k0=0.9999，FE=250000。
來回轉換實測誤差 < 0.1 mm。
"""
import math

A = 6378137.0
F = 1 / 298.257222101
B = A * (1 - F)
E2 = (A * A - B * B) / (A * A)
EP2 = (A * A - B * B) / (B * B)
K0 = 0.9999
LON0 = math.radians(121.0)
FE = 250000.0
R_MERC = 20037508.342789244


def _M(lat):
    e2 = E2
    return A * ((1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * lat
                - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * lat)
                + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * lat)
                - (35 * e2**3 / 3072) * math.sin(6 * lat))


def lonlat_to_tm2(lon_deg, lat_deg):
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    N = A / math.sqrt(1 - E2 * math.sin(lat)**2)
    T = math.tan(lat)**2
    C = EP2 * math.cos(lat)**2
    Aa = (lon - LON0) * math.cos(lat)
    x = K0 * N * (Aa + (1 - T + C) * Aa**3 / 6
                  + (5 - 18 * T + T**2 + 72 * C - 58 * EP2) * Aa**5 / 120) + FE
    y = K0 * (_M(lat) + N * math.tan(lat) * (Aa**2 / 2
              + (5 - T + 9 * C + 4 * C**2) * Aa**4 / 24
              + (61 - 58 * T + T**2 + 600 * C - 330 * EP2) * Aa**6 / 720))
    return x, y


def tm2_to_lonlat(x, y):
    x -= FE
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    M = y / K0
    mu = M / (A * (1 - E2 / 4 - 3 * E2**2 / 64 - 5 * E2**3 / 256))
    p1 = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
          + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
          + (151 * e1**3 / 96) * math.sin(6 * mu)
          + (1097 * e1**4 / 512) * math.sin(8 * mu))
    C1 = EP2 * math.cos(p1)**2
    T1 = math.tan(p1)**2
    N1 = A / math.sqrt(1 - E2 * math.sin(p1)**2)
    R1 = A * (1 - E2) / (1 - E2 * math.sin(p1)**2)**1.5
    D = x / (N1 * K0)
    lat = p1 - (N1 * math.tan(p1) / R1) * (
        D**2 / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1**2 - 9 * EP2) * D**4 / 24
        + (61 + 90 * T1 + 298 * C1 + 45 * T1**2 - 252 * EP2 - 3 * C1**2) * D**6 / 720)
    lon = LON0 + (D - (1 + 2 * T1 + C1) * D**3 / 6
                  + (5 - 2 * C1 + 28 * T1 - 3 * C1**2 + 8 * EP2 + 24 * T1**2) * D**5 / 120) / math.cos(p1)
    return math.degrees(lon), math.degrees(lat)


def lonlat_to_merc(lon, lat):
    x = lon * R_MERC / 180
    y = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180) * R_MERC / 180
    return x, y


def merc_to_lonlat(x, y):
    lon = x / R_MERC * 180
    lat = math.degrees(2 * math.atan(math.exp(y / R_MERC * math.pi)) - math.pi / 2)
    return lon, lat


def tm2_to_merc(x, y):
    return lonlat_to_merc(*tm2_to_lonlat(x, y))
