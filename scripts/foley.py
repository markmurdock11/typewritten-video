"""Synthetic, frame-locked keyboard Foley. Requires NumPy; no sample assets.

CLI: python foley.py events.json --output foley.wav [--audit audit.json]
Contract: fps is an integer 1..240; duration is positive and an integral number
of frames; keys is a list of {frame: int, kind: str, char: str, time?: seconds}.
Frame is authoritative. Optional time must equal frame/fps within 1 microsecond.
Kinds: letter, space, return, tab, backspace, click, paste, shortcut, replace.
Shortcut requires control: bold/italic/underline/size/font/highlight/case.
Replace permits control 'case' or no control. Empty key lists render silence.
Additional metadata is allowed; visual replacement semantics belong to renderer.
"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import math
import wave
import numpy as np

SR = 48000
PRIORITY = {'letter': 0, 'space': 1, 'click': 2, 'return': 3, 'tab': 3,
            'backspace': 4, 'paste': 5, 'shortcut': 6, 'replace': 7}
CONTROLS = {'bold': 27, 'italic': 31, 'underline': 24, 'size': 29,
            'font': 33, 'highlight': 25, 'case': 22, 'paste': 26}
CHORDS = {'paste', 'shortcut', 'replace'}


def validate_events(data):
    fps, duration, keys = data.get('fps'), data.get('duration'), data.get('keys')
    if type(fps) is not int or not 1 <= fps <= 240:
        raise ValueError('fps must be an integer from 1 to 240')
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('duration must be positive and finite')
    if not math.isfinite(fps * duration):
        raise ValueError('duration is too large')
    count = round(fps * duration)
    if abs(count - fps * duration) > 1e-6:
        raise ValueError('duration must contain an integral number of frames')
    if not isinstance(keys, list):
        raise ValueError('keys must be a list, possibly empty')
    for index, event in enumerate(keys):
        if not isinstance(event, dict):
            raise ValueError(f'Event {index} must be an object')
        frame, kind, char = event.get('frame'), event.get('kind'), event.get('char')
        if type(frame) is not int or not 0 <= frame < count:
            raise ValueError(f'Event {index}: frame is outside the film')
        if kind not in PRIORITY or not isinstance(char, str):
            raise ValueError(f'Event {index}: unsupported kind or missing string char')
        if 'time' in event:
            value = event['time']
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value-frame/fps) > 1e-6:
                raise ValueError(f'Event {index}: time differs from frame/fps')
        if kind == 'letter' and (len(char) != 1 or char.isspace()):
            raise ValueError(f'Event {index}: letter requires one non-whitespace character')
        if kind in ('space', 'return', 'tab') and char not in {'space': (' ',), 'return': ('\n',), 'tab': (' ', '\t')}[kind]:
            raise ValueError(f'Event {index}: invalid whitespace character')
        if kind == 'paste' and not char:
            raise ValueError(f'Event {index}: empty paste')
        if kind == 'shortcut' and event.get('control') not in set(CONTROLS)-{'paste'}:
            raise ValueError(f'Event {index}: unknown shortcut control')
        if kind == 'replace' and event.get('control') not in (None, 'case'):
            raise ValueError(f'Event {index}: unknown replacement control')
    return fps, float(duration), keys


def noise(rng, n, low, high):
    white = rng.normal(0, 1, n)
    signal = np.convolve(white, np.ones(low)/low, 'same') - np.convolve(white, np.ones(high)/high, 'same')
    return signal / max(np.sqrt(np.mean(signal*signal)), 1e-8)


def stroke(rng, kind, dense, accent):
    length = rng.uniform(.0105, .013) if dense and accent else rng.uniform(.0025, .0038)
    if not dense:
        length = rng.uniform(.016, .024)
    special = {'return': .024, 'tab': .019, 'backspace': .014, 'click': .007, 'modifier': .014}
    length = special.get(kind, length)
    n = round(length*SR); t = np.arange(n)/SR
    edge = noise(rng, n, 2, int(rng.integers(6, 10)))
    body = noise(rng, n, int(rng.integers(6, 13)), int(rng.integers(33, 53)))
    tau = rng.uniform(.002, .0034) if accent else rng.uniform(.00065, .0012)
    if not dense:
        tau = rng.uniform(.003, .004)
    tau = {'backspace': .0019, 'return': .003, 'tab': .0024, 'modifier': .0017, 'click': .00065}.get(kind, tau)*.85
    signal = .24*edge*np.exp(-t/rng.uniform(.00018, .00032)) + .95*body*np.exp(-t/tau)
    if not dense or kind in special:
        release = {'backspace': .006, 'return': .011, 'tab': .009, 'modifier': .007}.get(kind, rng.uniform(.007, .010))
        signal += .1*noise(rng, n, 3, 17)*np.exp(-np.maximum(0, t-release)/.0007)*(t >= release)
    envelope = np.minimum(1, t/.000065)*np.minimum(1, np.maximum(0, length-t)/.0005)
    signal *= envelope
    signal = (signal-np.mean(signal))*envelope
    return signal/max(np.max(np.abs(signal)), 1e-8)


def synthesize(data, output, *, source_sha256=None, gain=.557, seed=98471032):
    fps, duration, keys = validate_events(data)
    if not math.isfinite(gain) or not 0 < gain <= 1:
        raise ValueError('gain must be in (0, 1]')
    rng = np.random.default_rng(seed); n = round(SR*duration)
    mix = np.zeros((n, 2), dtype=np.float64); frames = defaultdict(list)
    for index, event in enumerate(keys):
        frames[event['frame']].append((index, event))
    ordered = sorted(frames); audit = []; next_accent = -1; prior_paragraph = None
    for i, frame in enumerate(ordered):
        group = frames[frame]; ordinary = [(j, e) for j, e in group if e['kind'] in ('letter', 'space')]
        groups = ([ordinary] if ordinary else []) + [[pair] for pair in group if pair[1]['kind'] not in ('letter', 'space')]
        before = (frame-ordered[i-1])/fps if i else 1
        after = (ordered[i+1]-frame)/fps if i+1 < len(ordered) else 1
        dense = min(before, after) <= .050001
        paragraph = group[0][1].get('paragraph')
        accent = not dense or frame >= next_accent or before > .085 or paragraph != prior_paragraph
        if accent:
            next_accent = frame+max(1, round(rng.choice([3, 4, 5])*fps/60))
        for pairs in groups:
            event = max((e for _, e in pairs), key=lambda e: PRIORITY[e['kind']])
            kind = event['kind']; special = kind not in ('letter', 'space'); offsets = None
            if kind in CHORDS:
                control = 'paste' if kind == 'paste' else 'case' if kind == 'replace' else event['control']
                modifier = stroke(rng, 'modifier', False, True); key = stroke(rng, 'letter', False, True)
                offset = round((CONTROLS[control]+rng.uniform(-1.2, 1.2))*SR/1000)
                signal = np.zeros(offset+len(key)); signal[:len(modifier)] += .60*modifier; signal[offset:] += .87*key
                offsets = [0, offset]
            else:
                signal = stroke(rng, kind, dense, accent or special)
            level = {'backspace': .84, 'return': .70, 'tab': .65, 'click': .46, 'paste': .60, 'shortcut': .66, 'replace': .66}.get(kind)
            level = level*rng.uniform(.91, 1.08) if special else rng.uniform(.57, .94) if accent else rng.uniform(.055, .115)
            level /= math.sqrt(len(groups))
            pan = -.13 if kind == 'backspace' else .11 if kind == 'return' else rng.uniform(-.20, .20)
            sample = round(frame/fps*SR)
            if sample+len(signal) > n:
                raise ValueError('An event tail exceeds the film. Add a final reading hold; do not cut the sound.')
            signal = signal*level
            theta = (pan+1)*math.pi/4
            mix[sample:sample+len(signal)] += signal[:, None]*np.array([math.cos(theta), math.sin(theta)])
            audit.append({'frame': frame, 'sample': sample, 'kind': kind, 'source_indices': [j for j, _ in pairs],
                          'foreground': bool(accent or special), 'samples': len(signal), 'chord_offsets': offsets})
        prior_paragraph = paragraph
    mix *= gain; peak = float(np.max(np.abs(mix)))
    if peak >= 1:
        raise ValueError(f'Audio would clip ({peak:.3f}); reduce --gain, do not normalize blindly')
    pcm = np.rint(mix*32767).astype('<i2'); permitted = np.zeros(n, dtype=bool)
    for item in audit:
        permitted[item['sample']:item['sample']+item['samples']] = True
    covered = sorted(index for item in audit for index in item['source_indices'])
    assert covered == list(range(len(keys))) and not np.any(pcm[~permitted])
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), 'wb') as wav:
        wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(SR); wav.writeframes(pcm.tobytes())
    return {'source_sha256': source_sha256, 'duration': duration, 'fps': fps, 'sample_rate': SR,
            'sample_frames': n, 'visual_events': len(keys), 'actuations': audit, 'seed': seed, 'gain': gain,
            'peak_dbfs': 20*math.log10(peak) if peak else None, 'silent': peak == 0,
            'event_counts': dict(Counter(e['kind'] for e in keys)), 'all_events_covered': True,
            'silent_outside_event_tails': True, 'clipped_samples': int(np.sum(np.abs(pcm.astype(np.int32)) >= 32767)),
            'maximum_frame_alignment_error_ms': max((abs(a['sample']/SR-a['frame']/fps)*1000 for a in audit), default=0)}


def render_file(source, output, audit=None, *, gain=.557, seed=98471032):
    source = Path(source); raw = source.read_bytes()
    report = synthesize(json.loads(raw), output, source_sha256=hashlib.sha256(raw).hexdigest(), gain=gain, seed=seed)
    if source.read_bytes() != raw:
        raise RuntimeError('Events changed while rendering Foley; regenerate it')
    audit = Path(audit) if audit else Path(output).with_suffix('.audit.json')
    audit.parent.mkdir(parents=True, exist_ok=True); audit.write_text(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('events'); parser.add_argument('--output', required=True); parser.add_argument('--audit')
    parser.add_argument('--gain', type=float, default=.557); parser.add_argument('--seed', type=int, default=98471032)
    args = parser.parse_args(); report = render_file(args.events, args.output, args.audit, gain=args.gain, seed=args.seed)
    print(json.dumps({k: v for k, v in report.items() if k != 'actuations'}, indent=2))
