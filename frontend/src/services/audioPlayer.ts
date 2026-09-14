// ==============================================================================
// 24kHz PCM Audio Player & Interruption Handler
// Plays Gemini Live 24kHz raw PCM streams with instant barge-in flushing.
// ==============================================================================

export type InterruptionCallback = () => void
export type PlayerLevelCallback = (level: number) => void

export class AudioPlayerService {
  private audioContext: AudioContext | null = null
  private gainNode: GainNode | null = null
  private analyserNode: AnalyserNode | null = null
  private nextPlayTime = 0
  private activeSources: AudioBufferSourceNode[] = []
  private isPlaying = false
  private onLevelUpdate: PlayerLevelCallback | null = null
  private animFrameId: number | null = null

  public init(onLevel?: PlayerLevelCallback): void {
    if (onLevel) this.onLevelUpdate = onLevel

    if (!this.audioContext || this.audioContext.state === 'closed') {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext
      // NOTE: Do not force sampleRate: 24000 on the AudioContext itself.
      // Doing so causes silent rendering or NotSupportedError on Windows audio drivers (WASAPI)
      // and Bluetooth/USB headphones that run at 44.1kHz or 48kHz.
      // AudioBuffer is explicitly created with 24000 Hz, which Web Audio natively resamples.
      this.audioContext = new AudioCtx()

      this.gainNode = this.audioContext.createGain()
      this.gainNode.gain.value = 1.0

      this.analyserNode = this.audioContext.createAnalyser()
      this.analyserNode.fftSize = 256

      // Audio pipeline: source -> gainNode -> analyserNode -> destination
      this.gainNode.connect(this.analyserNode)
      this.analyserNode.connect(this.audioContext.destination)

      this.startLevelLoop()
    }
  }

  /**
   * Resumes the AudioContext on user interaction to comply with browser autoplay policy.
   */
  public async resume(): Promise<void> {
    if (!this.audioContext || this.audioContext.state === 'closed') {
      this.init()
    }

    if (this.audioContext && this.audioContext.state === 'suspended') {
      try {
        await this.audioContext.resume()
        console.log('[AudioPlayer] AudioContext successfully resumed, state:', this.audioContext.state)
      } catch (err) {
        console.warn('[AudioPlayer] Failed to resume AudioContext:', err)
      }
    }
  }

  public isSuspended(): boolean {
    return !this.audioContext || this.audioContext.state === 'suspended'
  }

  /**
   * Enqueues a base64 encoded 24kHz 16-bit PCM chunk from Gemini Live
   */
  public queueAudioChunk(base64Data: string): void {
    if (!this.audioContext || this.audioContext.state === 'closed') {
      this.init()
    }

    if (this.audioContext?.state === 'suspended') {
      this.audioContext.resume().catch((err) => {
        console.warn('[AudioPlayer] AudioContext resume failed in queueAudioChunk (awaiting user gesture):', err)
      })
    }

    try {
      const rawBytes = this.base64ToArrayBuffer(base64Data)
      const sampleCount = Math.floor(rawBytes.byteLength / 2)
      if (sampleCount === 0) return

      // Safe alignment: always slice an even byte boundary
      const pcm16 = new Int16Array(rawBytes, 0, sampleCount)

      // Convert 16-bit signed PCM to Float32 [-1.0, 1.0]
      const float32 = new Float32Array(sampleCount)
      for (let i = 0; i < sampleCount; i++) {
        float32[i] = (pcm16[i] ?? 0) / 32768.0
      }

      // Create AudioBuffer at 24000 Hz (Gemini Live native model output rate)
      const audioBuffer = this.audioContext!.createBuffer(
        1,
        sampleCount,
        24000,
      )
      audioBuffer.copyToChannel(float32, 0)

      // Create Source Node
      const source = this.audioContext!.createBufferSource()
      source.buffer = audioBuffer

      // Route through GainNode -> AnalyserNode -> Destination
      if (this.gainNode) {
        source.connect(this.gainNode)
      } else if (this.analyserNode) {
        source.connect(this.analyserNode)
      } else {
        source.connect(this.audioContext!.destination)
      }

      const currentTime = this.audioContext!.currentTime
      // If we are starting fresh or the buffer ran dry (nextPlayTime is in the past),
      // schedule the next chunk to start slightly ahead of current time (30ms).
      // Otherwise, maintain seamless back-to-back sequential queuing without overlapping!
      if (this.nextPlayTime < currentTime) {
        this.nextPlayTime = currentTime + 0.03
      }

      source.start(this.nextPlayTime)
      this.nextPlayTime += audioBuffer.duration
      this.activeSources.push(source)
      this.isPlaying = true

      source.onended = () => {
        const index = this.activeSources.indexOf(source)
        if (index > -1) {
          this.activeSources.splice(index, 1)
        }
        if (this.activeSources.length === 0) {
          this.isPlaying = false
        }
      }
    } catch (err) {
      console.error('[AudioPlayer] Error decoding or queuing audio chunk:', err)
    }
  }

  /**
   * INSTANT BARGE-IN INTERRUPTION FLUSH
   * Immediately terminates all currently playing and queued audio buffers.
   * Latency is sub-50ms.
   */
  public handleInterruption(): void {
    console.log('[AudioPlayer] Barge-in interruption triggered: Flushing all audio buffers')

    // Stop and disconnect all active sources immediately
    for (const source of this.activeSources) {
      try {
        source.stop(0)
        source.disconnect()
      } catch (e) {
        // Source may have already stopped
      }
    }

    this.activeSources = []
    this.isPlaying = false
    this.nextPlayTime = 0

    if (this.onLevelUpdate) {
      this.onLevelUpdate(0)
    }
  }

  public getIsPlaying(): boolean {
    return this.isPlaying
  }

  public stop(): void {
    this.handleInterruption()
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId)
      this.animFrameId = null
    }
    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close()
      this.audioContext = null
    }
    this.gainNode = null
    this.analyserNode = null
  }

  private startLevelLoop(): void {
    const dataArray = new Uint8Array(this.analyserNode?.frequencyBinCount || 128)

    const update = () => {
      if (this.analyserNode && this.isPlaying) {
        this.analyserNode.getByteFrequencyData(dataArray)
        let sum = 0
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i] ?? 0
        }
        const average = sum / dataArray.length
        const level = Math.min(100, Math.round((average / 255) * 120))
        if (this.onLevelUpdate) {
          this.onLevelUpdate(level)
        }
      } else {
        if (this.onLevelUpdate) {
          this.onLevelUpdate(0)
        }
      }
      this.animFrameId = requestAnimationFrame(update)
    }

    this.animFrameId = requestAnimationFrame(update)
  }

  private base64ToArrayBuffer(base64: string): ArrayBuffer {
    const binaryString = window.atob(base64)
    const len = binaryString.length
    const bytes = new Uint8Array(len)
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i)
    }
    return bytes.buffer
  }
}

export const audioPlayerService = new AudioPlayerService()
