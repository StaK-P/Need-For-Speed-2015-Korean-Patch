"""Fetch GitHub's official favicon as a static pending-link mark.

Only saves source PNG and a colorized derivative in the installer build
assets; there is intentionally NO clickable repository link yet.
"""
from pathlib import Path
import urllib.request,hashlib,io
from PIL import Image
R=Path(__file__).resolve().parent.parent
source=R/"tools/assets/github-official-favicon.png"
target=R/"work/installer-build/github-mark.png"
url="https://github.githubassets.com/favicons/favicon.png"
if source.is_file():
    raw=source.read_bytes()
else:
    req=urllib.request.Request(url,headers={"User-Agent":"NFSKR-Setup/1.0"})
    with urllib.request.urlopen(req,timeout=18) as rsp:
        if rsp.status!=200 or "github.githubassets.com" not in rsp.geturl():
            raise ValueError("GitHub favicon must come from GitHub-hosted assets")
        raw=rsp.read(5000)
    source.parent.mkdir(parents=True,exist_ok=True)
    source.write_bytes(raw)
if len(raw)<100 or len(raw)>5000:
    raise ValueError("Official favicon data size invalid")
with Image.open(io.BytesIO(raw)) as im:
    img=im.convert("RGBA")
    if img.size!=(32,32):
        raise ValueError("Official GitHub icon is not the expected 32px favicon")
    print("SOURCE_PIXELS",img.getpixel((0,0)),img.getpixel((16,16)),img.getpixel((16,4)))
# Preserve GitHub's actual mark exactly. Its official favicon is black on
# transparent; update only color for legibility on NFSKR's navy header.
pixels=img.load()
colored=Image.new("RGBA",img.size,(0,0,0,0))
pix=colored.load()
for y in range(img.height):
    for x in range(img.width):
        red,green,blue,alpha=pixels[x,y]
        if not alpha:continue
        # Supports both white and dark favicon sources without changing geometry
        # by recoloring non-transparent portions.
        pix[x,y]=(193,205,224,alpha)
large=colored.resize((96,96),Image.Resampling.LANCZOS)
target.parent.mkdir(parents=True,exist_ok=True)
large.save(target,"PNG",optimize=True)
print("NFSKR_GITHUB_ICON_ASSET_READY","source_sha256",hashlib.sha256(raw).hexdigest().upper(),"saved",target)
