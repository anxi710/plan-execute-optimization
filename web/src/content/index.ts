export type DocumentCategory = 'project' | 'paper' | 'experiment' | 'research';

export interface ResearchDetail {
  id: string;
  title: string;
  markdown: string;
}

export interface ResearchContent {
  date: string;
  stage: string;
  judgment: string;
  unknown: string;
  next: string;
  details: ResearchDetail[];
  sourcePath: string;
}

export interface ResearchDocument {
  id: string;
  path: string;
  title: string;
  category: DocumentCategory;
  markdown: string;
}

export interface DocumentSearchResult {
  id: string;
  path: string;
  title: string;
  category: DocumentCategory;
  excerpt: string;
}

const sources = import.meta.glob<string>(
  [
    '../../../README.md',
    '../../../RESEARCH.md',
    '../../../AGENTS.md',
    '../../../.github/pull_request_template.md',
    '../../../.github/ISSUE_TEMPLATE/research-task.yml',
    '../../../papers/**/*.md',
    '../../../experiments/**/*.md',
  ],
  { eager: true, query: '?raw', import: 'default' },
);

function categoryFor(path: string): DocumentCategory {
  if (path === 'RESEARCH.md') return 'research';
  if (path.startsWith('papers/')) return 'paper';
  if (path.startsWith('experiments/')) return 'experiment';
  return 'project';
}

export const documents: ResearchDocument[] = Object.entries(sources)
  .map(([sourcePath, source]) => {
    const path = sourcePath.replace(/^\.\.\/\.\.\/\.\.\//, '');
    const markdown = path.endsWith('.yml')
      ? '# 研究任务模板\n\n```yaml\n' + source.trimEnd() + '\n```\n'
      : source;
    return {
      id: path.replace(/\.(?:md|yml)$/i, ''),
      path,
      title: markdown.match(/^#\s+(.+)$/m)?.[1].trim() ?? path.split('/').at(-1) ?? path,
      category: categoryFor(path),
      markdown,
    };
  })
  .sort((a, b) => a.path.localeCompare(b.path));

export function getDocument(id: string | undefined): ResearchDocument | undefined {
  if (!id) return undefined;
  let decoded = id;
  try {
    decoded = decodeURIComponent(id);
  } catch {
    return undefined;
  }
  return documents.find((document) => document.id === decoded);
}

export function parseResearch(markdown: string, sourcePath = 'RESEARCH.md'): ResearchContent {
  const details: ResearchDetail[] = [];
  const detailPattern = /<details\b([^>]*)>\s*<summary>([\s\S]*?)<\/summary>([\s\S]*?)<\/details>/g;
  const summaryMarkdown = markdown.replace(detailPattern, (_block, attributes: string, title: string, body: string) => {
    const id = attributes.match(/\bid\s*=\s*["']([^"']+)["']/)?.[1];
    if (!id) throw new Error(`${sourcePath}: each research detail needs an id`);
    if (details.some((detail) => detail.id === id)) {
      throw new Error(`${sourcePath}: duplicate detail id "${id}"`);
    }
    details.push({ id, title: title.trim(), markdown: body.trim() });
    return '';
  });

  if (details.length !== (markdown.match(/<details\b/g) ?? []).length) {
    throw new Error(`${sourcePath}: a research detail is missing its summary or closing tag`);
  }

  const sections = new Map<string, string>();
  const headings = [...summaryMarkdown.matchAll(/^##\s+([^\n]+)\n/gm)];
  headings.forEach((heading, index) => {
    const start = heading.index + heading[0].length;
    const end = headings[index + 1]?.index ?? summaryMarkdown.length;
    sections.set(heading[1].trim(), summaryMarkdown.slice(start, end).trim());
  });

  const requiredSection = (name: string): string => {
    const value = sections.get(name);
    if (!value) throw new Error(`${sourcePath}: missing section "${name}"`);
    return value;
  };
  const date = markdown.match(/更新[：:]\s*(\d{4}-\d{2}-\d{2})/)?.[1];
  const stage = markdown.match(/(?:当前)?阶段[：:]\s*([^。·\n]+)/)?.[1].trim();
  if (!date || !stage) throw new Error(`${sourcePath}: missing update date or research stage`);

  return {
    date,
    stage,
    judgment: requiredSection('当前判断'),
    unknown: requiredSection('最大未知'),
    next: requiredSection('下一步'),
    details,
    sourcePath,
  };
}

const researchDocument = documents.find((document) => document.path === 'RESEARCH.md');
if (!researchDocument) throw new Error('The repository is missing RESEARCH.md');
export const research = parseResearch(researchDocument.markdown, researchDocument.path);

function normalizePath(path: string): string | undefined {
  const parts: string[] = [];
  for (const part of path.split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') {
      if (!parts.length) return undefined;
      parts.pop();
    } else {
      parts.push(part);
    }
  }
  return parts.join('/');
}

export function resolveDocumentLink(href: string, fromPath: string): string {
  if (!href || href.startsWith('#') || href.startsWith('//') || /^[a-z][\w+.-]*:/i.test(href)) {
    return href;
  }
  const [beforeHash, ...hashParts] = href.split('#');
  const hash = hashParts.length ? `#${hashParts.join('#')}` : '';
  const filePath = beforeHash.split('?')[0];
  let decodedPath: string;
  try {
    decodedPath = decodeURIComponent(filePath);
  } catch {
    return href;
  }
  const directory = fromPath.split('/').slice(0, -1).join('/');
  const normalized = normalizePath(decodedPath.startsWith('/') ? decodedPath : `${directory}/${decodedPath}`);
  if (normalized === 'index.html') return `/${hash}`;
  const document = documents.find((entry) => entry.path === normalized);
  return document ? `/documents/${encodeURIComponent(document.id)}${hash}` : href;
}

function searchText(markdown: string): string {
  return markdown
    .replace(/<[^>]*>/g, ' ')
    .replace(/!?\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[`#*|>~]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function searchDocuments(query: string): DocumentSearchResult[] {
  const terms = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  return documents
    .map((document) => {
      const text = searchText(document.markdown);
      const haystack = `${document.title} ${text}`.toLocaleLowerCase();
      if (!terms.every((term) => haystack.includes(term))) return undefined;
      const lowerText = text.toLocaleLowerCase();
      const firstMatch = Math.min(...terms.map((term) => lowerText.indexOf(term)).filter((index) => index >= 0));
      const start = Number.isFinite(firstMatch) ? Math.max(0, firstMatch - 24) : 0;
      return {
        id: document.id,
        path: document.path,
        title: document.title,
        category: document.category,
        excerpt: `${start > 0 ? '…' : ''}${text.slice(start, start + 130)}${text.length > start + 130 ? '…' : ''}`,
      };
    })
    .filter((result): result is DocumentSearchResult => result !== undefined)
    .sort((a, b) => {
      const score = (title: string) => terms.filter((term) => title.toLocaleLowerCase().includes(term)).length;
      return score(b.title) - score(a.title) || a.title.localeCompare(b.title);
    });
}

// Directory indexes describe storage rules; nested README files can be real records.
export function getRecordDocuments(category: 'paper' | 'experiment', collection = documents): ResearchDocument[] {
  const indexPath = category === 'paper' ? 'papers/README.md' : 'experiments/README.md';
  return collection.filter((document) => document.category === category && document.path !== indexPath);
}

export const paperDocuments = getRecordDocuments('paper');
export const experimentDocuments = getRecordDocuments('experiment');
