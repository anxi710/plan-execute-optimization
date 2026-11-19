import { createRoot } from 'react-dom/client';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter } from 'react-router-dom';
import AlfworldResults from './pages/AlfworldResults';
import './styles.css';

createRoot(document.getElementById('root')!).render(
  <ConfigProvider locale={zhCN} theme={{
    algorithm: theme.darkAlgorithm,
    token: {
      colorPrimary: '#cba6f7', colorLink: '#89b4fa', colorText: '#cdd6f4',
      colorTextSecondary: '#bac2de', colorBgBase: '#1e1e2e',
      colorBgContainer: '#181825', colorBorder: '#45475a', borderRadius: 10, fontSize: 16,
      fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif',
    },
  }}>
    <BrowserRouter><div className="alfworld-standalone"><AlfworldResults /></div></BrowserRouter>
  </ConfigProvider>,
);
