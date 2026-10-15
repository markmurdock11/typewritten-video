# Typewritten Video

A Codex skill for turning essays into videos that feel like a live word-editor session: typing, selecting, revising, formatting, and exploring references, with synchronized keyboard sound.

Built from the Kurate essay-video workflow. The latest guidance emphasizes brisk pacing, source visuals you can read on a phone, one continuous document, and endings that preserve the argument and recommendation.

The package includes editorial guidance, reusable Python helpers, and a short original demo. Each film still needs editorial and visual direction.

## Try it

Download or clone the whole repository so the references and helper scripts stay together. Give Codex access to the folder, then ask it to read [SKILL.md](SKILL.md) and apply it to your essay.

Include your source text or document, approximate runtime, intended platforms and aspect ratios, whether cuts or rewrites are allowed, and any typography or audio preferences.

For example:

> Read SKILL.md and use Typewritten Video to make a roughly 90-second film from this essay. You may shorten it while preserving the argument and ending. Export a square version, keep the typing prominent, and show readable browser cutaways. Use bold, italics, underlining, and a few plausible corrections where they help the writing land.

## What's included

- [SKILL.md](SKILL.md): the creative and production workflow.
- [Editing playbook](references/editing-playbook.md): pacing, emphasis, source imagery, timelines, and endings.
- [Production guidance](references/production.md): setup, font configuration, timing, sound, demo commands, and export checks.
- [Scripts](scripts): text layout, synthetic keyboard sound, media export helpers, and a runnable original demo.

## Dependencies

Python, Pillow, NumPy, and FFmpeg. `imageio-ffmpeg` is an optional FFmpeg source. Reuse an available runtime where possible.

Fonts are supplied by your environment or project. The package contains no private essays, third-party portraits, proprietary fonts, or previous episode media.
