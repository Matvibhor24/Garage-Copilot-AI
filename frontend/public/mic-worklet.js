// Runs on the audio thread: forwards raw mic frames (Float32, device sample rate) to the page.
class MicCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (ch) this.port.postMessage(ch.slice(0))
    return true
  }
}
registerProcessor('mic-capture', MicCapture)
