import math, urllib.request, os, sys, io
from PIL import Image
S=sys.argv[1]
def t(lat,lon,z):
    n=2**z; x=(lon+180)/360*n; y=(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n; return x,y
S_LAT,N_LAT,W_LON,E_LON=41.1495,41.1610,-80.0900,-80.0705
def get(url,path):
    if os.path.exists(path): return Image.open(path)
    req=urllib.request.Request(url,headers={'User-Agent':'GrooveCityMap/1.0'})
    data=urllib.request.urlopen(req,timeout=30).read(); open(path,'wb').write(data); return Image.open(io.BytesIO(data))
def mosaic(z,urlf,name,ts=256):
    x0,y0=t(N_LAT,W_LON,z); x1,y1=t(S_LAT,E_LON,z)
    X0,Y0,X1,Y1=int(x0),int(y0),int(x1),int(y1)
    im=Image.new('RGB',((X1-X0+1)*ts,(Y1-Y0+1)*ts))
    for X in range(X0,X1+1):
        for Y in range(Y0,Y1+1):
            ti=get(urlf(z,X,Y),f'{S}/tiles/{name}_{z}_{X}_{Y}.png').convert('RGB')
            im.paste(ti,((X-X0)*ts,(Y-Y0)*ts))
    # crop to bbox
    im=im.crop((int((x0-X0)*ts),int((y0-Y0)*ts),int((x1-X0)*ts),int((y1-Y0)*ts)))
    im.save(f'{S}/{name}.png'); print(name,im.size)
mosaic(18,lambda z,x,y:f'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}','sat')
mosaic(15,lambda z,x,y:f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png','dem')
