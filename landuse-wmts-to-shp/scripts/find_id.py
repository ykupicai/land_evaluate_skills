# -*- coding: utf-8 -*-
r"""
查行政區代碼：把(可能含中文的)行政區界 SHP 列出/搜尋，找出可用於 run.py --filter-value 的 ASCII 代碼。

縣市/鄉鎮界的 DBF 常無 .cpg、用 UTF-8 或 Big5 存中文，直接拿中文做 ogr2ogr -where 容易出錯；
因此先用本工具把「中文名稱」對應到 ASCII 的 townid / COUNTYID，再餵給 run.py。

用法:
  # 列出某 SHP 全部行政區 (自動偵測欄位)
  env.bat python scripts\find_id.py --shp "<鄉鎮SHP>"
  # 依關鍵字搜尋 (縣市名或鄉鎮名，支援中文)
  env.bat python scripts\find_id.py --shp "<鄉鎮SHP>" --query 嘉義
"""
import argparse, struct, sys
sys.stdout.reconfigure(encoding="utf-8")

def read_dbf(dbf):
    f=open(dbf,"rb"); h=f.read(32)
    numrec=struct.unpack("<I",h[4:8])[0]; hsize=struct.unpack("<H",h[8:10])[0]
    recsize=struct.unpack("<H",h[10:12])[0]
    fields=[]
    while True:
        fd=f.read(32)
        if fd[0:1]==b"\r": break
        fields.append((fd[0:11].split(b"\x00")[0].decode("ascii","replace"),fd[16]))
    def dec(b):
        for enc in ("utf-8","big5"):
            try: return b.decode(enc).strip()
            except: pass
        return b.decode("latin1").strip()
    f.seek(hsize); rows=[]
    for _ in range(numrec):
        rec=f.read(recsize); off=1; row={}
        for n,l in fields:
            row[n]=dec(rec[off:off+l]); off+=l
        rows.append(row)
    return [n for n,_ in fields], rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shp",required=True,help="行政區界 SHP 或 DBF 路徑")
    p.add_argument("--query",default=None,help="中文關鍵字(縣市/鄉鎮名)")
    a=p.parse_args()
    dbf=a.shp[:-4]+".dbf" if a.shp.lower().endswith(".shp") else a.shp
    names,rows=read_dbf(dbf)
    # 猜 ID 欄位與名稱欄位
    id_field=next((c for c in ("townid","COUNTYID","TOWNID","countyid") if c in names), names[0])
    name_cols=[c for c in names if "name" in c.lower()]
    code_cols=[c for c in names if c.lower() in ("towncode","countycode") or c==id_field]
    cols=list(dict.fromkeys([id_field]+code_cols+name_cols))
    out=rows
    if a.query:
        q=a.query
        out=[r for r in rows if any(q in str(r.get(c,"")) for c in name_cols)]
    print(f"欄位: {names}")
    print(f"建議 --filter-field {id_field}")
    print(f"符合 {len(out)} 筆:")
    for r in out:
        print("  "+"  ".join(f"{c}={r.get(c,'')}" for c in cols))

if __name__=="__main__":
    main()
