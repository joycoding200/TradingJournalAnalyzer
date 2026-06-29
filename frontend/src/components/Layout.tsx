import { useState, useEffect } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { useConfirm } from "../context/ConfirmContext";
import { clearTrades } from "../api/upload";
import { getMe, updateNickname } from "../api/auth";
import { Input } from "./ui";
import BackToTop from "./BackToTop";

/* ─── Inline SVG icons ───────────────────────────────────────────────────── */
const UserIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

const HistoryIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

const TrashIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    <line x1="10" y1="11" x2="10" y2="17" />
    <line x1="14" y1="11" x2="14" y2="17" />
  </svg>
);

const LogoutIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
);

const EditIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
  </svg>
);

const MenuIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="3" y1="6" x2="21" y2="6" />
    <line x1="3" y1="12" x2="21" y2="12" />
    <line x1="3" y1="18" x2="21" y2="18" />
  </svg>
);

const CloseIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

/* ─── Nav link helper ─────────────────────────────────────────────────────── */
function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className="rounded-lg px-3 py-1.5 text-sm font-medium text-text-secondary no-underline transition-colors hover:bg-bg-tertiary hover:text-text-primary"
    >
      {children}
    </Link>
  );
}

/* ─── Dropdown menu item ──────────────────────────────────────────────────── */
function DropdownItem({
  onClick,
  disabled,
  icon,
  children,
  variant = "default",
}: {
  onClick: () => void;
  disabled?: boolean;
  icon: React.ReactNode;
  children: React.ReactNode;
  variant?: "default" | "warning" | "danger";
}) {
  const colorClass = {
    default: "text-text-primary hover:bg-bg-tertiary",
    warning: "text-warning hover:bg-warning/8",
    danger: "text-danger hover:bg-danger/8",
  }[variant];

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex w-full cursor-pointer items-center gap-2.5 border-0 bg-transparent px-4 py-2.5 text-left text-sm transition-colors disabled:opacity-50 focus-ring ${colorClass}`}
    >
      <span className="flex-shrink-0 opacity-70">{icon}</span>
      <span>{children}</span>
    </button>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
export default function Layout() {
  const { isLoggedIn, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const confirmDialog = useConfirm();
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [nickname, setNickname] = useState("");
  const [editingNick, setEditingNick] = useState(false);
  const [nickInput, setNickInput] = useState("");
  const [nickSaving, setNickSaving] = useState(false);

  useEffect(() => {
    if (isLoggedIn) {
      getMe().then((u) => setNickname(u.nickname || "")).catch(() => {});
    }
  }, [isLoggedIn]);

  // Close mobile nav & menu on route change
  useEffect(() => {
    setMobileNavOpen(false);
    setMenuOpen(false);
  }, [location.pathname]);

  const handleSaveNick = async () => {
    const v = nickInput.trim();
    if (!v || v.length < 2 || v.length > 20) return;
    setNickSaving(true);
    try {
      await updateNickname(v);
      setNickname(v);
      setEditingNick(false);
      toast.addToast("success", "昵称已更新");
    } catch (err) {
      toast.addToast("error", err instanceof Error ? err.message : "修改失败");
    } finally {
      setNickSaving(false);
    }
  };

  const handleLogout = () => {
    logout();
    toast.addToast("info", "已退出登录");
    navigate("/");
  };

  const handleClear = async () => {
    const ok = await confirmDialog.confirm({
      title: "清空全部数据",
      message: "将永久删除所有交易记录、分析结果、AI 报告和原始文件。此操作不可撤销，确定继续？",
      confirmText: "永久删除",
      cancelText: "取消",
      variant: "danger",
    });
    if (!ok) return;
    setMenuOpen(false);
    setClearing(true);
    try {
      await clearTrades();
      toast.addToast("success", "所有交易数据已永久删除");
      navigate("/upload");
    } catch (err) {
      toast.addToast("error", err instanceof Error ? err.message : "清空失败");
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      {/* E2.5: skip-to-content link — first keyboard focus, jumps to main */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
      >
        跳到主内容
      </a>

      {/* ═══ Navigation Bar ══════════════════════════════════════════════════ */}
      <nav className="sticky top-0 z-50 flex items-center justify-between border-b border-border bg-bg-secondary/95 px-4 py-2.5 backdrop-blur-sm md:px-6">
        {/* Logo */}
        <Link
          to="/"
          className="text-lg font-extrabold tracking-tight no-underline"
          aria-label="TradeDoctor 首页"
        >
          <span className="bg-gradient-to-r from-blue-400 via-accent to-purple-400 bg-clip-text text-transparent">
            TradeDoctor
          </span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden items-center gap-1 md:flex">
          {isLoggedIn ? (
            <>
              {/* A2.1+A2.2: top-level nav links with active highlight */}
              <Link
                to="/upload"
                className={`rounded-lg px-3 py-1.5 text-sm font-medium no-underline transition-colors ${
                  location.pathname.startsWith("/upload")
                    ? "bg-accent/10 text-accent"
                    : "text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
                }`}
              >
                新分析
              </Link>
              <Link
                to="/history"
                className={`rounded-lg px-3 py-1.5 text-sm font-medium no-underline transition-colors ${
                  location.pathname === "/history"
                    ? "bg-accent/10 text-accent"
                    : "text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
                }`}
              >
                历史
              </Link>

              {/* User avatar + dropdown */}
              <div className="relative ml-1">
                <button
                  type="button"
                  onClick={() => setMenuOpen(!menuOpen)}
                  aria-expanded={menuOpen}
                  aria-haspopup="true"
                  aria-label="账户菜单"
                  className={`flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border bg-transparent p-0 transition-all duration-200 focus-ring ${
                    menuOpen
                      ? "border-accent text-accent"
                      : "border-border text-text-secondary hover:border-text-secondary hover:text-text-primary"
                  }`}
                >
                  <UserIcon />
                </button>

                {menuOpen && (
                  <>
                    {/* Backdrop */}
                    <div
                      className="fixed inset-0 z-10"
                      onClick={() => setMenuOpen(false)}
                    />
                    {/* Dropdown */}
                    <div className="absolute right-0 top-full z-20 mt-2 min-w-44 animate-slide-down overflow-hidden rounded-xl border border-border/60 bg-bg-secondary shadow-[0_12px_40px_rgba(0,0,0,0.45)]">
                      {/* Header: nickname */}
                      <div className="border-b border-border px-4 py-3">
                        {editingNick ? (
                          <div className="flex items-center gap-1.5">
                            <Input
                              value={nickInput}
                              onChange={(e) => setNickInput(e.target.value)}
                              maxLength={20}
                              placeholder="输入昵称"
                              autoFocus
                              className="!w-28 !px-2 !py-1 !text-xs"
                            />
                            <button
                              type="button"
                              onClick={handleSaveNick}
                              disabled={nickSaving}
                              className="cursor-pointer rounded-md border-0 bg-accent px-2 py-1 text-xs text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
                            >
                              {nickSaving ? "..." : "保存"}
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-text-primary">
                              {nickname || "未设置昵称"}
                            </span>
                            <button
                              type="button"
                              onClick={() => { setNickInput(nickname); setEditingNick(true); }}
                              className="cursor-pointer rounded-md border-0 bg-transparent p-1 text-text-secondary transition-colors hover:bg-bg-tertiary hover:text-accent focus-ring"
                              aria-label="修改昵称"
                            >
                              <EditIcon />
                            </button>
                          </div>
                        )}
                        <div className="mt-1.5 text-[11px] text-text-secondary">
                          {nickname ? "点击编辑修改昵称" : "设置昵称让报告更亲切"}
                        </div>
                      </div>

                      {/* Menu items */}
                      <div className="py-1">
                        <DropdownItem
                          icon={<HistoryIcon />}
                          onClick={() => { navigate("/history"); setMenuOpen(false); }}
                        >
                          历史报告
                        </DropdownItem>

                        <DropdownItem
                          icon={<TrashIcon />}
                          onClick={handleClear}
                          disabled={clearing}
                          variant="warning"
                        >
                          {clearing ? "清空中..." : "清空数据"}
                        </DropdownItem>
                      </div>

                      <div className="border-t border-border py-1">
                        <DropdownItem
                          icon={<LogoutIcon />}
                          onClick={handleLogout}
                          variant="danger"
                        >
                          退出登录
                        </DropdownItem>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </>
          ) : (
            <>
              <NavLink to="/login">登录</NavLink>
              <NavLink to="/register">注册</NavLink>
            </>
          )}
        </div>

        {/* Mobile hamburger — A2.3: visual feedback when open */}
        <button
          type="button"
          className={`cursor-pointer rounded-lg border-0 bg-transparent p-1.5 transition-colors hover:bg-bg-tertiary focus-ring md:hidden ${
            mobileNavOpen
              ? "text-accent"
              : "text-text-secondary hover:text-text-primary"
          }`}
          onClick={() => setMobileNavOpen(!mobileNavOpen)}
          aria-label="菜单"
          aria-expanded={mobileNavOpen}
        >
          {mobileNavOpen ? <CloseIcon /> : <MenuIcon />}
        </button>
      </nav>

      {/* ═══ Mobile nav dropdown ══════════════════════════════════════════════ */}
      {mobileNavOpen && (
        <div className="animate-slide-down border-b border-border bg-bg-secondary px-4 py-3 md:hidden">
          {isLoggedIn ? (
            <div className="flex flex-col gap-1">
              <div className="mb-1 rounded-lg bg-bg-tertiary px-3 py-2">
                <span className="text-sm font-medium text-text-primary">
                  {nickname || "未设置昵称"}
                </span>
              </div>

              <Link
                to="/upload"
                className={`rounded-lg px-3 py-2 text-sm font-medium no-underline transition-colors ${
                  location.pathname.startsWith("/upload")
                    ? "bg-accent/10 text-accent"
                    : "text-accent hover:bg-accent/10"
                }`}
              >
                新分析
              </Link>

              <Link
                to="/history"
                className={`rounded-lg px-3 py-2 text-sm font-medium no-underline transition-colors ${
                  location.pathname === "/history"
                    ? "bg-accent/10 text-accent"
                    : "text-text-primary hover:bg-bg-tertiary"
                }`}
              >
                历史报告
              </Link>

              <button
                onClick={handleClear}
                disabled={clearing}
                className="cursor-pointer rounded-lg border-0 bg-transparent px-3 py-2 text-left text-sm font-medium text-warning transition-colors hover:bg-warning/8 disabled:opacity-50 focus-ring"
              >
                {clearing ? "清空中..." : "清空数据"}
              </button>

              <div className="my-1.5 border-t border-border" />

              <button
                onClick={handleLogout}
                className="cursor-pointer rounded-lg border-0 bg-transparent px-3 py-2 text-left text-sm font-medium text-danger transition-colors hover:bg-danger/8 focus-ring"
              >
                退出登录
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <Link
                to="/login"
                className="rounded-lg px-3 py-2 text-sm font-medium text-text-primary no-underline transition-colors hover:bg-bg-tertiary"
              >
                登录
              </Link>
              <Link
                to="/register"
                className="rounded-lg px-3 py-2 text-sm font-medium text-text-primary no-underline transition-colors hover:bg-bg-tertiary"
              >
                注册
              </Link>
            </div>
          )}
        </div>
      )}

      <main id="main-content" className="flex-1">
        <Outlet />
      </main>

      {/* A2.4: back-to-top button (appears after scrolling) */}
      <BackToTop />
    </div>
  );
}
