import { useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { BookOpen, Home, Newspaper, PieChart, Star, User, Users } from "lucide-react";
import { useLocale } from "../i18n";

const TABS = [
  { to: "/", zh: "首页", en: "Home", icon: Home },
  { to: "/watch", zh: "自选", en: "Watch", icon: Star },
  { to: "/portfolio", zh: "组合", en: "Portfolio", icon: PieChart },
  { to: "/news", zh: "资讯", en: "News", icon: Newspaper },
  { to: "/learn", zh: "学习", en: "Learn", icon: BookOpen },
  { to: "/community", zh: "社区", en: "Community", icon: Users },
  { to: "/me", zh: "我的", en: "Me", icon: User },
];

export default function Shell() {
  const { t } = useLocale();
  const loc = useLocation();
  const hideTab = /^\/(stock|topic)\//.test(loc.pathname);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [loc.pathname]);

  return (
    <div className={`app ${hideTab ? "no-tab" : ""}`}>
      <main className="app-main">
        <Outlet />
      </main>
      {!hideTab ? (
        <nav className="tabbar" aria-label={t("底部导航", "Bottom navigation")}>
          {TABS.map((item) => {
            const Icon = item.icon;
            const meArea = item.to === "/me" && /^\/(quant|paper|notifications)/.test(loc.pathname);
            const active = item.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(item.to) || meArea;
            return (
              <NavLink key={item.to} to={item.to} className={`tab ${active ? "on" : ""}`} aria-current={active ? "page" : undefined}>
                <Icon size={22} strokeWidth={active ? 2.4 : 1.9} />
                <span>{t(item.zh, item.en)}</span>
              </NavLink>
            );
          })}
        </nav>
      ) : null}
    </div>
  );
}
