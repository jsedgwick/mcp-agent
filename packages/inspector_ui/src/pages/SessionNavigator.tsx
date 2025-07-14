import React, { useEffect } from 'react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import { useSessionStore } from '../stores/sessionStore'
import { useUIStore } from '../stores/uiStore'
import { useSSE } from '../hooks/useSSE'
import { useTraceLoader } from '../hooks/useTraceLoader'
import { SpanTree } from '../components/SpanTree'
import { InspectorTabs } from '../components/InspectorTabs'
import { SessionCard } from '../components/SessionCard'
import type { components } from '../generated/api'

type SessionMeta = components['schemas']['SessionMeta']

// Main SessionNavigator component
export function SessionNavigator() {
  const { sessions, setSessions, getSortedSessions } = useSessionStore()
  const { selectedSessionId, setSelectedSession, selectedSpanId, setSelectedSpan, searchQuery, setLastError } = useUIStore()
  
  // Connect to SSE for real-time updates
  useSSE()
  
  // Load traces for selected session
  useTraceLoader()
  
  // Fetch sessions on mount
  useEffect(() => {
    console.log('[SessionNavigator] Fetching sessions...')
    fetch('/_inspector/sessions')
      .then(response => {
        console.log('[SessionNavigator] Response status:', response.status)
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        return response.json()
      })
      .then(data => {
        console.log('[SessionNavigator] Data received:', data)
        if (data.sessions) {
          console.log(`[SessionNavigator] Setting ${data.sessions.length} sessions`)
          setSessions(data.sessions)
        }
        if (data.temporal_error) {
          console.warn('Temporal connection issue:', data.temporal_error)
        }
      })
      .catch(error => {
        console.error('[SessionNavigator] Failed to fetch sessions:', error)
        setLastError(error.message)
      })
  }, [setSessions, setLastError])
  
  // Get filtered and sorted sessions
  const sortedSessions = getSortedSessions()
  const filteredSessions = searchQuery 
    ? sortedSessions.filter(session => 
        session.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        session.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        session.tags?.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : sortedSessions
  
  return (
    <div className="h-full">
      <PanelGroup direction="horizontal" className="h-full">
        {/* Session List Panel */}
        <Panel defaultSize={20} minSize={15} maxSize={30}>
          <div className="h-full border-r border-gray-200 flex flex-col">
            <div className="p-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Sessions</h2>
              <p className="text-sm text-gray-500 mt-1">
                {filteredSessions.length} of {sortedSessions.length} sessions
              </p>
            </div>
            
            <div className="flex-1 overflow-y-auto p-4">
              {filteredSessions.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  {searchQuery ? 'No sessions match your search' : 'No sessions found'}
                </div>
              ) : (
                filteredSessions.map(session => (
                  <SessionCard
                    key={session.id}
                    session={session}
                    isSelected={session.id === selectedSessionId}
                    onClick={() => setSelectedSession(session.id)}
                  />
                ))
              )}
            </div>
          </div>
        </Panel>
        
        <PanelResizeHandle className="w-1 bg-gray-200 hover:bg-gray-300 transition-colors cursor-col-resize" />
        
        {/* Main Content Area */}
        {selectedSessionId ? (
          <>
            {/* Span Tree Panel */}
            <Panel defaultSize={35} minSize={25} maxSize={50}>
              <div className="h-full border-r border-gray-200">
                <SpanTree onSpanSelect={setSelectedSpan} />
              </div>
            </Panel>
            
            <PanelResizeHandle className="w-1 bg-gray-200 hover:bg-gray-300 transition-colors cursor-col-resize" />
            
            {/* Inspector Panel */}
            <Panel defaultSize={45} minSize={30}>
              <div className="h-full">
                <InspectorTabs selectedSpanId={selectedSpanId} />
              </div>
            </Panel>
          </>
        ) : (
          <Panel>
            <div className="h-full flex items-center justify-center text-gray-500">
              Select a session to view details
            </div>
          </Panel>
        )}
      </PanelGroup>
    </div>
  )
}