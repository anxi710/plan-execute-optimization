import { expect, test, type Locator, type Page } from '@playwright/test'
import type { Trace } from '../src/content/alfworld'

const ALFWORLD_URL = 'http://127.0.0.1:4174/alfworld.html'

async function select(page: Page, label: string, option: string, searchable = false) {
  const control = page.getByRole('combobox', { name: label, exact: true })
  await control.click()
  if (searchable) await control.fill(option)
  await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({ has: page.getByText(option, { exact: true }) }).click()
}

async function expectRawCalls(page: Page, reader: Locator, trialId: string) {
  const response = await page.request.get(`http://127.0.0.1:4174/alfworld/data/traces/${trialId}.json`)
  expect(response.ok()).toBe(true)
  const trace: Trace = await response.json()
  const expected = trace.interactions.filter(item => item.kind === 'call')
  const calls = reader.locator('.aw-interaction:has(.aw-input)')
  await expect(calls).toHaveCount(expected.length)
  for (const [index, interaction] of expected.entries()) {
    const call = calls.nth(index)
    const messages = interaction.messages ?? []
    expect(await call.locator('.aw-prompt-message h5').allTextContents()).toEqual(messages.map((message, index) => `${index + 1} · ${message.role}`))
    expect(await call.locator('.aw-prompt-message pre.aw-raw-text').allTextContents()).toEqual(messages.map(message => message.content))
    expect(await call.locator('.aw-output pre.aw-raw-text').textContent()).toBe(interaction.output ?? '')
    if (interaction.reasoning) expect(await call.locator('.aw-reasoning pre.aw-raw-text').textContent()).toBe(interaction.reasoning)
  }
  const labels = await reader.evaluate(element => {
    const copy = element.cloneNode(true) as HTMLElement
    copy.querySelectorAll('pre.aw-raw-text').forEach(node => node.remove())
    return copy.textContent
  })
  expect(labels).not.toContain('timestamp')
  expect(labels).not.toContain('workspace_id')
  return expected
}

test('reads all four ALFWorld protocols, filters results and follows interaction boundaries', async ({ page }) => {
  const errors: string[] = []
  const traceRequests: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => { if (request.url().includes('/alfworld/data/traces/')) traceRequests.push(request.url()) })
  const preview = await page.request.get('http://127.0.0.1:4174/audit-preview.html')
  expect(preview.ok()).toBe(true)
  expect(await preview.text()).toContain('评分已终止 · 待人工核验')
  await page.goto('http://127.0.0.1:4174/audit.html')
  await page.locator('a[href="alfworld.html"]').first().click()
  await expect(page).toHaveURL(ALFWORLD_URL)
  await expect(page.getByRole('heading', { name: 'ALFWorld 实验结果', exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: '结果分析', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.aw-page-header')).toContainText('134 个任务 × 4 个模型 × 4 种架构 · 2,144 条有效评分')
  await expect(page.locator('body')).not.toContainText(/研究工作台|实验记录|Terminal-Bench|TerminalBench/)
  expect(traceRequests).toEqual([])

  await page.getByRole('tab', { name: '轨迹阅读', exact: true }).click()
  await select(page, '选择任务', '3 · put two pillow in sofa.', true)
  await select(page, '筛选模型', 'DeepSeek-V4.1-Flash')
  await expect(page.locator('.aw-trial-table tbody tr[data-row-key]')).toHaveCount(4)
  const reader = page.getByRole('tabpanel', { name: '轨迹阅读', exact: true }).getByTestId('trajectory-reader')

  for (const mode of ['eo', 'pe-s', 'pe-d', 'pc']) {
    await select(page, '筛选架构', mode.toUpperCase())
    await expect(page.locator('.aw-trial-table tbody tr[data-row-key]')).toHaveCount(1)
    await page.getByRole('button', { name: `读取轨迹 m1-t3-${mode}`, exact: true }).click()
    await expect(reader.locator('.aw-trace-heading h2')).toContainText(mode.toUpperCase())
    await expect(reader.locator('.aw-prompt-message pre.aw-raw-text').first()).toBeVisible()
    await expect(reader.getByRole('heading', { name: '原始 response', exact: true }).first()).toBeVisible()
    const calls = await expectRawCalls(page, reader, `m1-t3-${mode}`)
    expect(calls.some(call => call.messages?.some(message => message.content.startsWith('Interact with a household to solve a task.')))).toBe(true)
    expect(calls.some(call => call.messages?.some(message => message.role === 'assistant'))).toBe(true)
    const markers = await reader.locator('.aw-timeline .aw-node').allTextContents()
    expect(markers.length).toBeGreaterThan(0)
    expect(markers.every(marker => /^[PEGDRV]$/.test(marker))).toBe(true)
    expect(markers.at(-1)).toBe('V')
    expect(markers.filter(marker => marker === 'G').length).toBe(mode === 'pe-s' ? 1 : mode === 'pe-d' ? markers.filter(marker => marker === 'P').length : 0)
    expect(markers.includes('D')).toBe(mode === 'pc')
    if (mode === 'eo') {
      await expect(reader.locator('.aw-interaction-title h3').filter({ hasText: 'Planner 调用' })).toHaveCount(0)
    } else {
      await expect(reader.locator('.aw-interaction-title h3').filter({ hasText: 'Planner 调用' }).first()).toBeVisible()
    }
  }

  await expect(reader.locator('.aw-request')).toHaveCount(0)
  const boundary = reader.locator('.aw-interaction').filter({ has: page.getByRole('heading', { name: '委派阶段 2', exact: true }) })
  await reader.getByRole('navigation', { name: '按事件顺序查看模型调用与执行边界' }).getByRole('button', { name: /^委派阶段 2 · 事件 / }).click()
  await expect(boundary).toBeInViewport()

  await select(page, '筛选结果', '失败')
  await expect(page.locator('.aw-trial-table tbody tr[data-row-key]')).toHaveCount(0)
  await expect(page.locator('.aw-trial-table .ant-empty-description')).toHaveText('暂无数据')
  await select(page, '筛选结果', '成功')
  await expect(page.locator('.aw-trial-table tbody tr[data-row-key]')).toHaveCount(1)
  expect(errors).toEqual([])
})

test('compares the same task across architectures and preserves selected trajectories on reload', async ({ page }) => {
  await page.goto(`${ALFWORLD_URL}?tab=read&left=m1-t3-pc`)
  await page.getByRole('button', { name: /对比同任务的其他架构$/ }).click()
  const left = page.getByTestId('comparison-left')
  const right = page.getByTestId('comparison-right')
  await expect(left.locator('.aw-trace-heading h2')).toContainText('PC')
  await expect(right.locator('.aw-trace-heading h2')).toContainText('EO')
  await expect(left.locator('.aw-trace-heading')).toContainText('任务 3')
  await expect(right.locator('.aw-trace-heading')).toContainText('任务 3')

  await select(page, '右侧轨迹', '任务 3 · DeepSeek-V4.1-Flash · PE-D · 成功', true)
  await expect(right.locator('.aw-trace-heading h2')).toContainText('PE-D')
  await expectRawCalls(page, left.getByTestId('trajectory-reader'), 'm1-t3-pc')
  await expectRawCalls(page, right.getByTestId('trajectory-reader'), 'm1-t3-pe-d')
  await page.getByRole('button', { name: /交换左右$/ }).click()
  await expect(left.locator('.aw-trace-heading h2')).toContainText('PE-D')
  await expect(right.locator('.aw-trace-heading h2')).toContainText('PC')
  await page.reload()
  await expect(page.getByRole('tab', { name: '轨迹对比', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(left.locator('.aw-trace-heading h2')).toContainText('PE-D')
  await expect(right.locator('.aw-trace-heading h2')).toContainText('PC')
})

test('preserves complete raw prompts and a rejected planner response character for character', async ({ page }) => {
  await page.goto(`${ALFWORLD_URL}?tab=read&left=m4-t1-pe-d`)
  const reader = page.getByRole('tabpanel', { name: '轨迹阅读', exact: true }).getByTestId('trajectory-reader')
  await expect(reader.locator('.aw-trace-heading h2')).toContainText('Qwen3.8-27B')
  const calls = await expectRawCalls(page, reader, 'm4-t1-pe-d')
  expect(calls[0].messages?.[0].content).toContain('"event_id": 1')
  expect(calls[0].output).toContain('"evidence_refs": [\n    "1"\n  ]')
  expect(await reader.locator('.aw-output pre.aw-raw-text').textContent()).toBe(calls[0].output)
  await expect(reader.locator('.aw-evidence-value')).toHaveCount(0)
  await expect(reader).toContainText('unknown_evidence_ref')
})
