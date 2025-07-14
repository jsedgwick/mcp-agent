import * as Comlink from 'comlink'
import * as pako from 'pako'

// Type definitions
interface Span {
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

interface TraceWorkerAPI {
  parseTrace: (data: ArrayBuffer, isGzipped?: boolean) => Promise<Span[]>
}

// Decompress gzipped data
async function decompress(gzippedData: ArrayBuffer): Promise<string> {
  console.log('[TraceWorker] Starting decompression...')
  
  // Use native DecompressionStream if available (Chrome 80+)
  if ('DecompressionStream' in self) {
    console.log('[TraceWorker] Using native DecompressionStream')
    try {
      const stream = new Response(gzippedData).body!
        .pipeThrough(new (self as any).DecompressionStream('gzip'))
      const decompressed = await new Response(stream).text()
      console.log('[TraceWorker] Native decompression successful')
      return decompressed
    } catch (err) {
      console.warn('[TraceWorker] Native decompression failed, falling back to pako:', err)
      // Fall through to pako
    }
  }
  
  // Fallback to pako
  console.log('[TraceWorker] Using pako for decompression')
  try {
    const uint8Array = new Uint8Array(gzippedData)
    const decompressed = pako.ungzip(uint8Array, { to: 'string' })
    console.log('[TraceWorker] Pako decompression successful')
    return decompressed
  } catch (err) {
    console.error('[TraceWorker] Pako decompression failed:', err)
    throw new Error(`Decompression failed: ${err.message}`)
  }
}

// Parse JSONL format (newline-delimited JSON)
function parseJSONL(jsonl: string): Span[] {
  const lines = jsonl.trim().split('\n')
  const spans: Span[] = []
  
  for (const line of lines) {
    if (!line.trim()) continue
    
    try {
      const span = JSON.parse(line)
      spans.push(span)
    } catch (err) {
      console.error('Failed to parse span:', err, line)
    }
  }
  
  return spans
}

// Worker API implementation
const workerAPI: TraceWorkerAPI = {
  async parseTrace(data: ArrayBuffer, isGzipped: boolean = true): Promise<Span[]> {
    console.log('[TraceWorker] parseTrace called with ArrayBuffer size:', data.byteLength, 'isGzipped:', isGzipped)
    try {
      let jsonlString: string
      
      if (isGzipped) {
        // Decompress the data
        jsonlString = await decompress(data)
        console.log('[TraceWorker] Decompressed string length:', jsonlString.length)
      } else {
        // Data is already plain text, just decode it
        const decoder = new TextDecoder()
        jsonlString = decoder.decode(data)
        console.log('[TraceWorker] Decoded string length:', jsonlString.length)
      }
      
      // Parse JSONL
      const spans = parseJSONL(jsonlString)
      console.log('[TraceWorker] Parsed spans count:', spans.length)
      
      // Sort spans by start_time for consistent ordering
      spans.sort((a, b) => {
        const timeA = new Date(a.start_time).getTime()
        const timeB = new Date(b.start_time).getTime()
        return timeA - timeB
      })
      
      console.log('[TraceWorker] Returning sorted spans')
      return spans
    } catch (error) {
      console.error('[TraceWorker] Trace parsing error:', error)
      console.error('[TraceWorker] Error stack:', error.stack)
      throw error
    }
  }
}

// Expose the API via Comlink
Comlink.expose(workerAPI)