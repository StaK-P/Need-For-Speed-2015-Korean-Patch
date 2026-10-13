"""Verify new approved logo is in Windows ICO and in the CustomTkinter header."""
from pathlib import Path
from PIL import Image
from nfskr_modern_ui import NFSKRApp
import hashlib

R=Path(__file__).resolve().parent.parent
png=R/"work/installer-build/nfskr-logo.png"
ico=R/"work/installer-build/nfskr.ico"
art=R/"tools/assets/nfskr-approved-logo.webp"
assert hashlib.sha256(art.read_bytes()).hexdigest()=="2f5f00d38446a1a771047346ae50c7d1937eecc73d2f888918516f7a0a50fa64"
with Image.open(png) as im:
    assert im.size==(512,512)
    assert im.convert("RGBA").getpixel((0,0))[3]==0
with Image.open(ico) as icon:
    assert {(16,16),(32,32),(48,48),(256,256)} <= icon.ico.sizes()
    assert icon.ico.getimage((256,256)).convert("RGBA").getpixel((0,0))[3]==0
app=NFSKRApp(R,auto_scan=False)
app.withdraw()
try:
    app.update_idletasks()
    assert app.brand_logo is not None
    assert app.brand_logo_widget.cget("image") is app.brand_logo
    assert app.brand_logo._size==(50,50)
    print("NFSKR_LOGO_UI_ICON_PASS",
          {"png_size":png.stat().st_size,
           "ico_size":ico.stat().st_size,
           "icon_sizes":sorted(Image.open(ico).ico.sizes()),
           "header_image_size":app.brand_logo._size},flush=True)
finally:
    app.destroy()
