"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Activity,
  Building2,
  ChevronDown,
  Command,
  FileSearch,
  Layers3,
  Menu,
  MessageSquareText,
  Search,
  Settings2,
  Tags,
  X,
} from "lucide-react";

const navigation = [
  { label: "Overview", href: "/workspace/overview", icon: Layers3 },
  { label: "Intelligence", href: "/workspace/intelligence", icon: Activity },
  { label: "Watchlists", href: "/workspace/watchlists", icon: FileSearch },
  { label: "Companies", href: "/workspace/companies", icon: Building2 },
  { label: "Topics", href: "/workspace/topics", icon: Tags },
  { label: "Sources", href: "/workspace/sources", icon: Command },
  { label: "Ask Vantage", href: "/workspace/ask", icon: MessageSquareText },
];

// Settings lives outside `navigation` (rendered separately, pinned to the sidebar bottom),
// but the breadcrumb still needs to resolve its label for the current section.
const settingsSection = { label: "Settings", href: "/workspace/settings" };
const breadcrumbSections = [...navigation, settingsSection];

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const currentSectionLabel = breadcrumbSections.find((item) => pathname.startsWith(item.href))?.label ?? "Workspace";

  return (
    <div className="app-frame">
      {mobileOpen && <button aria-label="Close navigation" className="nav-scrim" onClick={() => setMobileOpen(false)} />}
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <Link className="brand" href="/workspace/overview" onClick={() => setMobileOpen(false)}>
          <span className="brand-mark" aria-hidden="true">V</span>
          <span>vantage<span className="brand-period">.</span></span>
        </Link>
        <div className="workspace-picker">
          <span className="workspace-monogram">N</span>
          <span className="workspace-name"><strong>Northstar Group</strong><small>Strategy workspace</small></span>
          <ChevronDown size={15} aria-hidden="true" />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav className="primary-nav" aria-label="Workspace navigation">
          {navigation.map(({ label, href, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={`nav-link ${active ? "nav-link-active" : ""}`}
                href={href}
                key={href}
                onClick={() => setMobileOpen(false)}
              >
                <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
                <span>{label}</span>
                {label === "Intelligence" && <span className="nav-count">4</span>}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <Link className={`nav-link ${pathname === "/workspace/settings" ? "nav-link-active" : ""}`} href="/workspace/settings" onClick={() => setMobileOpen(false)}>
            <Settings2 size={17} strokeWidth={1.8} aria-hidden="true" /><span>Settings</span>
          </Link>
          <div className="profile-row">
            <span className="avatar">JD</span>
            <span className="profile-copy"><strong>Jordan Davis</strong><small>Executive analyst</small></span>
            <ChevronDown size={15} aria-hidden="true" />
          </div>
          <Link className="public-site-link" href="/" onClick={() => setMobileOpen(false)}>
            View public site
          </Link>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <button className="mobile-menu icon-button" aria-label={mobileOpen ? "Close navigation" : "Open navigation"} onClick={() => setMobileOpen(!mobileOpen)}>
            {mobileOpen ? <X size={19} /> : <Menu size={19} />}
          </button>
          <div className="breadcrumb"><span>Northstar Group</span><span className="breadcrumb-slash">/</span><strong>{currentSectionLabel}</strong></div>
          <div className="topbar-tools">
            <label className="global-search">
              <Search size={15} aria-hidden="true" />
              <input aria-label="Search Vantage" placeholder="Search intelligence" />
              <kbd>⌘ K</kbd>
            </label>
            <span className="sample-indicator"><span />Sample workspace</span>
          </div>
        </header>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}