// AudioWorkletProcessor: forwards raw mono microphone frames (Float32) to the
// main thread. It intentionally writes nothing to its output, so nothing is
// played back through the speakers (no echo/feedback).
class PCMProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0][0];
    if (channel && channel.length) {
      // Copy — the underlying buffer is reused by the audio thread.
      this.port.postMessage(channel.slice(0));
    }
    return true; // keep the processor alive
  }
}

registerProcessor("pcm-processor", PCMProcessor);
