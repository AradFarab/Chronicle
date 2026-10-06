"""Generate the PWA icons in frontend/public/icons from the Vazirmatn font (run once; output committed).

python tools/make_pwa_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "hozur/public/fonts/vazirmatn/Vazirmatn-Bold.ttf"
OUT = ROOT / "frontend/public/icons"
BRAND = (15, 118, 110)  # --hz-brand
LETTER = "ح"


def icon(size: int, maskable: bool = False, radius: float = 0.22) -> Image.Image:
	scale = 4  # draw large, then downsample for smooth edges
	big = size * scale
	img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
	draw = ImageDraw.Draw(img)
	if maskable:
		draw.rectangle((0, 0, big, big), fill=BRAND)
	else:
		draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * radius), fill=BRAND)
	# maskable icons keep the glyph inside the 80% safe zone
	font = ImageFont.truetype(str(FONT), int(big * (0.5 if maskable else 0.62)))
	box = draw.textbbox((0, 0), LETTER, font=font)
	x = (big - (box[2] - box[0])) / 2 - box[0]
	y = (big - (box[3] - box[1])) / 2 - box[1]
	draw.text((x, y), LETTER, font=font, fill="white")
	return img.resize((size, size), Image.LANCZOS)


def main():
	OUT.mkdir(parents=True, exist_ok=True)
	icon(192).save(OUT / "icon-192.png")
	icon(512).save(OUT / "icon-512.png")
	icon(512, maskable=True).save(OUT / "maskable-512.png")
	icon(180, maskable=True).convert("RGB").save(OUT / "apple-touch-icon-180.png")
	icon(32, radius=0.18).save(OUT / "favicon-32.png")


if __name__ == "__main__":
	main()
