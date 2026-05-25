import type React from "react";
import {
  BriefcaseBusiness,
  FilePenLine,
  FileSearch,
  LayoutGrid,
  Orbit,
  Newspaper,
  Settings as SettingsIcon,
  ShieldAlert,
  ShieldCheck,
  Target,
  UserSearch,
  WandSparkles,
} from "lucide-react";
import type { ResearchTab, SideNavConfigValue } from "./types";

export type NavItem = {
  label: string;
  icon: React.ComponentType<{ size?: number }>;
  tab: ResearchTab;
};

export const CONFIGURABLE_SIDE_NAV_ITEMS: NavItem[] = [
  { label: "今日播报", icon: Newspaper, tab: "today" },
  { label: "项目工作台", icon: LayoutGrid, tab: "projects" },
  { label: "内容策略中心", icon: WandSparkles, tab: "key_insights" },
  { label: "内容生产", icon: FilePenLine, tab: "content_production" },
  { label: "内容追踪", icon: FileSearch, tab: "content_tracking" },
  { label: "线索归因", icon: Orbit, tab: "lead_attribution" },
  { label: "友商监控", icon: ShieldAlert, tab: "competitors" },
  { label: "达人发现", icon: UserSearch, tab: "creators" },
  { label: "达人商务", icon: BriefcaseBusiness, tab: "account_analysis" },
  { label: "线索转化", icon: Target, tab: "reports_center" },
];

export const FIXED_FOOTER_NAV_ITEMS: NavItem[] = [
  { label: "管理后台", icon: ShieldCheck, tab: "admin" },
  { label: "设置", icon: SettingsIcon, tab: "settings" },
];

export function defaultSideNavConfig(): SideNavConfigValue {
  return {
    items: CONFIGURABLE_SIDE_NAV_ITEMS.map((item, index) => ({
      tab: item.tab,
      visible: true,
      sort_order: index * 10,
    })),
  };
}

export function normalizeSideNavConfig(value?: Partial<SideNavConfigValue> | null): SideNavConfigValue {
  const allowedTabs = new Set(CONFIGURABLE_SIDE_NAV_ITEMS.map((item) => item.tab));
  const defaultIndex = new Map(CONFIGURABLE_SIDE_NAV_ITEMS.map((item, index) => [item.tab, index]));
  const rawItems = Array.isArray(value?.items) ? value.items : [];
  if (rawItems.length === 0) {
    return defaultSideNavConfig();
  }

  const configured = new Map<ResearchTab, { tab: ResearchTab; visible: boolean; sort_order: number }>();
  for (const item of rawItems) {
    if (!item || !allowedTabs.has(item.tab) || configured.has(item.tab)) continue;
    const fallbackOrder = (defaultIndex.get(item.tab) ?? configured.size) * 10;
    configured.set(item.tab, {
      tab: item.tab,
      visible: item.visible !== false,
      sort_order: Number.isFinite(item.sort_order) ? Number(item.sort_order) : fallbackOrder,
    });
  }

  let nextSortOrder = Math.max(-10, ...Array.from(configured.values()).map((item) => item.sort_order)) + 10;
  for (const item of CONFIGURABLE_SIDE_NAV_ITEMS) {
    if (configured.has(item.tab)) continue;
    configured.set(item.tab, {
      tab: item.tab,
      visible: true,
      sort_order: nextSortOrder,
    });
    nextSortOrder += 10;
  }

  const items = Array.from(configured.values())
    .sort((a, b) => a.sort_order - b.sort_order || (defaultIndex.get(a.tab) ?? 0) - (defaultIndex.get(b.tab) ?? 0))
    .map((item, index) => ({ ...item, sort_order: index * 10 }));

  if (items.length > 0 && !items.some((item) => item.visible)) {
    items[0] = { ...items[0], visible: true };
  }
  return { items };
}

export function configurableNavItems(config?: SideNavConfigValue | null): NavItem[] {
  const byTab = new Map(CONFIGURABLE_SIDE_NAV_ITEMS.map((item) => [item.tab, item]));
  return normalizeSideNavConfig(config).items
    .filter((item) => item.visible)
    .map((item) => byTab.get(item.tab))
    .filter((item): item is NavItem => Boolean(item));
}

export function firstVisibleConfigurableTab(config?: SideNavConfigValue | null): ResearchTab {
  return configurableNavItems(config)[0]?.tab || "projects";
}
