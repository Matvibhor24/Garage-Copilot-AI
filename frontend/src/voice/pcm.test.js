import { describe, expect, it } from 'vitest'
import { downsample, floatTo16, int16ToFloat, rms } from './pcm.js'

describe('pcm helpers', () => {
  it('downsamples 48 kHz to 16 kHz by averaging', () => {
    const out = downsample(new Float32Array([0.3, 0.3, 0.3, -0.6, -0.6, -0.6]), 48000, 16000)
    expect(Array.from(out).map((x) => +x.toFixed(2))).toEqual([0.3, -0.6])
  })
  it('round-trips PCM16 and clips', () => {
    const ints = floatTo16(new Float32Array([0, 0.5, -0.5, 2, -2]))
    expect(Array.from(ints)).toEqual([0, 16383, -16384, 32767, -32768])
    const back = int16ToFloat(ints.buffer)
    expect(+back[1].toFixed(2)).toBe(0.5)
  })
  it('measures level', () => {
    expect(rms(new Float32Array([0.5, -0.5]))).toBeCloseTo(0.5)
  })
})
