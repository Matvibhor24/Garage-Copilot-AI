"""The push-to-talk speech check on synthetic audio (16 kHz PCM16)."""

import math
import random
from array import array

from app import speech

RATE = 16000


def pcm(samples) -> bytes:
    return array("h", [max(-32768, min(32767, int(s))) for s in samples]).tobytes()


def silence(ms, level=20):
    rnd = random.Random(1)
    return [rnd.gauss(0, level) for _ in range(RATE * ms // 1000)]


def noise(ms, level):
    rnd = random.Random(2)
    return [rnd.gauss(0, level) for _ in range(RATE * ms // 1000)]


def voice(ms, level=4000):
    """A syllable-like burst: a 180 Hz voice with a 4 Hz rise and fall in loudness."""
    n = RATE * ms // 1000
    return [level * abs(math.sin(math.pi * 4 * i / RATE)) * math.sin(2 * math.pi * 180 * i / RATE) for i in range(n)]


def test_silent_taps_and_holds_have_no_speech():
    for ms in (200, 500, 1000):
        assert not speech.has_speech(pcm(silence(ms)))
    assert not speech.has_speech(b"")
    assert not speech.has_speech(b"\x01")


def test_steady_background_noise_is_not_speech():
    assert not speech.has_speech(pcm(noise(1000, 1500)))  # loud, steady (compressor, traffic)
    assert not speech.has_speech(pcm(noise(1000, 200)))   # quiet hiss


def test_a_click_is_too_short():
    click = silence(400) + [12000] * 160 + silence(400)  # 10 ms bang
    assert not speech.has_speech(pcm(click))


def test_a_short_command_counts_even_over_noise():
    assert speech.has_speech(pcm(silence(150) + voice(500) + silence(150)))  # "washing"
    background = noise(1200, 400)
    spoken = [b + v for b, v in zip(background, [0] * 3200 + voice(600) + [0] * 6400)]
    assert speech.has_speech(pcm(spoken))
    assert not speech.has_speech(pcm(silence(300) + voice(60) + silence(300)))  # clipped syllable
