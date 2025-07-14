import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { immer } from 'zustand/middleware/immer'
import { enableMapSet } from 'immer'
import type { components } from '../generated/api'

// Enable Immer's MapSet plugin
enableMapSet()

type SessionMeta = components['schemas']['SessionMeta']

interface SessionStore {
  sessions: Map<string, SessionMeta>
  setSessions: (sessions: SessionMeta[]) => void
  updateSession: (id: string, updates: Partial<SessionMeta>) => void
  getSession: (id: string) => SessionMeta | undefined
  getSortedSessions: () => SessionMeta[]
}

// Create store with Immer for immutable updates
export const useSessionStore = create<SessionStore>()(
  devtools(
    immer((set, get) => ({
      sessions: new Map(),
      
      setSessions: (sessions) => set((state) => {
        console.log('[SessionStore] Setting sessions:', sessions)
        // Clear existing sessions and add new ones
        state.sessions.clear()
        sessions.forEach(session => {
          state.sessions.set(session.id, session)
        })
        console.log('[SessionStore] Sessions map size:', state.sessions.size)
      }),
      
      updateSession: (id, updates) => set((state) => {
        const session = state.sessions.get(id)
        if (session) {
          state.sessions.set(id, { ...session, ...updates })
        }
      }),
      
      getSession: (id) => {
        return get().sessions.get(id)
      },
      
      getSortedSessions: () => {
        const sessions = Array.from(get().sessions.values())
        // Sort by started_at descending (newest first)
        return sessions.sort((a, b) => 
          new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
        )
      }
    })),
    {
      name: 'session-store',
      serialize: {
        options: {
          map: true,
          set: true
        }
      }
    }
  )
)