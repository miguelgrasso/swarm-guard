export type TaskStatus = 'done' | 'progress' | 'pending'

export type Task = {
  id: string
  title: string
  mark: string
  optional: boolean
  status: TaskStatus
  percent: number
  line: number
  phase: string
  parentId?: string
  subtaskIds: string[]
  requirements: string[]
  properties: string[]
  text: string
}

export type Phase = { name: string; short: string; taskIds: string[]; percent: number; done: number; progress: number; pending: number }

export type ReqItem = { id: string; title: string; text: string; line: number }

export type DesignHeading = { heading: string; line: number; level: number; validates: string[]; words: string[] }

export type SpecBoard = {
  name: string
  dir: string
  phases: Phase[]
  tasks: Task[]
  requirements: Record<string, ReqItem>
  design: DesignHeading[]
  done: number
  progress: number
  pending: number
  total: number
  percent: number
}

export type Board = { specs: SpecBoard[]; loadedAt: number; aidlc?: string; error?: string }

declare module 'claude-code' {
  interface PluginState {
    'spec-board': { board: Shaped<Board>; selected: string | null }
  }
}
