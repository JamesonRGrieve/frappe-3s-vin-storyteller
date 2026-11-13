# SPDX-License-Identifier: AGPL-3.0-or-later
"""A story's share card (card 391): the 1200x630 image link previews show when a story is posted to Facebook,
Messenger or a forum, and the text of its preview. Pure apart from Pillow; the API serves it.

The card shows the car's name, paint, interior, build date, its place in the model year and its rarest run, beside a
panel in its paint colour (card 390 will put a factory render of the car there). Fonts are the site's own Barlow
(public/fonts, SIL OFL 1.1)."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from vin_storyteller.story import MISSING, Story

WIDTH, HEIGHT = 1200, 630
NAVY, NAVY_2 = (10, 17, 50), (17, 26, 68)
TEXT, SOFT, KICKER = (238, 240, 246), (179, 185, 207), (140, 192, 232)
TIER_COLOURS = {  # the story page's rarity badge colours
	"one_of_one": (212, 175, 55),
	"sub10": (175, 31, 65),
	"sub25": (79, 142, 191),
	"sub50": (75, 105, 161),
	"sub100": (154, 161, 173),
}
TIER_NAMES = {
	"one_of_one": "One of one",
	"sub10": "Fewer than 10",
	"sub25": "Fewer than 25",
	"sub50": "Fewer than 50",
	"sub100": "Fewer than 100",
}
NO_COLOUR = (60, 64, 74)
FONTS = Path(__file__).parent / "public" / "fonts"


@dataclass(frozen=True)
class CardText:
	"""What a share card and its link preview say."""

	title: str  # '1991 Mitsubishi 3000GT VR-4'
	lines: tuple[str, ...]  # paint, interior, built
	position: str  # 'No. 345 of 27,207 built for 1991'
	rarity: str  # 'Fewer than 25: 1 of 20 in this exact specification ...' or ''
	tier: str | None
	description: str  # the preview's one-paragraph text


def _named(coded, what: str, hint: str = "") -> str:
	if not coded.code:
		return ""
	name = coded.description if coded.description and coded.description != MISSING else ""
	if name:
		return f"{what}: {name} ({coded.code})"
	return f"{what}: {hint} ({coded.code})" if hint else f"{what}: code {coded.code}"


def swatch_hints(swatches: dict, story: Story) -> tuple[str | None, str]:
	"""From swatches.json: the paint's colour (a code's "A" form takes its plain code's) and, for an interior the
	record doesn't name, its colour and material where they are known ('Red leather')."""
	paints = swatches.get("paint", {})
	paint = paints.get(story.exterior.code) or {}
	hex_value = paint.get("hex") or (paints.get(paint.get("same_paint_as", "")) or {}).get("hex")
	interior = swatches.get("interior", {}).get(story.interior.code) or {}
	material = interior.get("material") if interior.get("material") not in (None, "", "unknown") else ""
	hint = " ".join(p for p in ((interior.get("colour") or "").lower(), material) if p)
	return hex_value, hint[:1].upper() + hint[1:]  # 'Red leather', as the colour chart writes it


def _tone(text: str, tones) -> str | None:
	"""The representative tone for the first colour word in `text` (swatches.json interior_tones)."""
	lowered = (text or "").lower()
	return next((hex_value for word, hex_value in tones if re.search(rf"\b{word}\b", lowered)), None)


def interior_look(swatches: dict, story: Story) -> tuple[str | None, str]:
	"""The interior tile's colour and material, resolved as the animated swatch does (swatch-core.js interiorSwatch):
	a colour sampled from photos first, else the tone of a colour word in the record's description, else in the
	table's colour; leather or cloth from the description, else the table. (None, 'unknown') when nothing is on file."""
	entry = swatches.get("interior", {}).get(story.interior.code) or {}
	tones = swatches.get("interior_tones", [])
	named = (
		story.interior.description
		if story.interior.description not in ("", MISSING)
		else entry.get("description", "")
	)
	colour = _hex(entry.get("sampled_hex")) and entry.get("sampled_hex")
	colour = colour or _tone(named, tones) or _tone(entry.get("colour", ""), tones)
	if re.search(r"\bleather\b", named, re.IGNORECASE):
		material = "leather"
	elif re.search(r"\b(cloth|fabric|velour|tricot)\b", named, re.IGNORECASE):
		material = "cloth"
	else:
		material = entry.get("material") if entry.get("material") in ("leather", "cloth") else "unknown"
	return colour, material


def card_text(story: Story, interior_hint: str = "") -> CardText:
	"""A story's share card text, from its factory record."""
	lines = tuple(
		line
		for line in (
			_named(story.exterior, "Paint"),
			_named(story.interior, "Interior", interior_hint),
			f"Built {story.built}" if story.built else "",
		)
		if line
	)
	position = (
		f"No. {story.in_year.position:,} of {story.in_year.total:,} built for {story.model_year}"
		if not story.partial and story.in_year.total
		else ""
	)
	rarities = story.rarities
	rarest = rarities[0] if rarities else None
	rarity = (
		f"{TIER_NAMES[rarest.tier]}: 1 of {rarest.total:,} {rarest.description}"
		if rarest and rarest.total > 1
		else ""
	)
	if rarest and rarest.total == 1:
		rarity = f"{TIER_NAMES[rarest.tier]}: the only one {rarest.description}"
	description = " ".join(
		p
		for p in (
			". ".join(lines) + "." if lines else "",
			position + "." if position else "",
			rarity + "." if rarity else "",
		)
		if p
	)
	return CardText(story.vehicle_name, lines, position, rarity, rarest.tier if rarest else None, description)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
	return ImageFont.truetype(str(FONTS / name), size)


def _hex(value: str | None) -> tuple[int, int, int] | None:
	text = (value or "").lstrip("#")
	if len(text) != 6:
		return None
	try:
		return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))
	except ValueError:
		return None


def _fit(
	draw: ImageDraw.ImageDraw, text: str, name: str, size: int, width: int, floor: int
) -> ImageFont.FreeTypeFont:
	"""The largest size (down to `floor`) at which `text` fits in `width`."""
	while size > floor and draw.textlength(text, font=_font(name, size)) > width:
		size -= 2
	return _font(name, size)


def _paint_panel(colour: tuple[int, int, int] | None, size: tuple[int, int]) -> Image.Image:
	"""A lit panel in the paint colour (a still of the story's animated swatch), rounded."""
	w, h = size
	base = colour or NO_COLOUR
	panel = Image.new("RGB", size, base)
	light = Image.new("L", size, 0)
	ImageDraw.Draw(light).ellipse((int(w * 0.05), int(h * 0.02), int(w * 0.75), int(h * 0.62)), fill=150)
	light = light.filter(ImageFilter.GaussianBlur(min(w, h) // 5))
	panel = Image.composite(Image.new("RGB", size, tuple(min(255, c + 70) for c in base)), panel, light)
	shade = Image.linear_gradient("L").resize(size).point(lambda v: int(v * 0.55))
	panel = Image.composite(Image.new("RGB", size, tuple(int(c * 0.45) for c in base)), panel, shade)
	mask = Image.new("L", size, 0)
	ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=28, fill=255)
	panel.putalpha(mask)
	return panel


def _interior_tile(colour: tuple[int, int, int] | None, material: str, size: int) -> Image.Image:
	"""A square interior swatch: perforated leather, a cloth weave or plain, lit like the paint panel, with a navy
	ring so it reads over the paint."""
	base = colour or NO_COLOUR
	tile = _paint_panel(base if colour else None, (size, size)).convert("RGB")
	draw = ImageDraw.Draw(tile)
	dark = tuple(int(c * 0.45) for c in base)
	if material == "leather":
		step = max(8, size // 18)
		for row, y in enumerate(range(step // 2, size, step)):
			for x in range(step // 2 + (step // 2 if row % 2 else 0), size, step):
				draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=dark)
	elif material == "cloth":
		light = tuple(min(255, int(c * 1.18) + 8) for c in base)
		for i in range(0, size, 4):
			draw.line((i, 0, i, size), fill=dark if (i // 4) % 2 else light, width=1)
		for j in range(0, size, 6):
			draw.line((0, j, size, j), fill=dark, width=1)
		tile = Image.blend(tile, _paint_panel(base, (size, size)).convert("RGB"), 0.55)
	ring = 8
	framed = Image.new("RGBA", (size + 2 * ring, size + 2 * ring), (0, 0, 0, 0))
	ImageDraw.Draw(framed).rounded_rectangle(
		(0, 0, size + 2 * ring - 1, size + 2 * ring - 1), radius=26, fill=(*NAVY, 255)
	)
	mask = Image.new("L", (size, size), 0)
	ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=20, fill=255)
	framed.paste(tile, (ring, ring), mask)
	return framed


def render_card(
	story: Story,
	paint_hex: str | None,
	interior_hint: str = "",
	interior: tuple[str | None, str] | None = None,
) -> bytes:
	"""The story's share card as PNG bytes; `interior` (from interior_look) adds the interior tile."""
	text = card_text(story, interior_hint)
	glow = Image.linear_gradient("L").rotate(-35, expand=False).resize((WIDTH, HEIGHT))
	image = Image.composite(
		Image.new("RGB", (WIDTH, HEIGHT), NAVY), Image.new("RGB", (WIDTH, HEIGHT), NAVY_2), glow
	)
	draw = ImageDraw.Draw(image)
	left, text_width = 64, 600

	draw.text((left, 58), "3S HUB  ·  VIN STORYTELLER", font=_font("Barlow-SemiBold.ttf", 22), fill=KICKER)
	title = text.title.upper()
	title_font = _fit(draw, title, "BarlowCondensed-Bold.ttf", 72, text_width, 44)
	y = 100
	for chunk in _wrap(draw, title, title_font, text_width)[:2]:
		draw.text((left, y), chunk, font=title_font, fill=TEXT)
		y += int(title_font.size * 1.02)
	y += 18
	body = _font("Barlow-Medium.ttf", 27)
	for line in text.lines:
		for chunk in _wrap(draw, line, body, text_width)[:2]:
			draw.text((left, y), chunk, font=body, fill=SOFT)
			y += 38
	if text.position:
		y += 10
		draw.text((left, y), text.position, font=_font("Barlow-SemiBold.ttf", 30), fill=TEXT)
		y += 44
	if text.rarity and text.tier:
		y += 14
		tier = TIER_COLOURS[text.tier]
		label = TIER_NAMES[text.tier].upper()
		badge_font = _font("Barlow-SemiBold.ttf", 20)
		body_text = text.rarity.split(": ", 1)[-1]
		body_text = body_text[:1].upper() + body_text[1:]
		body_font = _font("Barlow-Medium.ttf", 22)
		pad, gap = 20, 10  # the same padding on every side; the gap between the tier name and the text
		lines = _wrap(draw, body_text, body_font, text_width - 2 * pad)[:2]
		# Laid out from the ink boxes, so the padding is what it says: label caps from the top, descenders at the bottom.
		label_box = draw.textbbox((0, 0), label, font=badge_font)
		line_box = draw.textbbox((0, 0), "Hg", font=body_font)  # one line's ink height, with a descender
		line_height = line_box[3] - line_box[1]
		pitch = line_height + 8
		body_top = y + pad + (label_box[3] - label_box[1]) + gap
		height = body_top - y + pitch * (len(lines) - 1) + line_height + pad
		if y + height < HEIGHT - 70:
			draw.rounded_rectangle(
				(left, y, left + text_width, y + height),
				radius=14,
				outline=tier,
				width=2,
				fill=tuple(int(c * 0.12 + n * 0.88) for c, n in zip(tier, NAVY, strict=True)),
			)
			draw.text((left + pad, y + pad - label_box[1]), label, font=badge_font, fill=tier)
			for i, chunk in enumerate(lines):
				draw.text((left + pad, body_top + pitch * i - line_box[1]), chunk, font=body_font, fill=TEXT)
	draw.text((left, HEIGHT - 52), "3shub.ca/storyteller", font=_font("Barlow-SemiBold.ttf", 22), fill=SOFT)

	panel = _paint_panel(_hex(paint_hex), (440, 470))
	image.paste(panel, (WIDTH - 440 - 64, 80), panel)
	if interior and story.interior.code:
		tile = _interior_tile(_hex(interior[0]), interior[1], 170)
		# Inside the paint panel's lower-left corner, clear of the text column.
		image.paste(tile, (WIDTH - 440 - 64 + 22, 80 + 470 - tile.height - 22), tile)
	buffer = io.BytesIO()
	image.save(buffer, "PNG", optimize=True)
	return buffer.getvalue()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
	"""`text` broken into lines no wider than `width`."""
	lines, current = [], ""
	for word in text.split():
		trial = f"{current} {word}".strip()
		if current and draw.textlength(trial, font=font) > width:
			lines.append(current)
			current = word
		else:
			current = trial
	return [*lines, current] if current else lines


def preview_html(story: Story, page_url: str, image_url: str, interior_hint: str = "") -> str:
	"""The page a shared link opens: Open Graph and Twitter card tags for link previews (crawlers read these and run
	no script), and a redirect that takes a person to the story page with the VIN filled in. Every value is escaped."""
	text = card_text(story, interior_hint)
	title = escape(f"{text.title} | 3S Hub VIN Storyteller")
	description = escape(text.description)
	page, image = escape(page_url), escape(image_url)
	return (
		"<!doctype html><html lang=en><head><meta charset=utf-8>"
		f"<title>{title}</title>"
		f'<meta name="description" content="{description}">'
		f'<meta property="og:type" content="website"><meta property="og:site_name" content="3S Hub">'
		f'<meta property="og:title" content="{title}"><meta property="og:description" content="{description}">'
		f'<meta property="og:url" content="{page}"><meta property="og:image" content="{image}">'
		f'<meta property="og:image:width" content="{WIDTH}"><meta property="og:image:height" content="{HEIGHT}">'
		f'<meta property="og:image:alt" content="{escape(text.title)}">'
		'<meta name="twitter:card" content="summary_large_image">'
		f'<meta name="twitter:title" content="{title}"><meta name="twitter:description" content="{description}">'
		f'<meta name="twitter:image" content="{image}">'
		f'<link rel="canonical" href="{page}"><meta http-equiv="refresh" content="0; url={page}">'
		f'</head><body><p><a href="{page}">{escape(text.title)}: open its story on 3S Hub</a></p></body></html>'
	)
