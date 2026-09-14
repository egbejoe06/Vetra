import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { audioCaptureService } from '@/services/audioCapture'
import { audioPlayerService } from '@/services/audioPlayer'
import { realtimeWebSocket } from '@/services/websocket'
import {
  type DialogueTurn,
  InterviewStage,
  TranscriptSpeaker,
  type WsServerMessage,
} from '@/types'
import { useWorkspaceStore } from '@/stores/workspace'
import { useInterviewStore } from '@/stores/interview'
import { api } from '@/services/api'

export const useRealtimeStore = defineStore('realtime', () => {
  const connectionStatus = ref<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected')
  const isMicMuted = ref<boolean>(false)
  const isCameraEnabled = ref<boolean>(true)
  const isInterviewerSpeaking = ref<boolean>(false)
  const isCandidateSpeaking = ref<boolean>(false)

  // Realtime Audio Levels (0 - 100)
  const candidateAudioLevel = ref<number>(0)
  const interviewerAudioLevel = ref<number>(0)
  const isAudioSuspended = ref<boolean>(false)

  // Dialogue transcript state
  const turns = ref<DialogueTurn[]>([])
  const interimCandidateText = ref<string>('')
  const interimInterviewerText = ref<string>('')

  // Active Session ID
  const activeSessionId = ref<string | null>(null)

  let unsubWsMessage: (() => void) | null = null
  let unsubWsStatus: (() => void) | null = null

  // Tracks whether the AI has completed its first greeting turn so we know
  // when it's safe to unmute the microphone without causing a false barge-in.
  let _firstAiTurnComplete = false

  // ---------------------------------------------------------------------------
  // Phase 1: Connect WebSocket only (called after resume upload is confirmed)
  //          The AI will not greet until sendSessionStart() is called.
  // ---------------------------------------------------------------------------
  async function connectSession(sessionId: string) {
    activeSessionId.value = sessionId
    turns.value = []
    interimCandidateText.value = ''
    interimInterviewerText.value = ''
    _firstAiTurnComplete = false

    // 1. Initialize Audio Player for 24kHz Gemini Voice
    audioPlayerService.init((level: number) => {
      interviewerAudioLevel.value = level
      isInterviewerSpeaking.value = level > 5
    })
    isAudioSuspended.value = audioPlayerService.isSuspended()

    // Clean up any existing WebSocket listeners before attaching new ones
    if (unsubWsMessage) {
      unsubWsMessage()
      unsubWsMessage = null
    }
    if (unsubWsStatus) {
      unsubWsStatus()
      unsubWsStatus = null
    }
    audioPlayerService.handleInterruption()

    // 2. Setup WebSocket Handlers
    unsubWsStatus = realtimeWebSocket.onStatusChange((status) => {
      connectionStatus.value = status
    })

    unsubWsMessage = realtimeWebSocket.onMessage((msg: WsServerMessage) => {
      handleServerMessage(msg)
    })

    // 3. Connect WebSocket
    realtimeWebSocket.connect(sessionId)

    // 4. Start Microphone Capture (16kHz PCM via AudioWorkletNode)
    //    The mic starts MUTED to prevent ambient noise / startup transients from
    //    triggering a false barge-in interruption on the AI's opening greeting.
    //    It will be automatically unmuted after the AI's first turn completes.
    try {
      await audioCaptureService.start(
        (base64Pcm: string) => {
          // Send 16kHz PCM audio chunk to WebSocket
          realtimeWebSocket.sendAudio(base64Pcm, 16000)
        },
        (level: number) => {
          candidateAudioLevel.value = level
          isCandidateSpeaking.value = level > 5
        },
      )
      // Mute immediately after starting so no audio streams to Gemini until the AI
      // has finished its opening greeting (first turn_complete from INTERVIEWER).
      audioCaptureService.setMute(true)
      isMicMuted.value = true
    } catch (err) {
      console.warn('Microphone permission not granted or capture failed:', err)
    }
  }

  // ---------------------------------------------------------------------------
  // Phase 2: Send session start message with enriched interview context.
  //          This primes the AI and triggers the opening greeting.
  // ---------------------------------------------------------------------------
  function sendSessionStart(context: string) {
    realtimeWebSocket.sendSessionStart(context)

    // Safety fallback: ensure mic is unmuted within 5s even if turn_complete event is delayed or missed
    setTimeout(() => {
      if (!_firstAiTurnComplete) {
        _firstAiTurnComplete = true
        console.log('[RealtimeStore] Opening greeting grace period ended — unmuting microphone.')
        audioCaptureService.setMute(false)
        isMicMuted.value = false
      }
    }, 5000)
  }

  function handleServerMessage(msg: WsServerMessage) {
    switch (msg.type) {
      case 'audio':
        if (audioPlayerService.isSuspended()) {
          isAudioSuspended.value = true
        }
        // Enqueue 24kHz PCM for playback
        audioPlayerService.queueAudioChunk(msg.data)
        break

      case 'interrupted':
        // Instant Interruption cutoff: Flush all audio playback buffers
        console.log('[RealtimeStore] Barge-in interrupted by candidate!')
        audioPlayerService.handleInterruption()
        interimInterviewerText.value = ''
        // If candidate interrupted, make sure the mic is live so their voice goes through!
        _firstAiTurnComplete = true
        audioCaptureService.setMute(false)
        isMicMuted.value = false
        break

      case 'turn_complete':
        // Auto-unmute the mic after the AI's first turn so the candidate can speak.
        if (!_firstAiTurnComplete && msg.speaker === TranscriptSpeaker.INTERVIEWER) {
          _firstAiTurnComplete = true
          console.log('[RealtimeStore] First AI turn complete — unmuting microphone.')
          audioCaptureService.setMute(false)
          isMicMuted.value = false
        }
        break

      case 'transcript':
        if (msg.speaker === TranscriptSpeaker.CANDIDATE) {
          if (msg.is_final) {
            turns.value.push({
              turn_id: msg.turn_id,
              speaker: TranscriptSpeaker.CANDIDATE,
              stage: msg.stage || InterviewStage.INTRO,
              content: msg.text,
              timestamp: msg.timestamp,
              is_final: true,
            })
            interimCandidateText.value = ''
          } else {
            interimCandidateText.value = msg.text
          }
        } else if (msg.speaker === TranscriptSpeaker.INTERVIEWER) {
          if (msg.is_final) {
            turns.value.push({
              turn_id: msg.turn_id,
              speaker: TranscriptSpeaker.INTERVIEWER,
              stage: msg.stage || InterviewStage.INTRO,
              content: msg.text,
              timestamp: msg.timestamp,
              is_final: true,
            })
            interimInterviewerText.value = ''
            // Interviewer finished speaking — ensure mic is unmuted
            if (!_firstAiTurnComplete) {
              _firstAiTurnComplete = true
              audioCaptureService.setMute(false)
              isMicMuted.value = false
            }
          } else {
            interimInterviewerText.value += msg.text
          }
        } else if (msg.speaker === TranscriptSpeaker.SYSTEM) {
          turns.value.push({
            turn_id: msg.turn_id,
            speaker: TranscriptSpeaker.SYSTEM,
            stage: msg.stage || InterviewStage.INTRO,
            content: msg.text,
            timestamp: msg.timestamp,
            is_final: true,
          })
        }
        break

      case 'problem_presented': {
        const workspaceStore = useWorkspaceStore()
        console.log('[RealtimeStore] Technical problem presented by interviewer:', msg.title)
        workspaceStore.loadTechnicalProblem(msg, true)
        break
      }

      case 'stage_update': {
        const interviewStore = useInterviewStore()
        const workspaceStore = useWorkspaceStore()
        console.log('[RealtimeStore] Stage updated to:', msg.stage)
        interviewStore.setSessionStage(msg.stage)
        if (msg.stage === InterviewStage.TECHNICAL_EXERCISE) {
          workspaceStore.setLayoutMode('coding')
          if (!workspaceStore.hasProblem && activeSessionId.value) {
            api.getTechnicalProblems(activeSessionId.value).then((probs) => {
              if (probs && probs.length > 0) {
                workspaceStore.loadTechnicalProblem(probs[0], true)
              }
            }).catch(console.error)
          }
        } else {
          // Automatically return to discussion mode when stage progresses past technical exercise
          workspaceStore.setLayoutMode('discussion')
        }
        break
      }

      case 'session_status':
        console.log('[RealtimeStore] Session status update:', msg.status)
        break

      case 'error':
        console.error('[RealtimeStore] Server Error:', msg.message)
        break
    }
  }

  function toggleMute() {
    const nextMuted = !isMicMuted.value
    audioCaptureService.setMute(nextMuted)
    isMicMuted.value = nextMuted
    // If the candidate manually unmutes before the AI's first turn completes,
    // mark it as done so the auto-unmute doesn't double-toggle later.
    if (!nextMuted) {
      _firstAiTurnComplete = true
    }
  }

  function toggleCamera() {
    isCameraEnabled.value = !isCameraEnabled.value
  }

  function sendChatMessage(text: string) {
    if (!text.trim()) return
    realtimeWebSocket.sendText(text)
    turns.value.push({
      speaker: TranscriptSpeaker.CANDIDATE,
      stage: InterviewStage.INTRO,
      content: text,
      timestamp: new Date().toISOString(),
      is_final: true,
    })
  }

  async function unlockAudio() {
    await audioPlayerService.resume()
    await audioCaptureService.resumeAudioContext()
    isAudioSuspended.value = audioPlayerService.isSuspended()
  }

  function disconnect() {
    if (unsubWsMessage) unsubWsMessage()
    if (unsubWsStatus) unsubWsStatus()
    audioCaptureService.stop()
    audioPlayerService.stop()
    realtimeWebSocket.disconnect()
    connectionStatus.value = 'disconnected'
    candidateAudioLevel.value = 0
    interviewerAudioLevel.value = 0
    isAudioSuspended.value = false
  }

  return {
    connectionStatus,
    isMicMuted,
    isCameraEnabled,
    isInterviewerSpeaking,
    isCandidateSpeaking,
    candidateAudioLevel,
    interviewerAudioLevel,
    isAudioSuspended,
    turns,
    interimCandidateText,
    interimInterviewerText,
    activeSessionId,
    connectSession,
    sendSessionStart,
    handleServerMessage,
    toggleMute,
    toggleCamera,
    sendChatMessage,
    unlockAudio,
    disconnect,
  }
})
