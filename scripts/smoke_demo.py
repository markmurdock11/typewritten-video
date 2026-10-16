"""Render an original 10-second helper demo, not a production episode template.

python smoke_demo.py --output /path/to/qa [--ffmpeg /path/to/ffmpeg]
                    [--font-map /path/to/fonts.json] [--width 432]
Requires Pillow and NumPy. Output belongs outside the published skill folder.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import wave
import numpy as np
from PIL import Image, ImageDraw
from editor_layout import configure_fonts, font_report, getfont, render_paragraph
from foley import render_file, synthesize, validate_events
from media import encode_frames, extract_frame, find_ffmpeg, mux_verify

FPS = 60
DURATION = 10
BASE = {'fontFamily': 'Arial', 'fontSize': {'magnitude': 16},
        'foregroundColor': {'color': {'rgbColor': {'red': .12, 'green': .12, 'blue': .14}}}}
PURPLE = {'color': {'rgbColor': {'red': .44, 'green': .24, 'blue': .75}}}
EXPECTED = 'Good ideas deserve a second look.\nONE thought. Many ways to see it.\nThis part arrives in one paste.'


def build_events():
    keys = []; frame = 12
    def add(at, kind, char='', **extra):
        keys.append({'frame': at, 'time': at/FPS, 'kind': kind, 'char': char, 'paragraph': 0, **extra})
    for char in 'Good ideas deserve a secodn':
        add(frame, 'space' if char == ' ' else 'letter', char); frame += 3
    frame += 12
    for char in 'nd':
        add(frame, 'backspace', char); frame += 5
    for char in 'nd look.':
        add(frame, 'space' if char == ' ' else 'letter', char); frame += 4
    add(174, 'shortcut', control='bold', start=0, end=10,
        updates={'bold': True, 'foregroundColor': PURPLE, 'fontSize': {'magnitude': 21}})
    add(204, 'return', '\n'); add(216, 'paste', 'One thought.')
    add(240, 'tab', ' '); add(250, 'paste', 'Many ways to see it.')
    add(278, 'return', '\n'); add(290, 'paste', 'This part arrives in one paste.')
    lo = EXPECTED.index('ONE')
    add(348, 'replace', 'ONE', start=lo, end=lo+3, removed='One', control='case')
    lo = EXPECTED.index('one paste.')
    add(396, 'shortcut', control='underline', start=lo, end=lo+10, updates={'underline': True})
    keys.sort(key=lambda event: event['frame'])
    return {'fps': FPS, 'duration': DURATION, 'keys': keys,
            'final_text': EXPECTED, 'note': 'Original demonstration copy, no external assets.'}


def replay(keys, frame):
    chars = []
    for event in keys:
        if event['frame'] > frame:
            break
        kind, char = event['kind'], event['char']
        if kind in ('letter', 'space', 'return', 'tab', 'paste'):
            chars += [(c, BASE.copy()) for c in char]
        elif kind == 'backspace':
            if not chars or chars[-1][0] != char:
                raise ValueError('Backspace does not match visible character')
            chars.pop()
        elif kind in ('replace', 'shortcut'):
            lo, hi = event['start'], event['end']
            if not 0 <= lo <= hi <= len(chars):
                raise ValueError('Selection lies outside current text')
            if kind == 'replace':
                if ''.join(c for c, _ in chars[lo:hi]) != event['removed']:
                    raise ValueError('Replacement does not match removed text')
                chars[lo:hi] = [(c, {**BASE, 'bold': True}) for c in char]
            else:
                chars[lo:hi] = [(c, {**style, **event['updates']}) for c, style in chars[lo:hi]]
    return chars


def draw_frame(data, width, height, frame):
    scale = 2.8*width/1080; r = width/1080
    chars = replay(data['keys'], frame); selection = None; badge = None
    for event in data['keys']:
        if event['kind'] in ('shortcut', 'replace') and event['frame']-12 <= frame < event['frame']+12:
            selection = (event['start'], event['end']); badge = event.get('control', 'edit').title()
        if event['kind'] in ('paste', 'tab') and event['frame'] <= frame < event['frame']+12:
            badge = 'Paste' if event['kind'] == 'paste' else 'Tab'
    image = Image.new('RGB', (width, height), 'white'); draw = ImageDraw.Draw(image)
    top = round(104*r)
    draw.rectangle((0, 0, width, top), fill='#f3f4f6')
    ui = getfont({'fontFamily': 'Arial', 'fontSize': {'magnitude': 12}}, scale)
    draw.text((25*r, 31*r), 'DRAFT  /  wordcel.mp4', font=ui, fill='#5f6066')
    draw.line((0, top, width, top), fill='#dddde2', width=1)
    layer, positions = render_paragraph(chars, width-64*r, BASE, selection=selection, scale=scale)
    x, y = round(32*r), round(top+44*r)
    if y+layer.height > height-40*r:
        raise ValueError('Demo text exceeds frame; adjust font/layout, not crop')
    image.paste(layer, (x, y), layer)
    if selection is None and (frame < 400 or (frame//30) % 2 == 0):
        cx, cy, size = positions[len(chars)]
        draw.line((x+cx, y+cy-size, x+cx, y+cy+size*.15), fill='#703dbe', width=max(1, round(3*r)))
    if badge:
        left = width-200*r; draw.rounded_rectangle((left, top+8*r, width-20*r, top+44*r), radius=5*r, fill='#eee8f6')
        draw.text((left+12*r, top+11*r), badge, font=ui, fill='#703dbe')
    return image


def guard_checks(output):
    empty = {'fps': 60, 'duration': 1, 'keys': []}
    report = synthesize(empty, output/'silence-check.wav')
    assert report['silent'] and report['visual_events'] == 0
    with wave.open(str(output/'silence-check.wav'), 'rb') as wav:
        assert not np.any(np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2'))
    failures = [dict(empty, fps=0), dict(empty, duration=float('nan')),
                dict(empty, keys=[{'frame': 60, 'kind': 'letter', 'char': 'a'}]),
                dict(empty, keys=[{'frame': 1, 'time': .5, 'kind': 'letter', 'char': 'a'}]),
                dict(empty, keys=[{'frame': 1, 'kind': 'unknown', 'char': ''}])]
    for bad in failures:
        try:
            validate_events(bad)
        except ValueError:
            continue
        raise AssertionError('Invalid event contract was accepted')
    try:
        synthesize(dict(empty, keys=[{'frame': 59, 'kind': 'paste', 'char': 'Too late'}]), output/'invalid-tail.wav')
    except ValueError as error:
        assert 'event tail' in str(error)
    else:
        raise AssertionError('An event tail was silently truncated')
    return {'silent_track': True, 'invalid_contracts_rejected': len(failures), 'truncated_tail_rejected': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True); parser.add_argument('--ffmpeg'); parser.add_argument('--font-map')
    parser.add_argument('--width', type=int, default=432); args = parser.parse_args()
    if args.width < 320 or args.width % 8:
        parser.error('--width must be at least 320 and a multiple of 8, for even 4:5 dimensions')
    out = Path(args.output).expanduser().resolve(); out.mkdir(parents=True, exist_ok=True)
    configure_fonts(args.font_map); ffmpeg = find_ffmpeg(args.ffmpeg); data = build_events(); validate_events(data)
    final = ''.join(c for c, _ in replay(data['keys'], FPS*DURATION-1))
    assert final == EXPECTED
    event_path = out/'events.json'; event_path.write_text(json.dumps(data, indent=2))
    audio = out/'foley.wav'; audit = out/'audio-audit.json'; sound = render_file(event_path, audio, audit)
    results = []; proofs = [(1.6, 'typo'), (2.9, 'bold'), (4.05, 'tab'), (5, 'paste'), (5.8, 'case'), (6.6, 'underline'), (8, 'hold')]
    for name, height in [('square', args.width), ('portrait', args.width*5//4)]:
        silent = out/f'{name}-silent.mp4'; target = out/f'{name}.mp4'
        frames = (draw_frame(data, args.width, height, frame) for frame in range(FPS*DURATION))
        encode_frames(ffmpeg, silent, frames, args.width, height, FPS, FPS*DURATION)
        report = mux_verify(ffmpeg, silent, audio, target, event_path, audit)
        report.update({'width': args.width, 'height': height, 'fps': FPS, 'frames': FPS*DURATION}); results.append(report)
        for seconds, label in proofs:
            extract_frame(ffmpeg, target, seconds, out/f'{name}-{label}.png')
        print(f'Rendered and decoded {target}', flush=True)
    report = {'original_demo_copy': True, 'final_text_verified': final, 'fonts': font_report(),
              'guards': guard_checks(out), 'audio_peak_dbfs': sound['peak_dbfs'], 'exports': results,
              'events_sha256': hashlib.sha256(event_path.read_bytes()).hexdigest()}
    (out/'smoke-audit.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
