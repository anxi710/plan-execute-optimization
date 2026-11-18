import { useEffect, useState, type ReactNode } from 'react';
import { Badge, Button, Card, Collapse, Drawer, Empty, Result, Space, Tag, Typography } from 'antd';
import {
  ArrowRightOutlined, BookOutlined, ExperimentOutlined, FileTextOutlined,
  HistoryOutlined, ReadOutlined,
} from '@ant-design/icons';
import { Link, useLocation, useParams } from 'react-router-dom';
import { historicalCandidates, historicalResearch, documents, getDocument, questionGroups, questions, research } from '../content';
import Markdown from '../components/Markdown';

const { Title, Text } = Typography;
const documentUrl = (id: string) => `/documents/${encodeURIComponent(id)}`;
const detail = (id: string) => research.details.find((item) => item.id === id);
const historicalGroup = questionGroups.find((item) => item.id === 'directions-current');
const archiveId = historicalResearch.sourcePath.replace(/\.md$/, '');
const reading = detail('l1');
const categoryName = { project: '项目说明', paper: '论文笔记', experiment: '实验记录', research: '研究工作台' };

function PageHeader({ title, description, extra }: { title: string; description: string; extra?: ReactNode }) {
  return <div className="page-heading"><div><Title level={2}>{title}</Title><p>{description}</p></div>{extra}</div>;
}

function DetailCard({ id }: { id: string }) {
  const item = detail(id);
  return item ? <Card className="reading-card"><Markdown content={item.markdown} sourcePath={research.sourcePath} /></Card> : null;
}

export function Overview() {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const evidence = detail('evidence');
  return <>
    <PageHeader title="研究总览" description="先看判断，再按需要深入。" extra={<Tag className="stage-tag" bordered={false}><Badge status="processing" />{research.stage}</Tag>} />
    <ReadingNavigation />
    <div className="research-summary" aria-label="当前判断、最大未知与下一步">
      {[
        { label: '当前判断', content: research.judgment, anchor: 'judgment-context' },
        { label: '最大未知', content: research.unknown, anchor: 'unknown-context' },
        { label: '下一步', content: research.next, anchor: 'next-context' },
      ].map((item) => <Card key={item.label} className="summary-card"><h3>{item.label}</h3><Markdown content={item.content} sourcePath={research.sourcePath} /><Link className="summary-source" to={documentUrl('RESEARCH') + '#' + item.anchor}>查看依据 <ArrowRightOutlined aria-hidden="true" /></Link></Card>)}
    </div>
    <div className="reading-section-heading"><h2>当前关注的研究提案</h2></div>
    <DetailCard id="current-proposal" />
    <div className="reading-sources">{evidence && <Button type="link" onClick={() => setEvidenceOpen(true)}>查看证据状态</Button>}<Link to={documentUrl('RESEARCH')}>完整研究工作台 <ArrowRightOutlined aria-hidden="true" /></Link></div>
    <ResearchLimits />
    <Drawer title="证据状态" width={700} open={evidenceOpen} onClose={() => setEvidenceOpen(false)}>{evidence && <Markdown content={evidence.markdown} sourcePath={research.sourcePath} />}</Drawer>
  </>;
}

const questionUrl = (id: string) => `/questions/${id}`;

function ReadingNavigation() {
  const { pathname } = useLocation();
  return <nav className="reading-navigation" aria-label="选择阅读方式">{[
    { path: '/', label: '看现状', selected: pathname === '/' },
    { path: documentUrl('PROPOSAL'), label: '阅读提案', selected: pathname === documentUrl('PROPOSAL') },
    { path: '/questions', label: '历史问题', selected: pathname.startsWith('/questions') },
  ].map((item) => <Link key={item.label} to={item.path} aria-current={item.selected ? 'page' : undefined}>{item.label}</Link>)}</nav>;
}

function FoundationQuestions() {
  const foundation = questionGroups.find((item) => item.id === 'directions-foundation');
  return foundation ? <div className="foundation-questions"><strong>历史基础问题</strong>{foundation.questions.map((item) => <Link key={item.id} to={questionUrl(item.id)}>{item.id} · {item.title}</Link>)}</div> : null;
}

function OtherQuestions() {
  return <details className="other-questions"><summary>其他分组与历史</summary><div>{questionGroups.filter((group) => !['directions-current', 'directions-foundation'].includes(group.id)).map((group) => <section key={group.id}><h3>{group.title}</h3><div className="question-links">{group.questions.map((item) => <Link key={item.id} to={questionUrl(item.id)}>{item.id} · {item.title}</Link>)}</div></section>)}<Link to={documentUrl(archiveId) + '#direction-menu'}>编号对照与审核经过 <ArrowRightOutlined aria-hidden="true" /></Link></div></details>;
}

function ResearchLimits() {
  return <p className="research-limits">固定 Executor · 只优化 Planner</p>;
}

export function Questions() {
  return <>
    <PageHeader title="历史问题" description="以下保留切换前的题卡与当时优先级，不代表当前研究安排。" />
    <ReadingNavigation />
    <FoundationQuestions />
    <div className="reading-section-heading"><h2>切换前的投稿候选</h2><span>{historicalGroup?.description}</span></div>
    {historicalCandidates.length ? <div className="question-comparison" tabIndex={0} role="region" aria-label="候选问题对比表，可横向滚动"><table><thead><tr><th scope="col">候选问题</th><th scope="col">核心疑问</th><th scope="col">必须取得的判别证据</th></tr></thead><tbody>{historicalCandidates.map((item) => <tr key={item.id}><th scope="row"><span className="question-id">{item.id}</span><strong>{item.title}</strong><Link to={questionUrl(item.id)}>打开题卡 <ArrowRightOutlined aria-hidden="true" /></Link></th><td>{item.question}</td><td>{item.evidence}</td></tr>)}</tbody></table></div> : <Empty description="没有已归档的投稿候选" />}
    <ResearchLimits />
    <OtherQuestions />
  </>;
}

export function QuestionPage() {
  const { id } = useParams();
  const item = questions.find((question) => question.id === id?.toUpperCase());
  if (!item) return <Result status="404" title="没有找到这项问题" extra={<Link to="/questions">返回历史问题</Link>} />;
  const group = questionGroups.find((group) => group.id === item.groupId)!;
  return <>
    <PageHeader title="历史题卡" description={"切换前记录 · " + group.title} />
    <ReadingNavigation />
    <nav className="question-selector" aria-label="选择同组问题">{group.questions.map((question) => <Link key={question.id} to={questionUrl(question.id)} aria-label={question.id + ' · ' + question.title} aria-current={question.id === item.id ? 'page' : undefined}>{question.id}</Link>)}</nav>
    <Card className="question-detail"><div className="question-detail-heading"><h2>{item.id} · {item.title}</h2><Tag bordered={false} color="gold">历史题卡</Tag></div><p className="question-lead">{item.question}</p><p className="question-status">{item.status}</p>{item.boundary !== item.question && <p className="question-boundary">{item.boundary}</p>}{item.diagram && <div className="question-diagram"><p>{item.diagramCaption}</p><Markdown content={item.diagram} sourcePath={historicalResearch.sourcePath} /></div>}</Card>
    {(item.evidence || item.alternative) && <div className="question-evidence">{item.evidence && <Card><h3>需要看到什么证据</h3><p>{item.evidence}</p></Card>}{item.alternative && <Card><h3>必须排除的替代解释</h3><p>{item.alternative}</p></Card>}</div>}
    <ResearchLimits />
    <Collapse key={item.id} className="full-question" items={[{ key: item.id, label: '完整题卡：来源、假设、基线与停止条件', children: <Markdown content={item.markdown} sourcePath={historicalResearch.sourcePath} /> }]} />
    <div className="reading-sources"><Link to={documentUrl(archiveId) + '#' + item.id.toLowerCase()}>在历史存档中查看原文 <ArrowRightOutlined aria-hidden="true" /></Link><Link to="/questions">返回历史问题</Link></div>
  </>;
}

export function Collection({ category }: { category: 'paper' | 'experiment' }) {
  const isPaper = category === 'paper';
  const records = documents.filter((item) => item.category === category && !/^(papers|experiments)\/README\.md$/i.test(item.path));
  const index = getDocument(isPaper ? 'papers/README' : 'experiments/README');
  return <>
    <PageHeader title={isPaper ? '文献阅读' : '实验记录'} description={isPaper ? '从一个明确问题出发，让原文证据改变判断。' : '把方案、运行与分析放在一起，保留可复核的证据。'} extra={<Tag bordered={false}>{records.length} 份记录</Tag>} />
    <div className="collection-grid">
      <section>
        {records.length ? <div className="document-grid">{records.map((item) => <Card key={item.id} className="document-card" title={<Space>{isPaper ? <BookOutlined /> : <ExperimentOutlined />}<span>{item.title}</span></Space>}><Text type="secondary">{item.path}</Text><Link to={documentUrl(item.id)}><Button type="link" icon={<ArrowRightOutlined aria-hidden="true" />} iconPosition="end">打开记录</Button></Link></Card>)}</div> : <Card className="empty-state-card"><Empty image={<span className="empty-icon">{isPaper ? <BookOutlined /> : <ExperimentOutlined />}</span>} description={<><h3>{isPaper ? '目录中还没有独立论文笔记' : '目录中还没有独立实验记录'}</h3><p>局部证据、验证草案与当前下一步统一保存在研究工作台。</p></>} /><Link to={documentUrl('RESEARCH')}><Button icon={<ReadOutlined />}>查看研究工作台</Button></Link></Card>}
        {isPaper && <section className="reading-task" id="reading-task"><Collapse items={[detail('direction-sources'), reading].filter((item) => item !== undefined).map((item) => ({
          key: item.id,
          label: item.title,
          children: <Markdown content={item.markdown} sourcePath={research.sourcePath} />,
        }))} /></section>}
      </section>
      <aside className="collection-aside"><Card title={<Space><FileTextOutlined /><span>记录方式</span></Space>}><p>详细证据就近保存在对应目录，研究判断写回工作台。</p><p>任务通过 Issue 跟踪，记录通过 PR 与版本关联。</p>{index && <Link to={documentUrl(index.id)}><Button type="link" icon={<ArrowRightOutlined aria-hidden="true" />} iconPosition="end">查看记录说明</Button></Link>}</Card></aside>
    </div>
  </>;
}

export function Decisions() {
  return <><PageHeader title="关键决定" description="只记录影响后续工作的决定、依据与未知项。" /><DetailCard id="decisions" /><div className="page-footnote"><HistoryOutlined />任务完成标记与科研结论分开记录。</div></>;
}

export function DocumentPage({ project = false }: { project?: boolean }) {
  const { id } = useParams();
  const location = useLocation();
  const document = getDocument(project ? 'README' : (id || ''));
  useEffect(() => {
    if (!location.hash) return;
    const handle = window.setTimeout(() => {
      const target = window.document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (target instanceof HTMLDetailsElement) target.open = true;
      target?.scrollIntoView({ block: 'start' });
    }, 80);
    return () => window.clearTimeout(handle);
  }, [location.pathname, location.hash]);
  if (!document) return <Result status="404" title="没有找到这份文档" subTitle="文件可能已移动，请从研究工作台重新选择。" extra={<Link to="/"><Button type="primary">返回总览</Button></Link>} />;
  return <><PageHeader title={project ? '项目说明' : document.title} description={project ? '研究目标、固定边界与个人工作方式。' : categoryName[document.category]} extra={<Tag bordered={false}><FileTextOutlined /> {document.path}</Tag>} /><Card className="reading-card document-reading"><Markdown content={document.markdown} sourcePath={document.path} /></Card></>;
}
