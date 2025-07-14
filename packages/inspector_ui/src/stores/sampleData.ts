import type { components } from '../generated/api'
import type { Span } from './traceStore'

type SessionMeta = components['schemas']['SessionMeta']

// Sample sessions for development
export const sampleSessions: SessionMeta[] = [
  {
    id: 'session-001',
    status: 'running',
    engine: 'asyncio',
    started_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(), // 5 mins ago
    title: 'Orchestrator Workflow - Planning Task',
    tags: ['orchestrator', 'planning']
  },
  {
    id: 'session-002',
    status: 'paused',
    engine: 'asyncio',
    started_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(), // 15 mins ago
    title: 'Human Input Required - Code Review',
    tags: ['human-input', 'review']
  },
  {
    id: 'session-003',
    status: 'completed',
    engine: 'temporal',
    started_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(), // 1 hour ago
    ended_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(), // 30 mins ago
    title: 'Data Processing Pipeline',
    tags: ['temporal', 'data-pipeline']
  },
  {
    id: 'session-004',
    status: 'failed',
    engine: 'inbound',
    started_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2 hours ago
    ended_at: new Date(Date.now() - 1.5 * 60 * 60 * 1000).toISOString(),
    title: 'MCP Request - Tool Call Failed',
    tags: ['mcp', 'error']
  }
]

// Sample spans for a trace
export const sampleSpans: Record<string, Span[]> = {
  'session-001': [
    {
      trace_id: 'trace-001',
      span_id: 'span-001',
      name: 'workflow.run',
      start_time: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      attributes: {
        'mcp.workflow.type': 'orchestrator',
        'mcp.workflow.input_json': JSON.stringify({
          task: 'Create a plan for implementing a new feature'
        }),
        'session.id': 'session-001'
      },
      status: { status_code: 'UNSET' }
    },
    {
      trace_id: 'trace-001',
      span_id: 'span-002',
      parent_span_id: 'span-001',
      name: 'agent.call',
      start_time: new Date(Date.now() - 4.5 * 60 * 1000).toISOString(),
      attributes: {
        'mcp.agent.name': 'PlannerAgent',
        'mcp.agent.class': 'Agent'
      }
    },
    {
      trace_id: 'trace-001',
      span_id: 'span-003',
      parent_span_id: 'span-002',
      name: 'llm.generate',
      start_time: new Date(Date.now() - 4 * 60 * 1000).toISOString(),
      end_time: new Date(Date.now() - 3.5 * 60 * 1000).toISOString(),
      attributes: {
        'mcp.llm.provider': 'anthropic',
        'mcp.llm.model': 'claude-3-sonnet-20240229',
        'mcp.llm.prompt_json': JSON.stringify({
          role: 'user',
          content: 'Create a detailed implementation plan...'
        }),
        'mcp.llm.response_json': JSON.stringify({
          role: 'assistant',
          content: 'Here is the implementation plan:\n1. First step...'
        })
      },
      status: { status_code: 'OK' }
    }
  ],
  'session-002': [
    {
      trace_id: 'trace-002',
      span_id: 'span-010',
      name: 'workflow.run',
      start_time: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
      attributes: {
        'mcp.workflow.type': 'review',
        'session.id': 'session-002'
      },
      events: [
        {
          name: 'WaitingOnSignal',
          time: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
          attributes: {
            signal_name: 'human_input',
            prompt: 'Please review the generated code and provide feedback'
          }
        }
      ]
    }
  ]
}

// Sample SSE events for development
export const sampleEvents = [
  {
    type: 'SessionStarted',
    session_id: 'session-005',
    engine: 'asyncio',
    title: 'New Live Session',
    timestamp: new Date().toISOString()
  },
  {
    type: 'Heartbeat',
    session_id: 'session-001',
    llm_calls_delta: 2,
    tokens_delta: 1500,
    tool_calls_delta: 1,
    current_span_count: 15,
    timestamp: new Date().toISOString()
  }
]