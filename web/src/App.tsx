import { App as AntApp, ConfigProvider, Result, type ThemeConfig } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import WorkspaceLayout from './layouts/WorkspaceLayout';
import { Collection, Decisions, DocumentPage, Overview, Questions } from './pages/ResearchPages';

const theme: ThemeConfig = {
  token: {
    colorPrimary: '#16776b',
    colorInfo: '#16776b',
    colorText: '#203536',
    colorTextSecondary: '#64776f',
    colorBgLayout: '#f5f7f8',
    colorBorderSecondary: '#e8edee',
    borderRadius: 10,
    fontSize: 14,
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif',
  },
  components: {
    Layout: { headerBg: '#fff', siderBg: '#fff' },
    Menu: { itemSelectedBg: '#eaf4f0', itemSelectedColor: '#136b61', itemHoverBg: '#f4f7f6', itemHeight: 43 },
    Card: { headerFontSize: 15, headerHeight: 62 },
    Button: { controlHeight: 38, primaryShadow: 'none' },
  },
};

export default function App() {
  return <ConfigProvider locale={zhCN} theme={theme}>
    <AntApp>
      <BrowserRouter>
        <Routes>
          <Route element={<WorkspaceLayout />}>
            <Route index element={<Overview />} />
            <Route path="questions" element={<Questions />} />
            <Route path="literature" element={<Collection category="paper" />} />
            <Route path="experiments" element={<Collection category="experiment" />} />
            <Route path="decisions" element={<Decisions />} />
            <Route path="project" element={<DocumentPage project />} />
            <Route path="documents/:id" element={<DocumentPage />} />
            <Route path="*" element={<Result status="404" title="页面不存在" extra={<Link to="/">返回研究总览</Link>} />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AntApp>
  </ConfigProvider>;
}
