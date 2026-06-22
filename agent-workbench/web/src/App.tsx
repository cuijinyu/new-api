import { useEffect, useState } from "react";
import { Activity, BadgeDollarSign, Bot, Database, FileUp, Gauge, LayoutList, Loader2, Percent, Receipt, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { Badge, Button } from "./components/ui";
import { ToastProvider } from "./hooks/useToast";
import { useWorkbench } from "./hooks/useWorkbench";
import { OverviewPage } from "./pages/OverviewPage";
import { BillingPage } from "./pages/BillingPage";
import { PricingPage } from "./pages/PricingPage";
import { DiscountsPage } from "./pages/DiscountsPage";
import { AutomationPage } from "./pages/AutomationPage";
import { BillsPage } from "./pages/BillsPage";
import { AgentPage } from "./pages/AgentPage";
import { GovernancePage } from "./pages/GovernancePage";
import { FilesPage } from "./pages/FilesPage";
import { RawLogsPage } from "./pages/RawLogsPage";
import type { PageId } from "./types";

type NavItem = { id: PageId; label: string; icon: typeof Gauge; title: string; desc?: string };

// 一级导航收敛为主流程 5 项。
const primaryNav: NavItem[] = [
  { id: "overview", label: "首页", icon: Gauge, title: "首页", desc: "下一步该做什么 + 进度概览" },
  { id: "billing", label: "生成账单", icon: Database, title: "生成账单", desc: "选月份即时预览，一键生成真实账单" },
  { id: "pricing", label: "价格管理", icon: BadgeDollarSign, title: "价格管理", desc: "各模型刊例价，全局生效，保存即用" },
  { id: "discounts", label: "折扣管理", icon: Percent, title: "折扣管理", desc: "渠道成本与客户折扣，全局生效，保存即用" },
  { id: "automation", label: "账单自动化", icon: LayoutList, title: "账单自动化", desc: "定时月结、批次追踪与交付" },
  { id: "bills", label: "账单库", icon: Receipt, title: "账单库", desc: "按类型与账期浏览结构化账单，查看明细并下载" },
  { id: "agent", label: "对账 Agent", icon: Bot, title: "对账 Agent", desc: "上传资料，直接提问即开始分析" },
  { id: "governance", label: "建议与经验", icon: ShieldCheck, title: "建议与经验", desc: "处理建议、沉淀经验" },
];

// 二级"更多"入口：资料库情境化保留总入口，S3 Raw Logs 降级为"日志检索"排查入口。
const secondaryNav: NavItem[] = [
  { id: "files", label: "资料库", icon: FileUp, title: "资料库", desc: "供应商账单、凭证与账单结果归档" },
  { id: "rawlogs", label: "日志检索", icon: Search, title: "日志检索", desc: "S3 原始日志排查（高级）" },
];

const allNav = [...primaryNav, ...secondaryNav];

export function App() {
  return (
    <ToastProvider>
      <WorkbenchShell />
    </ToastProvider>
  );
}

function WorkbenchShell() {
  const wb = useWorkbench();
  const [activePage, setActivePage] = useState<PageId>(() => {
    const hash = window.location.hash.replace("#", "");
    return allNav.some((page) => page.id === hash) ? (hash as PageId) : "overview";
  });

  useEffect(() => {
    const onHashChange = () => {
      const next = window.location.hash.replace("#", "");
      if (allNav.some((page) => page.id === next)) {
        setActivePage(next as PageId);
      }
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  function switchPage(page: PageId) {
    setActivePage(page);
    window.location.hash = page;
  }

  const currentPage = allNav.find((page) => page.id === activePage) || primaryNav[0];

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Activity size={20} />
          </div>
          <div>
            <h1>Agent 工作台</h1>
            <p>对账运营工作台</p>
          </div>
        </div>
        <nav className="nav-menu">
          {primaryNav.map((page) => {
            const Icon = page.icon;
            return (
              <button key={page.id} className={`nav-item ${activePage === page.id ? "active" : ""}`} onClick={() => switchPage(page.id)}>
                <Icon size={17} />
                {page.label}
              </button>
            );
          })}
          <div className="nav-divider">更多</div>
          {secondaryNav.map((page) => {
            const Icon = page.icon;
            return (
              <button key={page.id} className={`nav-item nav-item-secondary ${activePage === page.id ? "active" : ""}`} onClick={() => switchPage(page.id)}>
                <Icon size={16} />
                {page.label}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-status">
          <div className="metric">
            <span>API 服务</span>
            <Badge tone={wb.health?.ok ? "green" : "red"}>{wb.health?.ok ? "可用" : "未连接"}</Badge>
          </div>
          <div className="metric">
            <span>资料归档</span>
            <Badge tone="blue">{wb.health?.artifact_store ? "可用" : "-"}</Badge>
          </div>
        </div>
      </aside>

      <main className="admin-main">
        <header className="admin-topbar">
          <div>
            <h2>{currentPage.title}</h2>
            {currentPage.desc ? <p>{currentPage.desc}</p> : null}
          </div>
          <div className="topbar-actions">
            <Button variant="outline" onClick={wb.refreshHealth} disabled={wb.pending === "health"}>
              {wb.pending === "health" ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
              刷新
            </Button>
          </div>
        </header>

        {activePage === "overview" ? <OverviewPage wb={wb} switchPage={switchPage} /> : null}
        {activePage === "billing" ? <BillingPage wb={wb} switchPage={switchPage} /> : null}
        {activePage === "pricing" ? <PricingPage wb={wb} /> : null}
        {activePage === "discounts" ? <DiscountsPage wb={wb} /> : null}
        {activePage === "automation" ? <AutomationPage wb={wb} switchPage={setActivePage} /> : null}
        {activePage === "bills" ? <BillsPage wb={wb} switchPage={switchPage} /> : null}
        {activePage === "agent" ? <AgentPage wb={wb} switchPage={switchPage} /> : null}
        {activePage === "governance" ? <GovernancePage wb={wb} /> : null}
        {activePage === "files" ? <FilesPage wb={wb} switchPage={switchPage} /> : null}
        {activePage === "rawlogs" ? <RawLogsPage wb={wb} /> : null}
      </main>
    </div>
  );
}
