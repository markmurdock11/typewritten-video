"""Standalone rich-text paragraph layout for the typewritten essay films.

Google textStyle font sizes are in points; scale defaults to 2.8 pixels per point.
The returned image has the requested width, with small internal safety margins.
All character boundaries (0 through len(chars)) receive a caret position.
"""
from functools import lru_cache
from pathlib import Path
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

FONT_MAP = {}
FONT_USAGE = {}
DEFAULT_FAMILY = None


def configure_fonts(config=None):
    """Load a JSON font map or discover an installed four-face sans family.

    JSON shape: {"Arial": {"regular": "font.ttf", "bold": "bold.ttf",
    "italic": "italic.ttf", "bold_italic": "bolditalic.ttf"}}.
    Relative paths resolve beside the JSON file. All four faces are required.
    Fonts are never downloaded. Unknown families use the discovered/default
    family and the actual choice is recorded by ``font_report()``.
    """
    global FONT_MAP, DEFAULT_FAMILY
    config = config or os.environ.get('TYPEWRITTEN_FONT_MAP')
    variants = ('regular', 'bold', 'italic', 'bold_italic')
    if config:
        path = Path(config).expanduser().resolve()
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict) or not raw:
            raise ValueError('Font map must be a nonempty family-to-faces object')
        mapping = {}
        for family, faces in raw.items():
            if not isinstance(faces, dict) or not all(v in faces for v in variants):
                raise ValueError(f'{family}: regular/bold/italic/bold_italic are required')
            mapping[family] = {}
            for variant in variants:
                font_path = Path(faces[variant]).expanduser()
                if not font_path.is_absolute():
                    font_path = path.parent / font_path
                if not font_path.is_file():
                    raise FileNotFoundError(font_path)
                mapping[family][variant] = str(font_path.resolve())
    else:
        windows = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        candidates = [
            ('Arial', Path('/System/Library/Fonts/Supplemental'),
             ('Arial.ttf', 'Arial Bold.ttf', 'Arial Italic.ttf', 'Arial Bold Italic.ttf')),
            ('Arial', windows, ('arial.ttf', 'arialbd.ttf', 'ariali.ttf', 'arialbi.ttf')),
            ('Liberation Sans', Path('/usr/share/fonts/truetype/liberation2'),
             tuple('LiberationSans-' + s + '.ttf' for s in ('Regular', 'Bold', 'Italic', 'BoldItalic'))),
            ('Liberation Sans', Path('/usr/share/fonts/truetype/liberation'),
             tuple('LiberationSans-' + s + '.ttf' for s in ('Regular', 'Bold', 'Italic', 'BoldItalic'))),
            ('DejaVu Sans', Path('/usr/share/fonts/truetype/dejavu'),
             ('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans-Oblique.ttf', 'DejaVuSans-BoldOblique.ttf')),
        ]
        mapping = {}
        for family, root, names in candidates:
            if all((root / name).is_file() for name in names):
                mapping[family] = dict(zip(variants, (str(root / name) for name in names)))
                break
        if not mapping:
            raise FileNotFoundError('No supported font family found. Supply --font-map JSON or TYPEWRITTEN_FONT_MAP.')
    FONT_MAP = mapping
    DEFAULT_FAMILY = next(iter(mapping))
    FONT_USAGE.clear()
    _load_font.cache_clear()
    return font_report()


def font_report():
    return {'default_family': DEFAULT_FAMILY, 'faces': FONT_MAP,
            'requested_to_actual': dict(FONT_USAGE)}


@lru_cache(maxsize=512)
def _load_font(family, bold, italic, pixel_size):
    if not FONT_MAP:
        configure_fonts()
    actual = family if family in FONT_MAP else DEFAULT_FAMILY
    FONT_USAGE[family] = actual
    variant = 'bold_italic' if bold and italic else 'bold' if bold else 'italic' if italic else 'regular'
    return ImageFont.truetype(FONT_MAP[actual][variant], max(1, pixel_size))


def getfont(style, scale=2.8):
    family = style.get('weightedFontFamily', {})
    name = family.get('fontFamily', style.get('fontFamily', 'Arial'))
    bold = bool(style.get('bold', False)) or family.get('weight', 400) >= 600
    size = style.get('fontSize', {}).get('magnitude', 15)
    return _load_font(name, bold, bool(style.get('italic', False)), max(1, round(size * scale)))


def color(style):
    foreground = style.get('foregroundColor', {})
    rgb = foreground.get('color', {}).get('rgbColor')
    if rgb is None:
        return (17, 85, 204) if style.get('link') else (0, 0, 0)
    return tuple(round(max(0, min(1, rgb.get(channel, 0))) * 255) for channel in ('red', 'green', 'blue'))


def _runs(chars):
    result = []
    for char, style in chars:
        if result and result[-1][1] == style:
            result[-1] = (result[-1][0] + char, style)
        else:
            result.append((char, style))
    return result


def text_width(chars, scale=2.8):
    """Measure rich-text runs with the same kerning used while drawing."""
    return sum(getfont(style, scale).getlength(string) for string, style in _runs(chars))


# Small public aliases for callers that already use these conventional names.
font = getfont
width = text_width
col = color


def _measure(entries, scale):
    return text_width([(char, style) for _, char, style in entries], scale)


def _wrap(segment, available, scale):
    words, word = [], []
    for entry in segment:
        word.append(entry)
        if entry[1] == ' ':
            words.append(word)
            word = []
    if word:
        words.append(word)
    lines, current = [], []

    def flush(trim=True):
        nonlocal current
        visible, discarded = list(current), []
        if trim:
            while visible and visible[-1][1] == ' ':
                discarded.append(visible.pop())
            discarded.reverse()
        lines.append((visible, discarded))
        current = []

    for word in words:
        if current and _measure(current + word, scale) > available:
            flush()
        if _measure(word, scale) <= available:
            current += word
            continue
        # Very long words also wrap, so temporary enlarged words cannot overflow.
        for entry in word:
            if current and _measure(current + [entry], scale) > available:
                flush()
            current.append(entry)
    if current or not lines:
        flush(trim=False)
    return lines


def render_paragraph(chars, width, base_style, indent=0, alignment='left',
                     selection=None, bullet=False, scale=2.8):
    """Return ``(RGBA image, {index: (x, baseline, font_px)})``.

    ``chars`` is a sequence of ``(character, Google textStyle)`` pairs. Selection
    is an optional half-open ``(start, end)`` character range. Width and indent
    are in pixels. Hard newlines are real characters with positions on each side.
    Line height grows with the largest font on that particular line; ordinary
    body lines retain a minimum height based on 15-point text.
    """
    pixel_width = max(1, math.ceil(width))
    if scale <= 0:
        raise ValueError('scale must be positive')
    if alignment not in ('left', 'center', 'right'):
        raise ValueError('alignment must be left, center, or right')
    base = {'weightedFontFamily': {'fontFamily': 'Arial', 'weight': 400},
            'fontSize': {'magnitude': 15, 'unit': 'PT'}, **(base_style or {})}
    styled = []
    for index, (char, style) in enumerate(chars):
        if len(char) != 1:
            raise ValueError('Each chars entry must contain exactly one character')
        complete = {**base, **style}
        if style.get('link') and 'foregroundColor' not in style:
            complete.pop('foregroundColor', None)
        styled.append((index, char, complete))
    # A consistent margin for body fonts through 30 points also protects the
    # overhang of italic f/j; larger display text expands it when necessary.
    maximum_size = max([30 * scale, getfont(base, scale).size] +
                       [getfont(style, scale).size for _, _, style in styled])
    horizontal_pad = max(2, math.ceil(maximum_size * .20) + 1)
    pad = max(2, math.ceil(scale))
    bullet_indent = 24 * scale / 2.8 if bullet else 0
    start_x = horizontal_pad + max(0, indent) + bullet_indent
    available = pixel_width - horizontal_pad - start_x
    if available <= 0:
        raise ValueError('width must leave room after padding, indent, and bullet')

    segments, segment, segment_start = [], [], 0
    for entry in styled:
        if entry[1] == '\n':
            segments.append((segment, segment_start, entry[0]))
            segment, segment_start = [], entry[0] + 1
        else:
            segment.append(entry)
    segments.append((segment, segment_start, None))
    lines = []
    for segment, segment_start, newline_index in segments:
        wrapped = _wrap(segment, available, scale)
        for local_index, (entries, discarded) in enumerate(wrapped):
            lines.append({'entries': entries, 'discarded': discarded,
                          'start': segment_start if local_index == 0 else None,
                          'newline': newline_index if local_index == len(wrapped) - 1 else None})

    # Ascents/descents come from actual fonts, including temporary large phrases.
    min_style = {**base, 'fontSize': {'magnitude': max(15, base.get('fontSize', {}).get('magnitude', 15)), 'unit': 'PT'}}
    minimum_font = getfont(min_style, scale)
    y = float(pad)
    for line in lines:
        styles = [style for _, _, style in line['entries']] or [base]
        fonts = [getfont(style, scale) for style in styles] + [minimum_font]
        ascent = max(f.getmetrics()[0] for f in fonts)
        descent = max(f.getmetrics()[1] for f in fonts)
        max_size = max(f.size for f in fonts)
        underline_depth = max((max(2, getfont(s, scale).size * .06) +
                               max(1, getfont(s, scale).size * .043)
                               for s in styles if s.get('underline')), default=0)
        # Account for every actual glyph; unusual ascenders/descenders stay safe.
        for string, style in _runs([(c, s) for _, c, s in line['entries']]):
            box = getfont(style, scale).getbbox(string, anchor='ls')
            ascent, descent = max(ascent, -box[1]), max(descent, box[3])
        descent = max(descent, underline_depth)
        natural_height = ascent + descent
        line_height = max(max_size * 1.36, natural_height + pad)
        leading = max(0, (line_height - natural_height) / 2)
        line['baseline'] = y + leading + ascent
        line['height'] = line_height
        line['max_size'] = max_size
        y += line_height
    image = Image.new('RGBA', (pixel_width, math.ceil(y + pad)), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    positions = {}
    for line_number, line in enumerate(lines):
        entries, baseline = line['entries'], line['baseline']
        measured = _measure(entries, scale)
        x = start_x + ((available - measured) / 2 if alignment == 'center' else
                       available - measured if alignment == 'right' else 0)
        initial_font_size = getfont(entries[0][2] if entries else base, scale).size
        if line['start'] is not None:
            positions[line['start']] = (x, baseline, initial_font_size)
        if bullet and line_number == 0:
            radius = max(2, 3 * scale / 2.8)
            bx, by = start_x - 17 * scale / 2.8, baseline - minimum_font.size * .3
            draw.ellipse((bx - radius, by - radius, bx + radius, by + radius), fill=(0, 0, 0, 255))
        rich_runs = []
        for index, char, style in entries:
            selected = selection is not None and selection[0] <= index < selection[1]
            if rich_runs and rich_runs[-1][1] == style and rich_runs[-1][2] == selected:
                rich_runs[-1][0] += char
                rich_runs[-1][3].append(index)
            else:
                rich_runs.append([char, style, selected, [index]])
        last_size = initial_font_size
        for string, style, selected, indices in rich_runs:
            current_font = getfont(style, scale)
            run_width = current_font.getlength(string)
            ascent, descent = current_font.getmetrics()
            background = style.get('backgroundColor', {}).get('color', {}).get('rgbColor')
            if background is not None and not selected:
                fill = tuple(round(background.get(c, 0)*255) for c in ('red','green','blue'))
                draw.rectangle((x-2, baseline-ascent, x+run_width+2, baseline+descent), fill=(*fill,255))
            if selected:
                draw.rectangle((math.floor(x), math.floor(baseline - ascent),
                                math.ceil(x + run_width), math.ceil(baseline + descent)),
                               fill=(185, 215, 255, 255))
            if hasattr(current_font,'draw_run'):
                current_font.draw_run(image,x,baseline,string,color(style))
            else:
                draw.text((x, baseline), string, font=current_font, fill=(*color(style), 255), anchor='ls')
            if style.get('underline'):
                underline_y = baseline + max(2, current_font.size * .06)
                draw.rectangle((x, underline_y, x + run_width,
                                underline_y + max(1, current_font.size * .043)),
                               fill=(*color(style), 255))
            for offset, index in enumerate(indices):
                positions[index] = (x + current_font.getlength(string[:offset]), baseline, current_font.size)
            x += run_width
            positions[indices[-1] + 1] = (x, baseline, current_font.size)
            last_size = current_font.size
        for index, _, style in line['discarded']:
            positions[index] = (x, baseline, getfont(style, scale).size)
            positions[index + 1] = (x, baseline, getfont(style, scale).size)
        if line['newline'] is not None:
            newline_index = line['newline']
            positions[newline_index] = (x, baseline, getfont(styled[newline_index][2], scale).size)
            if selection is not None and selection[0] <= newline_index < selection[1]:
                draw.rectangle((x, baseline - last_size * .95,
                                min(pixel_width - horizontal_pad, x + last_size * .22), baseline + last_size * .23),
                               fill=(185, 215, 255, 255))
        if line_number == len(lines) - 1:
            positions.setdefault(len(chars), (x, baseline, last_size))
    previous = positions.get(0, (start_x, lines[0]['baseline'], getfont(base, scale).size))
    for index in range(len(chars) + 1):
        if index in positions:
            previous = positions[index]
        else:
            positions[index] = previous
    return image, positions
