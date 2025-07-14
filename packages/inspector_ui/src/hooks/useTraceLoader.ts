import { useEffect, useRef, useCallback } from 'react'
import * as Comlink from 'comlink'
import { useTraceStore, buildTraceHierarchy } from '../stores/traceStore'
import { useUIStore } from '../stores/uiStore'

interface TraceWorkerAPI {
  parseTrace: (data: ArrayBuffer, isGzipped?: boolean) => Promise<any[]>
}

export function useTraceLoader() {
  const workerRef = useRef<Worker | null>(null)
  const workerApiRef = useRef<TraceWorkerAPI | null>(null)
  
  const { setTrace, setLoading, setError } = useTraceStore()
  const { selectedSessionId } = useUIStore()
  
  // Initialize worker on mount
  useEffect(() => {
    const worker = new Worker(
      new URL('../workers/traceWorker.ts', import.meta.url),
      { type: 'module' }
    )
    workerRef.current = worker
    workerApiRef.current = Comlink.wrap<TraceWorkerAPI>(worker)
    
    return () => {
      worker.terminate()
    }
  }, [])
  
  // Load trace for selected session
  const loadTrace = useCallback(async (sessionId: string) => {
    if (!workerApiRef.current) {
      console.error('Worker not initialized')
      return
    }
    
    setLoading(sessionId, true)
    setError(sessionId, null)
    
    try {
      // Fetch the trace file
      console.log(`[TraceLoader] Fetching trace for session: ${sessionId}`)
      const response = await fetch(`/_inspector/trace/${sessionId}`)
      
      console.log(`[TraceLoader] Response status: ${response.status}`)
      console.log(`[TraceLoader] Response headers:`)
      response.headers.forEach((value, key) => {
        console.log(`  ${key}: ${value}`)
      })
      
      if (!response.ok) {
        throw new Error(`Failed to fetch trace: ${response.status} ${response.statusText}`)
      }
      
      // Get the gzipped data as ArrayBuffer
      console.log('[TraceLoader] Converting to ArrayBuffer...')
      const gzippedData = await response.arrayBuffer()
      console.log(`[TraceLoader] ArrayBuffer size: ${gzippedData.byteLength} bytes`)
      
      // Check if it's actually gzipped by looking at the magic number
      const view = new DataView(gzippedData)
      let isGzipped = false
      if (gzippedData.byteLength >= 2) {
        const magic = view.getUint16(0)
        console.log(`[TraceLoader] First two bytes (magic number): 0x${magic.toString(16)} (should be 0x1f8b for gzip)`)
        isGzipped = magic === 0x1f8b
      }
      
      // Parse in worker thread
      console.log(`[TraceLoader] Sending to worker... (isGzipped: ${isGzipped})`)
      const spans = await workerApiRef.current.parseTrace(gzippedData, isGzipped)
      
      // Build hierarchy
      const parsedTrace = buildTraceHierarchy(spans)
      
      // Store in state
      setTrace(sessionId, parsedTrace)
      
      console.log(`[TraceLoader] Loaded ${spans.length} spans for session ${sessionId}`)
    } catch (error) {
      console.error('[TraceLoader] Error loading trace:', error)
      console.error('[TraceLoader] Error stack:', error.stack)
      setError(sessionId, error as Error)
    } finally {
      setLoading(sessionId, false)
    }
  }, [setTrace, setLoading, setError])
  
  // Auto-load trace when session is selected
  useEffect(() => {
    if (selectedSessionId) {
      loadTrace(selectedSessionId)
    }
  }, [selectedSessionId, loadTrace])
  
  return {
    loadTrace,
    reloadTrace: () => {
      if (selectedSessionId) {
        loadTrace(selectedSessionId)
      }
    }
  }
}