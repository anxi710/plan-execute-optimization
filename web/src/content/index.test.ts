import { describe, expect, it } from 'vitest';
import {
  documents,
  experimentDocuments,
  getDocument,
  getRecordDocuments,
  paperDocuments,
  parseResearch,
  research,
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
});
