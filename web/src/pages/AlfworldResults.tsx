import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Alert, Button, Empty, Input, Select, Spin, Table, Tabs, Tag } from 'antd';
import { ArrowRightOutlined, SwapOutlined } from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import {
  modeName, pairedOutcomes, percent, protocols, summarize,
  type AlfworldIndex, type Interaction, type Trace, type Trial,
} from '../content/alfworld';
import './alfworld.css';

const integer = (value: number) => value.toLocaleString('en-US');
const labels: Record<string, string> = {
  executorLimit: 'Executor 调用上限', plannerLimits: 'Planner 调用上限', returnEvery: '每多少轮返回', plannerMaxTokens: 'Planner 每次输出 token 上限',
};

function ReadableContent({ value }: { value: unknown }): ReactNode {
  if (value === null || value === undefined) return <span className="aw-muted">无</span>;
  if (Array.isArray(value)) return value.length ? <ol className="aw-content-list">{value.map((item, index) => <li key={index}><ReadableContent value={item} /></li>)}</ol> : <span className="aw-muted">无</span>;
  if (typeof value === 'object') return <dl className="aw-fields">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{labels[key] ?? key.replaceAll('_', ' ')}</dt><dd><ReadableContent value={item} /></dd></div>)}</dl>;
  return <div className="aw-message-text">{String(value)}</div>;
}

function useJson<T>(url: string) {
  const [result, setResult] = useState<{ data?: T; error?: string }>({});
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setResult({});
    fetch(url, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error(`读取失败（HTTP ${response.status}）`);
      return await response.json() as T;
    }).then(data => { if (!controller.signal.aborted) setResult({ data }); })
      .catch((error: Error) => { if (!controller.signal.aborted) setResult({ error: error.message }); });
    return () => controller.abort();
  }, [url, retry]);
  return { ...result, reload: () => setRetry(value => value + 1) };
}

function LoadError({ error, reload, index = false }: { error: string; reload: () => void; index?: boolean }) {
  return <Alert type="error" showIcon title={index ? '实验数据尚未就绪' : '轨迹读取失败'} description={<><p>{error}。{index ? '请先在仓库根目录运行本地导出命令，再重试。' : '请重试，或重新导出本地数据。'}</p>{index && <code>/home/anxi/tools/miniconda3/envs/plan-test/bin/python src/recipe/planner-centered/export_alfworld.py</code>}<p><Button onClick={reload}>重新读取</Button></p></>} />;
}

function Analysis({ data }: { data: AlfworldIndex }) {
  const [model, setModel] = useState('all');
  const trials = data.trials.filter(trial => model === 'all' || trial.model === model);
  const total = summarize(data.trials);
  const baseline = trials.filter(trial => trial.mode === 'eo');
  const groups = data.modes.map(mode => ({ mode, ...summarize(trials.filter(trial => trial.mode === mode)) }));
  const rows = data.models.filter(item => model === 'all' || item === model).flatMap(model => data.modes.map(mode => {
    const subset = data.trials.filter(trial => trial.model === model && trial.mode === mode);
    return { key: `${model}/${mode}`, model, mode, ...summarize(subset), protocol: subset.filter(trial => trial.stopReason === 'protocol_error').length };
  }));
  const failures = Object.entries(trials.filter(trial => !trial.success).reduce<Record<string, number>>((counts, trial) => {
    counts[trial.stop] = (counts[trial.stop] ?? 0) + 1;
    return counts;
  }, {})).sort((a, b) => b[1] - a[1]);
  const protocolRows = data.models.filter(item => model === 'all' || item === model).map(model => ({ model, counts: data.modes.map(mode => data.trials.filter(trial => trial.model === model && trial.mode === mode && trial.stopReason === 'protocol_error').length) }));
  return <div className="aw-analysis">
    <section className="aw-takeaway">
      <h2>完整测试集中的架构表现</h2>
      <p>最终合并结果覆盖全部 {data.tasks.length} 个任务。四种架构各有 {integer(data.tasks.length * data.models.length)} 条评分，使用同一组任务进行比较。</p>
      <p>当前数据中，EO 的总体成功率最高。动态规划组包含 Planner 协议拒绝导致的失败，架构差异与模型遵循协议的能力共同影响结果。下方可按模型查看。</p>
      <p className="aw-muted">这是本轮未训练的框架评测。单次运行不提供多 seed 方差，也不能据此认定 Planner 的学习收益或某种架构普遍更优。</p>
    </section>
    <div className="aw-section-heading"><h2>成功率与配对差异</h2><Select aria-label="分析模型" value={model} onChange={setModel} options={[{ value: 'all', label: '全部模型' }, ...data.models.map(value => ({ value, label: value }))]} /></div>
    <div className="aw-analysis-grid">
      <figure className="aw-success-chart"><figcaption>原生成功率 <span>成功数 / 有评分轨迹</span></figcaption>{groups.map(group => <div className={`aw-bar-row aw-mode-${group.mode}`} key={group.mode}><strong>{modeName(group.mode)}</strong><div className="aw-bar-track"><div style={{ width: percent(group.wins, group.count) }} /></div><span>{percent(group.wins, group.count)}<small>{group.wins} / {group.count}</small></span></div>)}</figure>
      <div className="aw-paired"><h3>相对 EO，同任务的结果如何变化？</h3><p className="aw-muted">每个模型内部按任务配对。更好 / 相同 / 更差。</p><table><thead><tr><th>架构</th><th>更好</th><th>相同</th><th>更差</th></tr></thead><tbody>{data.modes.filter(mode => mode !== 'eo').map(mode => <tr key={mode}><th>{modeName(mode)}</th>{pairedOutcomes(trials.filter(trial => trial.mode === mode), baseline).map((count, i) => <td key={i}>{count}</td>)}</tr>)}</tbody></table></div>
    </div>
    <div className="aw-section-heading"><h2>分模型结果与调用成本</h2></div>
    <p className="aw-muted">成功率只使用最终有分轨迹；动作、调用和 token 纳入归档尝试。共计 {integer(total.archives)} 次归档尝试。带 ≥ 的 token 是已报告用量的下界，调用失败可能没有返回用量。</p>
    <p className="aw-muted">全部配置累计 {integer(total.actions)} 次环境动作、{integer(total.plannerCalls)} 次 Planner 请求尝试、{integer(total.executorCalls)} 次 Executor 请求尝试。累计 token {total.known < total.expected ? '≥ ' : ''}{integer(total.tokens)}，{integer(total.known)} / {integer(total.expected)} 次预期调用有用量记录。</p>
    <Table className="aw-results-table" size="middle" pagination={false} dataSource={rows} scroll={{ x: 1000 }} columns={[
      { title: '模型', dataIndex: 'model', width: 220 },
      { title: '架构', dataIndex: 'mode', render: modeName },
      { title: '成功率', render: (_, row) => <span className="aw-rate">{percent(row.wins, row.count)}<small>{row.wins} / {row.count}</small></span> },
      { title: '协议终止', dataIndex: 'protocol' },
      { title: '动作 / 轨迹', render: (_, row) => (row.actions / row.count).toFixed(1) },
      { title: 'Planner / Executor 请求尝试', render: (_, row) => `${integer(row.plannerCalls)} / ${integer(row.executorCalls)}` },
      { title: '累计 token', render: (_, row) => `${row.known < row.expected ? '≥ ' : ''}${integer(row.tokens)}` },
    ]} />
    <section className="aw-protocol-analysis"><h2>协议遵循会改变结果的解释</h2><p>四个模型的 Planner 每次输出上限均为 1,536 token。部分规划被截断，或因证据引用编号不符合协议而被拒绝。下面展示各组协议终止的条数，分母均为 {data.tasks.length} 条轨迹。</p><div className="aw-paired"><table><thead><tr><th>模型</th>{data.modes.map(mode => <th key={mode}>{modeName(mode)}</th>)}</tr></thead><tbody>{protocolRows.map(row => <tr key={row.model}><th>{row.model}</th>{row.counts.map((count, i) => <td key={i}>{count}</td>)}</tr>)}</tbody></table></div><p className="aw-muted">例如 Qwen 的动态组大量在首次 Planner 回复后即停止。不能把这些零分直接归因为执行阶段或战略规划失败；轨迹页保留模型原文与协议拒绝位置。</p></section>
    <div className="aw-analysis-grid aw-limitations">
      <section><h2>失败停在哪里？</h2><p className="aw-muted">停止原因只描述运行结束位置，不能独立证明失败机制。</p><ul className="aw-failure-list">{failures.map(([reason, count]) => <li key={reason}><span>{reason}</span><strong>{count}</strong></li>)}</ul></section>
      <section><h2>比较范围与证据边界</h2><ul><li>ALFWorld 的原生 won 标志为真时计成功，得 1 分，其余为 0 分。</li><li>每个模型的四架构共用任务、工具和执行额度。Planner 与 Executor 使用同一基座模型；不同模型分开展示。</li><li>补跑针对外部错误导致的缺评，保留已有有效评分和归档成本；运行并发曾调整。</li><li>协议拒绝属于本轮系统表现，不能直接解释为高层战略能力不足。阅读失败轨迹可进一步核对。</li></ul><details><summary>本轮预算与数据来源</summary><ReadableContent value={data.budget} /><p>来源：最终合并清单 alfworld-test-01-recovery-03/manifest.json，以及清单引用的最终轨迹和归档尝试。</p><a href="runs/alfworld-test-01-recovery-03/manifest.json">查看 ALFWorld 最终清单 <ArrowRightOutlined /></a></details></section>
    </div>
  </div>;
}

function Call({ interaction }: { interaction: Interaction }) {
  const messages = interaction.messages ?? [];
  return <>
    <div className="aw-input"><h4>原始 prompt · {messages.length} 条消息</h4>{messages.map((message, index) => <div className="aw-prompt-message" key={index}><h5>{index + 1} · {message.role}</h5><pre className="aw-raw-text">{message.content}</pre></div>)}</div>
    {interaction.reasoning !== undefined && <div className="aw-reasoning"><h4>原始 reasoning</h4><pre className="aw-raw-text">{interaction.reasoning}</pre></div>}
    <div className="aw-output"><h4>原始 response</h4><pre className="aw-raw-text">{interaction.output ?? ''}</pre></div>
    {interaction.content && <div className="aw-call-note aw-message-text">{interaction.content}</div>}
  </>;
}

function TraceReader({ trial, panel }: { trial: Trial; panel: string }) {
  const { data, error, reload } = useJson<Trace>(trial.traceUrl);
  const [role, setRole] = useState('all');
  const [search, setSearch] = useState('');
  const prefix = `aw-${panel}-${trial.id}`;
  if (error) return <LoadError error={error} reload={reload} />;
  if (!data) return <div className="aw-loading"><Spin /> 正在读取交互数据…</div>;
  const shown = data.interactions.filter(item => (role === 'all' || item.role === role || item.kind !== 'call') &&
    (!search || JSON.stringify([item.title, item.content, item.messages, item.output]).toLowerCase().includes(search.toLowerCase())));
  const modelCalls = data.interactions.filter(item => item.kind === 'call').length;
  return <div className="aw-trace" data-testid="trajectory-reader">
    <header className="aw-trace-heading"><div><h2>{modeName(trial.mode)} <span>{trial.model}</span></h2><p>任务 {trial.taskId} · <span className={trial.success ? 'aw-success' : 'aw-failure'}>{trial.success ? '成功' : '失败'}</span> · {trial.stop}</p></div><Tag>{modelCalls} 次模型调用</Tag></header>
    <p className="aw-protocol">{protocols[trial.mode]}</p>
    <div className="aw-goal"><strong>任务目标</strong><p>{data.goal}</p></div>
    <nav className="aw-timeline" aria-label="按事件顺序查看模型调用与执行边界"><h3>模型调用与执行边界</h3><p>点击节点定位到对应输入、输出或阶段返回。</p><div className="aw-timeline-nodes">{data.interactions.filter(item => item.marker).map(item => <Button size="small" key={item.id} className={`aw-node aw-symbol-${item.marker}`} title={`${item.title} · 事件 ${item.id}`} aria-label={`${item.title} · 事件 ${item.id}`} onClick={() => { setRole('all'); setSearch(''); window.setTimeout(() => document.getElementById(`${prefix}-${item.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0); }}>{item.marker}</Button>)}</div><div className="aw-timeline-legend">{Object.entries({ P: 'Planner', E: 'Executor', G: '交付指导', D: '委派阶段', R: '检查点或反馈', V: '环境终局' }).map(([marker, label]) => <span key={marker}><b className={`aw-symbol-${marker}`}>{marker}</b>{label}</span>)}</div></nav>
    <div className="aw-reader-tools"><Input aria-label={`${panel} 搜索交互内容`} placeholder="搜索输入、输出或动作" value={search} onChange={event => setSearch(event.target.value)} allowClear /><Select aria-label={`${panel} 交互角色`} value={role} onChange={setRole} options={[{ value: 'all', label: '全部交互' }, { value: 'planner', label: 'Planner 调用与边界' }, { value: 'executor', label: 'Executor 调用与边界' }]} /></div>
    <p className="aw-muted">每次调用完整展示原始 prompt 中全部消息及原始 response，保留消息顺序、role、原文、换行和协议标签。</p>
    {shown.length ? <ol className="aw-interactions">{shown.map(item => <li key={item.id} id={`${prefix}-${item.id}`} className={`aw-interaction aw-${item.role ?? item.kind}`}><div className="aw-interaction-title"><h3>{item.title}</h3><span>{item.requestId}{item.planVersion !== undefined && ` · 计划 v${item.planVersion}`}</span></div>{item.stageObjective && <p><strong>阶段目标：</strong>{item.stageObjective}</p>}{item.kind === 'call' ? <Call interaction={item} /> : item.content ? <div className="aw-message-text">{item.content}</div> : null}</li>)}</ol> : <Empty description="没有匹配的交互，请调整搜索内容" />}
  </div>;
}

function Results({ data }: { data: AlfworldIndex }) {
  const [params, setParams] = useSearchParams();
  const [task, setTask] = useState('all');
  const [model, setModel] = useState('all');
  const [mode, setMode] = useState('all');
  const [outcome, setOutcome] = useState('all');
  const [query, setQuery] = useState('');
  const tab = ['analysis', 'read', 'compare'].includes(params.get('tab') ?? '') ? params.get('tab')! : 'analysis';
  const left = data.trials.find(trial => trial.id === params.get('left')) ?? data.trials[0];
  const right = data.trials.find(trial => trial.id === params.get('right')) ?? data.trials.find(trial => trial.taskId === left.taskId && trial.model === left.model && trial.mode !== left.mode) ?? data.trials[1];
  function update(values: Record<string, string>) { setParams(previous => { const next = new URLSearchParams(previous); Object.entries(values).forEach(([key, value]) => next.set(key, value)); return next; }, { replace: true }); }
  const goals = useMemo(() => new Map(data.tasks.map(task => [task.id, task.goal])), [data]);
  const options = data.trials.map(trial => ({ value: trial.id, label: `任务 ${trial.taskId} · ${trial.model} · ${modeName(trial.mode)} · ${trial.success ? '成功' : '失败'}`, searchText: `${trial.id} ${goals.get(trial.taskId)}` }));
  const filtered = data.trials.filter(trial => (task === 'all' || trial.taskId === task) && (model === 'all' || trial.model === model) && (mode === 'all' || trial.mode === mode) && (outcome === 'all' || trial.success === (outcome === 'success')) && `${trial.id} ${goals.get(trial.taskId)}`.toLowerCase().includes(query.toLowerCase()));
  const trajectorySelect = (side: 'left' | 'right') => <label className="aw-trace-select">{side === 'left' ? '左侧轨迹' : '右侧轨迹'}<Select aria-label={side === 'left' ? '左侧轨迹' : '右侧轨迹'} value={side === 'left' ? left.id : right.id} showSearch optionFilterProp="label" options={options} filterOption={(input, option) => `${option?.label} ${option?.searchText}`.toLowerCase().includes(input.toLowerCase())} onChange={value => update({ [side]: value })} /></label>;
  return <main className="alfworld-results">
    <header className="aw-page-header"><div><h1>ALFWorld 实验结果</h1><p>完整测试集 · {data.tasks.length} 个任务 × {data.models.length} 个模型 × {data.modes.length} 种架构 · {integer(data.trials.length)} 条有效评分</p></div><a href="audit.html">返回运行审查 <ArrowRightOutlined /></a></header>
    <Tabs className="aw-tabs" activeKey={tab} onChange={value => update({ tab: value })} items={[
      { key: 'analysis', label: '结果分析', children: <Analysis data={data} /> },
      { key: 'read', label: '轨迹阅读', children: <>
        <div className="aw-section-heading"><h2>查找一条轨迹</h2><span className="aw-muted">{filtered.length} / {data.trials.length} 条</span></div>
        <div className="aw-filters"><Select aria-label="选择任务" value={task} onChange={setTask} showSearch optionFilterProp="label" options={[{ value: 'all', label: '全部任务' }, ...data.tasks.map(task => ({ value: task.id, label: `${task.id} · ${task.goal}` }))]} /><Select aria-label="筛选模型" value={model} onChange={setModel} options={[{ value: 'all', label: '全部模型' }, ...data.models.map(value => ({ value, label: value }))]} /><Select aria-label="筛选架构" value={mode} onChange={setMode} options={[{ value: 'all', label: '全部架构' }, ...data.modes.map(value => ({ value, label: modeName(value) }))]} /><Select aria-label="筛选结果" value={outcome} onChange={setOutcome} options={[{ value: 'all', label: '全部结果' }, { value: 'success', label: '成功' }, { value: 'failure', label: '失败' }]} /></div>
        <Input className="aw-search" aria-label="搜索轨迹" placeholder="搜索任务目标或轨迹编号" value={query} onChange={event => setQuery(event.target.value)} allowClear />
        <Table size="small" rowKey="id" className="aw-trial-table" dataSource={filtered} rowClassName={trial => trial.id === left.id ? 'aw-selected-row' : ''} pagination={{ pageSize: 8, showSizeChanger: false, hideOnSinglePage: true, showTotal: total => `共 ${total} 条` }} scroll={{ x: 650 }} columns={[
          { title: '任务', dataIndex: 'taskId', width: 65 }, { title: '模型', dataIndex: 'model' }, { title: '架构', dataIndex: 'mode', render: modeName }, { title: '结果', render: (_, trial) => <span className={trial.success ? 'aw-success' : 'aw-failure'}>{trial.success ? '成功' : '失败'}</span> },
          { title: '阅读与对比', render: (_, trial) => <div className="aw-row-actions"><Button type="link" aria-label={`读取轨迹 ${trial.id}`} onClick={() => update({ left: trial.id })}>阅读</Button><Button type="link" aria-label={`对比轨迹 ${trial.id}`} onClick={() => update({ right: trial.id, tab: 'compare' })}>加入对比</Button></div> },
        ]} />
        <div className="aw-reading-actions"><span>正在阅读：{left.id}</span><Button icon={<SwapOutlined />} onClick={() => update({ tab: 'compare', right: (data.trials.find(trial => trial.taskId === left.taskId && trial.model === left.model && trial.mode !== left.mode) ?? right).id })}>对比同任务的其他架构</Button></div>
        <TraceReader key={left.id} trial={left} panel="read" />
      </> },
      { key: 'compare', label: '轨迹对比', children: <><div className="aw-section-heading"><h2>并排阅读两条轨迹</h2><Button icon={<SwapOutlined />} onClick={() => update({ left: right.id, right: left.id })}>交换左右</Button></div><p className="aw-muted">可选择全部 {integer(data.trials.length)} 条轨迹，比较不同架构、模型或任务。每栏保留独立的交互顺序与搜索。</p><div className="aw-compare-selectors">{trajectorySelect('left')}{trajectorySelect('right')}</div>{left.taskId !== right.taskId && <Alert type="info" showIcon title="当前两条轨迹来自不同任务，不能作为同任务的配对比较。" />}<div className="aw-comparison"><section data-testid="comparison-left" aria-label="左侧轨迹内容"><TraceReader key={left.id} trial={left} panel="left" /></section><section data-testid="comparison-right" aria-label="右侧轨迹内容"><TraceReader key={right.id} trial={right} panel="right" /></section></div></> },
    ]} />
  </main>;
}

export default function AlfworldResults() {
  const { data, error, reload } = useJson<AlfworldIndex>('alfworld/data/index.json');
  if (error) return <LoadError error={error} reload={reload} index />;
  if (!data) return <div className="aw-loading"><Spin /> 正在读取完整 ALFWorld 结果…</div>;
  if (data.schemaVersion !== 1 || !data.trials?.length) return <LoadError error="结果索引版本不受支持或缺少轨迹" reload={reload} index />;
  return <Results data={data} />;
}
