import numpy as np, sys
from PIL import Image, ImageFilter
S=sys.argv[1]
im=Image.open(f'{S}/sat.png').convert('RGB')
a=np.asarray(im).astype(np.float32)
r,g,b=a[...,0],a[...,1],a[...,2]
L=(r+g+b)/3
gray=Image.fromarray(L.astype(np.uint8))
m=np.asarray(gray.filter(ImageFilter.BoxBlur(3))).astype(np.float32)
m2=np.asarray(Image.fromarray(np.clip(L*L/255,0,255).astype(np.uint8)).filter(ImageFilter.BoxBlur(3))).astype(np.float32)*255
std=np.sqrt(np.maximum(m2-m*m,0))
green=(g>r+4)&(g>=b-2)
mask=((g>=r)&(g>=b-4)&(L<45))|(green&(L<88)&(std>12))
mask=np.asarray(Image.fromarray((mask*255).astype(np.uint8)).filter(ImageFilter.BoxBlur(4)))>120
np.save(f'{S}/canopy.npy',mask)
vis=a.copy(); vis[mask]=vis[mask]*0.4+np.array([255,0,255])*0.6
Image.fromarray(vis.astype(np.uint8)).crop((1000,400,2400,1500)).resize((700,550)).save(f'{S}/canopy_core.png')
Image.fromarray(vis.astype(np.uint8)).crop((1800,1100,3200,2300)).resize((700,600)).save(f'{S}/canopy_se.png')
print(mask.mean())
