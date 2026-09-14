// ==============================================================================
// Realtime WebSocket Media Bridge Client
// Connects candidate browser directly to FastAPI / Gemini Live session bridge.
// ==============================================================================

import type { WsServerMessage } from '@/types'

export type MessageHandler = (msg: WsServerMessage) => void
export type StatusHandler = (status: 'connecting' | 'connected' | 'disconnected' | 'error') => void

export class RealtimeWebSocketClient {
  private socket: WebSocket | null = null
  private sessionId: string | null = null
  private messageHandlers: Set<MessageHandler> = new Set()
  private statusHandlers: Set<StatusHandler> = new Set()
  private pingIntervalId: number | null = null
  private reconnectTimeoutId: number | null = null
  private shouldReconnect = true
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private connectionStatus: 'connecting' | 'connected' | 'disconnected' | 'error' = 'disconnected'

  public connect(sessionId: string): void {
    this.sessionId = sessionId
    this.shouldReconnect = true
    this.reconnectAttempts = 0
    this.initSocket()
  }

  private initSocket(): void {
    if (!this.sessionId) return

    // Clear existing
    this.cleanup()

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const defaultHost = window.location.port === '5173' ? 'localhost:8000' : window.location.host
    const wsBase = import.meta.env.VITE_WS_URL || `${protocol}//${defaultHost}`
    const wsUrl = `${wsBase}/ws/interview/${this.sessionId}`

    console.log(`[WebSocket] Connecting to ${wsUrl}`)
    this.setStatus('connecting')

    try {
      this.socket = new WebSocket(wsUrl)

      this.socket.onopen = () => {
        console.log(`[WebSocket] Connected to session ${this.sessionId}`)
        this.reconnectAttempts = 0
        this.setStatus('connected')
        this.startHeartbeat()
      }

      this.socket.onmessage = (event: MessageEvent) => {
        try {
          const data: WsServerMessage = JSON.parse(event.data)
          this.notifyMessage(data)
        } catch (err) {
          console.error('[WebSocket] Failed to parse inbound message:', event.data, err)
        }
      }

      this.socket.onerror = (err) => {
        console.error('[WebSocket] Socket error:', err)
        this.setStatus('error')
      }

      this.socket.onclose = (event) => {
        console.warn(`[WebSocket] Closed (code: ${event.code}, reason: ${event.reason})`)
        this.setStatus('disconnected')
        this.stopHeartbeat()

        if (this.shouldReconnect && event.code !== 1000 && event.code !== 1008) {
          if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++
            const delay = Math.min(2000 * Math.pow(1.5, this.reconnectAttempts - 1), 10000)
            console.log(`[WebSocket] Attempting auto-reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${Math.round(delay / 1000)}s...`)
            this.reconnectTimeoutId = window.setTimeout(() => {
              this.initSocket()
            }, delay)
          } else {
            console.warn(`[WebSocket] Reconnect limit reached (${this.maxReconnectAttempts} attempts).`)
            this.setStatus('error')
          }
        }
      }
    } catch (err) {
      console.error('[WebSocket] Connection attempt failed:', err)
      this.setStatus('error')
    }
  }

  public sendAudio(base64Pcm: string, sampleRate = 16000): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: 'audio',
          data: base64Pcm,
          sample_rate: sampleRate,
        }),
      )
    }
  }

  public sendText(text: string): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: 'text',
          text,
        }),
      )
    }
  }

  public sendSessionStart(context: string): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: 'session_start',
          context,
        }),
      )
    }
  }

  public sendPing(): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          type: 'ping',
        }),
      )
    }
  }

  public onMessage(handler: MessageHandler): () => void {
    this.messageHandlers.add(handler)
    return () => this.messageHandlers.delete(handler)
  }

  public onStatusChange(handler: StatusHandler): () => void {
    this.statusHandlers.add(handler)
    handler(this.connectionStatus)
    return () => this.statusHandlers.delete(handler)
  }

  public getStatus(): 'connecting' | 'connected' | 'disconnected' | 'error' {
    return this.connectionStatus
  }

  public disconnect(): void {
    this.shouldReconnect = false
    this.cleanup()
    this.setStatus('disconnected')
  }

  private setStatus(status: 'connecting' | 'connected' | 'disconnected' | 'error'): void {
    this.connectionStatus = status
    this.statusHandlers.forEach((handler) => handler(status))
  }

  private notifyMessage(msg: WsServerMessage): void {
    this.messageHandlers.forEach((handler) => handler(msg))
  }

  private startHeartbeat(): void {
    this.stopHeartbeat()
    this.pingIntervalId = window.setInterval(() => {
      this.sendPing()
    }, 10000)
  }

  private stopHeartbeat(): void {
    if (this.pingIntervalId) {
      clearInterval(this.pingIntervalId)
      this.pingIntervalId = null
    }
  }

  private cleanup(): void {
    this.stopHeartbeat()
    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId)
      this.reconnectTimeoutId = null
    }
    if (this.socket) {
      this.socket.onopen = null
      this.socket.onmessage = null
      this.socket.onerror = null
      this.socket.onclose = null
      try {
        this.socket.close()
      } catch (e) {
        // Ignore
      }
      this.socket = null
    }
  }
}

export const realtimeWebSocket = new RealtimeWebSocketClient()
