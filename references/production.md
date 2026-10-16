# Production and verification

Use this when implementing, retiming, or exporting. The helpers use Python, Pillow, NumPy, and FFmpeg. `imageio-ffmpeg` is an optional way to supply the FFmpeg executable. Reuse an available runtime before installing anything.

## Project boundary

Keep the skill's reusable code separate from each film's source, assets, timing, and renders. A practical project holds:

- canonical source text and its revision identifier;
- the source-to-screen ledger and final display copy;
- a relative-path asset manifest with source URLs, credits, acquisition notes, and relevant usage constraints;
- the authored animation and its derived event JSON;
- preview frames, sound, and versioned final exports.

Do not bundle private essays, source captures, third-party portraits, proprietary fonts, or old episode media into a shared skill. The supplied demo uses original text and synthetic sound. The scripts should run without another episode's files.

## Portable primitives

`editor_layout.py` exposes rich-text rendering and character geometry. Font faces are configurable; the installed-font fallback must report which family it actually found. When exact typography matters, supply the actual available font files. Font substitution changes wrapping, so inspect both aspect ratios again. Do not redistribute a system font as an asset just because it is installed locally.

`foley.py` turns a visual event file into a stereo WAV and an audit. Its sound is synthesized, with no recorded samples or music. `media.py` resolves FFmpeg from an explicit argument, `TYPEWRITTEN_FFMPEG`, PATH, or the optional `imageio_ffmpeg` package. `smoke_demo.py` exercises the primitives in a short, original editor sequence. Use each script's `--help` for its current interface.

The demo is a working starting point, not a prescribed story structure or a finished production renderer. Adapt its state replay, document layout, and toolbar to the actual essay; add source browser panels as needed. Render only the requested formats in production.

From the skill directory, a short verification run is:

```sh
python scripts/smoke_demo.py --output /path/to/project/demo --ffmpeg /path/to/ffmpeg
python scripts/foley.py /path/to/project/events.json --output /path/to/project/foley.wav --audit /path/to/project/audio-audit.json
```

Omit `--ffmpeg` when discovery works. The demo defaults to a small preview resolution; use its `--width` option for another even width. `--font-map /path/to/fonts.json` supplies explicit installed or project font files, with relative paths resolved beside the JSON:

```json
{
  "Project Sans": {
    "regular": "fonts/regular.ttf",
    "bold": "fonts/bold.ttf",
    "italic": "fonts/italic.ttf",
    "bold_italic": "fonts/bold-italic.ttf"
  }
}
```

All four faces are required so an emphasized phrase does not silently fall back to another font. The demo reports the actual requested-to-rendered family mapping. Do not commit generated demo output into the skill package.

## Shared event contract

```json
{
  "fps": 60,
  "duration": 10,
  "keys": [
    {"frame": 6, "time": 0.1, "kind": "letter", "char": "H"}
  ]
}
```

- `fps` is an integer from 1 to 240. `duration` is positive and resolves to an integral number of frames.
- Each event requires an integer `frame`, a supported `kind`, and `char`. Frames are within the film and ordered. If `time` is present, it must equal `frame / fps` within the helper's tolerance; the frame is authoritative.
- Supported sound kinds are `letter`, `space`, `return`, `tab`, `backspace`, `click`, `paste`, `shortcut`, and `replace`. Use `char: ""` for a sound-producing action with no inserted text. A paste or replacement can carry its whole string.
- A `shortcut` requires `control`: `bold`, `italic`, `underline`, `size`, `font`, `highlight`, or `case`. A `replace` may use `control: "case"` or omit it. Include optional `paragraph`, selection range, and provenance fields where useful. The Foley helper does not prove those ranges or the final copy are correct. The visual replay must verify them.
- Pure selections, silent format preparation, camera motion, and reading holds belong in the animation state; do not invent keystrokes just to fill silence.

Quantize authored moments once, then derive `time` from `frame`. Keep sound and visuals on the same frame rate. Hash the exact event file used for the WAV; a new timing file invalidates the old soundtrack.

## Document state and camera

Model the actual edited text, not just an increasing character count. A replacement removes a known range and inserts new characters. A backspace removes the visible preceding character. A bold or case change operates on the selected span. Replay to a final state and compare it against the intended display copy.

For a continuous editor film, lay out all revealed paragraphs in one ordered document coordinate system before applying the camera offset. A scene may select the active passage, formatting action, or browser asset; it should not replace the visible document with only that scene's paragraphs. Move the camera using the active range's actual position. A transition between two complete page images does not establish document continuity. Inspect at least two exported section handoffs to verify that previous writing persists while the next passage enters.

Wrap using real font metrics, including bold and italic variants. Reserve space for italic overhang and underline depth. Derive selection rectangles and the caret from the same positions used for drawing glyphs.

Scroll toward revealed text, not a future paragraph endpoint. Keep the hook planted through its payoff. Give an exceptional thesis a different camera focus when needed. Account for the lower viewport when a browser dock appears. A paste badge or toolbar tooltip can obscure words even when the text layout itself is valid.

Give source assets their own framing plan: the establishing view, the detail the viewer needs, its attribution, and the time needed to see it. Use separate crops and dock proportions for each aspect ratio when necessary. Inspect important source detail at a phone-sized preview, roughly 360–430 pixels wide. Fitting the full image inside its panel is a geometry check, not a readability pass. If the relevant text becomes tiny, enlarge or reframe it rather than extending the hold. Keep identity and meaning intact when cropping; a clearly attributed exact excerpt is an option when the source pixels cannot support an adequate close-up.

For transcript views, keep source text and provenance separate from editorial context, identity labels, headshots, and timeline state. Reserve their space before measuring the quotation; verify the actual bold/italic wrapping and the densest completed reveal. Label a new message as a reply, forward, continuation, or separate document only when the source supports that relationship. Drive excerpt replacements, corresponding paste/Tab gestures, and timeline advances from the same schedule. Marker travel and quiet reading holds do not require fabricated key sounds.

When retiming a section, move its dependent panels, gestures, camera keys, chapter boundaries, and audio together. Preserve intentional reading holds outside the requested change. Update preview timestamps and export checks; stale checks can make the wrong cut appear verified.

## Sound behavior

The synthesized track uses short aperiodic transients, irregular foreground accents, and quieter ticks between them. Dense letters on the same video frame can combine into one actuation. Actual editing gestures remain distinct: a paste/shortcut/replacement uses a modifier-plus-key chord; Tab, Return, deletion, and browser clicks have different bodies.

Validate event coverage, frame alignment, finite audio samples, peak level, and silence outside event tails. An empty event list should produce silence. If the last sound's tail would run beyond the film, add a final hold instead of truncating it. Do not normalize every new version to a louder peak. Listen to the densest span, not just the pleasing slow opening.

## Export and checks

For this series, common outputs are 1080×1080 square and 1080×1350 portrait, at 60 fps, with H.264 video, yuv420p, and stereo 48 kHz AAC. These are established deliverable defaults, not a claim about every platform's current limits. Use the brief's format; verify current upload requirements if publication depends on them. Include fast-start metadata for a web-friendly MP4.

A useful release check has four parts:

1. **Meaning and text.** Compare the final replay to the source ledger. Verify names, dates, quotes, scores, required definitions, corrected typos, and newly authorized copy. Read the final display copy on its own, including the ending: the claim, support, reason to click, and closing connection must survive the cuts. Exact excerpts can still lose meaning when the connecting context is removed. Verify quotation authorship separately from editorial setup and forwarded material, and check the selected message’s recipient and date rather than inferring them from the whole thread.
2. **Visibility and pace.** Sample actual glyph bounds under scrolling, selections, badges, and browser docks. Check how long a whole sentence or title is fully visible, not just whether each word appeared once. Inspect each aspect ratio at phone viewing size and normal playback speed. Verify that both the editor text and the important source detail are readable without pausing or zooming. Include the densest connected exchange, headshot/name pairings, and every timeline handoff. Check whether a new viewer can follow the argument, not merely read individual words. Then inspect the longest holds and repeated handoffs for time that no longer serves comprehension. Geometric checks establish neither readability nor good pacing.
3. **Audio.** Confirm the current event hash, no clipping, audible distinct edits, quiet holds, and sync in the encoded AAC track. Measure or listen at more than the opening if timing was changed later in the film.
4. **Export.** Check duration, frame rate, dimensions, streams, and complete decoding of each delivered file. Inspect encoded frames from the changed sections. A successful render command alone does not establish a correct final video.

For a small revision, review the changed intervals and their neighboring transitions, then run the relevant export checks. Broaden the review only when a new problem or global change warrants it. Preserve the approved earlier file and use a new versioned output name.
