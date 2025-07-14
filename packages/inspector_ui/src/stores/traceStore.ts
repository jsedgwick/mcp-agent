import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { immer } from 'zustand/middleware/immer'
import { enableMapSet } from 'immer'

// Enable Immer's MapSet plugin (in case it wasn't already enabled)
enableMapSet()

// Span type following OpenTelemetry conventions from telemetry-spec.md
export interface Span {
  trace_id: string
  span_id: string
  parent_span_id?: string
  name: string
  start_time: string
  end_time?: string
  attributes: Record<string, any>
  status?: {
    status_code: 'OK' | 'ERROR' | 'UNSET'
    description?: string
  }
  events?: Array<{
    name: string
    time: string
    attributes?: Record<string, any>
  }>
}

export interface ParsedTrace {
  spans: Span[]
  rootSpanId?: string
  spansByParent: Map<string | undefined, Span[]>
  spansById: Map<string, Span>
}

interface TraceStore {
  traces: Map<string, ParsedTrace>
  loadingTraces: Set<string>
  errorTraces: Map<string, Error>
  
  setTrace: (sessionId: string, trace: ParsedTrace) => void
  setLoading: (sessionId: string, loading: boolean) => void
  setError: (sessionId: string, error: Error | null) => void
  getTrace: (sessionId: string) => ParsedTrace | undefined
  isLoading: (sessionId: string) => boolean
  getError: (sessionId: string) => Error | undefined
}

// Helper function to build trace hierarchy
export function buildTraceHierarchy(spans: Span[]): ParsedTrace {
  const spansById = new Map<string, Span>()
  const spansByParent = new Map<string | undefined, Span[]>()
  let rootSpanId: string | undefined
  
  // First pass: index spans
  spans.forEach(span => {
    spansById.set(span.span_id, span)
    
    // Group by parent
    const parentId = span.parent_span_id
    if (!spansByParent.has(parentId)) {
      spansByParent.set(parentId, [])
    }
    spansByParent.get(parentId)!.push(span)
    
    // Track root span (no parent)
    if (!parentId) {
      rootSpanId = span.span_id
    }
  })
  
  return {
    spans,
    rootSpanId,
    spansByParent,
    spansById
  }
}

export const useTraceStore = create<TraceStore>()(
  devtools(
    immer((set, get) => ({
      traces: new Map(),
      loadingTraces: new Set(),
      errorTraces: new Map(),
      
      setTrace: (sessionId, trace) => set((state) => {
        state.traces.set(sessionId, trace)
        state.loadingTraces.delete(sessionId)
        state.errorTraces.delete(sessionId)
      }),
      
      setLoading: (sessionId, loading) => set((state) => {
        if (loading) {
          state.loadingTraces.add(sessionId)
        } else {
          state.loadingTraces.delete(sessionId)
        }
      }),
      
      setError: (sessionId, error) => set((state) => {
        if (error) {
          state.errorTraces.set(sessionId, error)
        } else {
          state.errorTraces.delete(sessionId)
        }
        state.loadingTraces.delete(sessionId)
      }),
      
      getTrace: (sessionId) => {
        return get().traces.get(sessionId)
      },
      
      isLoading: (sessionId) => {
        return get().loadingTraces.has(sessionId)
      },
      
      getError: (sessionId) => {
        return get().errorTraces.get(sessionId)
      }
    })),
    {
      name: 'trace-store',
      serialize: {
        options: {
          map: true,
          set: true
        }
      }
    }
  )
)