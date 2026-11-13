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
	paint: str  # 'Glacier White Pearl · WA5' (the paint chip's heading)
	interior: str  # 'Red leather · 14U' (the interior chip's heading)
	built: str  # 'Built the 1st production period of July, 1990'
	position: str  # 'No. 345 of 27,207 built for 1991'
	positions: tuple[
		str, ...
	]  # its place among its model, then its colour: 'No. 155 of 3,693 1991 ... VR-4s'
	rarity: str  # 'Fewer than 25: 1 of 20 in this exact specification' or ''
	tier: str | None
	option: str  # 'A07' (the option code the list is from)
	options: tuple[str, ...]  # what the option code fits, then factory features from the parts catalogue
	description: str  # the preview's one-paragraph text


# The card's rarity scopes, short enough for one line (the story page and preview text give the full wording).
CARD_SCOPES = {
	"spec": "in this exact specification",
	"colour": "in this colour for this model and year",
	"model": "of this model for the year",
}


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
	plain = paints.get(paint.get("same_paint_as", "")) or {}
	# As swatch-core.js paintValue: a Dodge is drawn in Dodge's published value where there is one.
	dodge = paint.get("dodge_hex") or plain.get("dodge_hex")
	hex_value = dodge if dodge and story.manufacturer == "Dodge" else paint.get("hex") or plain.get("hex")
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


def _chip_heading(coded, hint: str = "") -> str:
	if not coded.code:
		return "Not on record"
	name = coded.description if coded.description and coded.description != MISSING else hint
	return f"{name} \u00b7 {coded.code}" if name else f"Code {coded.code}"


def card_text(story: Story, interior_hint: str = "") -> CardText:
	"""A story's share card text, from its factory record."""
	built = f"Built {story.built}" if story.built else ""
	position = (
		f"No. {story.in_year.position:,} of {story.in_year.total:,} built for {story.model_year}"
		if not story.partial and story.in_year.total
		else ""
	)
	positions = ()
	if not story.partial and story.in_model.total:
		paint_name = story.exterior.description if story.exterior.description not in ("", MISSING) else ""
		positions = (
			f"No. {story.in_model.position:,} of {story.in_model.total:,} {story.vehicle_name}s",
			*(
				(f"No. {story.in_colour.position:,} of {story.in_colour.total:,} in {paint_name}",)
				if paint_name and story.in_colour.total
				else ()
			),
		)
	rarities = story.rarities
	rarest = rarities[0] if rarities else None
	rarity, long_rarity = "", ""
	if rarest:
		count = "the only one" if rarest.total == 1 else f"1 of {rarest.total:,}"
		rarity = f"{TIER_NAMES[rarest.tier]}: {count} {CARD_SCOPES[rarest.scope]}"
		long_rarity = f"{TIER_NAMES[rarest.tier]}: {count} {rarest.description}"
	items = tuple(
		item.description if item.description and item.description != MISSING else f"Item {item.code}"
		for item in story.equipment_items
	)
	options = items + tuple(story.features)
	colours = [_named(story.exterior, "Paint"), _named(story.interior, "Interior", interior_hint)]
	description = " ".join(
		f"{p}."
		for p in (
			*(c for c in colours if c),
			built,
			position,
			long_rarity,
			f"Options: {', '.join(options)}" if options else "",
		)
		if p
	)
	equipment = story.equipment.code if story.equipment.code not in ("", "EQU") else ""
	return CardText(
		title=story.vehicle_name,
		paint=_chip_heading(story.exterior),
		interior=_chip_heading(story.interior, interior_hint),
		built=built,
		position=position,
		positions=positions,
		rarity=rarity,
		tier=rarest.tier if rarest else None,
		option=equipment,
		options=options,
		description=description,
	)


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
	ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=20, fill=255)
	panel.putalpha(mask)
	return panel


def _interior_chip(colour: tuple[int, int, int] | None, material: str, size: tuple[int, int]) -> Image.Image:
	"""An interior swatch: perforated leather, a cloth weave or plain, lit like the paint chip."""
	w, h = size
	base = colour or NO_COLOUR
	chip = _paint_panel(colour, size)
	draw = ImageDraw.Draw(chip)
	dark = (*tuple(int(c * 0.45) for c in base), 255)
	if material == "leather":
		step = 11
		for row, y in enumerate(range(step // 2, h, step)):
			for x in range(step // 2 + (step // 2 if row % 2 else 0), w, step):
				draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=dark)
	elif material == "cloth":
		weave = Image.new("RGBA", size, (0, 0, 0, 0))
		lines = ImageDraw.Draw(weave)
		for i in range(0, w, 4):
			lines.line((i, 0, i, h), fill=(*tuple(int(c * 0.6) for c in base), 110), width=1)
		for j in range(0, h, 6):
			lines.line((0, j, w, j), fill=(*tuple(int(c * 0.5) for c in base), 120), width=1)
		chip = Image.alpha_composite(chip, weave)
	mask = Image.new("L", size, 0)
	ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=20, fill=255)
	chip.putalpha(mask)
	return chip


def _ellipsis(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> str:
	"""`text`, cut with an ellipsis to fit `width`."""
	if draw.textlength(text, font=font) <= width:
		return text
	while text and draw.textlength(f"{text}\u2026", font=font) > width:
		text = text[:-1]
	return f"{text.rstrip()}\u2026"


LEFT, LEFT_WIDTH = 64, 620  # the text column
RIGHT, RIGHT_WIDTH = 744, 392  # the colour column: paint over interior
BOTTOM = HEIGHT - 72  # above the site address


def _badge(draw, text: CardText, y: int) -> int:
	"""The rarity badge at `y`, laid out from its text's ink boxes with even padding; returns its bottom."""
	tier = TIER_COLOURS[text.tier]
	label_font, body_font = _font("Barlow-SemiBold.ttf", 20), _font("Barlow-Medium.ttf", 22)
	label = TIER_NAMES[text.tier].upper()
	body = text.rarity.split(": ", 1)[-1]
	body = body[:1].upper() + body[1:]
	pad, gap = 20, 10  # the same padding on every side; the gap between the tier name and the text
	lines = _wrap(draw, body, body_font, LEFT_WIDTH - 2 * pad)[:2]
	label_box = draw.textbbox((0, 0), label, font=label_font)
	line_box = draw.textbbox((0, 0), "Hg", font=body_font)  # one line's ink height, with a descender
	line_height = line_box[3] - line_box[1]
	pitch = line_height + 8
	body_top = y + pad + (label_box[3] - label_box[1]) + gap
	bottom = body_top + pitch * (len(lines) - 1) + line_height + pad
	draw.rounded_rectangle(
		(LEFT, y, LEFT + LEFT_WIDTH, bottom),
		radius=14,
		outline=tier,
		width=2,
		fill=tuple(int(c * 0.12 + n * 0.88) for c, n in zip(tier, NAVY, strict=True)),
	)
	draw.text((LEFT + pad, y + pad - label_box[1]), label, font=label_font, fill=tier)
	for i, chunk in enumerate(lines):
		draw.text((LEFT + pad, body_top + pitch * i - line_box[1]), chunk, font=body_font, fill=TEXT)
	return bottom


def _options(draw, text: CardText, y: int) -> None:
	"""The option list from `y` down to BOTTOM: one column at 19 px when every item fits on a line, else two columns
	at 18 px where a long item wraps onto a second, indented line. What the space can't hold is counted ('+3 more')."""
	kicker = _font("Barlow-SemiBold.ttf", 18)
	heading = f"FACTORY OPTIONS \u00b7 {text.option}" if text.option else "FACTORY OPTIONS"
	draw.text((LEFT, y), heading, font=kicker, fill=KICKER)
	y += 34
	if not text.options:
		message = "Not yet decoded" if text.option else "Not recorded"
		draw.text((LEFT, y), message, font=_font("Barlow-Medium.ttf", 19), fill=SOFT)
		return
	items = list(text.options)
	bullet, indent, gutter = "\u2022", 18, 24
	single = _font("Barlow-Medium.ttf", 19)
	rows = (BOTTOM - y) // 28
	if len(items) <= rows and all(draw.textlength(i, font=single) <= LEFT_WIDTH - indent for i in items):
		columns, font, pitch, width = 1, single, 28, LEFT_WIDTH
	else:
		columns, font, pitch = 2, _font("Barlow-Medium.ttf", 18), 25
		width = (LEFT_WIDTH - gutter) // 2
	rows = (BOTTOM - y) // pitch
	# Each item's lines; items fill the first column, then the second.
	blocks = [_wrap(draw, item, font, width - indent)[:2] for item in items]
	placed, column, row = [], 0, 0
	for lines in blocks:
		if row + len(lines) > rows:
			column, row = column + 1, 0
		if column >= columns or row + len(lines) > rows:
			break
		placed.append((column, row, lines))
		row += len(lines)
	hidden = len(items) - len(placed)
	more_at = None
	if hidden:  # a last line says how many more there are: free a row for it at the end of the last column
		while placed and placed[-1][1] + len(placed[-1][2]) >= rows:
			placed.pop()
			hidden += 1
		more_at = (placed[-1][0], placed[-1][1] + len(placed[-1][2])) if placed else (0, 0)
	for col, row, lines in placed:
		x = LEFT + col * (width + gutter)
		draw.text((x, y + row * pitch), bullet, font=font, fill=SOFT)
		for k, line in enumerate(lines):
			draw.text(
				(x + indent, y + (row + k) * pitch),
				_ellipsis(draw, line, font, width - indent),
				font=font,
				fill=SOFT,
			)
	if more_at:
		draw.text(
			(LEFT + more_at[0] * (width + gutter) + indent, y + more_at[1] * pitch),
			f"+{hidden} more",
			font=font,
			fill=KICKER,
		)


def _colour_block(image, draw, y: int, kicker: str, heading: str, chip: Image.Image) -> int:
	"""A heading (kind and name) above its chip, in the colour column; returns its bottom."""
	draw.text((RIGHT, y), kicker, font=_font("Barlow-SemiBold.ttf", 18), fill=KICKER)
	name_font = _fit(draw, heading, "Barlow-SemiBold.ttf", 26, RIGHT_WIDTH, 18)
	draw.text((RIGHT, y + 26), _ellipsis(draw, heading, name_font, RIGHT_WIDTH), font=name_font, fill=TEXT)
	image.paste(chip, (RIGHT, y + 66), chip)
	# A fine light edge, so a paint as dark as the card (Danube Blue, Jet Black) keeps its shape.
	edge = Image.new("RGBA", image.size, (0, 0, 0, 0))
	ImageDraw.Draw(edge).rounded_rectangle(
		(RIGHT, y + 66, RIGHT + chip.width - 1, y + 66 + chip.height - 1),
		radius=20,
		outline=(255, 255, 255, 56),
		width=2,
	)
	image.paste(edge, (0, 0), edge)
	return y + 66 + chip.height


def render_card(
	story: Story,
	paint_hex: str | None,
	interior_hint: str = "",
	interior: tuple[str | None, str] | None = None,
) -> bytes:
	"""The story's share card as PNG bytes: the car, its build and rarity and its factory options on the left; its
	paint over its interior on the right, each under its name (`interior` from interior_look)."""
	text = card_text(story, interior_hint)
	glow = Image.linear_gradient("L").rotate(-35, expand=False).resize((WIDTH, HEIGHT))
	image = Image.composite(
		Image.new("RGB", (WIDTH, HEIGHT), NAVY), Image.new("RGB", (WIDTH, HEIGHT), NAVY_2), glow
	)
	draw = ImageDraw.Draw(image)

	draw.text(
		(LEFT, 52), "3S HUB  \u00b7  VIN STORYTELLER", font=_font("Barlow-SemiBold.ttf", 20), fill=KICKER
	)
	title = text.title.upper()
	title_font = _fit(draw, title, "BarlowCondensed-Bold.ttf", 64, LEFT_WIDTH, 44)
	y = 86
	for chunk in _wrap(draw, title, title_font, LEFT_WIDTH)[:2]:
		draw.text((LEFT, y), chunk, font=title_font, fill=TEXT)
		y += int(title_font.size * 1.02)
	y += 12
	if text.built:
		draw.text(
			(LEFT, y),
			_ellipsis(draw, text.built, _font("Barlow-Medium.ttf", 24), LEFT_WIDTH),
			font=_font("Barlow-Medium.ttf", 24),
			fill=SOFT,
		)
		y += 36
	if text.position:
		draw.text((LEFT, y), text.position, font=_font("Barlow-SemiBold.ttf", 26), fill=TEXT)
		y += 38
	for line in text.positions:
		small = _font("Barlow-Medium.ttf", 21)
		draw.text((LEFT, y), _ellipsis(draw, line, small, LEFT_WIDTH), font=small, fill=SOFT)
		y += 30
	if text.position or text.positions:
		y += 4
	if text.rarity and text.tier:
		y = _badge(draw, text, y + 8) + 24
	else:
		y += 8
	_options(draw, text, y)
	draw.text((LEFT, HEIGHT - 50), "3shub.ca/storyteller", font=_font("Barlow-SemiBold.ttf", 20), fill=SOFT)

	chip_size = (RIGHT_WIDTH, 168)
	bottom = _colour_block(image, draw, 52, "PAINT", text.paint, _paint_panel(_hex(paint_hex), chip_size))
	colour, material = interior if interior else (None, "unknown")
	_colour_block(
		image, draw, bottom + 28, "INTERIOR", text.interior, _interior_chip(_hex(colour), material, chip_size)
	)
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
