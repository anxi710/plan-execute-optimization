import { useEffect, useState } from 'react';
import { Avatar, Breadcrumb, Button, Drawer, Layout, Menu, Tag, type MenuProps } from 'antd';
import {
  BookOutlined, CompassOutlined, ExperimentOutlined, FolderOpenOutlined,
  HistoryOutlined, HomeOutlined, MenuOutlined, NodeIndexOutlined,
  ReadOutlined, SearchOutlined, SettingOutlined,
} from '@ant-design/icons';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { research } from '../content';
import SearchDialog from '../components/SearchDialog';

const { Header, Sider, Content } = Layout;

const sections = [
  { path: '/', label: '研究总览', icon: <HomeOutlined /> },
  { path: '/questions', label: '候选问题', icon: <CompassOutlined /> },
  { path: '/literature', label: '文献阅读', icon: <BookOutlined /> },
  { path: '/experiments', label: '实验记录', icon: <ExperimentOutlined /> },
  { path: '/decisions', label: '关键决定', icon: <HistoryOutlined /> },
  { path: '/project', label: '项目说明', icon: <FolderOpenOutlined /> },
];

export default function WorkspaceLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const current = sections.find((item) => item.path === location.pathname);
  const selected = current?.path || (location.pathname.startsWith('/documents/') ? '/project' : '/');
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setSearchOpen((value) => !value); }
    }
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, []);
  useEffect(() => { window.scrollTo(0, 0); }, [location.pathname]);
  const items: MenuProps['items'] = [
    { type: 'group', label: '研究工作台', children: sections.slice(0, 4).map((item) => ({ key: item.path, icon: item.icon, label: item.label })) },
    { type: 'group', label: '项目记录', children: sections.slice(4).map((item) => ({ key: item.path, icon: item.icon, label: item.label })) },
  ];
  const navigation = <><Link to="/" className="workspace-brand" onClick={() => setMobileOpen(false)}><span className="brand-mark"><NodeIndexOutlined /></span><span><strong>Planner Lab</strong><small>个人研究工作台</small></span></Link><div className="project-switcher"><span className="project-symbol">PE</span><span><strong>Planner–Executor</strong><small>Optimization</small></span><Tag bordered={false}>ICML</Tag></div><Menu mode="inline" selectedKeys={[selected]} items={items} onClick={({ key }) => { navigate(key); setMobileOpen(false); }} /><div className="sidebar-bottom"><span className="workspace-avatar"><Avatar size={30} icon={<ReadOutlined />} /></span><div><strong>个人研究空间</strong><small>判断与证据，持续积累</small></div><SettingOutlined /></div></>;
  return <Layout className="workspace-layout">
    <a href="#workspace-main" className="skip-link">跳到主要内容</a>
    <Sider className="desktop-sidebar" width={248} breakpoint="lg" collapsedWidth={0} trigger={null}>{navigation}</Sider>
    <Drawer placement="left" width={280} open={mobileOpen} onClose={() => setMobileOpen(false)} className="mobile-navigation" title="研究工作台">{navigation}</Drawer>
    <Layout className="main-shell"><Header className="workspace-header"><div className="header-left"><Button className="mobile-menu-button" type="text" icon={<MenuOutlined />} onClick={() => setMobileOpen(true)} aria-label="打开导航" /><Breadcrumb items={[{ title: <Link to="/"><HomeOutlined /></Link> }, { title: current?.label || '阅读文档' }]} /></div><div className="header-right"><Button className="search-trigger" icon={<SearchOutlined />} onClick={() => setSearchOpen(true)} aria-label="搜索研究内容"><span>搜索研究内容</span><kbd>⌘ K</kbd></Button><span className="header-divider" /><Avatar size={30} className="header-avatar" icon={<ReadOutlined />} /></div></Header>
      <Content id="workspace-main" className="workspace-body"><div className="page-container"><Outlet /><footer className="workspace-footer"><span><span className="status-dot" />来自仓库中的研究记录</span><span>记录更新 {research.date}</span></footer></div></Content>
    </Layout><SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} />
  </Layout>;
}
