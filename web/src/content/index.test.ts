import { describe, expect, it } from 'vitest';
import {
  documents,
  experimentDocuments,
  getDocument,
  getRecordDocuments,
  paperDocuments,
  parseQuestionGroups,
  parseResearch,
  research,
  historicalCandidates,
  historicalResearch,
  questions,
  resolveDocumentLink,
  searchDocuments,
} from './index';

describe('repository content', () => {
  it('extracts a summary while preserving the detailed Markdown evidence', () => {
    const detail = '| 条件 | 证据 |\n|---|---|\n| 待验证 | 保留限制 |';
    const source = `# 工作台\n更新：2026-11-01 · 阶段：收敛\n\n## 当前判断\n仍是待验证假设。\n\n## 最大未知\n缺少成本测量。\n\n## 下一步\n核查原文，不运行实验。\n\n<details id="p1">\n<summary>候选问题</summary>\n\n${detail}\n\n</details>`;
    const parsed = parseResearch(source);
    expect(parsed).toMatchObject({ date: '2026-11-01', stage: '收敛', judgment: '仍是待验证假设。', unknown: '缺少成本测量。', next: '核查原文，不运行实验。' });
    expect(parsed.details).toEqual([{ id: 'p1', title: '候选问题', markdown: detail }]);
    expect(research.sourcePath).toBe('RESEARCH.md');
  });

  it('does not count directory index pages as paper or experiment records', () => {
    expect(documents.some((document) => document.path === 'papers/README.md')).toBe(true);
    expect(documents.some((document) => document.path === 'experiments/README.md')).toBe(true);
    expect(paperDocuments.every((document) => document.path !== 'papers/README.md')).toBe(true);
    expect(experimentDocuments.every((document) => document.path !== 'experiments/README.md')).toBe(true);
    const records = [
      { id: 'papers/README', path: 'papers/README.md', title: 'Index', category: 'paper' as const, markdown: '' },
      { id: 'papers/example/README', path: 'papers/example/README.md', title: 'A paper note', category: 'paper' as const, markdown: '' },
      { id: 'experiments/README', path: 'experiments/README.md', title: 'Index', category: 'experiment' as const, markdown: '' },
      { id: 'experiments/example/README', path: 'experiments/example/README.md', title: 'An experiment', category: 'experiment' as const, markdown: '' },
    ];
    expect(getRecordDocuments('paper', records)).toEqual([records[1]]);
    expect(getRecordDocuments('experiment', records)).toEqual([records[3]]);
  });

  it('rejects an incomplete source instead of silently hiding a research summary', () => {
    const source = '# Research\n更新：2026-11-01 · 阶段：收敛\n## 当前判断\n仍待验证';
    expect(() => parseResearch(source)).toThrow('最大未知');
  });

  it('resolves relative Markdown links into readable document routes', () => {
    expect(resolveDocumentLink('../RESEARCH.md#下一步', 'papers/README.md')).toBe('/documents/RESEARCH#下一步');
    expect(resolveDocumentLink('papers/README.md', 'RESEARCH.md')).toBe('/documents/papers%2FREADME');
    expect(resolveDocumentLink('README.md#研究设置', 'RESEARCH.md')).toBe('/documents/README#研究设置');
    expect(resolveDocumentLink('.github/ISSUE_TEMPLATE/research-task.yml', 'README.md')).toBe('/documents/.github%2FISSUE_TEMPLATE%2Fresearch-task');
    expect(resolveDocumentLink('index.html', 'RESEARCH.md')).toBe('/');
    expect(getDocument('papers%2FREADME')?.path).toBe('papers/README.md');
    expect(resolveDocumentLink('../PROPOSAL.md', 'papers/README.md')).toBe('/documents/PROPOSAL');
    expect(resolveDocumentLink('archive/pre-v04/RESEARCH.md#d03', 'RESEARCH.md')).toBe('/documents/archive%2Fpre-v04%2FRESEARCH#d03');
    expect(resolveDocumentLink('../../PROPOSAL.md', historicalResearch.sourcePath)).toBe('/documents/PROPOSAL');
    const recipeId = 'src/recipe/strategy-sampling/README';
    expect(resolveDocumentLink(`../../${recipeId}.md`, 'experiments/strategy-sampling/README.md'))
      .toBe(`/documents/${encodeURIComponent(recipeId)}`);
    expect(getDocument(recipeId)?.category).toBe('project');
    expect(resolveDocumentLink('../../toolkit/README.md', `${recipeId}.md`))
      .toBe('/documents/src%2Ftoolkit%2FREADME');
  });

  it('resolves proposal and paper images relative to their source document', () => {
    const figure = 'fig1_fullplan_learning_v04_refined.png';
    const direct = resolveDocumentLink(`assets/${figure}`, 'PROPOSAL.md');
    expect(direct).toContain(figure);
    expect(direct).not.toBe(`assets/${figure}`);
    expect(resolveDocumentLink(`../assets/${figure}`, 'papers/planner-centered-review.md')).toBe(direct);
    expect(getDocument('archive/pre-v04/RESEARCH')?.title).toMatch(/^历史/);
  });

  it('opens the real research task template as a readable project document', () => {
    const template = getDocument('.github%2FISSUE_TEMPLATE%2Fresearch-task');
    expect(template).toMatchObject({ path: '.github/ISSUE_TEMPLATE/research-task.yml', title: '研究任务模板', category: 'project' });
    expect(template?.markdown).toContain('\n```yaml\nname:');
    expect(template?.markdown.trimEnd()).toMatch(/```$/);
  });

  it('keeps external destinations, local anchors and unknown files unchanged', () => {
    expect(resolveDocumentLink('https://example.org/paper', 'RESEARCH.md')).toBe('https://example.org/paper');
    expect(resolveDocumentLink('#p1', 'RESEARCH.md')).toBe('#p1');
    expect(resolveDocumentLink('figure.png', 'papers/README.md')).toBe('figure.png');
  });

  it('searches actual document content and ignores an empty query', () => {
    expect(searchDocuments('')).toEqual([]);
    const source = getDocument('RESEARCH')!;
    const result = searchDocuments(source.title).find((document) => document.id === source.id);
    expect(result?.excerpt).toContain(source.title);
    expect(searchDocuments('not-a-real-research-phrase')).toEqual([]);
  });

  it('reads changing topic groups, Markdown cells and diagrams from the same source', () => {
    const groups = parseQuestionGroups([
      { id: 'direction-menu', title: 'Menu', markdown: '| ID | Old | Topic | Status | Boundary |\n|---|---|---|---|---|\n| D21 | D01 | Signal \\| feedback | Draft | Keep the executor fixed |\n| D22 | D02 | Another topic | Draft | Separate evidence |\n| D03 | D03 | Reserved topic | Reserved | Do not start yet |' },
      { id: 'directions-current', title: 'Current topics', markdown: 'Methods are not selected.\n\n| ID | Question | Evidence | Alternative |\n|---|---|---|---|\n| D21 | Does [feedback](https://example.org) work \\| fail? | Learning improves | More compute |\n| D22 | Another question | New evidence | Another explanation |\n\n<a id="d21"></a>\n\n### D21 · Signal\n\nUntested diagram.\n\n```mermaid\nflowchart LR\n A --> B\n```\n\nFirst topic evidence.\n\n<a id="d22"></a>\n\n### D22 · Another topic\n\nSecond topic evidence.' },
      { id: 'directions-future', title: 'Future topics', markdown: 'Reserved.\n\n### D03 · Reserved topic\n\nOriginal evidence.' },
    ]);
    expect(groups[0].description).toBe('Methods are not selected.');
    expect(groups[0].questions.map((item) => item.id)).toEqual(['D21', 'D22']);
    expect(groups[0].questions[0]).toMatchObject({ title: 'Signal | feedback', question: 'Does feedback work | fail?', evidence: 'Learning improves', alternative: 'More compute', boundary: 'Keep the executor fixed', diagramCaption: 'Untested diagram.' });
    expect(groups[0].questions[0].diagram).toContain('A --> B');
    expect(groups[0].questions[0].markdown).not.toContain('d22');
    expect(groups[0].questions[1].diagram).toBeUndefined();
    expect(groups[1].questions[0]).toMatchObject({ id: 'D03', groupId: 'directions-future', question: 'Do not start yet' });
  });

  it('keeps archived topics accessible without treating them as current candidates', () => {
    expect(parseQuestionGroups(research.details)).toEqual([]);
    expect(research.details.find((item) => item.id === 'current-proposal')?.markdown).toContain('PROPOSAL.md');
    expect(research.stage).toBe('新实验实现准备，提案 v0.6 待审核');
    expect(research.details.find((item) => item.id === 'decisions')?.markdown).toContain('列为通过审核');
    expect(getDocument('PROPOSAL')?.markdown).toContain('[研究者审核记录](RESEARCH.md#decisions)');
    const menu = historicalResearch.details.find((item) => item.id === 'direction-menu')!;
    const ids = [...menu.markdown.matchAll(/^\| (D\d+) \|/gm)].map((match) => match[1]);
    expect(questions.map((item) => item.id)).toEqual(ids);
    expect(historicalCandidates.length).toBeGreaterThan(0);
    for (const item of historicalCandidates) {
      expect(item.evidence).toBeTruthy();
      expect(item.alternative).toBeTruthy();
      expect(item.diagram).toContain('```mermaid');
      expect(getDocument('archive/pre-v04/RESEARCH')?.markdown).toContain(`id="${item.id.toLowerCase()}"`);
    }
  });
});
