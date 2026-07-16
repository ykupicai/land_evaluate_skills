# -*- coding: utf-8 -*-
r"""
LUIMAP WMTS -> 行政區裁切向量化 SHP  (single-entry pipeline)

流程: 取縣市界 -> 算圖磚範圍 -> 下載 LUIMAP -> 地理參考拼接 ->
      RGB 最近色分類 -> sieve 去雜點 -> 向量化 -> 裁切到縣市界 -> 輸出 SHP

用 QGIS 內建 GDAL/Python 透過 env.bat 執行，例如:
  # 縣市尺度
  scripts\env.bat python scripts\run.py ^
     --boundary-shp <縣市SHP> --filter-field COUNTYID --filter-value I --zoom 16 ^
     --colortable references\luimap_colortable.csv --out output\chiayi_landuse.shp
  # 鄉鎮尺度
  scripts\env.bat python scripts\run.py ^
     --boundary-shp <鄉鎮SHP> --filter-field townid --filter-value 10020001 --zoom 16 ^
     --colortable references\luimap_colortable.csv --out output\chiayi_east_landuse.shp
"""
import argparse, os, sys, tempfile, subprocess, urllib.request, time
import numpy as np
from osgeo import gdal, ogr, osr
gdal.UseExceptions()
sys.stdout.reconfigure(encoding="utf-8")

ORIGIN = 20037508.342789244
URL = "https://wmts.nlsc.gov.tw/wmts/LUIMAP/default/GoogleMapsCompatible/{z}/{row}/{col}"

def log(m): print(m, flush=True)

def extract_boundary(boundary_shp, field, value, wd):
    """篩出單一行政區(縣市或鄉鎮)，轉 3857 當作裁切界與圖磚範圍。"""
    out = os.path.join(wd, "boundary_3857.shp")
    subprocess.run(["ogr2ogr","-f","ESRI Shapefile",out,boundary_shp,
                    "-where",f"{field}='{value}'","-t_srs","EPSG:3857"], check=True)
    ds = ogr.Open(out); lyr = ds.GetLayer()
    if lyr.GetFeatureCount() == 0:
        sys.exit(f"找不到 {field}='{value}' 的行政區，請檢查代碼或欄位名 "
                 f"(縣市用 COUNTYID，鄉鎮用 townid；可先跑 find_id.py 查)")
    ext = lyr.GetExtent()  # xmin,xmax,ymin,ymax
    ds = None
    return out, ext

def _boundary_geom_3857(boundary_shp):
    """讀 3857 邊界，聯集成單一幾何供圖磚相交測試。"""
    ds = ogr.Open(boundary_shp); lyr = ds.GetLayer()
    geom = None
    for f in lyr:
        g = f.GetGeometryRef()
        if g is None: continue
        g = g.Clone()
        geom = g if geom is None else geom.Union(g)
    return geom

def build_mosaic(ext, z, wd, boundary_shp=None):
    """下載 LUIMAP 圖磚拼接成磁碟 GeoTIFF。逐圖磚寫入(不佔大量記憶體)，
    且只抓與行政區實際相交的圖磚 — 離島型行政區(基隆/台東/澎湖等)不會因
    遠方離島把整片海域算進來而下載上萬張空圖磚。"""
    xmin,xmax,ymin,ymax = ext
    tile_m = 2*ORIGIN/(2**z)
    col_min = int((xmin+ORIGIN)/tile_m); col_max = int((xmax+ORIGIN)/tile_m)
    row_min = int((ORIGIN-ymax)/tile_m); row_max = int((ORIGIN-ymin)/tile_m)
    ncol, nrow = col_max-col_min+1, row_max-row_min+1
    W,H = ncol*256, nrow*256
    pix = tile_m/256.0
    ox = col_min*tile_m - ORIGIN; oy = ORIGIN - row_min*tile_m
    bgeom = _boundary_geom_3857(boundary_shp) if boundary_shp else None
    # 預先挑出與邊界相交的圖磚
    todo = []
    for r in range(row_min,row_max+1):
        ty0 = oy - (r-row_min)*tile_m
        for c in range(col_min,col_max+1):
            tx0 = ox + (c-col_min)*tile_m
            if bgeom is not None:
                ring = ogr.Geometry(ogr.wkbLinearRing)
                for px,py in [(tx0,ty0),(tx0+tile_m,ty0),(tx0+tile_m,ty0-tile_m),
                              (tx0,ty0-tile_m),(tx0,ty0)]: ring.AddPoint_2D(px,py)
                poly = ogr.Geometry(ogr.wkbPolygon); poly.AddGeometry(ring)
                if not bgeom.Intersects(poly): continue
            todo.append((r,c))
    log(f"z{z} 圖磚範圍 {ncol}x{nrow}={ncol*nrow}，與行政區相交需下載 {len(todo)} 張")
    # 建磁碟 GeoTIFF，逐圖磚寫入
    out = os.path.join(wd,"mosaic.tif")
    drv = gdal.GetDriverByName("GTiff")
    d = drv.Create(out,W,H,3,gdal.GDT_Byte,
                   options=["COMPRESS=DEFLATE","TILED=YES","BIGTIFF=IF_SAFER"])
    d.SetGeoTransform((ox,pix,0,oy,0,-pix))
    srs=osr.SpatialReference(); srs.ImportFromEPSG(3857); d.SetProjection(srs.ExportToWkt())
    for b in range(3): d.GetRasterBand(b+1).Fill(255)      # 背景白(界外，最後會被裁掉)
    bands=[d.GetRasterBand(b+1) for b in range(3)]
    hdr={"User-Agent":"Mozilla/5.0 (QGIS GDAL tile fetch)"}
    tiledir=os.path.join(wd,"tiles"); os.makedirs(tiledir,exist_ok=True)
    ok=miss=0
    for i,(r,c) in enumerate(todo):
        fn=os.path.join(tiledir,f"{z}_{r}_{c}.png")
        if not os.path.exists(fn) or os.path.getsize(fn)<100:
            u=URL.format(z=z,row=r,col=c)
            for att in range(3):
                try:
                    data=urllib.request.urlopen(urllib.request.Request(u,headers=hdr),timeout=30).read()
                    open(fn,"wb").write(data); break
                except Exception as e:
                    if att==2: log(f"  FAIL {u}: {e}")
                    else: time.sleep(1)
        try:
            blob=open(fn,"rb").read()
            if blob[:3]==b"GIF": miss+=1; continue
            mem="/vsimem/t.png"; gdal.FileFromMemBuffer(mem,blob)
            t=gdal.Open(mem); arr=t.ReadAsArray(); gdal.Unlink(mem)
            if arr is None: miss+=1; continue
            if arr.ndim==2: arr=np.stack([arr]*3)
            x0=(c-col_min)*256; y0=(r-row_min)*256
            for b in range(3): bands[b].WriteArray(arr[b],x0,y0)
            ok+=1
        except Exception as e:
            log(f"  read err {fn}: {e}"); miss+=1
        if (i+1)%200==0 or i+1==len(todo):
            log(f"  下載 {i+1}/{len(todo)} ({ok} ok / {miss} blank)")
    d.FlushCache(); d=None
    log(f"拼接完成 {out} ({W}x{H}px, {pix:.3f}m/px, {ok} tiles)")
    return out

def load_palette(csvf):
    import csv as _csv
    codes=[]; names=[]; rg=[]
    with open(csvf,encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            codes.append(row["lu_code"]); names.append(row["lu_name"])
            rg.append((int(row["R"]),int(row["G"]),int(row["B"])))
    seen={}
    for i,(c,col) in enumerate(zip(codes,rg)):
        if col not in seen or len(c)>len(codes[seen[col]]): seen[col]=i
    keep=sorted(seen.values())
    return ([codes[i] for i in keep],[names[i] for i in keep],
            np.array([rg[i] for i in keep],dtype=np.int32))

def classify_polygonize(mosaic_tif, csvf, sieve, wd):
    codes,names,pal = load_palette(csvf)
    log(f"色碼表類別 (去重後): {len(codes)}")
    ds=gdal.Open(mosaic_tif); gt=ds.GetGeoTransform(); proj=ds.GetProjection()
    W=ds.RasterXSize; H=ds.RasterYSize
    clstif=os.path.join(wd,"class.tif")
    cds=gdal.GetDriverByName("GTiff").Create(clstif,W,H,1,gdal.GDT_Int32,
            options=["COMPRESS=DEFLATE","TILED=YES","BIGTIFF=IF_SAFER"])
    cds.SetGeoTransform(gt); cds.SetProjection(proj)
    band=cds.GetRasterBand(1); band.SetNoDataValue(0)
    # 逐區塊(列)做最近色比對，記憶體不隨影像大小爆炸；色->類別 用 cache 跨區塊重用
    cache={}; near30=tot_u=0; BH=1024
    for y in range(0,H,BH):
        bh=min(BH,H-y)
        blk=ds.ReadAsArray(0,y,W,bh)                      # (3,bh,W) uint8
        flat=blk.reshape(3,-1).T
        uniq,inv=np.unique(flat,axis=0,return_inverse=True); inv=inv.ravel()
        keys=[(int(a),int(b),int(c)) for a,b,c in uniq]
        new=[i for i,k in enumerate(keys) if k not in cache]
        if new:
            nc=uniq[new].astype(np.int32)
            dd=((nc[:,None,:]-pal[None,:,:])**2).sum(2); nn=dd.argmin(1)
            dmin=np.sqrt(dd[np.arange(len(nc)),nn])
            for j,i in enumerate(new): cache[keys[i]]=int(nn[j])+1
            near30+=int((dmin<=30).sum()); tot_u+=len(nc)
        lut=np.array([cache[k] for k in keys],dtype=np.int32)
        band.WriteArray(lut[inv].reshape(bh,W),0,y)
    log(f"最近色比對完成: {tot_u} 色, "
        f"{(100*near30/tot_u if tot_u else 0):.1f}% 落在距離30內 (其餘為邊界反鋸齒)")
    if sieve>0: gdal.SieveFilter(band,None,band,threshold=sieve,connectedness=8)
    cds.FlushCache()
    gpkg=os.path.join(wd,"poly.gpkg")
    gdrv=ogr.GetDriverByName("GPKG")
    if os.path.exists(gpkg): gdrv.DeleteDataSource(gpkg)
    gds=gdrv.CreateDataSource(gpkg)
    srs=osr.SpatialReference(); srs.ImportFromWkt(proj)
    lyr=gds.CreateLayer("landuse",srs=srs,geom_type=ogr.wkbPolygon)
    lyr.CreateField(ogr.FieldDefn("classid",ogr.OFTInteger))
    gdal.Polygonize(band,band,lyr,0,[],callback=None)
    for fn,ft,wdth in [("lu_code",ogr.OFTString,10),("lu_name",ogr.OFTString,60),
                       ("R",ogr.OFTInteger,0),("G",ogr.OFTInteger,0),("B",ogr.OFTInteger,0),
                       ("std_RGB",ogr.OFTString,16)]:
        fd=ogr.FieldDefn(fn,ft)
        if wdth: fd.SetWidth(wdth)
        lyr.CreateField(fd)
    lyr.ResetReading(); n=0
    for feat in lyr:
        cid=feat.GetField("classid")
        if not cid or cid<1: continue
        i=cid-1; r,g,b=(int(x) for x in pal[i])
        feat.SetField("lu_code",codes[i]); feat.SetField("lu_name",names[i])
        feat.SetField("R",r); feat.SetField("G",g); feat.SetField("B",b)
        feat.SetField("std_RGB",f"{r},{g},{b}")
        lyr.SetFeature(feat); n+=1
    gds=None; cds=None
    log(f"向量化 {n} 個多邊形")
    return gpkg

def clip_output(gpkg, county_3857, out, epsg):
    os.makedirs(os.path.dirname(os.path.abspath(out)),exist_ok=True)
    subprocess.run(["ogr2ogr","-f","ESRI Shapefile",out,gpkg,"landuse",
                    "-clipsrc",county_3857,"-t_srs",f"EPSG:{epsg}",
                    "-lco","ENCODING=UTF-8","-nlt","PROMOTE_TO_MULTI"],check=True)
    ds=ogr.Open(out); lyr=ds.GetLayer()
    log(f"輸出 {out}: {lyr.GetFeatureCount()} features, EPSG:{epsg}")
    ds=None

def main():
    p=argparse.ArgumentParser(description="LUIMAP WMTS -> 行政區(縣市/鄉鎮) 裁切向量化 SHP")
    p.add_argument("--boundary-shp",required=True,
                   help="行政區界 SHP：縣市界(COUNTY_MOI) 或鄉鎮界(鄉鎮界_97TM2)")
    p.add_argument("--filter-field",required=True,
                   help="篩選欄位：縣市用 COUNTYID，鄉鎮用 townid (皆為 ASCII，避免中文編碼問題)")
    p.add_argument("--filter-value",required=True,
                   help="代碼值，如 I(嘉義市) 或 10020001(嘉義市東區)；不確定請先跑 find_id.py")
    p.add_argument("--zoom",type=int,default=16)
    p.add_argument("--colortable",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--target-epsg",type=int,default=3826)
    p.add_argument("--sieve",type=int,default=8)
    p.add_argument("--workdir",default=None)
    a=p.parse_args()
    wd=a.workdir or tempfile.mkdtemp(prefix="luimap_")
    os.makedirs(wd,exist_ok=True)
    log(f"workdir: {wd}")
    bnd_3857,ext=extract_boundary(a.boundary_shp,a.filter_field,a.filter_value,wd)
    log(f"範圍(3857): X[{ext[0]:.0f},{ext[1]:.0f}] Y[{ext[2]:.0f},{ext[3]:.0f}]")
    mosaic=build_mosaic(ext,a.zoom,wd,bnd_3857)
    gpkg=classify_polygonize(mosaic,a.colortable,a.sieve,wd)
    clip_output(gpkg,bnd_3857,a.out,a.target_epsg)
    log("完成 ✅")

if __name__=="__main__":
    main()
