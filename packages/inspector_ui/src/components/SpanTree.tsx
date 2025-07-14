import React, { useRef, useMemo, useCallback, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useTraceStore, type Span } from '../stores/traceStore'
import { useUIStore } from '../stores/uiStore'

interface SpanRowProps {
  span: Span
  depth: number
  isExpanded: boolean
  hasChildren: boolean
  onToggle: () => void
  onSelect: () => void
  isSelected: boolean
}

// Individual span row component
function SpanRow({ span, depth, isExpanded, hasChildren, onToggle, onSelect, isSelected }: SpanRowProps) {
  const formatDuration = (span: Span) => {
    if (!span.end_time) return 'Running'
    const start = new Date(span.start_time).getTime()
    const end = new Date(span.end_time).getTime()
    const duration = end - start
    if (duration < 1000) return `${duration}ms`
    return `${(duration / 1000).toFixed(2)}s`
  }
  
  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'OK': return 'text-green-600'
      case 'ERROR': return 'text-red-600'
      default: return 'text-gray-600'
    }
  }
  
  const getSpanIcon = (name: string) => {
    if (name.startsWith('workflow.')) return '📊'
    if (name.startsWith('agent.')) return '🤖'
    if (name.startsWith('llm.')) return '🧠'
    if (name.startsWith('tool.')) return '🔧'
    if (name.startsWith('resource.')) return '📁'
    if (name.startsWith('prompt.')) return '📝'
    return '•'
  }
  
  return (
    <div
      className={`
        flex items-center py-1 px-2 text-sm cursor-pointer hover:bg-gray-50
        ${isSelected ? 'bg-blue-50 border-l-2 border-blue-500' : ''}
      `}
      style={{ paddingLeft: `${depth * 20 + 8}px` }}
      onClick={onSelect}
      role="treeitem"
      aria-selected={isSelected}
      aria-expanded={hasChildren ? isExpanded : undefined}
    >
      {/* Expand/collapse button */}
      {hasChildren && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
          className="mr-1 p-0.5 hover:bg-gray-200 rounded"
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
        >
          <svg className="w-3 h-3" viewBox="0 0 12 12">
            <path
              fill="currentColor"
              d={isExpanded 
                ? 'M3 5h6v2H3z' // minus
                : 'M5 3h2v2h2v2H7v2H5V7H3V5h2V3z' // plus
              }
            />
          </svg>
        </button>
      )}
      {!hasChildren && <span className="w-5 inline-block" />}
      
      {/* Span icon */}
      <span className="mr-2 text-base">{getSpanIcon(span.name)}</span>
      
      {/* Span name */}
      <span className="flex-1 truncate font-medium">{span.name}</span>
      
      {/* Duration */}
      <span className="ml-2 text-xs text-gray-500">{formatDuration(span)}</span>
      
      {/* Status */}
      {span.status && (
        <span className={`ml-2 text-xs ${getStatusColor(span.status.status_code)}`}>
          {span.status.status_code}
        </span>
      )}
    </div>
  )
}

// Main SpanTree component
export function SpanTree({ onSpanSelect }: { onSpanSelect?: (spanId: string) => void }) {
  const parentRef = useRef<HTMLDivElement>(null)
  
  const { selectedSessionId, selectedSpanId, setSelectedSpan } = useUIStore()
  const { getTrace, isLoading } = useTraceStore()
  const { expandedSpans, toggleSpanExpanded, collapseAllSpans } = useUIStore()
  const { setSelectedTab } = useUIStore()
  
  const trace = selectedSessionId ? getTrace(selectedSessionId) : undefined
  const loading = selectedSessionId ? isLoading(selectedSessionId) : false
  
  // Build flat list of visible spans for virtualization
  const visibleSpans = useMemo(() => {
    if (!trace) return []
    
    const visible: Array<{ span: Span; depth: number }> = []
    const visited = new Set<string>()
    
    const addSpanAndChildren = (spanId: string | undefined, depth: number) => {
      // Prevent infinite loops from circular references
      if (spanId && visited.has(spanId)) {
        console.warn(`Circular reference detected for span ${spanId}`)
        return
      }
      if (spanId) visited.add(spanId)
      
      // Limit depth to prevent stack overflow
      if (depth > 50) {
        console.warn(`Maximum depth exceeded at span ${spanId}`)
        return
      }
      
      const children = trace.spansByParent.get(spanId) || []
      
      for (const span of children) {
        visible.push({ span, depth })
        
        // Add children if expanded
        if (expandedSpans.has(span.span_id)) {
          addSpanAndChildren(span.span_id, depth + 1)
        }
      }
    }
    
    // Start from root spans (no parent)
    addSpanAndChildren(undefined, 0)
    
    return visible
  }, [trace, expandedSpans])
  
  // Virtual list setup
  const virtualizer = useVirtualizer({
    count: visibleSpans.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 28, // Row height in pixels
    overscan: 10 // Render 10 items outside viewport
  })
  
  const handleSpanSelect = useCallback((spanId: string) => {
    setSelectedSpan(spanId)
    setSelectedTab('attributes')
    onSpanSelect?.(spanId)
  }, [setSelectedSpan, setSelectedTab, onSpanSelect])
  
  if (!selectedSessionId) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        Select a session to view trace
      </div>
    )
  }
  
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-2"></div>
          <p>Loading trace...</p>
        </div>
      </div>
    )
  }
  
  if (!trace || trace.spans.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        No spans found for this session
      </div>
    )
  }
  
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-2 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-700">
            Trace ({trace.spans.length} spans)
          </h3>
          <button
            onClick={() => {
              if (expandedSpans.size === 0 && trace) {
                // Expand all spans
                trace.spans.forEach(span => {
                  toggleSpanExpanded(span.span_id)
                })
              } else {
                // Collapse all spans
                collapseAllSpans()
              }
            }}
            className="text-xs text-blue-600 hover:text-blue-800"
          >
            {expandedSpans.size > 0 ? 'Collapse All' : 'Expand All'}
          </button>
        </div>
      </div>
      
      {/* Virtual list */}
      <div
        ref={parentRef}
        className="flex-1 overflow-auto"
        role="tree"
        aria-label="Span tree"
      >
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative'
          }}
        >
          {virtualizer.getVirtualItems().map((virtualItem) => {
            const { span, depth } = visibleSpans[virtualItem.index]
            const hasChildren = (trace.spansByParent.get(span.span_id)?.length || 0) > 0
            
            return (
              <div
                key={span.span_id}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: `${virtualItem.size}px`,
                  transform: `translateY(${virtualItem.start}px)`
                }}
              >
                <SpanRow
                  span={span}
                  depth={depth}
                  isExpanded={expandedSpans.has(span.span_id)}
                  hasChildren={hasChildren}
                  onToggle={() => toggleSpanExpanded(span.span_id)}
                  onSelect={() => handleSpanSelect(span.span_id)}
                  isSelected={selectedSpanId === span.span_id}
                />
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}