# SPDX-License-Identifier: AGPL-3.0-or-later
"""A story's share card (card 391): the 1200x630 image link previews show when a story is posted to Facebook,
Messenger or a forum, and the text of its preview. Pure apart from Pillow; the API serves it.

The card shows the car's name, build date and its places: in the model year, its model line, its paint, its interior,
its combination of paint and interior, its exact specification (in a tier badge when that run is rare), then its factory options;
beside them its paint over its interior (card 390 will add a factory render of the car). Fonts are the site's own Barlow
(public/fonts, SIL OFL 1.1)."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from vin_storyteller.story import COMMON_TIER, MISSING, TIER_NAMES, Story, rarity_tier

WIDTH, HEIGHT = 1200, 630
NAVY, NAVY_2 = (10, 17, 50), (17, 26, 68)
TEXT, SOFT, KICKER = (238, 240, 246), (179, 185, 207), (140, 192, 232)
# Each tier's colour and how iridescent its badge is (0 none, 1 full): story.RARITY_TIERS, operator 2026-11-13.
TIER_STYLES = {
	"one_of_one": ((236, 236, 240), 1.0),  # fully iridescent, holographic
	"one_of_two": ((229, 228, 226), 0.35),  # platinum, a hint of iridescence
	"one_of_three": ((229, 228, 226), 0.0),  # platinum
	"five": ((212, 175, 55), 0.0),  # gold
	"ten": ((192, 192, 196), 0.0),  # silver
	"twenty_five": ((184, 115, 51), 0.0),  # copper
	"fifty": ((79, 142, 191), 0.0),  # Fiji Blue
	"hundred": ((175, 31, 65), 0.0),  # Morocco Red
	COMMON_TIER: ((128, 132, 142), 0.0),  # grey
}
SPECTRUM = (
	(255, 120, 170),
	(255, 210, 120),
	(150, 240, 170),
	(110, 210, 255),
	(170, 140, 255),
	(255, 120, 170),
)
NO_COLOUR = (60, 64, 74)
FONTS = Path(__file__).parent / "public" / "fonts"


@dataclass(frozen=True)
class CardText:
	"""What a share card and its link preview say."""

	title: str  # '1991 Mitsubishi 3000GT VR-4'
	paint: str  # 'Glacier White Pearl · WA5' (the paint chip's heading)
	interior: str  # 'Red leather · 14U' (the interior chip's heading)
	built: str  # 'Built the 1st production period of July, 1990'
	position: str  # '#345 of 27,207 built for 1991'
	positions: tuple[
		str, ...
	]  # its model-line, paint, interior and paint-and-interior places: '#155 of 3,693 1991 ... VR-4s'
	rarity: str  # 'Fewer than 25: 1 of 20 in this exact specification' or ''
	tier: str | None
	option: str  # 'A07' (the option code the list is from)
	options: tuple[str, ...]  # what the option code fits, then factory features from the parts catalogue
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
		f"#{story.in_year.position:,} of {story.in_year.total:,} built for {story.model_year}"
		if not story.partial and story.in_year.total
		else ""
	)

	def place(p, scope: str) -> str:
		return f"#{p.position:,} of {p.total:,} {scope}" if p.total else ""

	positions, spec_line, tier = (), "", None
	if not story.partial and story.in_model.total:
		positions = tuple(
			line
			for line in (
				# Left out where it repeats the year line (a JDM year is all GTOs of one line).
				f"#{story.in_model.position:,} of {story.in_model.total:,} {story.vehicle_name}s"
				if story.in_model != story.in_year
				else "",
				place(story.in_colour, "in this paint"),
				place(story.in_interior, "in this interior"),
				place(story.in_colours, "in this combination of paint and interior"),
				place(story.among_identical, "in this exact specification"),
			)
			if line
		)
		# The badge says how rare the spec is ('1 of 4'); the place line above it says which one this car is.
		spec_line = f"1 of {story.among_identical.total:,} in this exact specification"
		# The exact spec is always the smallest, so rarest, run; past 100 cars it is common (grey).
		tier = rarity_tier(story.among_identical.total) or COMMON_TIER
	rarity = f"{TIER_NAMES[tier]}: {spec_line}" if tier else ""
	long_rarity = rarity
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
		tier=tier,
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


def _spectrum(width: int, height: int, strength: float, base: tuple[int, int, int]) -> Image.Image:
	"""A diagonal holographic gradient across the spectrum, blended into `base` by `strength` (0 to 1)."""
	stops = SPECTRUM
	row = Image.new("RGB", (width + height, 1))
	n = len(stops) - 1
	for x in range(width + height):
		t = x / max(1, width + height - 1) * n
		i = min(int(t), n - 1)
		f = t - i
		c = tuple(int(stops[i][k] * (1 - f) + stops[i + 1][k] * f) for k in range(3))
		row.putpixel((x, 0), tuple(int(c[k] * strength + base[k] * (1 - strength)) for k in range(3)))
	full = row.resize((width + height, height))
	sheared = Image.new("RGB", (width, height))
	for yy in range(height):  # shift each row so the bands run diagonally
		sheared.paste(full.crop((yy, yy, yy + width, yy + 1)), (0, yy))
	return sheared


def _iridescent(image: Image.Image, box: tuple[int, int, int, int], strength: float) -> None:
	"""A rounded outline in the holographic gradient (a platinum one with a hint of it when `strength` is low), with a
	soft sheen across the badge for a full one."""
	x0, y0, x1, y1 = box
	w, h = x1 - x0 + 1, y1 - y0 + 1
	ring = Image.new("L", (w, h), 0)
	ImageDraw.Draw(ring).rounded_rectangle(
		(0, 0, w - 1, h - 1), radius=14, outline=255, width=3 if strength >= 1 else 2
	)
	image.paste(_spectrum(w, h, strength, TIER_STYLES["one_of_two"][0]), (x0, y0), ring)
	if strength >= 1:  # a faint holographic wash inside the badge
		inside = Image.new("L", (w, h), 0)
		ImageDraw.Draw(inside).rounded_rectangle((3, 3, w - 4, h - 4), radius=12, fill=34)
		image.paste(_spectrum(w, h, 1.0, (0, 0, 0)), (x0, y0), inside)


def _spectral_text(image: Image.Image, xy: tuple[int, int], text: str, font: ImageFont.FreeTypeFont) -> None:
	"""`text` filled with the holographic gradient."""
	box = ImageDraw.Draw(image).textbbox(xy, text, font=font)
	w, h = box[2] - xy[0] + 2, box[3] - xy[1] + 2
	mask = Image.new("L", (w, h), 0)
	ImageDraw.Draw(mask).text((0, 0), text, font=font, fill=255)
	image.paste(_spectrum(w, h, 1.0, (0, 0, 0)), xy, mask)


def _badge(image: Image.Image, draw, text: CardText, y: int) -> int:
	"""The rarity badge at `y`, laid out from its text's ink boxes with even padding; returns its bottom."""
	tier, iridescence = TIER_STYLES[text.tier]
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
	box = (LEFT, y, LEFT + LEFT_WIDTH, bottom)
	draw.rounded_rectangle(
		box, radius=14, fill=tuple(int(c * 0.12 + n * 0.88) for c, n in zip(tier, NAVY, strict=True))
	)
	if iridescence:
		_iridescent(image, box, iridescence)
	else:
		draw.rounded_rectangle(box, radius=14, outline=tier, width=2)
	if iridescence >= 1:  # the one-of-one's name shimmers through the spectrum
		_spectral_text(image, (LEFT + pad, y + pad - label_box[1]), label, label_font)
	else:
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
		y = _badge(image, draw, text, y + 8) + 24
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
