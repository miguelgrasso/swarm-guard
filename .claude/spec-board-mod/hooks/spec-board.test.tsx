import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

const PANE = {
  plugin: 'spec-board',
  component: 'Pane',
  requestId: 'spec-board',
  props: {
    title: 'Spec board',
    isFocused: false,
    bodyColumns: 80,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

const RUN = { origin: { kind: 'sdk' }, presentation: { isFullscreen: false, columns: 80 } } as const

const TASKS = `# Implementation Plan: demo

## Phase A — Offline

- [x] A1. Scaffolding
  - _Requirements: 8.1_

- [ ] A2. BudgetGuard
  - _Requirements: 3.4_
  - [x] A2.1 Property test (P2)
    - **Validates: Requirements 3.4 — Correctness Property P2**
  - [ ] A2.2 Another test

## Phase B — Live

- [ ] B1. Bedrock run
  - _Requirements: 6.1_
`

const REQUIREMENTS = `# Requirements

### Requirement 3: Configs

#### Acceptance Criteria

1. THE Baseline SHALL apply defaults.
4. THE Budget Guard SHALL stop the swarm.

### Requirement 8: Structure

1. THE Project SHALL follow the structure.
`

const DESIGN = `# Design

## Components and Interfaces

### 3.2 BudgetGuard

text

## Correctness Properties

### Property 2: Budget Guard Threshold Monotonicity

**Validates: Requirements 3.4**
`

function files(on: On): void {
  const texts: Record<string, string> = {
    '.kiro/specs/demo/tasks.md': TASKS,
    '.kiro/specs/demo/requirements.md': REQUIREMENTS,
    '.kiro/specs/demo/design.md': DESIGN,
  }
  on('fs.list', () => ({
    value: [{ name: 'demo', kind: 'dir', size: 0, mtimeMs: 0, isLink: false }],
  }))
  // The engine may hand the hook a resolved path: match on the relative suffix.
  const lookup = (path: string): string | undefined => {
    const normal = path.replace(/\\/g, '/')
    const key = Object.keys(texts).find(k => normal === k || normal.endsWith('/' + k))
    return key === undefined ? undefined : texts[key]
  }
  on('fs.exists', (_, e) => ({ value: lookup(e.path) !== undefined }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 1, isLink: false } }))
  on('fs.read', (_, e) => {
    const text = lookup(e.path)
    return text === undefined ? { deny: `missing: ${e.path}` } : { value: text }
  })
  on('ui.status', () => ({ value: undefined }))
  mock.clock(on)
  mock.store(on)
  on('command.register', () => ({ value: { command: 'spec-board' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
}

test('the pane shows a semaphore per task with phase progress', async ($, on) => {
  files(on)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })

    const header = await ui.find({ type: 'Text', text: /spec demo/ })
    expect(header?.text).toContain('1/3')

    // A2 has one of two subtasks done and its own box unchecked: in progress, 50%.
    const a2 = await ui.find({ type: 'Button', text: /A2 BudgetGuard/ })
    expect(a2?.text).toContain('50%')
    expect(a2?.text).toContain('[3.4]')

    const phaseB = await ui.find({ type: 'Text', text: /Phase B/ })
    expect(phaseB?.text).toContain('0%')

    await ui.unmount()
  }
})

test('the command describes a task with its requirements and design', async ($, on) => {
  files(on)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: false })

  const ran = await $.command.run({ command: 'spec-board', args: 'A2', ...RUN })
  expect(ran.text).toContain('A2 BudgetGuard — progress 50%')
  expect(ran.text).toContain('3.4 — THE Budget Guard SHALL stop the swarm.')
  expect(ran.text).toContain('Property 2: Budget Guard Threshold Monotonicity')
  expect(ran.text).toContain('3.2 BudgetGuard')
})

test('a manual percentage marks a pending task as in progress', async ($, on) => {
  files(on)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: false })

  const ran = await $.command.run({ command: 'spec-board', args: 'B1 40', ...RUN })
  expect(ran.text).toContain('B1 → 40% (progress)')
})
