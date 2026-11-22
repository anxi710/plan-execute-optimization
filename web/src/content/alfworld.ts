export interface Trial {
  id: string; taskId: string; model: string; mode: string; score: number | null; success: boolean | null;
  stop: string; stopReason?: string | null; error?: string | null; actions: number; plannerCalls: number;
  executorCalls: number; tokens: number; knownTokenCalls: number; totalTokenCalls: number;
  archivedAttempts: number; traceUrl: string;
}

export interface AlfworldIndex {
  schemaVersion: number; runId: string; benchmark: string;
  selection?: string; split?: string; protocolVersion?: string | null; manifestUrl?: string;
  models: string[]; modes: string[];
  tasks: { id: string; goal: string; family?: string; initial?: string }[];
  budget: Record<string, unknown>; trials: Trial[];
}

interface FunctionCall {
  id: string; type: string; function: { name: string; arguments: string };
}

export interface Interaction {
  id: string; kind: 'call' | 'boundary' | 'observation' | 'error';
  marker?: 'P' | 'E' | 'G' | 'D' | 'R' | 'V';
  role?: string; title: string; messages?: {
    role: string; content: string | null; tool_call_id?: string; tool_calls?: FunctionCall[];
  }[];
  tools?: unknown[]; toolChoice?: unknown; toolCalls?: FunctionCall[]; phase?: string;
  output?: string; reasoning?: string; content?: string;
  requestId?: string; planVersion?: number; stageObjective?: string; stageId?: number;
}

export interface Trace {
  id: string; mode: string; model: string; taskId: string; goal: string;
  interactions: Interaction[];
}

export const protocols: Record<string, string> = {
  eo: 'Executor 根据任务与环境反馈自主执行，没有外部 Planner。',
  'pe-s': 'Planner 在执行前交付一次整体计划，Executor 依此完成整项任务。',
  'pe-d': 'Planner 在返回边界修订剩余整体计划，Executor 续接同一个整项任务请求。',
  pc: 'Planner 根据执行反馈更新计划，并向 Executor 委派新的有界阶段。',
  'pe-d-f': 'Executor 通过原生工具按需请求修订剩余全局计划。',
  'pe-d-s': 'Executor 通过原生工具按需取得下一份子计划，继续负责整项任务。',
  'pc-f': 'Planner 制定带编号的全局计划，每次执行一个动作后监控并更新活动阶段。',
  'pc-s': 'Planner 制定当前子计划，每次执行一个动作后监控并决定是否换阶段。',
};

export const modeName = (mode: string) => mode.toUpperCase();
export const verdict = (trial: Trial) => trial.score === null ? '缺评' : trial.success ? '成功' : '失败';
export const percent = (wins: number, total: number) => total ? `${(100 * wins / total).toFixed(1)}%` : '—';

export function summarize(trials: Trial[]) {
  return {
    count: trials.filter(t => t.score !== null).length,
    wins: trials.filter(t => t.success).length,
    tokens: trials.reduce((n, t) => n + t.tokens, 0),
    actions: trials.reduce((n, t) => n + t.actions, 0),
    calls: trials.reduce((n, t) => n + t.plannerCalls + t.executorCalls, 0),
    plannerCalls: trials.reduce((n, t) => n + t.plannerCalls, 0),
    executorCalls: trials.reduce((n, t) => n + t.executorCalls, 0),
    known: trials.reduce((n, t) => n + t.knownTokenCalls, 0),
    expected: trials.reduce((n, t) => n + t.totalTokenCalls, 0),
    archives: trials.reduce((n, t) => n + t.archivedAttempts, 0),
  };
}

export function pairedOutcomes(trials: Trial[], baseline: Trial[]) {
  const byTask = new Map(baseline.map(trial => [`${trial.model}/${trial.taskId}`, trial]));
  return trials.reduce((counts, trial) => {
    const other = byTask.get(`${trial.model}/${trial.taskId}`);
    if (other && trial.score !== null && other.score !== null) {
      counts[trial.score > other.score ? 0 : trial.score === other.score ? 1 : 2]++;
    }
    return counts;
  }, [0, 0, 0]);
}
