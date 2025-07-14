import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { immer } from 'zustand/middleware/immer'
import { enableMapSet } from 'immer'

// Enable Immer's MapSet plugin (in case it wasn't already enabled)
enableMapSet()

interface UIStore {
  // Session selection
  selectedSessionId: string | null
  setSelectedSession: (sessionId: string | null) => void
  
  // Span selection
  selectedSpanId: string | null
  setSelectedSpan: (spanId: string | null) => void
  
  // Span tree expansion state
  expandedSpans: Set<string>
  toggleSpanExpanded: (spanId: string) => void
  expandAllSpans: () => void
  collapseAllSpans: () => void
  
  // Inspector tabs
  selectedTab: 'attributes' | 'state' | 'context'
  setSelectedTab: (tab: 'attributes' | 'state' | 'context') => void
  
  // SSE connection state
  sseConnected: boolean
  sseReconnectCount: number
  setSseConnected: (connected: boolean) => void
  incrementSseReconnect: () => void
  
  // Search/filter state
  searchQuery: string
  setSearchQuery: (query: string) => void
  
  // View preferences
  showTimestamps: boolean
  setShowTimestamps: (show: boolean) => void
  
  // Error state
  lastError: string | null
  setLastError: (error: string | null) => void
}

export const useUIStore = create<UIStore>()(
  devtools(
    immer((set, get) => ({
      // Session selection
      selectedSessionId: null,
      setSelectedSession: (sessionId) => set((state) => {
        state.selectedSessionId = sessionId
      }),
      
      // Span selection
      selectedSpanId: null,
      setSelectedSpan: (spanId) => set((state) => {
        state.selectedSpanId = spanId
      }),
      
      // Span tree expansion
      expandedSpans: new Set(),
      toggleSpanExpanded: (spanId) => set((state) => {
        if (state.expandedSpans.has(spanId)) {
          state.expandedSpans.delete(spanId)
        } else {
          state.expandedSpans.add(spanId)
        }
      }),
      expandAllSpans: () => set((state) => {
        // This will be populated when trace is loaded
        state.expandedSpans.clear()
      }),
      collapseAllSpans: () => set((state) => {
        state.expandedSpans.clear()
      }),
      
      // Inspector tabs
      selectedTab: 'attributes',
      setSelectedTab: (tab) => set((state) => {
        state.selectedTab = tab
      }),
      
      // SSE connection
      sseConnected: false,
      sseReconnectCount: 0,
      setSseConnected: (connected) => set((state) => {
        state.sseConnected = connected
        if (connected) {
          state.sseReconnectCount = 0
        }
      }),
      incrementSseReconnect: () => set((state) => {
        state.sseReconnectCount += 1
      }),
      
      // Search/filter
      searchQuery: '',
      setSearchQuery: (query) => set((state) => {
        state.searchQuery = query
      }),
      
      // View preferences
      showTimestamps: true,
      setShowTimestamps: (show) => set((state) => {
        state.showTimestamps = show
      }),
      
      // Error state
      lastError: null,
      setLastError: (error) => set((state) => {
        state.lastError = error
      })
    })),
    {
      name: 'ui-store',
      serialize: {
        options: {
          set: true
        }
      }
    }
  )
)