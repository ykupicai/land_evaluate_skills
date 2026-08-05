# -*- coding: utf-8 -*-
"""政府網站 TLS 相容層——只放寬 `VERIFY_X509_STRICT`，其餘驗證照常。

⚠ 為什麼需要（2026-08-04 實測，不是猜的）：
  多個政府網站的伺服器憑證**缺 Subject Key Identifier 擴充欄位**（RFC 5280 要求），
  而 Python **3.12 起** `ssl.create_default_context()` 預設帶 `VERIFY_X509_STRICT`，
  於是直接擋下來：
      SSLCertVerificationError: certificate verify failed:
      Missing Subject Key Identifier
  本機 Python 3.14 因此整支 skill 跑不起來（skill 原在 3.11 開發，那時還沒這旗標）。
  實測受影響主機：
      eland.nlma.gov.tw        （應免查範圍查詢）
      coastal.nps.gov.tw       （國家公園署海岸圖台，一次接 20+ 項的主力來源）
      gic.wra.gov.tw           （水利署 GIC，SHP 直接下載）
  ⚠ 用 `urllib.request` + 系統憑證存放區時**測起來是通的**，用 `requests`／`urllib3`
    （走 certifi CA bundle）才會失敗——所以「我手動測過可以」不代表 skill 跑得動，
    務必用 requests 復測。

★ 這裡**只清掉 strict 旗標**：CA 憑證鏈驗證與主機名檢查（check_hostname、
  verify_mode=CERT_REQUIRED）全部保留。**絕不可改成 `verify=False`**——那連中間人
  攻擊都擋不住，而我們要解的只是對方憑證少一個非安全關鍵的擴充欄位。
  政府網站把憑證修好後，整個模組可以直接拿掉。
"""
from __future__ import annotations

import ssl

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# 已實測需要放寬的政府主機；新增來源若出現 Missing Subject Key Identifier 就加進來
GOV_HOSTS = (
    "https://eland.nlma.gov.tw",
    "https://coastal.nps.gov.tw",
    "https://gic.wra.gov.tw",
    "https://maps.wra.gov.tw",
    "https://gis.ardswc.gov.tw",
    "https://data.boch.gov.tw",   # 文化部文化資產局 OpenData v2（紀念建築/史蹟）
    "https://www.tgos.tw",        # TGOS 國家空間資料資產（本機環敏 shp 換版下載）
)


class RelaxedStrictAdapter(HTTPAdapter):
    """憑證鏈與主機名照驗，只不要求 RFC 5280 的嚴格擴充欄位。"""

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.load_default_certs()
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def mount_gov_tls(session: requests.Session) -> requests.Session:
    """把相容 adapter 掛到已知政府主機上（其他網域維持 Python 預設的嚴格驗證）。"""
    ad = RelaxedStrictAdapter()
    for h in GOV_HOSTS:
        session.mount(h, ad)
    return session


def gov_session() -> requests.Session:
    """建一個已掛好相容 adapter 的 Session。"""
    return mount_gov_tls(requests.Session())
