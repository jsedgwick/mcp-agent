import React from 'react'
import type { components } from '../generated/api'

type SessionMeta = components['schemas']['SessionMeta']

// Session status badge component
function StatusBadge({ status }: { status: string }) {
  const statusColors = {
    running: 'bg-green-100 text-green-800',
    paused: 'bg-yellow-100 text-yellow-800',
    failed: 'bg-red-100 text-red-800',
    completed: 'bg-gray-100 text-gray-800'
  }
  
  return (
    <span className={`
      inline-flex items-center px-2 py-0.5 rounded text-xs font-medium
      ${statusColors[status as keyof typeof statusColors] || statusColors.completed}
    `}>
      {status}
    </span>
  )
}

// Session card component
export function SessionCard({ session, isSelected, onClick }: { 
  session: SessionMeta
  isSelected: boolean
  onClick: () => void
}) {
  const formatTime = (isoString: string) => {
    const date = new Date(isoString)
    return date.toLocaleTimeString()
  }
  
  const getDuration = () => {
    if (!session.ended_at) return 'In progress'
    const start = new Date(session.started_at).getTime()
    const end = new Date(session.ended_at).getTime()
    const durationMs = end - start
    const minutes = Math.floor(durationMs / 60000)
    return `${minutes}m`
  }
  
  return (
    <div
      onClick={onClick}
      className={`
        p-4 mb-2 rounded-lg border cursor-pointer transition-colors
        ${isSelected 
          ? 'border-blue-500 bg-blue-50' 
          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
        }
      `}
      role="button"
      tabIndex={0}
      aria-selected={isSelected}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-medium text-gray-900 truncate">
            {session.title}
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            {session.id} • {formatTime(session.started_at)}
            {session.ended_at && ` • ${getDuration()}`}
          </p>
          {session.tags && session.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {session.tags.map(tag => (
                <span
                  key={tag}
                  className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="ml-4 flex flex-col items-end gap-2">
          <StatusBadge status={session.status} />
          <span className={`
            inline-flex items-center px-2 py-0.5 rounded text-xs font-medium
            ${session.engine === 'temporal' 
              ? 'bg-purple-100 text-purple-800'
              : session.engine === 'inbound'
              ? 'bg-orange-100 text-orange-800'
              : 'bg-gray-100 text-gray-800'
            }
          `}>
            {session.engine}
          </span>
        </div>
      </div>
    </div>
  )
}