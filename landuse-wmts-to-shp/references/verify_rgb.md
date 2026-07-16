# 可選驗證：把成果 SHP 還原成 RGB 影像與原始 WMTS 視覺比對

```python
from osgeo import gdal, ogr
ds=ogr.Open(out); lyr=ds.GetLayer(); xmin,xmax,ymin,ymax=lyr.GetExtent(); res=3.0
W=int((xmax-xmin)/res); H=int((ymax-ymin)/res)
r=gdal.GetDriverByName("GTiff").Create("check.tif",W,H,3,gdal.GDT_Byte)
r.SetGeoTransform((xmin,res,0,ymax,0,-res)); r.SetProjection(lyr.GetSpatialRef().ExportToWkt())
for b,a in [(1,"R"),(2,"G"),(3,"B")]: gdal.RasterizeLayer(r,[b],lyr,options=[f"ATTRIBUTE={a}"])
r.FlushCache(); gdal.Translate("check.png", r, width=900, format="PNG")
```

還原圖應與原始 WMTS 一致；若整體偏移或顏色全錯，多半是 CRS 或色碼表欄位對不上。
（記得透過 `scripts\env.bat python ...` 執行，才有 osgeo。）
