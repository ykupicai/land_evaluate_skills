# -*- coding: utf-8 -*-
"""路徑設定：快取與輸出目錄。

設定檔 config.json 與本檔同層或上層皆可，兩個鍵都可省略：
  cache_dir   都市計畫圖磚快取，留空 = skill 目錄下的 .cache/
  output_dir  成果輸出位置，留空 = 執行時所在目錄的 cadastre_out/

幾何與屬性都走線上 API，不需要任何本機底圖——原本 2022 地籍底圖的
多來源探索邏輯已隨圖磚管線退役一併移除。
"""

import json
import os
import sys


def use_utf8_console():
    """把主控台與 stdout/stderr 都切成 UTF-8。

    Windows 主控台預設 cp950。只改 Python 這端不夠：
      · 不改  -> 遇到 ✔ ✖ m² 會 UnicodeEncodeError，整支腳本中斷
      · 只改 Python 端 -> 不中斷了，但主控台仍以 cp950 解讀，中文全變亂碼
    兩邊都要改。每個有畫面輸出的進入點都要呼叫一次。
    """
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for name in ("stdout", "stderr"):
        st = getattr(sys, name, None)
        if st is None:
            continue
        if (getattr(st, "encoding", "") or "").lower() in ("utf-8", "utf8"):
            continue
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_NAME = "config.json"

def _config_candidates():
    home = os.path.expanduser("~")
    raw = [
        os.path.join(SKILL_DIR, CONFIG_NAME),
        os.path.join(os.getcwd(), CONFIG_NAME),
        os.path.join(home, ".config", "cadastre-check", CONFIG_NAME),
    ]
    seen, out = set(), []
    for p in raw:                      # 工作目錄可能就是 skill 目錄，去重免得訊息重複
        k = os.path.normcase(os.path.abspath(p))
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def load_config():
    for p in _config_candidates():
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                cfg["__source__"] = p
                return cfg
            except Exception as e:
                print("[warn] 設定檔解析失敗 %s：%s" % (p, e), file=sys.stderr)
    return {}


def cache_dir():
    d = os.environ.get("CADASTRE_CACHE_DIR")
    if not d:
        cfg = load_config()
        d = cfg.get("cache_dir")
    if not d:
        d = os.path.join(SKILL_DIR, ".cache")
    os.makedirs(d, exist_ok=True)
    return d


def output_dir(cli_value=None):
    if cli_value:
        os.makedirs(cli_value, exist_ok=True)
        return os.path.abspath(cli_value)
    cfg = load_config()
    d = cfg.get("output_dir") or os.path.join(os.getcwd(), "cadastre_out")
    os.makedirs(d, exist_ok=True)
    return os.path.abspath(d)
