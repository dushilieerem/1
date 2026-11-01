import { useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Home, Newspaper, PieChart, Star, User, Users } from "lucide-react";

const TABS = [
  { to: "/", label: "首页", icon: Home },
  { to: "/watch", label: "自选", icon: Star },
  { to: "/portfolio", label: "组合", icon: PieChart },
  { to: "/news", label: "资讯", icon: Newspaper },
  { to: "/community", label: "社区", icon: Users },
  { to: "/me", label: "我的", icon: User },
];

export default function Shell() {
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
        <nav className="tabbar" aria-label="底部导航">
          {TABS.map((item) => {
            const Icon = item.icon;
            const active = item.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(item.to);
            return (
              <NavLink key={item.to} to={item.to} className={`tab ${active ? "on" : ""}`} aria-current={active ? "page" : undefined}>
                <Icon size={22} strokeWidth={active ? 2.4 : 1.9} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      ) : null}
    </div>
  );
}
