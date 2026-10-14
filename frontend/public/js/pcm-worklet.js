// AudioWorklet: captures the microphone, downsamples to 16 kHz mono and posts 40 ms Int16 chunks.
class Pcm16kProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.pos = 0;
    this.acc = 0;
    this.count = 0;
    this.chunk = new Int16Array(640);
    this.filled = 0;
    this.energy = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      this.acc += channel[i];
      this.count += 1;
      this.pos += 1;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        const sample = Math.max(-1, Math.min(1, this.acc / this.count));
        this.acc = 0;
        this.count = 0;
        this.energy += sample * sample;
        this.chunk[this.filled++] = sample < 0 ? sample * 32768 : sample * 32767;
        if (this.filled === this.chunk.length) {
          const rms = Math.sqrt(this.energy / this.filled);
          this.port.postMessage({ pcm: this.chunk.buffer, rms }, [this.chunk.buffer]);
          this.chunk = new Int16Array(640);
          this.filled = 0;
          this.energy = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("pcm16k", Pcm16kProcessor);
