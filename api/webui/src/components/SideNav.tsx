import React from "react";
import { ChevronsLeft, ChevronsRight, Sprout } from "lucide-react";
import { configurableNavItems, FIXED_FOOTER_NAV_ITEMS, type NavItem } from "../navigation";
import type { ResearchTab, SideNavConfigValue } from "../types";

export interface SideNavProps {
  tab: ResearchTab;
  onChange: (tab: ResearchTab) => void;
  showAdmin?: boolean;
  config?: SideNavConfigValue | null;
}

export function SideNav({ tab, onChange, showAdmin = false, config }: SideNavProps) {
  const [collapsed, setCollapsed] = React.useState(false);
  const asideRef = React.useRef<HTMLElement | null>(null);
  const primaryItems = configurableNavItems(config);
  const footerItems = showAdmin
    ? FIXED_FOOTER_NAV_ITEMS
    : FIXED_FOOTER_NAV_ITEMS.filter((item) => item.tab !== "admin");

  const handleWheel = React.useCallback((event: React.WheelEvent<HTMLElement>) => {
    const aside = asideRef.current;
    if (!aside) return;

    const canScrollSelf = aside.scrollHeight > aside.clientHeight + 1;
    if (canScrollSelf) {
      const atTop = aside.scrollTop <= 0;
      const atBottom = aside.scrollTop + aside.clientHeight >= aside.scrollHeight - 1;
      const scrollingUp = event.deltaY < 0;
      const scrollingDown = event.deltaY > 0;

      if ((!atTop || !scrollingUp) && (!atBottom || !scrollingDown)) {
        return;
      }
    }

    const isScrollable = (element: HTMLElement) => {
      const style = window.getComputedStyle(element);
      const overflowY = style.overflowY;
      return (
        (overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") &&
        element.scrollHeight > element.clientHeight + 1
      );
    };

    const canScrollInDirection = (element: HTMLElement, deltaY: number) => {
      if (deltaY < 0) return element.scrollTop > 0;
      if (deltaY > 0) return element.scrollTop + element.clientHeight < element.scrollHeight - 1;
      return false;
    };

    const findScrollableAncestor = (start: HTMLElement | null, deltaY: number) => {
      let current: HTMLElement | null = start;
      while (current) {
        if (isScrollable(current) && canScrollInDirection(current, deltaY)) {
          return current;
        }
        current = current.parentElement;
      }
      return null;
    };

    const workspace = document.querySelector<HTMLElement>(".app-shell__main .workspace");
    if (!workspace) return;

    const asideRect = aside.getBoundingClientRect();
    const probeX = Math.min(window.innerWidth - 8, Math.max(asideRect.right + 24, asideRect.right + 1));
    const probeY = Math.min(window.innerHeight - 8, Math.max(8, event.clientY));
    const probeElement = document.elementFromPoint(probeX, probeY) as HTMLElement | null;

    let target =
      findScrollableAncestor(probeElement, event.deltaY) ||
      Array.from(workspace.querySelectorAll<HTMLElement>("*")).find(
        (element) => isScrollable(element) && canScrollInDirection(element, event.deltaY),
      ) ||
      (isScrollable(workspace) ? workspace : null);

    if (!target) {
      target = workspace;
    }

    target.scrollBy({ top: event.deltaY, behavior: "auto" });
    event.preventDefault();
  }, []);

  const renderItem = (item: NavItem) => {
    const Icon = item.icon;
    const active = tab === item.tab;
    return (
      <li key={item.tab}>
        <button
          type="button"
          className={`side-nav__item ${active ? "is-active" : ""}`}
          onClick={() => onChange(item.tab)}
          title={collapsed ? item.label : undefined}
        >
          <Icon size={18} />
          {!collapsed && <span>{item.label}</span>}
        </button>
      </li>
    );
  };

  return (
    <aside
      ref={asideRef}
      className={`side-nav ${collapsed ? "is-collapsed" : ""}`}
      aria-label="主导航"
      onWheel={handleWheel}
    >
      <div className="side-nav__brand">
        <span className="side-nav__brand-mark">
          <Sprout size={20} />
        </span>
        {!collapsed && (
          <div className="side-nav__brand-text">
            <strong>增长雷达</strong>
            <span>社媒增长智能系统</span>
          </div>
        )}
      </div>

      <nav className="side-nav__body">
        {!collapsed && <div className="side-nav__group-label">核心模块</div>}
        <ul className="side-nav__list">{primaryItems.map(renderItem)}</ul>
      </nav>

      <div className="side-nav__footer">
        {!collapsed && (
          <div className="side-nav__status-card">
            <span className="side-nav__status-label">数据更新于</span>
            <strong>2026-05-22 09:30</strong>
          </div>
        )}
        <ul className="side-nav__list">{footerItems.map(renderItem)}</ul>
        <button
          type="button"
          className="side-nav__collapse"
          onClick={() => setCollapsed((value) => !value)}
          title={collapsed ? "展开" : "收起"}
        >
          {collapsed ? <ChevronsRight size={14} /> : <ChevronsLeft size={14} />}
          {!collapsed && <span>收起边栏</span>}
        </button>
      </div>
    </aside>
  );
}
