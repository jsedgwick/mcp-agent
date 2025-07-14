import { useEffect, useRef, useCallback } from 'react'
import { useUIStore } from '../stores/uiStore'
import { useSessionStore } from '../stores/sessionStore'

interface SSEEvent {
  type: string
  data: any
  timestamp: string
  event_id?: number
}

interface SessionStartedEvent extends SSEEvent {
  type: 'SessionStarted'
  session_id: string
  engine: 'asyncio' | 'temporal' | 'inbound'
  title?: string
  metadata?: Record<string, any>
}

interface SessionFinishedEvent extends SSEEvent {
  type: 'SessionFinished'
  session_id: string
  status: 'completed' | 'failed' | 'cancelled'
  error?: string
  duration_ms?: number
}

interface WaitingOnSignalEvent extends SSEEvent {
  type: 'WaitingOnSignal'
  session_id: string
  signal_name: string
  prompt?: string
  signal_schema?: Record<string, any>
}

interface HeartbeatEvent extends SSEEvent {
  type: 'Heartbeat'
  session_id: string
  llm_calls_delta: number
  tokens_delta: number
  tool_calls_delta: number
  current_span_count: number
}

type InspectorEvent = SessionStartedEvent | SessionFinishedEvent | WaitingOnSignalEvent | HeartbeatEvent

export function useSSE() {
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectDelayRef = useRef(250) // Start with 250ms
  
  const { setSseConnected, incrementSseReconnect } = useUIStore()
  const { updateSession, getSession } = useSessionStore()
  
  const handleEvent = useCallback((event: InspectorEvent) => {
    console.log('[SSE] Event received:', event.type, event)
    
    switch (event.type) {
      case 'SessionStarted': {
        // Fetch full session list to get complete metadata
        fetch('/_inspector/sessions')
          .then(res => res.json())
          .then(data => {
            const session = data.sessions.find((s: any) => s.id === event.session_id)
            if (session) {
              updateSession(event.session_id, session)
            }
          })
          .catch(err => console.error('[SSE] Failed to fetch session:', err))
        break
      }
      
      case 'SessionFinished': {
        updateSession(event.session_id, {
          status: event.status === 'completed' ? 'completed' : 'failed',
          ended_at: new Date().toISOString()
        })
        break
      }
      
      case 'WaitingOnSignal': {
        updateSession(event.session_id, {
          status: 'paused'
        })
        // TODO: Store signal info for UI display
        break
      }
      
      case 'Heartbeat': {
        const session = getSession(event.session_id)
        if (session) {
          // Update session with latest metrics
          // In a real implementation, we'd accumulate these metrics
          console.log('[SSE] Heartbeat for', event.session_id, {
            llm_calls: event.llm_calls_delta,
            tokens: event.tokens_delta,
            spans: event.current_span_count
          })
        }
        break
      }
    }
  }, [updateSession, getSession])
  
  const connect = useCallback(() => {
    if (eventSourceRef.current?.readyState === EventSource.OPEN) {
      return // Already connected
    }
    
    console.log('[SSE] Connecting to event stream...')
    
    try {
      const eventSource = new EventSource('/_inspector/events')
      eventSourceRef.current = eventSource
      
      eventSource.onopen = () => {
        console.log('[SSE] Connected')
        setSseConnected(true)
        reconnectDelayRef.current = 250 // Reset delay on successful connection
      }
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          handleEvent(data)
        } catch (err) {
          console.error('[SSE] Failed to parse event:', err)
        }
      }
      
      eventSource.onerror = (error) => {
        console.error('[SSE] Connection error:', error)
        setSseConnected(false)
        eventSource.close()
        
        // Exponential backoff for reconnection
        const delay = Math.min(reconnectDelayRef.current * 2, 5000) // Max 5s
        reconnectDelayRef.current = delay
        
        console.log(`[SSE] Reconnecting in ${delay}ms...`)
        incrementSseReconnect()
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect()
        }, delay)
      }
    } catch (err) {
      console.error('[SSE] Failed to create EventSource:', err)
      setSseConnected(false)
    }
  }, [setSseConnected, incrementSseReconnect, handleEvent])
  
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    
    if (eventSourceRef.current) {
      console.log('[SSE] Disconnecting...')
      eventSourceRef.current.close()
      eventSourceRef.current = null
      setSseConnected(false)
    }
  }, [setSseConnected])
  
  useEffect(() => {
    connect()
    
    return () => {
      disconnect()
    }
  }, [connect, disconnect])
  
  return {
    connected: eventSourceRef.current?.readyState === EventSource.OPEN,
    reconnect: connect,
    disconnect
  }
}