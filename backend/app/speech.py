"""Is there speech in a push-to-talk turn? A small energy check on 16 kHz mono PCM16, no dependencies.

A 20 ms frame counts as voiced when it is loud enough in absolute terms (PTT_SPEECH_RMS) and clearly above the
turn's own background (3x the quietest fifth of frames). Steady noise (compressor, traffic) lifts the
background with it, so it does not count; a click or bang is too short. A turn needs PTT_MIN_SPEECH_MS of
voiced audio, which a one-word command like "washing" easily has."""

from array import array

from app import config

RATE = 16000
FRAME = RATE // 50  # 20 ms
NOISE_FACTOR = 3.0


def frame_levels(pcm: bytes) -> list[float]:
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    levels = []
    for i in range(0, len(samples) - FRAME + 1, FRAME):
        frame = samples[i:i + FRAME]
        levels.append((sum(s * s for s in frame) / FRAME) ** 0.5)
    return levels


def voiced_ms(pcm: bytes) -> int:
    levels = frame_levels(pcm)
    if not levels:
        return 0
    floor = sorted(levels)[len(levels) // 5]
    threshold = max(config.PTT_SPEECH_RMS, NOISE_FACTOR * floor)
    return 20 * sum(1 for level in levels if level > threshold)


def has_speech(pcm: bytes) -> bool:
    return voiced_ms(pcm) >= config.PTT_MIN_SPEECH_MS
