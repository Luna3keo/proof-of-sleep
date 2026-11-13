"""Voices the demo script with Kokoro, an open-weights text-to-speech model that runs locally.

Needs its own environment:  pip install kokoro-onnx numpy imageio-ffmpeg
and the two model files from github.com/thewh1teagle/kokoro-onnx (model-files-v1.0).

    python video/make_voice.py --model-dir path/to/models

Writes video/out/voice.wav, music.wav and timeline.json, which video/make_film.py reads.
"""
import argparse
import hashlib
import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from script import MOODS, script  # noqa: E402

OUT = HERE / "out"
VOICE = "af_heart"
RATE = 24_000
MUSIC_RATE = 48_000
LIMIT_SECONDS = 140          # X's limit for a standard account
LEAD_IN, TAIL = 0.35, 0.8


def write_wav(path, samples, rate):
    data = np.clip(samples, -1, 1)
    pcm = (data * 32767).astype("<i2")
    channels = 1 if pcm.ndim == 1 else pcm.shape[1]
    raw = pcm.tobytes()
    head = b"RIFF" + (36 + len(raw)).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
    head += (1).to_bytes(2, "little") + channels.to_bytes(2, "little") + rate.to_bytes(4, "little")
    head += (rate * channels * 2).to_bytes(4, "little") + (channels * 2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    pathlib.Path(path).write_bytes(head + b"data" + len(raw).to_bytes(4, "little") + raw)


def level(samples, target_db):
    window = RATE // 50
    frames = samples[: len(samples) // window * window].reshape(-1, window)
    energy = np.sqrt(np.mean(np.square(frames), axis=1))
    voiced = frames[energy > max(energy.max() * 0.12, 1e-4)]
    rms = np.sqrt(np.mean(np.square(voiced))) if len(voiced) else np.sqrt(np.mean(np.square(samples)))
    return samples * 10 ** ((target_db - 20 * np.log10(rms + 1e-9)) / 20)


def fade(samples, ms=12):
    n = min(int(RATE * ms / 1000), len(samples) // 2)
    if n:
        ramp = np.linspace(0, 1, n)
        samples = samples.copy()
        samples[:n] *= ramp
        samples[-n:] *= ramp[::-1]
    return samples


def perform(engine, entry):
    mood = MOODS[entry["mood"]]
    key = hashlib.sha256(json.dumps([VOICE, entry["say"], mood]).encode()).hexdigest()[:20]
    cached = OUT / "lines" / f"{key}.npy"
    if cached.exists():
        return np.load(cached)
    lift = 1 + mood["pitch"]
    samples, rate = engine.create(entry["say"], voice=VOICE, speed=float(mood["speed"] / lift), lang="en-us")
    assert rate == RATE
    samples = np.asarray(samples, dtype=np.float32)
    if abs(lift - 1) > 1e-6:
        positions = np.arange(0, len(samples) - 1, lift)
        samples = np.interp(positions, np.arange(len(samples)), samples).astype(np.float32)
    samples = fade(level(samples, -20 + mood["gain"]))
    cached.parent.mkdir(parents=True, exist_ok=True)
    np.save(cached, samples)
    return samples


def soundtrack(duration, speech_spans):
    """A quiet pad synthesised here, so there is nothing to license. It ducks under speech."""
    t = np.arange(int(duration * MUSIC_RATE)) / MUSIC_RATE
    chords = [(110.0, 164.81, 220.0, 277.18), (98.0, 146.83, 196.0, 246.94), (87.31, 130.81, 174.61, 220.0), (98.0, 146.83, 196.0, 293.66)]
    bar = 8.0
    pad = np.zeros_like(t)
    for i in range(int(duration // bar) + 2):
        start, freqs = i * bar, chords[i % len(chords)]
        env = np.clip((t - start) / 2.0, 0, 1) * np.clip((start + bar + 2.0 - t) / 2.0, 0, 1)
        for j, f in enumerate(freqs):
            pad += env * (0.5 / (j + 1)) * np.sin(2 * np.pi * f * t + i * 0.7 + j)
    pad /= np.max(np.abs(pad)) + 1e-9
    gate = np.full_like(t, 1.0)
    for a, b in speech_spans:
        gate[int(max(a - 0.25, 0) * MUSIC_RATE): int((b + 0.25) * MUSIC_RATE)] = 0.35
    width = int(0.35 * MUSIC_RATE)              # smooth the ducking with a moving average
    running = np.cumsum(np.concatenate([np.full(width, gate[0]), gate, np.full(width, gate[-1])]))
    gate = (running[width:] - running[:-width])[width // 2: width // 2 + len(gate)] / width
    music = pad * gate * 10 ** (-16 / 20)
    edge = np.clip(t / 2.0, 0, 1) * np.clip((duration - t) / 2.5, 0, 1)
    music *= edge
    return np.stack([music, music], axis=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    from kokoro_onnx import Kokoro
    model = pathlib.Path(args.model_dir)
    engine = Kokoro(str(model / "kokoro-v1.0.onnx"), str(model / "voices-v1.0.bin"))

    takes = script()
    parts = [np.zeros(int(LEAD_IN * RATE), dtype=np.float32)]
    at = LEAD_IN
    timeline = {"takes": [], "voice": "kokoro-" + VOICE}
    spans = []
    for take in takes:
        entry = {"name": take["name"], "label": take["label"], "start": at, "lines": []}
        for line in take["lines"]:
            speech = perform(engine, line)
            start, end = at, at + len(speech) / RATE
            entry["lines"].append({"mark": line["mark"], "show": line["show"], "start": start, "end": end})
            spans.append((start, end))
            parts += [speech, np.zeros(int(line["pause"] * RATE), dtype=np.float32)]
            at = end + line["pause"]
        entry["end"] = at
        timeline["takes"].append(entry)
        print(take["name"], f"{entry['start']:.1f}-{at:.1f}s", flush=True)
    parts.append(np.zeros(int(TAIL * RATE), dtype=np.float32))
    at += TAIL
    voice = np.concatenate(parts)
    timeline["duration"] = len(voice) / RATE
    write_wav(OUT / "voice.wav", voice, RATE)
    write_wav(OUT / "music.wav", soundtrack(timeline["duration"], spans), MUSIC_RATE)
    (OUT / "timeline.json").write_text(json.dumps(timeline, indent=1), encoding="utf-8")
    print(f"total {timeline['duration']:.1f}s (limit {LIMIT_SECONDS}s)")
    if timeline["duration"] > LIMIT_SECONDS:
        print("TOO LONG: shorten the script", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
