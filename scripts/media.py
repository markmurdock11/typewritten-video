"""Small FFmpeg helpers. Never installs tools or downloads media."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import wave
import numpy as np


def find_ffmpeg(explicit=None):
    """Resolve explicit argument, TYPEWRITTEN_FFMPEG, PATH, imageio_ffmpeg."""
    candidate = explicit or os.environ.get('TYPEWRITTEN_FFMPEG')
    if not candidate:
        candidate = shutil.which('ffmpeg')
    if not candidate:
        try:
            import imageio_ffmpeg
            candidate = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            pass
    if not candidate:
        raise FileNotFoundError('Supply --ffmpeg or TYPEWRITTEN_FFMPEG, or install FFmpeg/imageio-ffmpeg.')
    candidate = shutil.which(str(candidate)) or str(Path(candidate).expanduser().resolve())
    subprocess.run([candidate, '-version'], check=True, capture_output=True)
    return candidate


def encode_frames(ffmpeg, output, frames, width, height, fps, count):
    """Encode exactly count Pillow RGB frames; never reuse the prior output."""
    if min(width, height, fps, count) <= 0 or width % 2 or height % 2:
        raise ValueError('Positive dimensions/count/fps and even dimensions required')
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', f'{width}x{height}', '-r', str(fps), '-i', 'pipe:0', '-an', '-c:v', 'libx264',
               '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE)
    seen = 0
    try:
        for frame in frames:
            if frame.size != (width, height) or seen >= count:
                raise ValueError('Frame shape or count differs from requested export')
            proc.stdin.write(frame.convert('RGB').tobytes()); seen += 1
        proc.stdin.close()
        if proc.wait() or seen != count:
            raise RuntimeError(f'Encoding failed or incomplete: {seen}/{count} frames')
    except BaseException:
        proc.kill(); proc.wait(); output.unlink(missing_ok=True)
        raise
    return output


def mux_verify(ffmpeg, silent_video, wav, output, events, audio_audit):
    """Mux, fully decode, and compare decoded AAC timing to source PCM.

    Uses first three seconds containing audio; silence-only tracks skip sync
    correlation explicitly. Returns measurements, never claims a visual review.
    """
    raw = Path(events).read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw); audit = json.loads(Path(audio_audit).read_text())
    if digest != audit['source_sha256']:
        raise ValueError('Foley was generated from different events; regenerate it')
    duration = data['duration']; output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(silent_video), '-i', str(wav),
                    '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-ar', '48000',
                    '-t', str(duration), '-movflags', '+faststart', str(output)], check=True)
    decoded = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-progress', 'pipe:1', '-nostats',
                              '-i', str(output), '-f', 'null', '-'], capture_output=True, text=True)
    if decoded.returncode or decoded.stderr:
        raise RuntimeError(f'Export failed full decoding: {decoded.stderr}')
    frames = [int(line.split('=')[1]) for line in decoded.stdout.splitlines() if line.startswith('frame=')]
    if not frames or frames[-1] != round(duration*data['fps']):
        raise ValueError('Decoded video frame count differs from events')
    with wave.open(str(wav), 'rb') as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (48000, 2, 2):
            raise ValueError('Source WAV must be 48kHz, stereo, signed 16-bit PCM')
        x = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').reshape(-1, 2).mean(axis=1)/32768
    raw_audio = subprocess.check_output([ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', str(output), '-vn',
                                       '-ac', '1', '-ar', '48000', '-f', 'f32le', 'pipe:1'])
    y = np.frombuffer(raw_audio, dtype='<f4').astype(float)
    if abs(len(y)/48000-duration) > .025 or abs(len(x)/48000-duration) > 1/48000:
        raise ValueError('Encoded/source audio duration does not match events')
    audible = np.flatnonzero(np.abs(x) > .001); lag = None
    if len(audible):
        start = max(0, int(audible[0]) - 4800); end = min(len(x), start+3*48000)
        a, b = x[start:end], y[start:end]; n = 1 << (len(a)+len(b)-1).bit_length()
        corr = np.fft.irfft(np.fft.rfft(b, n)*np.conj(np.fft.rfft(a, n)), n)
        window = min(2400, n//2-1); candidates = np.r_[np.arange(window+1), np.arange(n-window, n)]
        lag = int(candidates[np.argmax(corr[candidates])]); lag = lag-n if lag > n//2 else lag
        if abs(lag) > 48:
            raise ValueError(f'Encoded audio offset exceeds 1 ms: {lag/48:.3f} ms')
    return {'file': str(output), 'bytes': output.stat().st_size, 'duration_seconds': duration,
            'fully_decoded': True, 'decoded_frames': frames[-1], 'aac_alignment_ms': lag/48 if lag is not None else None,
            'sync_check': 'cross-correlation' if lag is not None else 'skipped: silent source',
            'events_sha256': digest, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


def extract_frame(ffmpeg, video, seconds, output):
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(seconds), '-i', str(video),
                    '-frames:v', '1', str(output)], check=True)
