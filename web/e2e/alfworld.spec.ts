import { expect, test, type Locator, type Page } from '@playwright/test'
import type { AlfworldIndex, Interaction, Trace } from '../src/content/alfworld'

const ALFWORLD_URL = '/alfworld.html'
const modes = ['eo', 'pe-s', 'pe-d-f', 'pe-d-s', 'pc-f', 'pc-s']
const goal = 'Put the book on the desk.'
const model = 'fixture-model'
const nativeCall = {
  id: 'call_plan', type: 'function', function: {
    name: 'request_plan', arguments: '{\n  "reason": "Book found  <tag>",\n  "evidence_refs": [2]\n}\n',
  },
}
const tools = [{ type: 'function', function: { name: 'request_plan', parameters: { type: 'object' } } }]

// Synthetic protocol fixtures exercise the reader without loading archived experiments.
function makeTrace(mode: string): Trace {
  const interactions: Interaction[] = [
    { id: '1', kind: 'observation', title: '初始环境观察 · Observation #1', content: 'A room with a desk.' },
  ]
  if (mode !== 'eo') interactions.push(
    { id: '2', kind: 'call', marker: 'P', role: 'planner', title: 'Planner 调用',
      phase: 'Initial Sub-Plan Generation',
      messages: [{ role: 'user', content: `Task: ${goal}\nObservation #1: A room with a desk.\nKeep  spaces and <tags>.` }],
      output: '{\n  "assessment": "Need to find the book.",\n  "full_plan": [{"id":1,"stage_objective":"Find the book"}]\n}' },
    { id: '3', kind: 'boundary', marker: mode.startsWith('pc-') ? 'D' : 'G', title: mode.startsWith('pc-') ? '委派阶段 1' : '交付规划',
      content: 'Find the book.', requestId: mode.startsWith('pc-') ? '阶段 1' : '整任务', planVersion: 1 },
  )
  interactions.push(
    { id: '10', kind: 'call', marker: 'E', role: 'executor', title: 'Executor 调用',
      messages: [{ role: 'user', content: `Task: ${goal}\nComplete interaction history:\nObservation #1: A room with a desk.\n\nUse  exact spacing.` }],
      output: 'Thought: Inspect the room.\nAction: look\n' },
    { id: '11', kind: 'observation', title: '环境反馈 · Observation #2', content: '动作：look\n\nA book is visible.' },
  )
  if (mode.startsWith('pe-d-')) interactions.push(
    { id: '12', kind: 'call', marker: 'E', role: 'executor', title: 'Executor 规划求助',
      messages: [{ role: 'user', content: `Task: ${goal}\nHistory:\nObservation #2 after look: A book is visible.` }],
      output: '', tools, toolChoice: 'auto', toolCalls: [nativeCall] },
    { id: '13', kind: 'call', marker: 'P', role: 'planner', title: 'Planner 调用', phase: 'Continuous Execution Monitoring',
      messages: [{ role: 'user', content: 'Task and complete history\nObservation #2: A book is visible.\nExecutor request: Book found  <tag>' }],
      output: '{\n  "assessment": "The book is visible.",\n  "stage_objective": "Take the book",\n  "evidence_refs": [2]\n}' },
    { id: '14', kind: 'boundary', marker: 'R', title: '返回原生工具结果 · request_plan', content: 'Take the book.' },
    { id: '15', kind: 'call', marker: 'E', role: 'executor', title: 'Executor 调用',
      messages: [
        { role: 'user', content: `Task: ${goal}\nComplete history embedded once.\nObservation #2: A book is visible.` },
        { role: 'assistant', content: null, tool_calls: [nativeCall] },
        { role: 'tool', tool_call_id: 'call_plan', content: 'Take the book.\nKeep  original text.' },
      ], output: 'Thought: Follow the updated plan.\nAction: take book 1 from desk 1\n' },
  )
  if (mode.startsWith('pc-')) interactions.push(
    { id: '12', kind: 'call', marker: 'P', role: 'planner', title: 'Planner 调用', phase: 'Continuous Execution Monitoring',
      messages: [{ role: 'user', content: `Task: ${goal}\nObservation #2: A book is visible.\nCurrent phase: Find the book.` }],
      output: '{\n  "assessment": "The book is visible.",\n  "decision": "advance",\n  "evidence_refs": [2]\n}' },
    { id: '13', kind: 'boundary', marker: 'R', title: '记录上一阶段结果',
      content: '已验证 · Find the book.\nThe book is visible.\n观察编号 2' },
    { id: '14', kind: 'boundary', marker: 'D', title: '委派阶段 2', requestId: '阶段 2', stageId: 2,
      stageObjective: 'Take the book.', content: 'Take the book.\n完成条件：The book is held.' },
  )
  interactions.push({ id: '20', kind: 'boundary', marker: 'V', title: '环境原生评分',
    content: mode === 'pc-f' ? '缺评' : mode === 'eo' ? '失败 · 得分 0' : '成功 · 得分 1' })
  return { id: `fixture-${mode}`, mode, model, taskId: '1', goal, interactions }
}

const traces = new Map(modes.map(mode => [`fixture-${mode}`, makeTrace(mode)]))
const index: AlfworldIndex = {
  schemaVersion: 1, runId: 'synthetic-current-protocol', benchmark: 'ALFWorld', selection: 'single_task', split: 'dev',
  protocolVersion: 'two-phase-v3', manifestUrl: 'fixture-manifest.json', models: [model], modes,
  roleModels: { [model]: { planner: 'fixture-planner', executor: model } },
  tasks: [{ id: '1', goal }], budget: { environmentStepLimit: 20, contextWindow: { max_input_tokens: null } },
  trials: modes.map(mode => ({
    id: `fixture-${mode}`, taskId: '1', model, mode,
    score: mode === 'pc-f' ? null : mode === 'eo' ? 0 : 1,
    success: mode === 'pc-f' ? null : mode !== 'eo',
    stop: mode === 'pc-f' ? '运行错误' : '环境任务终止',
    stopReason: mode === 'pc-f' ? 'runtime_error' : 'task_finish',
    actions: 2, plannerCalls: mode === 'eo' ? 0 : mode === 'pe-s' ? 1 : 2, executorCalls: 2,
    tokens: 100, knownTokenCalls: 2, totalTokenCalls: 3, archivedAttempts: 1,
    traceUrl: `alfworld/data/traces/fixture-${mode}.json`,
  })),
}

async function mockData(page: Page) {
  await page.route('**/alfworld/data/**', async route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname === '/alfworld/data/index.json') return route.fulfill({ json: index })
    const id = pathname.match(/\/traces\/([^/]+)\.json$/)?.[1]
    const trace = id ? traces.get(id) : undefined
    return trace ? route.fulfill({ json: trace }) : route.fulfill({ status: 404, body: 'Unknown synthetic fixture' })
  })
}

async function select(page: Page, label: string, option: string, searchable = false) {
  const control = page.getByRole('combobox', { name: label, exact: true })
  await control.click()
  if (searchable) await control.fill(option)
  await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({ has: page.getByText(option, { exact: true }) }).click()
}

async function expectRawCalls(reader: Locator, trialId: string) {
  const expected = traces.get(trialId)!.interactions.filter(item => item.kind === 'call')
  const calls = reader.locator('.aw-interaction:has(.aw-input)')
  await expect(calls).toHaveCount(expected.length)
  for (const [index, interaction] of expected.entries()) {
    const call = calls.nth(index)
    const messages = interaction.messages ?? []
    expect(await call.locator('.aw-prompt-message > h5').allTextContents()).toEqual(messages.map((message, index) =>
      `${index + 1} · ${message.role}${message.tool_call_id ? ` · ${message.tool_call_id}` : ''}`))
    expect(await call.locator('.aw-prompt-message > pre.aw-raw-text').allTextContents()).toEqual(messages.map(message => message.content ?? ''))
    expect(await call.locator('.aw-output > pre.aw-raw-text').textContent()).toBe(interaction.output ?? '')
    for (const [toolIndex, tool] of (interaction.toolCalls ?? []).entries()) {
      expect(await call.locator('.aw-output .aw-tool-call pre').nth(toolIndex).textContent()).toBe(tool.function.arguments)
    }
  }
  return expected
}

test.beforeEach(async ({ page }) => { await mockData(page) })

test('reads six current protocols with lazy trajectories, filters, raw calls and observation references', async ({ page }) => {
  const errors: string[] = []
  const traceRequests: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (request.url().includes('/alfworld/data/traces/')) traceRequests.push(request.url()) })
  await page.goto(ALFWORLD_URL)
  await expect(page.getByRole('heading', { name: 'ALFWorld 实验结果', exact: true })).toBeVisible()
  await expect(page.locator('.aw-page-header')).toContainText('1 个任务 × 1 组角色模型配置 × 6 种架构 · 5 条有效评分 · 1 条缺评')
  await expect(page.getByRole('tab', { name: '结果分析', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.aw-role-models')).toHaveText(`Planner：fixture-planner · Executor：${model}。EO 不调用 Planner。`)
  await expect(page.locator('body')).not.toContainText('Planner 与 Executor 使用同一基座模型')
  expect(traceRequests).toEqual([])
  await page.getByRole('tab', { name: '轨迹阅读', exact: true }).click()
  await select(page, '选择任务', `1 · ${goal}`, true)
  await select(page, '筛选模型', model)
  await expect(page.locator('.aw-trial-table tbody tr[data-row-key]')).toHaveCount(6)
  const reader = page.getByRole('tabpanel', { name: '轨迹阅读', exact: true }).getByTestId('trajectory-reader')
  for (const mode of modes) {
    await select(page, '筛选架构', mode.toUpperCase())
    await expect(page.locator('.aw-trial-table tbody tr[data-row-key]')).toHaveCount(1)
    await page.getByRole('button', { name: `读取轨迹 fixture-${mode}`, exact: true }).click()
    await expect(reader.locator('.aw-trace-heading h2')).toContainText(mode.toUpperCase())
    await expectRawCalls(reader, `fixture-${mode}`)
    await expect(reader.getByRole('heading', { name: '环境反馈 · Observation #2', exact: true })).toBeVisible()
    const markers = await reader.locator('.aw-timeline .aw-node').allTextContents()
    expect(markers.at(-1)).toBe('V')
    expect(markers.includes('P')).toBe(mode !== 'eo')
    expect(markers.includes('D')).toBe(mode.startsWith('pc-'))
    expect(markers.filter(marker => marker === 'G').length).toBe(mode.startsWith('pe-') ? 1 : 0)
    if (mode.startsWith('pc-')) await expect(reader).toContainText('观察编号 2')
  }
  const boundary = reader.locator('.aw-interaction').filter({ has: page.getByRole('heading', { name: '委派阶段 2', exact: true }) })
  await reader.getByRole('navigation', { name: '按事件顺序查看模型调用与执行边界' }).getByRole('button', { name: '委派阶段 2 · 事件 14', exact: true }).click()
  await expect(boundary).toBeInViewport()
  await select(page, '筛选架构', '全部架构')
  await select(page, '筛选结果', '缺评')
  await expect(page.locator('.aw-trial-table tbody tr[data-row-key]')).toHaveCount(1)
  await expect(page.locator('.aw-trial-table tbody')).toContainText('PC-F')
  await select(page, '筛选结果', '失败')
  await expect(page.locator('.aw-trial-table tbody tr[data-row-key]')).toHaveCount(1)
  await expect(page.locator('.aw-trial-table tbody')).toContainText('EO')
  await select(page, '筛选结果', '成功')
  await expect(page.locator('.aw-trial-table tbody tr[data-row-key]')).toHaveCount(4)
  expect(errors).toEqual([])
})

test('compares a matched task, swaps sides and preserves the selected trajectories on reload', async ({ page }) => {
  await page.goto(`${ALFWORLD_URL}?tab=read&left=fixture-pc-s`)
  await page.getByRole('button', { name: /对比同任务的其他架构$/ }).click()
  const left = page.getByTestId('comparison-left')
  const right = page.getByTestId('comparison-right')
  await expect(left.locator('.aw-trace-heading h2')).toContainText('PC-S')
  await expect(right.locator('.aw-trace-heading h2')).toContainText('EO')
  await select(page, '右侧轨迹', `任务 1 · ${model} · PE-D-S · 成功`, true)
  await expect(right.locator('.aw-trace-heading h2')).toContainText('PE-D-S')
  await expect(left.locator('.aw-trace-heading')).toContainText('任务 1')
  await expect(right.locator('.aw-trace-heading')).toContainText('任务 1')
  await expectRawCalls(left.getByTestId('trajectory-reader'), 'fixture-pc-s')
  await expectRawCalls(right.getByTestId('trajectory-reader'), 'fixture-pe-d-s')
  await page.getByRole('button', { name: /交换左右$/ }).click()
  await expect(left.locator('.aw-trace-heading h2')).toContainText('PE-D-S')
  await expect(right.locator('.aw-trace-heading h2')).toContainText('PC-S')
  await page.reload()
  await expect(page.getByRole('tab', { name: '轨迹对比', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(left.locator('.aw-trace-heading h2')).toContainText('PE-D-S')
  await expect(right.locator('.aw-trace-heading h2')).toContainText('PC-S')
})

test('preserves native tool arguments, null assistant content, paired results and assessment JSON', async ({ page }) => {
  await page.goto(`${ALFWORLD_URL}?tab=read&left=fixture-pe-d-s`)
  const reader = page.getByRole('tabpanel', { name: '轨迹阅读', exact: true }).getByTestId('trajectory-reader')
  await expectRawCalls(reader, 'fixture-pe-d-s')
  const toolRequest = reader.locator('.aw-interaction').filter({ has: page.getByRole('heading', { name: 'Executor 规划求助', exact: true }) })
  expect(await toolRequest.locator('.aw-output .aw-tool-call pre').textContent()).toBe(nativeCall.function.arguments)
  await toolRequest.getByText('已注册工具与选择方式', { exact: true }).click()
  expect(await toolRequest.locator('details > pre').textContent()).toBe(JSON.stringify({ tools, tool_choice: 'auto' }, null, 2))
  const pairedCall = reader.locator('.aw-interaction:has(.aw-input)').last()
  await expect(pairedCall.locator('.aw-prompt-message').nth(1).locator('> pre')).toHaveText('')
  expect(await pairedCall.locator('.aw-prompt-message').nth(1).locator('.aw-tool-call pre').textContent()).toBe(nativeCall.function.arguments)
  expect(await pairedCall.locator('.aw-prompt-message').nth(2).locator('> pre').textContent()).toBe('Take the book.\nKeep  original text.')
  await expect(reader).toContainText('"assessment": "The book is visible."')
  await expect(reader).not.toContainText('thinking_summary')
})
