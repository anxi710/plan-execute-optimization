import { useRef, useState } from 'react';
import { Empty, Input, Modal, Tag, type InputRef } from 'antd';
import { ArrowRightOutlined, FileTextOutlined, SearchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { documents, searchDocuments } from '../content';

const documentUrl = (id: string) => `/documents/${encodeURIComponent(id)}`;
const categoryName = { project: '项目说明', paper: '论文笔记', experiment: '实验记录', research: '研究工作台' };

export default function SearchDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const input = useRef<InputRef>(null);
  const navigate = useNavigate();
  const matches = query.trim() ? searchDocuments(query) : documents.map((item) => ({ ...item, excerpt: item.path }));
  function choose(id: string) { onClose(); navigate(documentUrl(id)); }
  return <Modal open={open} onCancel={onClose} footer={null} closable={false} className="search-dialog" width={660} afterOpenChange={(visible) => { if (visible) input.current?.focus(); }}>
    <Input ref={input} variant="borderless" size="large" prefix={<SearchOutlined />} placeholder="搜索问题、论文、实验与项目说明" value={query} onChange={(event) => setQuery(event.target.value)} suffix={<kbd>esc</kbd>} aria-label="搜索研究内容" />
    <div className="search-results"><div className="search-caption">{query.trim() ? `找到 ${matches.length} 条内容` : '浏览研究内容'}</div>{matches.length ? matches.map((item) => <button className="search-result" key={item.id} onClick={() => choose(item.id)}><span className="search-result-icon"><FileTextOutlined /></span><span className="search-result-copy"><strong>{item.title}<Tag bordered={false}>{categoryName[item.category]}</Tag></strong><small>{item.excerpt}</small></span><ArrowRightOutlined /></button>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有找到匹配内容，试试其他关键词" />}</div>
    <div className="search-footer">搜索仓库中的真实记录，不包含外部检索。</div>
  </Modal>;
}
