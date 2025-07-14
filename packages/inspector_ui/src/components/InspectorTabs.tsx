import React, { useMemo } from 'react'
import { useUIStore } from '../stores/uiStore'
import { useTraceStore } from '../stores/traceStore'

// JSON viewer component
function JSONViewer({ data, expanded = true }: { data: any; expanded?: boolean }) {
  const formatted = useMemo(() => {
    try {
      return JSON.stringify(data, null, 2)
    } catch {
      return 'Invalid JSON'
    }
  }, [data])
  
  return (
    <pre className="bg-gray-50 p-3 rounded text-xs overflow-auto">
      <code>{formatted}</code>
    </pre>
  )
}

// Attributes tab - shows all span attributes
function AttributesTab({ spanId }: { spanId?: string }) {
  const { selectedSessionId } = useUIStore()
  const { getTrace } = useTraceStore()
  
  const span = useMemo(() => {
    if (!selectedSessionId || !spanId) return null
    const trace = getTrace(selectedSessionId)
    return trace?.spansById.get(spanId)
  }, [selectedSessionId, spanId, getTrace])
  
  if (!span) {
    return (
      <div className="p-4 text-gray-500 text-center">
        Select a span to view attributes
      </div>
    )
  }
  
  const attributes = Object.entries(span.attributes || {})
  
  return (
    <div className="p-4 space-y-3">
      <h3 className="text-sm font-medium text-gray-700 mb-2">Span Attributes</h3>
      
      {attributes.length === 0 ? (
        <p className="text-sm text-gray-500">No attributes</p>
      ) : (
        <div className="space-y-2">
          {attributes.map(([key, value]) => (
            <div key={key} className="border-b border-gray-100 pb-2">
              <div className="text-xs font-medium text-gray-600">{key}</div>
              <div className="mt-1">
                {typeof value === 'string' && key.endsWith('_json') ? (
                  <JSONViewer data={JSON.parse(value)} />
                ) : (
                  <div className="text-sm text-gray-900">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// State tab - shows state/result JSON attributes
function StateTab({ spanId }: { spanId?: string }) {
  const { selectedSessionId } = useUIStore()
  const { getTrace } = useTraceStore()
  
  const stateData = useMemo(() => {
    if (!selectedSessionId || !spanId) return []
    const trace = getTrace(selectedSessionId)
    const span = trace?.spansById.get(spanId)
    if (!span) return []
    
    // Find all state/result attributes
    const stateAttrs: Array<{ key: string; value: any }> = []
    
    Object.entries(span.attributes || {}).forEach(([key, value]) => {
      if (key.includes('.state.') || key.includes('.result.')) {
        try {
          const parsed = typeof value === 'string' ? JSON.parse(value) : value
          stateAttrs.push({ key, value: parsed })
        } catch {
          stateAttrs.push({ key, value })
        }
      }
    })
    
    return stateAttrs
  }, [selectedSessionId, spanId, getTrace])
  
  if (!spanId) {
    return (
      <div className="p-4 text-gray-500 text-center">
        Select a span to view state
      </div>
    )
  }
  
  return (
    <div className="p-4 space-y-3">
      <h3 className="text-sm font-medium text-gray-700 mb-2">State & Results</h3>
      
      {stateData.length === 0 ? (
        <p className="text-sm text-gray-500">No state data captured for this span</p>
      ) : (
        <div className="space-y-4">
          {stateData.map(({ key, value }) => (
            <div key={key}>
              <div className="text-xs font-medium text-gray-600 mb-1">{key}</div>
              <JSONViewer data={value} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Context tab - shows LLM prompts and responses
function ContextTab({ spanId }: { spanId?: string }) {
  const { selectedSessionId } = useUIStore()
  const { getTrace } = useTraceStore()
  
  const contextData = useMemo(() => {
    if (!selectedSessionId || !spanId) return null
    const trace = getTrace(selectedSessionId)
    const span = trace?.spansById.get(spanId)
    if (!span) return null
    
    const result: any = {}
    
    // Extract LLM context
    if (span.attributes['mcp.llm.prompt_json']) {
      try {
        result.prompt = JSON.parse(span.attributes['mcp.llm.prompt_json'])
      } catch {}
    }
    
    if (span.attributes['mcp.llm.response_json']) {
      try {
        result.response = JSON.parse(span.attributes['mcp.llm.response_json'])
      } catch {}
    }
    
    // Extract model info
    result.model = span.attributes['mcp.llm.model']
    result.provider = span.attributes['mcp.llm.provider']
    
    return Object.keys(result).length > 0 ? result : null
  }, [selectedSessionId, spanId, getTrace])
  
  if (!spanId) {
    return (
      <div className="p-4 text-gray-500 text-center">
        Select an LLM span to view context
      </div>
    )
  }
  
  if (!contextData) {
    return (
      <div className="p-4 text-gray-500 text-center">
        No LLM context available for this span
      </div>
    )
  }
  
  return (
    <div className="p-4 space-y-4">
      <h3 className="text-sm font-medium text-gray-700 mb-2">LLM Context</h3>
      
      {contextData.model && (
        <div className="flex gap-4 text-xs">
          <span className="text-gray-600">Model:</span>
          <span className="font-medium">{contextData.model}</span>
          {contextData.provider && (
            <>
              <span className="text-gray-600">Provider:</span>
              <span className="font-medium">{contextData.provider}</span>
            </>
          )}
        </div>
      )}
      
      {contextData.prompt && (
        <div>
          <div className="text-xs font-medium text-gray-600 mb-1">Prompt</div>
          <JSONViewer data={contextData.prompt} />
        </div>
      )}
      
      {contextData.response && (
        <div>
          <div className="text-xs font-medium text-gray-600 mb-1">Response</div>
          <JSONViewer data={contextData.response} />
        </div>
      )}
    </div>
  )
}

// Main InspectorTabs component
export function InspectorTabs({ selectedSpanId }: { selectedSpanId?: string }) {
  const { selectedTab, setSelectedTab } = useUIStore()
  
  const tabs = [
    { id: 'attributes' as const, label: 'Attributes', icon: '🏷️' },
    { id: 'state' as const, label: 'State', icon: '📊' },
    { id: 'context' as const, label: 'Context', icon: '💬' }
  ]
  
  return (
    <div className="h-full flex flex-col bg-white">
      {/* Tab headers */}
      <div className="border-b border-gray-200">
        <nav className="flex -mb-px">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setSelectedTab(tab.id)}
              className={`
                py-2 px-4 text-sm font-medium border-b-2 transition-colors
                ${selectedTab === tab.id
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }
              `}
            >
              <span className="mr-1">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </nav>
      </div>
      
      {/* Tab content */}
      <div className="flex-1 overflow-auto">
        {selectedTab === 'attributes' && <AttributesTab spanId={selectedSpanId} />}
        {selectedTab === 'state' && <StateTab spanId={selectedSpanId} />}
        {selectedTab === 'context' && <ContextTab spanId={selectedSpanId} />}
      </div>
    </div>
  )
}