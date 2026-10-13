// Audio format helpers for the voice gateway: mic Float32 at the device rate -> 16 kHz PCM16 out,
// agent PCM16 at 24 kHz -> Float32 for playback.

export const MIC_RATE = 16000
export const AGENT_RATE = 24000

// Average-based downsampling (good enough for speech; avoids aliasing better than dropping samples).
export function downsample(input, inRate, outRate = MIC_RATE) {
  if (inRate === outRate) return input
  const ratio = inRate / outRate
  const out = new Float32Array(Math.floor(input.length / ratio))
  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio)
    const end = Math.min(input.length, Math.floor((i + 1) * ratio))
    let sum = 0
    for (let j = start; j < end; j++) sum += input[j]
    out[i] = sum / Math.max(1, end - start)
  }
  return out
}

export function floatTo16(input) {
  const out = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}

export function int16ToFloat(buffer) {
  const ints = new Int16Array(buffer)
  const out = new Float32Array(ints.length)
  for (let i = 0; i < ints.length; i++) out[i] = ints[i] / 0x8000
  return out
}

export function rms(input) {
  let sum = 0
  for (let i = 0; i < input.length; i++) sum += input[i] * input[i]
  return Math.sqrt(sum / Math.max(1, input.length))
}
