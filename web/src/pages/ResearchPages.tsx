import { useEffect, useState, type ReactNode } from 'react';
import { Badge, Button, Card, Drawer, Empty, Result, Space, Tag, Typography } from 'antd';
import {
  ArrowRightOutlined, ArrowUpOutlined, BookOutlined, ClockCircleOutlined,
  CodeOutlined, CompassOutlined, ExperimentOutlined, FileTextOutlined,
  HistoryOutlined, NodeIndexOutlined, ReadOutlined, SearchOutlined,
} from '@ant-design/icons';
import { Link, useLocation, useParams } from 'react-router-dom';
import { documents, getDocument, research } from '../content';
import Markdown from '../components/Markdown';

const { Title, Text } = Typography;
const documentUrl = (id: string) => `/documents/${encodeURIComponent(id)}`;
const detail = (id: string) => research.details.find((item) => item.id === id);
const question = detail('p1');
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
    <PageHeader title="研究总览" description="围绕当前问题，找到下一项最有用的证据。" extra={<Tag className="stage-tag" bordered={false}><Badge status="processing" />{research.stage}</Tag>} />
    <div className="overview-grid">
      <div className="overview-main">
        <Card className="focus-card" bordered={false}>
          <div className="card-eyebrow"><span className="eyebrow-icon"><CompassOutlined /></span>当前关注的问题<span className="reference-label">P1</span></div>
          <h2>{question ? question.title.replace(/^P1\s*题卡\s*[·：:]\s*/, '') : '当前研究问题'}</h2>
          <div className="focus-judgment"><Markdown content={research.judgment} sourcePath={research.sourcePath} /></div>
          <div className="focus-actions"><Link to="/questions"><Button type="primary" icon={<ArrowRightOutlined />} iconPosition="end">打开问题卡</Button></Link>{evidence && <Button type="text" onClick={() => setEvidenceOpen(true)}>查看证据状态</Button>}</div>
        </Card>
        <Card className="unknown-card" title={<Space><span className="section-icon amber"><SearchOutlined /></span><span>当前最大的未知</span></Space>} extra={<Tag bordered={false} color="gold">待核查</Tag>}>
          <Markdown content={research.unknown} sourcePath={research.sourcePath} />
          <div className="subtle-note"><ClockCircleOutlined />核查前，保留问题，不预选解决方法。</div>
        </Card>
        <Card className="system-card" title={<Space><span className="section-icon"><NodeIndexOutlined /></span><span>研究设置</span></Space>} extra={<Link to="/project">项目边界 <ArrowRightOutlined /></Link>}>
          <div className="architecture" aria-label="Planner 生成计划，固定 Executor 与环境交互，执行反馈用于优化 Planner">
            <div className="architecture-node planner-node"><div className="architecture-icon"><NodeIndexOutlined /></div><strong>Planner</strong><Tag bordered={false} color="cyan">优化参数</Tag></div>
            <div className="architecture-edge"><span>计划</span><ArrowRightOutlined /></div>
            <div className="architecture-node"><div className="architecture-icon"><CodeOutlined /></div><strong>Executor</strong><Tag bordered={false}>保持固定</Tag></div>
            <div className="architecture-edge"><span>执行</span><ArrowRightOutlined /></div>
            <div className="architecture-node"><div className="architecture-icon"><ExperimentOutlined /></div><strong>环境</strong><Text type="secondary">交互与反馈</Text></div>
          </div>
          <div className="feedback-line"><ArrowUpOutlined rotate={90} /><span>执行反馈用于 Planner 优化，实际交互成本计入比较</span></div>
        </Card>
      </div>
      <aside className="overview-aside" aria-label="下一步与阅读入口">
        <Card className="next-card" title={<Space><span className="section-icon"><ArrowRightOutlined /></span><span>下一步</span></Space>}>
          <Tag className="task-label" bordered={false}>L1 · 文献核查</Tag>
          <Markdown content={research.next} sourcePath={research.sourcePath} />
          <Link to="/literature"><Button block icon={<ReadOutlined />}>查看阅读任务</Button></Link>
        </Card>
        <Card className="quick-links-card" title="研究资料">
          <Link className="resource-link" to="/literature"><span className="resource-icon"><BookOutlined /></span><span><strong>文献阅读</strong><small>原文、方法与证据</small></span><ArrowRightOutlined /></Link>
          <Link className="resource-link" to="/experiments"><span className="resource-icon"><ExperimentOutlined /></span><span><strong>实验记录</strong><small>方案、配置与结果</small></span><ArrowRightOutlined /></Link>
          <Link className="resource-link" to="/decisions"><span className="resource-icon"><HistoryOutlined /></span><span><strong>关键决定</strong><small>判断变化与未决项</small></span><ArrowRightOutlined /></Link>
        </Card>
        <div className="reading-tip"><ReadOutlined /><p>先读判断，再看依据。需要细节时，打开对应的题卡或记录。</p></div>
      </aside>
    </div>
    <Drawer title="证据状态" width={700} open={evidenceOpen} onClose={() => setEvidenceOpen(false)}>{evidence && <Markdown content={evidence.markdown} sourcePath={research.sourcePath} />}</Drawer>
  </>;
}

export function Questions() {
  const candidates = research.details.filter((item) => /^p\d+$/i.test(item.id));
  return <>
    <PageHeader title="候选问题" description="保留可检验的假设，也保留能推翻它的条件。" extra={<Tag bordered={false}>{candidates.length} 个候选</Tag>} />
    <div className="page-notice"><CompassOutlined /><span>候选题卡用于判断是否值得继续，尚未核查的线索不代表研究空白。</span></div>
    {candidates.map((item) => <section className="candidate-section" key={item.id} id={item.id}>
      <div className="section-heading"><span className="number-label">{item.id.toUpperCase()}</span><h3>{item.title.replace(/^P\d+\s*题卡\s*[·：:]\s*/, '')}</h3></div>
      <Card className="reading-card"><Markdown content={item.markdown} sourcePath={research.sourcePath} /></Card>
    </section>)}
    {candidates.length === 0 && <Card><Empty description="还没有记录候选问题" /></Card>}
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
        {records.length ? <div className="document-grid">{records.map((item) => <Card key={item.id} className="document-card" title={<Space>{isPaper ? <BookOutlined /> : <ExperimentOutlined />}<span>{item.title}</span></Space>}><Text type="secondary">{item.path}</Text><Link to={documentUrl(item.id)}><Button type="link" icon={<ArrowRightOutlined />} iconPosition="end">打开记录</Button></Link></Card>)}</div> : <Card className="empty-state-card"><Empty image={<span className="empty-icon">{isPaper ? <BookOutlined /> : <ExperimentOutlined />}</span>} description={<><h3>{isPaper ? '还没有已完成核查的论文笔记' : '还没有已设计或执行的实验'}</h3><p>{isPaper ? '当前先核查代表方法的来源与反馈流程。完成后，笔记会出现在这里。' : '先核实问题与最近邻差异，再决定是否设计有界诊断。'}</p></>} /><Link to={isPaper ? '#reading-task' : '/questions'}><Button icon={isPaper ? <ReadOutlined /> : <CompassOutlined />}>{isPaper ? '查看当前阅读任务' : '查看候选问题'}</Button></Link></Card>}
        {isPaper && reading && <section className="reading-task" id="reading-task"><div className="section-heading"><span className="number-label">L1</span><h3>当前阅读任务</h3></div><DetailCard id="l1" /></section>}
      </section>
      <aside className="collection-aside"><Card title={<Space><FileTextOutlined /><span>记录方式</span></Space>}><p>详细证据就近保存在对应目录，研究判断写回工作台。</p><p>任务通过 Issue 跟踪，记录通过 PR 与版本关联。</p>{index && <Link to={documentUrl(index.id)}><Button type="link" icon={<ArrowRightOutlined />} iconPosition="end">查看记录说明</Button></Link>}</Card></aside>
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
