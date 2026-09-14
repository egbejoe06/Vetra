// ==============================================================================
// 16kHz PCM Audio Capture — AudioWorkletNode (replaces deprecated ScriptProcessorNode)
// Downsamples microphone input to 16kHz mono 16-bit Little-Endian PCM chunks.
// ==============================================================================

export type AudioChunkCallback = (base64Pcm: string) => void
export type AudioLevelCallback = (level: number) => void

// ---------------------------------------------------------------------------
// Inline AudioWorklet processor source
// Runs on a dedicated audio rendering thread.
// ---------------------------------------------------------------------------
const WORKLET_CODE = /* js */ `
class Pcm16Processor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._sourceSampleRate = sampleRate; // global provided by AudioWorkletGlobalScope
    this._ratio = this._sourceSampleRate / 16000;
    this._buffer = [];
    this._chunkSamples = Math.round(4096 / this._ratio); // ~equivalent to 4096-frame ScriptProcessor chunks
  }

  static get parameterDescriptors() { return []; }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const channel = input[0];

    // Accumulate until we have enough for a resample chunk
    for (let i = 0; i < channel.length; i++) {
      this._buffer.push(channel[i]);
    }

    while (this._buffer.length >= Math.round(this._chunkSamples * this._ratio)) {
      const needed = Math.round(this._chunkSamples * this._ratio);
      const slice = this._buffer.splice(0, needed);

      // Compute RMS level (0-100)
      let sumSq = 0;
      for (let i = 0; i < slice.length; i++) sumSq += slice[i] * slice[i];
      const rms = Math.sqrt(sumSq / slice.length);
      const level = Math.min(100, Math.round(rms * 400));

      // Downsample to 16 kHz (linear interpolation averaging)
      const outLen = Math.round(slice.length / this._ratio);
      const out = new Float32Array(outLen);
      for (let r = 0; r < outLen; r++) {
        const nextOff = Math.round((r + 1) * this._ratio);
        let accum = 0, count = 0;
        for (let k = Math.round(r * this._ratio); k < nextOff && k < slice.length; k++) {
          accum += slice[k];
          count++;
        }
        out[r] = count > 0 ? accum / count : 0;
      }

      // Float32 -> Int16 PCM
      const pcm = new Int16Array(out.length);
      for (let i = 0; i < out.length; i++) {
        const s = Math.max(-1, Math.min(1, out[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }

      // Post to main thread (transfer ownership for zero-copy)
      this.port.postMessage({ level, pcm: pcm.buffer }, [pcm.buffer]);
    }

    return true; // keep processor alive
  }
}

registerProcessor('pcm16-processor', Pcm16Processor);
`

function buildWorkletBlobUrl(): string {
  const blob = new Blob([WORKLET_CODE], { type: 'application/javascript' })
  return URL.createObjectURL(blob)
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = ''
  const bytes = new Uint8Array(buffer)
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i] ?? 0)
  }
  return window.btoa(binary)
}

// ---------------------------------------------------------------------------
// AudioCaptureService
// ---------------------------------------------------------------------------
export class AudioCaptureService {
  private mediaStream: MediaStream | null = null
  private audioContext: AudioContext | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private workletNode: AudioWorkletNode | null = null
  // Legacy fallback (older browsers)
  private processorNode: ScriptProcessorNode | null = null
  private onAudioChunk: AudioChunkCallback | null = null
  private onAudioLevel: AudioLevelCallback | null = null
  private isCapturing = false
  private isMuted = false
  private _workletBlobUrl: string | null = null

  public async start(
    onChunk: AudioChunkCallback,
    onLevel?: AudioLevelCallback,
  ): Promise<void> {
    if (this.isCapturing) return

    this.onAudioChunk = onChunk
    if (onLevel) this.onAudioLevel = onLevel

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      })

      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext
      this.audioContext = new AudioCtx()
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume()
      }
      this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream)

      const useWorklet = typeof AudioWorkletNode !== 'undefined' && this.audioContext.audioWorklet

      if (useWorklet) {
        await this._startWithWorklet()
      } else {
        this._startWithScriptProcessor()
      }

      this.isCapturing = true
    } catch (err) {
      console.error('[AudioCapture] Failed to initialize microphone stream:', err)
      throw err
    }
  }

  // -------------------------------------------------------------------------
  // AudioWorkletNode path (modern browsers)
  // -------------------------------------------------------------------------
  private async _startWithWorklet(): Promise<void> {
    if (!this.audioContext || !this.sourceNode) return

    this._workletBlobUrl = buildWorkletBlobUrl()
    await this.audioContext.audioWorklet.addModule(this._workletBlobUrl)

    this.workletNode = new AudioWorkletNode(this.audioContext, 'pcm16-processor', {
      numberOfInputs: 1,
      numberOfOutputs: 0,
      channelCount: 1,
    })

    this.workletNode.port.onmessage = (event: MessageEvent) => {
      if (!this.isCapturing || this.isMuted) {
        if (this.onAudioLevel) this.onAudioLevel(0)
        return
      }

      const { level, pcm } = event.data as { level: number; pcm: ArrayBuffer }

      if (this.onAudioLevel) this.onAudioLevel(level)

      if (pcm && pcm.byteLength > 0 && this.onAudioChunk) {
        const base64 = arrayBufferToBase64(pcm)
        if (base64) this.onAudioChunk(base64)
      }
    }

    this.sourceNode.connect(this.workletNode)
  }

  // -------------------------------------------------------------------------
  // ScriptProcessorNode fallback (older Safari / browsers without AudioWorklet)
  // -------------------------------------------------------------------------
  private _startWithScriptProcessor(): void {
    if (!this.audioContext || !this.sourceNode) return

    const sampleRate = this.audioContext.sampleRate
    const bufferSize = 4096
    this.processorNode = this.audioContext.createScriptProcessor(bufferSize, 1, 1)

    this.processorNode.onaudioprocess = (event: AudioProcessingEvent) => {
      if (!this.isCapturing || this.isMuted) {
        if (this.onAudioLevel) this.onAudioLevel(0)
        return
      }

      const inputData = event.inputBuffer.getChannelData(0)

      let sumSquares = 0
      for (let i = 0; i < inputData.length; i++) {
        const val = inputData[i] ?? 0
        sumSquares += val * val
      }
      const rms = Math.sqrt(sumSquares / inputData.length)
      const level = Math.min(100, Math.round(rms * 400))
      if (this.onAudioLevel) this.onAudioLevel(level)

      const downsampled = this._downsampleTo16k(inputData, sampleRate)
      const pcm16 = this._floatTo16BitPCM(downsampled)
      const base64 = arrayBufferToBase64(pcm16.buffer as ArrayBuffer)
      if (this.onAudioChunk && base64) this.onAudioChunk(base64)
    }

    // Connect through a zero-gain mute node to keep onaudioprocess alive
    // without feeding microphone sound back into the user's speakers/headphones (loopback echo).
    const muteNode = this.audioContext.createGain()
    muteNode.gain.value = 0
    this.sourceNode.connect(this.processorNode)
    this.processorNode.connect(muteNode)
    muteNode.connect(this.audioContext.destination)
  }

  public async setMute(muted: boolean): Promise<void> {
    this.isMuted = muted
    if (this.audioContext && this.audioContext.state === 'suspended' && !muted) {
      try {
        await this.audioContext.resume()
      } catch (err) {
        console.warn('[AudioCapture] Failed to resume AudioContext:', err)
      }
    }
    if (this.mediaStream) {
      this.mediaStream.getAudioTracks().forEach((track) => {
        track.enabled = !muted
      })
    }
    if (muted && this.onAudioLevel) this.onAudioLevel(0)
  }

  public async resumeAudioContext(): Promise<void> {
    if (this.audioContext && this.audioContext.state === 'suspended') {
      try {
        await this.audioContext.resume()
      } catch (err) {
        console.warn('[AudioCapture] Failed to resume AudioContext:', err)
      }
    }
  }

  public getIsMuted(): boolean {
    return this.isMuted
  }

  public getIsCapturing(): boolean {
    return this.isCapturing
  }

  public stop(): void {
    this.isCapturing = false

    if (this.workletNode) {
      this.workletNode.port.onmessage = null
      this.workletNode.disconnect()
      this.workletNode = null
    }

    if (this.processorNode) {
      this.processorNode.disconnect()
      this.processorNode = null
    }

    if (this.sourceNode) {
      this.sourceNode.disconnect()
      this.sourceNode = null
    }

    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close()
      this.audioContext = null
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop())
      this.mediaStream = null
    }

    if (this._workletBlobUrl) {
      URL.revokeObjectURL(this._workletBlobUrl)
      this._workletBlobUrl = null
    }

    if (this.onAudioLevel) this.onAudioLevel(0)
  }

  // -------------------------------------------------------------------------
  // Helpers (used by legacy fallback path only)
  // -------------------------------------------------------------------------
  private _downsampleTo16k(buffer: Float32Array, sourceSampleRate: number): Float32Array {
    if (sourceSampleRate === 16000) return buffer
    const ratio = sourceSampleRate / 16000
    const newLength = Math.round(buffer.length / ratio)
    const result = new Float32Array(newLength)
    let offsetResult = 0
    let offsetBuffer = 0
    while (offsetResult < result.length) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio)
      let accum = 0
      let count = 0
      for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
        accum += buffer[i] ?? 0
        count++
      }
      result[offsetResult] = count > 0 ? accum / count : 0
      offsetResult++
      offsetBuffer = nextOffsetBuffer
    }
    return result
  }

  private _floatTo16BitPCM(input: Float32Array): Int16Array {
    const output = new Int16Array(input.length)
    for (let i = 0; i < input.length; i++) {
      const val = input[i] ?? 0
      const s = Math.max(-1, Math.min(1, val))
      output[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    return output
  }
}

export const audioCaptureService = new AudioCaptureService()
