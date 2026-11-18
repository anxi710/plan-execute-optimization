import { App as AntApp, ConfigProvider, Result, theme as antTheme, type ThemeConfig } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import WorkspaceLayout from './layouts/WorkspaceLayout';
import { Collection, Decisions, DocumentPage, Overview, QuestionPage, Questions } from './pages/ResearchPages';

const theme: ThemeConfig = {
  algorithm: antTheme.darkAlgorithm,
  token: {
    colorPrimary: '#cba6f7',
    colorPrimaryHover: '#b4befe',
    colorPrimaryActive: '#b4befe',
    colorInfo: '#89b4fa',
    colorSuccess: '#a6e3a1',
    colorWarning: '#f9e2af',
    colorError: '#f38ba8',
    colorText: '#cdd6f4',
    colorTextSecondary: '#bac2de',
    colorTextTertiary: '#a6adc8',
    colorTextLightSolid: '#1e1e2e',
    colorLink: '#89b4fa',
    colorLinkHover: '#b4befe',
    colorBgBase: '#1e1e2e',
    colorBgLayout: '#1e1e2e',
    colorBgContainer: '#181825',
    colorBgElevated: '#1e1e2e',
    colorBorder: '#45475a',
    colorBorderSecondary: '#313244',
    borderRadius: 10,
    fontSize: 16,
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif',
  },
  components: {
    Layout: { headerBg: '#181825', siderBg: '#181825' },
    Menu: { itemSelectedBg: '#313244', itemSelectedColor: '#cba6f7', itemHoverBg: '#313244', itemHeight: 43 },
    Card: { headerFontSize: 15, headerHeight: 62 },
    Button: { controlHeight: 38, primaryColor: '#1e1e2e', primaryShadow: 'none' },
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
            <Route path="questions/:id" element={<QuestionPage />} />
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
