"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/elements/ui/utils";
import {
  Activity,
  CheckSquare,
  MessageSquare,
  Briefcase,
  BarChart3,
  Zap,
  Settings,
  ChevronLeft,
  ChevronRight,
  FileText,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/pulse", label: "Pulse", icon: Activity },
  { href: "/decisions", label: "Decisions", icon: CheckSquare },
  { href: "/briefs", label: "Briefs", icon: FileText },
  { href: "/debate", label: "Debate", icon: MessageSquare },
  { href: "/portfolio", label: "Portfolio", icon: Briefcase },
  { href: "/backtest", label: "Backtest", icon: BarChart3 },
  { href: "/signal", label: "Signal", icon: Zap },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("midas_sidebar_collapsed");
    if (stored === "true") setCollapsed(true);
  }, []);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("midas_sidebar_collapsed", String(next));
  };

  return (
    <aside
      className={cn(
        "flex flex-col h-screen border-r border-[var(--border-default)] bg-[var(--bg-surface)] transition-[width] duration-[var(--transition-default)]",
        collapsed ? "w-16" : "w-52",
      )}
    >
      <div className="flex-1 flex flex-col py-4">
        <div
          className={cn(
            "px-4 mb-6 flex items-center",
            collapsed ? "justify-center" : "justify-between",
          )}
        >
          {!collapsed && (
            <span className="text-lg font-semibold text-[var(--accent-gold)]">
              Midas
            </span>
          )}
          <button
            onClick={toggle}
            className="p-1 rounded hover:bg-[var(--bg-hover)] text-[var(--text-muted)] transition-colors"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        <nav className="flex-1 flex flex-col gap-1 px-2">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname?.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-[var(--radius)] text-sm transition-colors",
                  active
                    ? "bg-[var(--bg-hover)] text-[var(--accent-gold)]"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]",
                  collapsed && "justify-center px-0",
                )}
                title={collapsed ? label : undefined}
              >
                <Icon size={18} />
                {!collapsed && <span>{label}</span>}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="border-t border-[var(--border-default)] py-2 px-2">
        <Link
          href="/settings"
          className={cn(
            "flex items-center gap-3 px-3 py-2 rounded-[var(--radius)] text-sm transition-colors",
            pathname === "/settings"
              ? "bg-[var(--bg-hover)] text-[var(--accent-gold)]"
              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]",
            collapsed && "justify-center px-0",
          )}
          title={collapsed ? "Settings" : undefined}
        >
          <Settings size={18} />
          {!collapsed && <span>Settings</span>}
        </Link>
      </div>
    </aside>
  );
}

export function ViewportGate({ children }: { children: React.ReactNode }) {
  const [wideEnough, setWideEnough] = useState(true);

  useEffect(() => {
    const check = () => setWideEnough(window.innerWidth >= 1024);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  if (!wideEnough) {
    return (
      <div className="flex items-center justify-center h-screen bg-[var(--bg-base)] p-8 text-center">
        <div className="space-y-3">
          <p className="text-lg font-semibold text-[var(--text-primary)]">
            Desktop Required
          </p>
          <p className="text-sm text-[var(--text-secondary)] max-w-sm">
            Midas is optimized for screens 1024px and wider. Please use a
            desktop browser for the best experience.
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
