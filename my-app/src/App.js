import React, { createContext, lazy, Suspense, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity, ArchiveX as Trash2, ArrowDownRight, ArrowDownRight as TrendingDown, ArrowRight, ArrowUpRight, BarChart3, Bolt as Zap, Check, CheckCircle2,
  ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Cloud, Download, Eye, Filter,
  Globe2, Grid2X2, HeartPulse, Home, ImagePlus, Info, LayoutDashboard, List, LockKeyhole,
  Menu, MessageCircle, MoreHorizontal, Plus, Receipt, ScanLine, Search, Send, Settings,
  ShieldCheck, ShoppingBag, SlidersHorizontal, Sparkles, CloudUpload, CircleUserRound as User,
  CreditCard as Wallet, CircleX as X,
} from 'lucide-react';
import './App.css';
import LandingPage from './LandingPage';
import AuthPage from './AuthPage';
import { supabase } from './lib/supabase';

const SpendingChart = lazy(() => import('./components/Charts').then(module => ({ default: module.SpendingChart })));
const CategoryChart = lazy(() => import('./components/Charts').then(module => ({ default: module.CategoryChart })));
const InsightsChart = lazy(() => import('./components/Charts').then(module => ({ default: module.InsightsChart })));
const MerchantChart = lazy(() => import('./components/Charts').then(module => ({ default: module.MerchantChart })));

const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

export function getInitials(name, email) {
  if (name && name.trim()) {
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return parts[0].slice(0, 2).toUpperCase();
  }
  if (email && email.trim()) {
    return email.slice(0, 2).toUpperCase();
  }
  return 'U';
}

const money = (value, currency = 'INR') => new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 2 }).format(Number(value) || 0);
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
function getStoredAccessToken() {
  const stores = [window.localStorage, window.sessionStorage];
  for (const store of stores) {
    for (let index = 0; index < store.length; index += 1) {
      const key = store.key(index);
      if (!key || !(key.startsWith('sb-') && key.endsWith('-auth-token')) && !['supabase.auth.token', 'billsnap-auth-session'].includes(key)) continue;
      try {
        const session = JSON.parse(store.getItem(key));
        const token = session?.access_token || session?.currentSession?.access_token;
        if (typeof token === 'string' && token) return token;
      } catch {
        continue;
      }
    }
  }
  return null;
}

async function getAccessToken() {
  if (supabase) {
    const { data, error } = await supabase.auth.getSession();
    if (error) throw error;
    return data.session?.access_token || null;
  }
  return getStoredAccessToken();
}

async function apiRequest(path, token, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
      Authorization: `Bearer ${token}`,
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(typeof payload?.detail === 'string' ? payload.detail : `Request failed (${response.status}).`);
    error.status = response.status;
    error.detail = payload?.detail;
    throw error;
  }
  return payload;
}

function toBillRow(bill, categoryName = null) {
  return {
    id: bill.id,
    merchant: bill.merchant_name,
    category: categoryName || 'Uncategorized',
    amount: Number(bill.total_amount),
    currency: bill.currency || 'INR',
    date: bill.bill_date,
    payment: bill.payment_method || '',
    status: bill.review_status || 'Saved',
    icon: '◈',
    color: '#26332d',
  };
}

const readStorage = (key, fallback) => {
  try {
    const saved = localStorage.getItem(key);
    return saved ? JSON.parse(saved) : fallback;
  } catch (error) {
    console.error(`Unable to read ${key} from local storage`, error);
    return fallback;
  }
};

function AppProvider({ children }) {
  const [bills, setBills] = useState([]);
  const [preferences, setPreferences] = useState(() => readStorage('billsnap-preferences', { currency: 'INR', language: 'English', cloudSync: false, privacyMode: true }));
  const [toast, setToast] = useState('');
  const [pendingBill, setPendingBill] = useState(null);
  const [user, setUser] = useState(null);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');

  useEffect(() => { localStorage.removeItem('billsnap-bills'); }, []);
  useEffect(() => localStorage.setItem('billsnap-preferences', JSON.stringify(preferences)), [preferences]);

  useEffect(() => {
    if (!supabase) return undefined;
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        setUser(session.user);
        setName(session.user.user_metadata?.full_name || session.user.user_metadata?.name || '');
        setEmail(session.user.email || '');
      }
    }).catch(console.error);

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        setUser(session.user);
        setName(session.user.user_metadata?.full_name || session.user.user_metadata?.name || '');
        setEmail(session.user.email || '');
      } else {
        setUser(null);
        setName('');
        setEmail('');
      }
    });

    return () => subscription?.unsubscribe();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const loadBills = token => apiRequest('/api/bills/categories', token, { signal: controller.signal })
      .catch(error => {
        if (error.name !== 'AbortError') console.warn('Categories could not be loaded:', error);
        return [];
      })
      .then(categoryList => apiRequest('/api/bills/?page_size=100', token, { signal: controller.signal })
        .then(result => setBills((result.items || []).map(bill => toBillRow(
          bill,
          categoryList.find(category => category.id === bill.category_id)?.name,
        )))))
      .catch(error => {
        if (error.name !== 'AbortError') console.warn('Saved bills could not be loaded:', error);
      });
    getAccessToken().then(token => { if (token) loadBills(token); }).catch(error => {
      console.warn('Unable to get access token:', error);
    });
    const authStateChange = supabase?.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_OUT' || !session) {
        setBills([]);
        return;
      }
      if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED' || event === 'USER_UPDATED') {
        Promise.resolve().then(() => loadBills(session.access_token));
      }
    });
    const subscription = authStateChange?.data.subscription;
    return () => {
      controller.abort();
      subscription?.unsubscribe();
    };
  }, []);
  useEffect(() => {
    if (!toast) return undefined;
    const timeout = window.setTimeout(() => setToast(''), 2800);
    return () => window.clearTimeout(timeout);
  }, [toast]);
  const value = { bills, setBills, preferences, setPreferences, toast, setToast, pendingBill, setPendingBill, user, setUser, name, setName, email, setEmail };
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

const navItems = [
  { to: '/app', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/bills', label: 'My bills', icon: Receipt },
  { to: '/scan', label: 'Scan a bill', icon: ScanLine },
  { to: '/insights', label: 'Insights', icon: Activity },
  { to: '/assistant', label: 'AI assistant', icon: Sparkles },
];

function Brand({ compact = false }) {
  return <Link to="/" aria-label="Bill Snap home" className={`brand ${compact ? 'brand-compact' : ''}`}><span className="brand-mark"><span /></span><span className="brand-name">bill<span>snap</span></span></Link>;
}

function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { name, email } = useApp();
  const initials = getInitials(name, email);
  const displayName = name || (email ? email.split('@')[0] : 'My Account');
  const displayRole = email || 'Personal space';
  return <>
    <aside className={`sidebar ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <div className="sidebar-top"><Brand /><button className="icon-btn collapse-btn" title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} onClick={() => setCollapsed(!collapsed)}><ChevronLeft size={17} className={collapsed ? 'rotate-icon' : ''} /></button></div>
      <Link to="/" aria-label="Personal space home" title="Go to Bill Snap landing page" className="workspace-switch"><span className="workspace-symbol">A</span><span className="workspace-copy"><strong>Personal space</strong></span></Link>
      <div className="nav-caption">WORKSPACE</div>
      <nav className="side-nav">
        {navItems.map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end} title={collapsed ? label : undefined} className={({ isActive }) => `nav-link ${isActive ? 'nav-active' : ''}`}><Icon size={18} strokeWidth={1.8} /><span>{label}</span>{label === 'AI assistant' && !collapsed && <span className="nav-new">NEW</span>}</NavLink>)}
      </nav>
      <div className="nav-caption tools-caption">PREFERENCES</div>
      <nav className="side-nav"><NavLink to="/settings" title={collapsed ? 'Settings & privacy' : undefined} className={({ isActive }) => `nav-link ${isActive ? 'nav-active' : ''}`}><Settings size={18} strokeWidth={1.8} /><span>Settings & privacy</span></NavLink></nav>
      <div className="sidebar-bottom">
        <button className="profile-button" title="Open account settings" aria-label="Open account settings" onClick={() => navigate('/settings')}><span className="avatar">{initials}</span><span className="profile-copy"><strong>{displayName}</strong><small>{displayRole}</small></span><MoreHorizontal size={17} /></button>
      </div>
    </aside>
    {location.pathname === '/scan' && <span className="sr-only">Scan bill</span>}
  </>;
}

function Topbar() {
  const location = useLocation();
  const [searchOpen, setSearchOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();
  const { name, email } = useApp();
  const initials = getInitials(name, email);
  const current = navItems.find(item => item.to === location.pathname);
  const title = current?.label || (location.pathname === '/privacy' ? 'Privacy review' : location.pathname === '/bill-details' ? 'Bill details' : 'Settings & privacy');
  return <header className="topbar">
    <div className="topbar-page"><span className="breadcrumb-root">Workspace</span><ChevronRight size={14} /><strong>{title}</strong></div>
    <div className="topbar-actions">
      <button className="mobile-menu-trigger" aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'} aria-expanded={mobileMenuOpen} onClick={() => setMobileMenuOpen(!mobileMenuOpen)}>{mobileMenuOpen ? <X size={19} /> : <Menu size={19} />}</button>
      {searchOpen && <input autoFocus aria-label="Search bills" className="top-search-input" placeholder="Search bills..." onKeyDown={event => { if (event.key === 'Enter') { navigate(`/bills?search=${encodeURIComponent(event.target.value)}`); setSearchOpen(false); } }} />}
      <button className="topbar-search" aria-label="Search" onClick={() => setSearchOpen(!searchOpen)}><Search size={17} /></button>
      <span className="topbar-divider" />
      <button className="top-avatar" aria-label="Account avatar" onClick={() => navigate('/settings')}>{initials}</button>
    </div>
    {mobileMenuOpen && <><button className="mobile-menu-backdrop" aria-label="Close menu" onClick={() => setMobileMenuOpen(false)} /><nav className="mobile-menu-panel" aria-label="More navigation"><Brand compact /><NavLink to="/settings" onClick={() => setMobileMenuOpen(false)}><Settings size={17} />Settings & privacy<ChevronRight size={15} /></NavLink></nav></>}
  </header>;
}

function MobileNav() {
  return <nav className="mobile-nav" aria-label="Mobile navigation">
    <NavLink to="/app" end><Home size={19} /><span>Home</span></NavLink>
    <NavLink to="/bills"><Receipt size={19} /><span>Bills</span></NavLink>
    <NavLink to="/scan" className="mobile-scan"><span><ScanLine size={21} /></span><small>Scan</small></NavLink>
    <NavLink to="/insights"><Activity size={19} /><span>Insights</span></NavLink>
    <NavLink to="/assistant"><MessageCircle size={19} /><span>AI chat</span></NavLink>
  </nav>;
}

function Layout() {
  const location = useLocation();
  const { toast, setToast } = useApp();
  useEffect(() => {
    const onToast = event => setToast(event.detail);
    window.addEventListener('billSnapToast', onToast);
    return () => window.removeEventListener('billSnapToast', onToast);
  }, [setToast]);
  if (location.pathname === '/') return <LandingPage />;
  if (location.pathname === '/login') return <AuthPage defaultSignup={false} />;
  if (location.pathname === '/signup') return <AuthPage defaultSignup={true} />;
  return <div className="app-shell">
    <Sidebar />
    <div className="main-shell"><Topbar />
      <main className="main-content"><AnimatePresence mode="wait"><motion.div key={location.pathname} className="route-page" initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: 0.2 }}><Routes>
        <Route path="/app" element={<Dashboard />} />
        <Route path="/bills" element={<MyBills />} />
        <Route path="/scan" element={<ScanBill />} />
        <Route path="/privacy" element={<PrivacyReview />} />
        <Route path="/bill-details" element={<BillDetails />} />
        <Route path="/insights" element={<SpendingInsights />} />
        <Route path="/assistant" element={<AIChat />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Dashboard />} />
      </Routes></motion.div></AnimatePresence></main>
      <MobileNav />
    </div>
    <AnimatePresence>{toast && <motion.div className="toast" initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }}><CheckCircle2 size={17} />{toast}</motion.div>}</AnimatePresence>
  </div>;
}

function PageIntro({ eyebrow, title, description, actions, compact = false }) {
  return <div className={`page-intro ${compact ? 'page-intro-compact' : ''}`}><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="intro-actions">{actions}</div>}</div>;
}

function Button({ children, variant = 'primary', icon: Icon, onClick, className = '', type = 'button', disabled }) {
  return <button type={type} onClick={onClick} disabled={disabled} className={`button button-${variant} ${className}`}>{Icon && <Icon size={16} />}{children}</button>;
}

function Panel({ children, className = '' }) {
  return <section className={`panel ${className}`}>{children}</section>;
}

function SectionHeading({ title, subtitle, action }) {
  return <div className="section-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>;
}

function Dashboard() {
  const navigate = useNavigate();
  const { bills, name, setToast } = useApp();
  const [range, setRange] = useState('Last 6 months');

  const now = new Date();
  const thisMonth = now.getMonth();
  const thisYear = now.getFullYear();

  const totalSpent = useMemo(() => bills.reduce((sum, b) => sum + (Number(b.amount) || 0), 0), [bills]);
  const avgPerBill = useMemo(() => bills.length > 0 ? totalSpent / bills.length : 0, [bills, totalSpent]);
  const categoryCounts = useMemo(() => {
    const map = {};
    bills.forEach(b => {
      const cat = b.category || 'Uncategorized';
      map[cat] = (map[cat] || 0) + (Number(b.amount) || 0);
    });
    return map;
  }, [bills]);
  const topCategory = useMemo(() => {
    let top = 'None'; let max = 0;
    Object.entries(categoryCounts).forEach(([cat, amt]) => { if (amt > max) { max = amt; top = cat; } });
    return top;
  }, [categoryCounts]);
  const topCategoryPercent = useMemo(() => {
    if (!totalSpent || topCategory === 'None') return '';
    return `${Math.round(((categoryCounts[topCategory] || 0) / totalSpent) * 100)}%`;
  }, [totalSpent, topCategory, categoryCounts]);

  // Monthly spend chart from real bills
  const MONTHS_BACK = range === 'Last 3 months' ? 3 : 6;
  const chartData = useMemo(() => {
    const months = [];
    for (let i = MONTHS_BACK - 1; i >= 0; i--) {
      const d = new Date(thisYear, thisMonth - i, 1);
      const mo = d.getMonth(); const yr = d.getFullYear();
      const label = d.toLocaleString('en-IN', { month: 'short' });
      const amt = bills
        .filter(b => { const bd = b.date ? new Date(b.date) : null; return bd && bd.getMonth() === mo && bd.getFullYear() === yr; })
        .reduce((s, b) => s + (Number(b.amount) || 0), 0);
      months.push({ month: label, amount: amt });
    }
    return months;
  }, [bills, range, thisMonth, thisYear, MONTHS_BACK]);

  // Category donut from real bills
  const CATEGORY_COLORS = ['#A78BFA','#67E8F9','#FBBF24','#34D399','#FB7185','#64748B','#F97316','#06B6D4'];
  const categoryChartData = useMemo(() =>
    Object.entries(categoryCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([name, amount], i) => ({ name, amount, color: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }))
  , [categoryCounts]);

  const stats = [
    { label: 'Spent this month', value: money(totalSpent), trend: '', note: `${bills.length} bills`, icon: Wallet, tone: 'violet' },
    { label: 'Bills organized', value: `${bills.length}`, trend: '', note: 'saved bills', icon: Receipt, tone: 'cyan' },
    { label: 'Average per bill', value: money(avgPerBill), trend: '', note: 'per receipt', icon: BarChart3, tone: 'amber' },
    { label: 'Top category', value: topCategory, trend: topCategoryPercent, note: topCategory !== 'None' ? 'of total spend' : 'no bills yet', icon: HeartPulse, tone: 'green', small: true },
  ];

  const formattedToday = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: '2-digit' }).format(new Date()).toUpperCase();
  const hour = new Date().getHours();
  const timeGreeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  const greeting = name ? `${timeGreeting}, ${name}` : 'Welcome';

  return <div className="page dashboard-page">
    <div className="welcome-strip"><div><span className="welcome-date">{formattedToday}</span><h1>{greeting}<span className="wave">✦</span></h1><p>A little more clarity for every rupee you spend.</p></div><Button icon={Plus} onClick={() => navigate('/scan')}>Add a bill</Button></div>
    <div className="stat-grid">{stats.map(({ label, value, trend, note, icon: Icon, tone, down, small }, index) => <motion.div key={label} className={`stat-card stat-${tone}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.05 }}><div className="stat-top"><span>{label}</span><span className="stat-icon"><Icon size={17} /></span></div><div className={`stat-value ${small ? 'stat-value-small' : ''}`}>{value}</div><div className="stat-foot"><span className={`trend ${down ? 'trend-down' : ''}`}>{trend && (down ? <ArrowDownRight size={13} /> : <ArrowUpRight size={13} />)}{trend}</span><span>{note}</span></div></motion.div>)}</div>
    <div className="dashboard-grid">
      <Panel className="spending-panel"><div className="panel-heading-row"><div><span className="panel-kicker">YOUR MONEY, OVER TIME</span><h2>Spending rhythm</h2><p>Every month, at a glance.</p></div><label className="select-button"><select aria-label="Dashboard date range" value={range} onChange={event => setRange(event.target.value)}><option>Last 6 months</option><option>Last 3 months</option></select><ChevronDown size={14} /></label></div><div className="chart-total"><strong>{money(totalSpent)}</strong><span className="positive-note">{bills.length} active bills</span></div><div className="spending-chart"><Suspense fallback={<div className="chart-skeleton" />}><SpendingChart data={chartData} /></Suspense></div><div className="chart-legend"><span><i className="legend-dot violet-dot" />Monthly spend</span><span className="chart-caption">Keep tracking your receipts. Nice work.</span></div></Panel>
      <Panel className="category-panel"><div className="panel-heading-row"><div><span className="panel-kicker">WHERE IT GOES</span><h2>Spending mix</h2></div><button className="icon-btn" title="More options" aria-label="About category breakdown" onClick={() => navigate('/insights')}><MoreHorizontal size={19} /></button></div><div className="donut-wrap"><Suspense fallback={<div className="chart-skeleton" />}><CategoryChart data={categoryChartData} /></Suspense><div className="donut-center"><span>TOTAL</span><strong>{money(totalSpent)}</strong></div></div><div className="category-legend">{categoryChartData.slice(0, 4).map(category => <div key={category.name}><span><i style={{ background: category.color }} />{category.name}</span><strong>{totalSpent > 0 ? Math.round(category.amount / totalSpent * 100) : 0}%</strong></div>)}</div><button className="text-link" onClick={() => navigate('/insights')}>See category breakdown <ArrowRight size={14} /></button></Panel>
    </div>
    <div className="lower-grid">
      <Panel className="transactions-panel"><SectionHeading title="Recent activity" subtitle="Your latest organized bills." action={<button className="text-link" onClick={() => navigate('/bills')}>All bills <ArrowRight size={14} /></button>} /><div className="transaction-list">{bills.slice(0, 5).map((bill, index) => <TransactionRow key={`${bill.merchant}-${index}`} bill={bill} onClick={() => navigate('/bills')} />)}</div></Panel>
      <div className="insight-card"><div className="insight-orbit orbit-one" /><div className="insight-orbit orbit-two" /><div className="insight-content"><div className="ai-label"><span><Sparkles size={14} /></span> A LITTLE INSIGHT</div><h2>Small wins<br />add up.</h2><p>{bills.length > 0 ? `You have organized ${bills.length} bills totaling ${money(totalSpent)}. Consistent tracking leads to better clarity.` : 'Scan your first receipt or invoice to begin organizing your expenses with Bill Snap.'}</p><button onClick={() => navigate('/assistant')}>Explore with AI <ArrowRight size={14} /></button></div><div className="insight-spark">✳</div></div>
    </div>
  </div>;
}

function TransactionRow({ bill, onClick }) {
  const date = bill.date || 'Date not detected';
  return <button className="transaction-row" onClick={onClick}><span className="merchant-icon" style={{ background: bill.color || '#222838' }}>{bill.icon || '◈'}</span><span className="transaction-name"><strong>{bill.merchant}</strong><small>{date}<i>·</i>{bill.category}</small></span><span className="transaction-amount">{money(bill.amount, bill.currency)}</span><span className="verified-mark"><Check size={12} /></span></button>;
}

function ScanBill() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [cameraActive, setCameraActive] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [sessionAvailable, setSessionAvailable] = useState(false);
  const [enablingDemo, setEnablingDemo] = useState(false);
  const [authError, setAuthError] = useState('');
  const [classification, setClassification] = useState(null);
  const [warning, setWarning] = useState('');
  const [qualityWarning, setQualityWarning] = useState('');
  const galleryInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const videoRef = useRef(null);
  const cameraStreamRef = useRef(null);
  const { setPendingBill, setToast } = useApp();
  const navigate = useNavigate();
  useEffect(() => {
    setPendingBill(null);
  }, []);
  useEffect(() => {
    if (!file && !scanning) return undefined;
    const handleBeforeUnload = event => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [file, scanning]);
  useEffect(() => {
    let active = true;
    getAccessToken()
      .then(token => { if (active) setSessionAvailable(Boolean(token)); })
      .catch(error => {
        console.error('Unable to verify the scanning session', error);
        if (active) setAuthError('Could not verify an OCR session. Refresh and try again.');
      });
    const authStateChange = supabase?.auth.onAuthStateChange((_event, session) => {
      if (active) setSessionAvailable(Boolean(session));
    });
    const subscription = authStateChange?.data.subscription;
    return () => {
      active = false;
      subscription?.unsubscribe();
    };
  }, []);
  const enableDemoOCR = async () => {
    try {
      if (await getAccessToken()) {
        setSessionAvailable(true);
        setAuthError('');
        return;
      }
    } catch (error) {
      console.error('Unable to verify the existing scanning session', error);
    }
    if (!supabase) {
      setAuthError('Supabase is not configured. Set the frontend Supabase URL and publishable key to enable OCR.');
      return;
    }
    setEnablingDemo(true);
    setAuthError('');
    try {
      const { data, error } = await supabase.auth.signInAnonymously();
      if (error) throw error;
      if (!data.session) throw new Error('Supabase did not create an authenticated demo session.');
      setSessionAvailable(true);
    } catch (error) {
      console.error('Unable to start an authenticated demo session', error);
      setAuthError(`${error.message || 'Could not start an authenticated demo session.'} Enable anonymous sign-ins in the Supabase project to use demo OCR.`);
    } finally {
      setEnablingDemo(false);
    }
  };
  const stopCamera = () => {
    cameraStreamRef.current?.getTracks().forEach(track => track.stop());
    cameraStreamRef.current = null;
    setCameraActive(false);
  };
  useEffect(() => () => cameraStreamRef.current?.getTracks().forEach(track => track.stop()), []);
  useEffect(() => {
    if (cameraActive && videoRef.current && cameraStreamRef.current) videoRef.current.srcObject = cameraStreamRef.current;
  }, [cameraActive]);
  const addFile = picked => {
    if (!picked) return;
    setPendingBill(null);
    setFile(null);
    setPreview('');
    setClassification(null);
    if (!['image/jpeg', 'image/png'].includes(picked.type)) { setWarning('Please choose a valid JPG or PNG image.'); return; }
    if (picked.size > 10 * 1024 * 1024) { setWarning('This image is over 10 MB. Choose a smaller file.'); return; }
    setWarning('');
    setQualityWarning('');
    setFile(picked);
    setPreview(URL.createObjectURL(picked));
  };
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  useEffect(() => {
    if (!preview) return undefined;
    const image = new Image();
    image.onload = () => {
      if (image.naturalWidth < 700 || image.naturalHeight < 500) setQualityWarning('This image may be a little small. A sharper photo usually makes bill details easier to read.');
    };
    image.src = preview;
    return () => { image.onload = null; };
  }, [preview]);
  const analyze = async () => {
    if (!file) { setWarning('Add a bill image first to continue.'); return; }
    setWarning('');
    setClassification(null);
    setPendingBill(null);
    setScanning(true);
    try {
      const token = await getAccessToken();
      if (!token) {
        setWarning('OCR requires an authenticated session. Login and signup are currently disabled, so scanning is unavailable in the public demo.');
        return;
      }
      const formData = new FormData();
      formData.append('file', file);
      const result = await apiRequest('/api/scanner/ocr', token, { method: 'POST', body: formData });
      setClassification(result.classification);
      const docType = result.classification?.document_type || result.classification?.label;
      if (docType === 'normal_photograph') {
        setWarning('Photograph detected. Please upload a clear receipt, bill, or invoice image.');
        return;
      }
      if (docType === 'identity_document') {
        setWarning('Identity document detected. Identity cards cannot be saved as expense bills.');
        return;
      }
      if (docType === 'bank_statement') {
        setWarning('Bank statement detected. Bank statements cannot currently be processed as single expense bills.');
        return;
      }
      if (result.classification?.label === 'non_bill' && !['receipt', 'bill', 'invoice'].includes(docType)) {
        setWarning(result.classification.message || 'This image does not appear to be a bill or receipt.');
        return;
      }
      if (!['bill', 'receipt', 'invoice'].includes(docType) && !result.classification?.should_continue_field_extraction) {
        setWarning(result.classification?.message || 'We could not confidently identify this image as a bill or receipt. Try a clearer image.');
        return;
      }
      setPendingBill({ file, result });
      setToast('OCR complete. Review the detected details before saving.');
      navigate('/bill-details');
    } catch (error) {
      const detail = error.detail;
      if (detail?.code === 'not_a_bill' || detail?.code === 'bill_image_uncertain') {
        setClassification(detail.classification || null);
        setWarning(detail.classification?.message || (detail.code === 'not_a_bill' ? 'This image does not appear to be a bill.' : 'We could not confidently identify this image as a bill.'));
      } else if (error.status === 401) {
        setWarning('Your scanning session expired. Restart the app before trying again.');
      } else {
        setWarning(error.message || 'OCR could not process this image. Try again with a JPG or PNG file.');
      }
    } finally {
      setScanning(false);
    }
  };
  const openCamera = async () => {
    const getUserMedia = navigator.mediaDevices?.getUserMedia?.bind(navigator.mediaDevices);
    if (!getUserMedia) {
      cameraInputRef.current?.click();
      return;
    }
    try {
      const stream = await getUserMedia({ audio: false, video: { facingMode: { ideal: 'environment' } } });
      cameraStreamRef.current = stream;
      setCameraActive(true);
      setWarning('');
    } catch (error) {
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        setWarning('Camera access was denied. Allow camera access in your browser settings, or choose Take a photo to use your device camera instead.');
      } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
        setWarning('No camera was found. Choose an image from your gallery instead.');
      } else {
        setWarning('We couldn’t open your camera. Camera access needs HTTPS or localhost; use your gallery or the photo fallback.');
      }
      cameraInputRef.current?.click();
    }
  };
  const capturePhoto = () => {
    const video = videoRef.current;
    if (!video?.videoWidth || !video?.videoHeight) {
      setWarning('The camera is still starting. Try capturing again in a moment.');
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext('2d');
    if (!context) {
      setWarning('Photo capture is unavailable in this browser. Please choose an image from your gallery.');
      return;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob => {
      if (!blob) {
        setWarning('We couldn’t capture that photo. Please try again or choose it from your gallery.');
        return;
      }
      addFile(new File([blob], `bill-snap-${Date.now()}.jpg`, { type: 'image/jpeg' }));
      stopCamera();
    }, 'image/jpeg', 0.88);
  };
  return <div className="page">
    <PageIntro eyebrow="A BETTER WAY TO KEEP TRACK" title="Let’s scan your bill." description="One photo in. A little more clarity out." />
    <div className="scan-layout"><div className="scan-main"><div className={`upload-zone ${file || cameraActive ? 'upload-filled' : ''}`} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); addFile(event.dataTransfer.files[0]); }} onClick={() => !file && !cameraActive && galleryInputRef.current?.click()} role="group" aria-label="Bill image upload" tabIndex={0} onKeyDown={event => { if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ') && !cameraActive) galleryInputRef.current?.click(); }}>
      <input ref={galleryInputRef} type="file" accept=".jpg,.jpeg,.png,image/jpeg,image/png" hidden onChange={event => { addFile(event.target.files[0]); event.target.value = ''; }} />
      <input ref={cameraInputRef} type="file" accept=".jpg,.jpeg,.png,image/jpeg,image/png" capture="environment" hidden onChange={event => { addFile(event.target.files[0]); event.target.value = ''; }} />
      {cameraActive ? <div className="camera-preview"><video ref={videoRef} autoPlay playsInline muted aria-label="Camera preview" /><div className="camera-controls"><button onClick={event => { event.stopPropagation(); stopCamera(); }}><X size={17} /> Cancel</button><button className="capture-button" aria-label="Capture photo" onClick={event => { event.stopPropagation(); capturePhoto(); }}><span /></button><span className="camera-control-spacer" /></div></div> : file ? <div className="preview-wrap"><img src={preview} alt="Selected bill preview" /><div className="preview-overlay"><span><CheckCircle2 size={16} /> Ready to review</span><span className="preview-actions"><button aria-label="Retake photo" onClick={event => { event.stopPropagation(); setFile(null); setPreview(''); setClassification(null); setWarning(''); setPendingBill(null); openCamera(); }}><ScanLine size={15} /></button><button aria-label="Remove image" onClick={event => { event.stopPropagation(); setFile(null); setPreview(''); setClassification(null); setWarning(''); setPendingBill(null); }}><X size={15} /></button></span></div></div> : <div className="upload-prompt"><span className="upload-icon"><ImagePlus size={24} /></span><h2>Drop your bill right here</h2><p>or browse from your device</p><div className="upload-actions"><Button icon={CloudUpload} onClick={event => { event.stopPropagation(); galleryInputRef.current?.click(); }}>Choose from gallery</Button><button className="camera-button" onClick={event => { event.stopPropagation(); openCamera(); }}><ScanLine size={16} /> Take a photo</button></div><span className="upload-formats">JPG or PNG <i /> Up to 10 MB</span></div>}
      {scanning && <div className="scan-overlay"><span className="scan-line" /><div className="scan-status"><span className="scan-spinner" /><strong>Analyzing your image</strong><small>OCR and bill classification are running…</small></div></div>}
    </div>
      <div className="page-navigation-tip">
        <Info size={16} />
        <span><strong>Tip:</strong> Please stay on this page while uploading and analyzing. Navigating to another page will reset your scan.</span>
      </div>
      {warning && <div className="inline-warning" role="alert"><Info size={15} />{warning}</div>}
      {qualityWarning && file && !warning && <div className="inline-warning quality-warning"><Info size={15} />{qualityWarning}</div>}
      {classification && <div className="analysis-success"><span><Info size={18} /></span><div><strong>{classification.label === 'bill' ? 'Valid receipt detected.' : classification.label === 'non_bill' ? 'This image does not appear to be a bill.' : 'We could not confidently identify this image as a bill.'}</strong><p>{classification.reasons?.join(' ') || classification.message}</p>{classification.warnings?.length > 0 && <p>{classification.warnings.join(' ')}</p>}</div></div>}
      {!sessionAvailable && <div className="demo-auth-actions"><Button icon={LockKeyhole} disabled={enablingDemo} onClick={enableDemoOCR}>{enablingDemo ? 'Starting secure session…' : 'Enable demo OCR'}</Button><span>This creates an anonymous Supabase session for this browser.</span></div>}
      {authError && <div className="inline-warning" role="alert">{authError}</div>}
      <div className="scan-footer"><Button icon={Sparkles} disabled={scanning || !file} onClick={analyze}>{scanning ? 'Analyzing…' : classification?.label === 'bill' ? 'Analyze again' : 'Analyze bill'}</Button><span>{sessionAvailable ? 'Image is processed by your configured OCR backend.' : 'Enable a secure demo session to run OCR.'}</span></div>
    </div><aside className="scan-aside"><Panel className="scan-help"><span className="aside-icon"><ShieldCheck size={18} /></span><h3>Your bill stays yours.</h3><p>{sessionAvailable ? 'The selected image is sent to your configured backend for OCR. It is not saved as a bill until you confirm the review.' : 'Enable demo OCR to create an anonymous authenticated session. The backend verifies this session before processing an image.'}</p><div className="aside-rule" /><div className="help-line"><CheckCircle2 size={15} /><span>Authenticated upload</span></div><div className="help-line"><CheckCircle2 size={15} /><span>You review before saving</span></div></Panel><Panel className="photo-tips"><h3>For the clearest scan</h3><p>A few small things make a big difference.</p><ul><li>Keep the whole bill in frame</li><li>Use bright, even lighting</li><li>Lay it flat to avoid shadows</li><li><strong>Do not change pages:</strong> Stay on this screen until your bill is analyzed and saved; leaving will discard your scan.</li></ul></Panel><div className="help-link"><CircleHelp size={15} /> <span>JPG and PNG supported up to 10 MB</span></div></aside></div>
  </div>;
}

function PrivacyReview() {
  const { pendingBill } = useApp();
  const navigate = useNavigate();
  const [previewUrl, setPreviewUrl] = useState('');
  useEffect(() => {
    if (!pendingBill?.file) {
      navigate('/scan', { replace: true });
      return undefined;
    }
    const url = URL.createObjectURL(pendingBill.file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [pendingBill, navigate]);
  if (!pendingBill) return null;
  return <div className="page">
    <PageIntro eyebrow="YOUR DATA, YOUR CALL" title="Privacy review." description="Your uploaded image is shown as received. No redaction is applied." />
    <Panel className="receipt-panel">
      <div className="receipt-topline"><span>UPLOADED IMAGE</span><span className="receipt-page">OCR PREVIEW</span></div>
      {previewUrl && <div className="privacy-image-preview"><img src={previewUrl} alt="Uploaded receipt preview" /></div>}
      <div className="privacy-disclaimer"><Info size={15} /><span>Privacy masking and redaction are not implemented. Review this original image before saving.</span></div>
      <Button icon={ShieldCheck} onClick={() => navigate('/bill-details')}>Continue to bill review</Button>
    </Panel>
  </div>;
}

function BillDetails() {
  const { pendingBill, setPendingBill, setBills, setToast } = useApp();
  const navigate = useNavigate();
  const [details, setDetails] = useState(null);
  const [backendCategories, setBackendCategories] = useState([]);
  const [previewUrl, setPreviewUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [ocrFields, setOcrFields] = useState({});
  const result = pendingBill?.result;
  useEffect(() => {
    if (!pendingBill?.file || !result) {
      navigate('/scan', { replace: true });
      return undefined;
    }
    const fields = result.fields || {};
    setDetails({
      merchant: fields.merchant_name?.value || '',
      date: fields.bill_date?.value || '',
      amount: fields.total_amount?.value ?? '',
      subtotal: fields.subtotal?.value ?? '',
      tax: fields.tax?.value ?? '',
      invoiceNumber: fields.invoice_number?.value || '',
      phoneNumber: fields.phone_number?.value || '',
      currency: fields.currency?.value || '',
      categoryId: '',
      payment: '',
    });
    setOcrFields(fields);
    const url = URL.createObjectURL(pendingBill.file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [pendingBill, navigate]);
  useEffect(() => {
    if (!pendingBill) return undefined;
    const controller = new AbortController();
    getAccessToken()
      .then(token => token ? apiRequest('/api/bills/categories', token, { signal: controller.signal }) : [])
      .then(setBackendCategories)
      .catch(loadError => {
        if (loadError.name !== 'AbortError') setError(loadError.status === 401 ? 'Your session expired. Categories could not be loaded. You can still save without a category.' : 'Categories could not be loaded. You can still save without a category.');
      });
    return () => controller.abort();
  }, [pendingBill]);
  const update = event => setDetails(previous => ({ ...previous, [event.target.name]: event.target.value }));
  const save = async event => {
    event.preventDefault();
    if (!details?.merchant.trim() || !details.date || details.amount === '' || !details.currency) {
      setError('Merchant, date, total and currency are required to save this bill.');
      return;
    }
    setSaving(true);
    setError('');
    const payload = {
      merchant_name: details.merchant.trim(),
      bill_date: details.date,
      total_amount: String(details.amount).replace(/,/g, ''),
      currency: details.currency,
      bill_type: 'receipt',
      ...(details.categoryId ? { category_id: details.categoryId } : {}),
      ...(details.payment ? { payment_method: details.payment } : {}),
    };
    try {
      const token = await getAccessToken();
      if (!token) {
        setError('Bill saving is unavailable in the public demo.');
        return;
      }
      const saved = await apiRequest('/api/bills/', token, { method: 'POST', body: JSON.stringify(payload) });
      const categoryName = backendCategories.find(category => category.id === saved.category_id)?.name;
      setBills(previous => [toBillRow(saved, categoryName), ...previous]);
      setPendingBill(null);
      setToast('Confirmed bill saved to your account.');
      navigate('/bills');
    } catch (saveError) {
      setError(saveError.status === 401 ? 'Your session expired. The bill could not be saved. Your review remains available.' : saveError.message || 'The bill could not be saved. Your review remains available.');
    } finally {
      setSaving(false);
    }
  };
  if (!pendingBill || !result || !details) return null;
  const confidence = fieldName => {
    const field = ocrFields[fieldName];
    if (!field || field.value === null || field.value === '') return 'Not detected';
    const suffix = field.uncertain ? ' · Review' : '';
    return `${field.confidence_level} confidence${suffix}`;
  };
  return <div className="page"><PageIntro eyebrow="ONE LAST LOOK" title="Review your bill." description="Correct the detected fields. Nothing is saved until you confirm." actions={<span className="confidence-badge"><span /> OCR confidence is not a correctness guarantee</span>} />
    <div className="details-layout"><Panel className="details-preview"><div className="detail-preview-head"><span>UPLOADED IMAGE</span><button onClick={() => navigate('/privacy')}><Eye size={14} /> Privacy review</button></div>{previewUrl && <div className="privacy-image-preview bill-review-image"><img src={previewUrl} alt="Uploaded bill preview" /></div>}<div className="confidence-legend"><span>Classification: {result.classification?.label || 'unknown'} · {Math.round((result.classification?.confidence || 0) * 100)}%</span><span>{Number(result.processing_time_ms || 0).toFixed(0)} ms</span></div></Panel>
      <Panel className="details-form-panel"><div className="form-panel-title"><span className="panel-kicker">EXTRACTED DETAILS</span><h2>Does everything look right?</h2><p>Fields not detected are left empty.</p></div><form className="details-form" onSubmit={save}>
        <label>Merchant name<input name="merchant" value={details.merchant} placeholder="Enter merchant name" onChange={update} /><span className="field-confidence">{confidence('merchant_name')}</span></label>
        <div className="form-row"><label>Bill date<input name="date" type="date" value={details.date} onChange={update} /><span className="field-confidence">{confidence('bill_date')}</span></label><label>Total amount<input name="amount" inputMode="decimal" value={details.amount} placeholder="Enter total" onChange={update} /><span className="field-confidence">{confidence('total_amount')}</span></label></div>
        <div className="form-row"><label>Subtotal<input name="subtotal" inputMode="decimal" value={details.subtotal} placeholder="Not detected" onChange={update} /><span className="field-confidence">{confidence('subtotal')}</span></label><label>Tax / GST<input name="tax" inputMode="decimal" value={details.tax} placeholder="Not detected" onChange={update} /><span className="field-confidence">{confidence('tax')}</span></label></div>
        <div className="form-row"><label>Invoice number<input name="invoiceNumber" value={details.invoiceNumber} placeholder="Not detected" onChange={update} /><span className="field-confidence">{confidence('invoice_number')}</span></label><label>Phone number<input name="phoneNumber" value={details.phoneNumber} placeholder="Not detected" onChange={update} /><span className="field-confidence">{confidence('phone_number')}</span></label></div>
        <p className="field-storage-note">Subtotal, tax, invoice and phone values are shown from OCR but are not stored by the current bill API schema.</p>
        <div className="form-row"><label>Currency<select name="currency" value={details.currency} onChange={update}><option value="">Choose currency</option><option value="INR">INR · ₹</option><option value="USD">USD · $</option><option value="EUR">EUR · €</option><option value="GBP">GBP · £</option></select><span className="field-confidence">{confidence('currency')}</span></label><label>Expense category<select name="categoryId" value={details.categoryId} onChange={update}><option value="">Choose category</option>{backendCategories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label></div>
        <label>Payment method<select name="payment" value={details.payment} onChange={update}><option value="">Choose payment method</option><option>UPI</option><option>Credit card</option><option>Debit card</option><option>Cash</option><option>Other</option></select><span className="field-confidence">Not detected · choose manually</span></label>
        {result.warnings?.length > 0 && <div className="inline-warning"><Info size={15} />{result.warnings.join(' ')}</div>}
        {error && <div className="inline-warning" role="alert"><Info size={15} />{error}</div>}
        <div className="details-form-actions"><button type="button" className="button button-quiet" onClick={() => { setPendingBill(null); navigate('/scan'); }}>Cancel</button><Button type="submit" icon={Check} disabled={saving}>{saving ? 'Saving…' : 'Confirm & save bill'}</Button></div>
      </form></Panel></div>
  </div>;
}

function MyBills() {
  const { bills, setBills, setToast } = useApp();
  const navigate = useNavigate();
  const [params] = useState(() => new URLSearchParams(window.location.search));
  const [query, setQuery] = useState(params.get('search') || '');
  const [category, setCategory] = useState('All categories');
  const [dateFilter, setDateFilter] = useState('All dates');
  const [sort, setSort] = useState('Newest first');
  const [view, setView] = useState('grid');
  const [pageSize, setPageSize] = useState(9);
  const [menuBill, setMenuBill] = useState(null);
  const [selectedBill, setSelectedBill] = useState(null);
  const [deleteBill, setDeleteBill] = useState(null);
  const categoryOptions = useMemo(() => {
    const set = new Set(['Food & Dining', 'Shopping', 'Travel', 'Healthcare', 'Utilities', 'Others']);
    bills.forEach(b => { if (b.category) set.add(b.category); });
    return Array.from(set);
  }, [bills]);
  useEffect(() => setPageSize(9), [query, category, dateFilter, sort]);
  const visible = useMemo(() => {
    let rows = bills.filter(bill => {
      const date = new Date(bill.date);
      const matchesDate = dateFilter === 'All dates'
        || (dateFilter === 'November 2026' && date.getMonth() === 10 && date.getFullYear() === 2026)
        || (dateFilter === 'October 2026' && date.getMonth() === 9 && date.getFullYear() === 2026);
      return bill.merchant.toLowerCase().includes(query.toLowerCase())
        && (category === 'All categories' || bill.category === category)
        && matchesDate;
    });
    if (sort === 'Highest amount') rows = [...rows].sort((a, b) => b.amount - a.amount);
    else if (sort === 'Lowest amount') rows = [...rows].sort((a, b) => a.amount - b.amount);
    else rows = [...rows].sort((a, b) => new Date(b.date) - new Date(a.date));
    return rows;
  }, [bills, category, dateFilter, query, sort]);
  const remove = async () => {
    if (!deleteBill?.id) {
      setToast('This bill is missing its server ID and could not be deleted.');
      return;
    }
    try {
      const token = await getAccessToken();
      if (!token) throw new Error('Bill deletion is unavailable in the public demo.');
      await apiRequest(`/api/bills/${deleteBill.id}`, token, { method: 'DELETE' });
      setBills(previous => previous.filter(item => item.id !== deleteBill.id));
      setToast('Bill deleted from your account.');
      setDeleteBill(null);
    } catch (error) {
      setToast(error.status === 401 ? 'Your session expired; the bill could not be deleted.' : error.message || 'The bill could not be deleted.');
    }
  };
  return <div className="page">
    <PageIntro eyebrow="YOUR RECEIPTS, IN ONE PLACE" title="Your expense history." description="A clear picture of where each rupee goes." actions={<Button icon={Plus} onClick={() => navigate('/scan')}>Add a bill</Button>} />
    <Panel className="bills-toolbar"><div className="bill-search"><Search size={16} /><input placeholder="Search merchants…" value={query} onChange={event => setQuery(event.target.value)} /><kbd>⌘ K</kbd></div><span className="toolbar-divider" />
      <label className="filter-control"><Filter size={15} /><select aria-label="Filter by category" value={category} onChange={event => setCategory(event.target.value)}><option>All categories</option>{categoryOptions.map(catName => <option key={catName}>{catName}</option>)}</select><ChevronDown size={13} /></label>
      <label className="filter-control date-filter"><select aria-label="Filter by date" value={dateFilter} onChange={event => setDateFilter(event.target.value)}><option>All dates</option><option>November 2026</option><option>October 2026</option></select><ChevronDown size={13} /></label>
      <label className="filter-control sort-control"><SlidersHorizontal size={15} /><select aria-label="Sort bills" value={sort} onChange={event => setSort(event.target.value)}><option>Newest first</option><option>Highest amount</option><option>Lowest amount</option></select><ChevronDown size={13} /></label><span className="toolbar-divider view-divider" />
      <div className="view-toggle"><button className={view === 'grid' ? 'view-selected' : ''} onClick={() => setView('grid')} aria-label="Grid view"><Grid2X2 size={16} /></button><button className={view === 'list' ? 'view-selected' : ''} onClick={() => setView('list')} aria-label="List view"><List size={17} /></button></div>
    </Panel>
    <div className="bills-results-head"><span><strong>{visible.length}</strong> bills found</span><span>Showing {Math.min(pageSize, visible.length)} of {visible.length}</span></div>
    {visible.length ? <>
      <div className={`bill-grid ${view === 'list' ? 'bill-list' : ''}`}>{visible.slice(0, pageSize).map((bill, index) => <motion.article key={bill.id || `${bill.merchant}-${index}`} className="bill-card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(index * .025, .2) }}><div className="bill-thumb"><div className="thumb-paper"><span className="thumb-logo">{bill.merchant.slice(0, 1)}</span><i /><i /><i /><b /></div><button className="card-menu-trigger" aria-label={`Actions for ${bill.merchant}`} onClick={() => setMenuBill(menuBill === index ? null : index)}><MoreHorizontal size={17} /></button>{menuBill === index && <div className="card-menu"><button onClick={() => { setSelectedBill(bill); setMenuBill(null); }}>View details</button><button onClick={() => { setDeleteBill(bill); setMenuBill(null); }}>Delete bill</button></div>}</div><button className="bill-info" onClick={() => setSelectedBill(bill)}><span className="bill-info-top"><span className="merchant-icon small-merchant-icon" style={{ background: bill.color || '#222838' }}>{bill.icon || '◈'}</span><span><strong>{bill.merchant}</strong><small>{bill.date}</small></span></span><span className="bill-info-bottom"><span className="category-pill">{bill.category}</span><strong>{money(bill.amount, bill.currency)}</strong></span></button></motion.article>)}</div>
      {visible.length > pageSize && <div className="load-more"><Button variant="secondary" onClick={() => setPageSize(previous => previous + 9)}>Load more bills <ChevronDown size={14} /></Button></div>}
    </> : <div className="empty-state"><span><Receipt size={22} /></span><h2>No bills found</h2><p>Try a different search or category, or add your first bill.</p><Button icon={Plus} onClick={() => navigate('/scan')}>Scan a bill</Button></div>}
    {(selectedBill || deleteBill) && <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) { setSelectedBill(null); setDeleteBill(null); } }}><motion.div className="modal-card" initial={{ opacity: 0, scale: .96, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }}><button className="modal-close" onClick={() => { setSelectedBill(null); setDeleteBill(null); }}><X size={18} /></button>{selectedBill ? <><div className="modal-kicker">BILL DETAILS</div><div className="modal-merchant"><span className="merchant-icon" style={{ background: selectedBill.color || '#222838' }}>{selectedBill.icon || '◈'}</span><div><h2>{selectedBill.merchant}</h2><p>{selectedBill.date}</p></div></div><div className="modal-details"><span>Amount</span><strong>{money(selectedBill.amount, selectedBill.currency)}</strong><span>Category</span><strong>{selectedBill.category}</strong><span>Status</span><strong className="verified-status"><CheckCircle2 size={14} />{selectedBill.status || 'Saved'}</strong></div><Button className="modal-full-button" onClick={() => setSelectedBill(null)}>Done</Button></> : <><span className="delete-icon"><Trash2 size={19} /></span><div className="modal-kicker">REMOVE THIS BILL?</div><h2>Delete this receipt?</h2><p className="modal-copy">This will permanently remove the {deleteBill.merchant} bill from your account.</p><div className="modal-actions"><button className="button button-quiet" onClick={() => setDeleteBill(null)}>Keep bill</button><button className="button button-danger" onClick={remove}>Delete bill</button></div></>}</motion.div></div>}
  </div>;
}

function SpendingInsights() {
  const { bills } = useApp();
  const [range, setRange] = useState('Last 6 months');

  // ── derive real data from bills ──────────────────────────────────────────
  const now = new Date();
  const thisMonth = now.getMonth();
  const thisYear = now.getFullYear();
  const lastMonth = thisMonth === 0 ? 11 : thisMonth - 1;
  const lastMonthYear = thisMonth === 0 ? thisYear - 1 : thisYear;

  const billsThisMonth = useMemo(() => bills.filter(b => {
    const d = b.date ? new Date(b.date) : null;
    return d && d.getMonth() === thisMonth && d.getFullYear() === thisYear;
  }), [bills, thisMonth, thisYear]);

  const billsLastMonth = useMemo(() => bills.filter(b => {
    const d = b.date ? new Date(b.date) : null;
    return d && d.getMonth() === lastMonth && d.getFullYear() === lastMonthYear;
  }), [bills, lastMonth, lastMonthYear]);

  const totalThisMonth = useMemo(() => billsThisMonth.reduce((s, b) => s + (Number(b.amount) || 0), 0), [billsThisMonth]);
  const totalLastMonth = useMemo(() => billsLastMonth.reduce((s, b) => s + (Number(b.amount) || 0), 0), [billsLastMonth]);

  const monthPctChange = useMemo(() => {
    if (!totalLastMonth) return null;
    return ((totalThisMonth - totalLastMonth) / totalLastMonth) * 100;
  }, [totalThisMonth, totalLastMonth]);

  const daysInMonth = new Date(thisYear, thisMonth + 1, 0).getDate();
  const dailyAvg = totalThisMonth > 0 ? totalThisMonth / daysInMonth : 0;

  // Category totals from real bills
  const categoryTotals = useMemo(() => {
    const map = {};
    bills.forEach(b => {
      const cat = b.category || 'Uncategorised';
      map[cat] = (map[cat] || 0) + (Number(b.amount) || 0);
    });
    return Object.entries(map).sort((a, b) => b[1] - a[1]);
  }, [bills]);

  const topCategory = categoryTotals[0]?.[0] || null;
  const topCategoryAmt = categoryTotals[0]?.[1] || 0;
  const totalAll = useMemo(() => bills.reduce((s, b) => s + (Number(b.amount) || 0), 0), [bills]);
  const topCategoryPct = totalAll > 0 ? Math.round((topCategoryAmt / totalAll) * 100) : 0;

  // Merchant frequency
  const merchantCounts = useMemo(() => {
    const map = {};
    billsThisMonth.forEach(b => {
      const m = b.vendor || b.merchant || null;
      if (m) map[m] = (map[m] || 0) + 1;
    });
    return Object.entries(map).sort((a, b) => b[1] - a[1]);
  }, [billsThisMonth]);
  const topMerchant = merchantCounts[0]?.[0] || null;
  const topMerchantVisits = merchantCounts[0]?.[1] || 0;

  // Monthly chart data from real bills (last 6 months)
  const chartData = useMemo(() => {
    const months = [];
    for (let i = 5; i >= 0; i--) {
      const d = new Date(thisYear, thisMonth - i, 1);
      const mo = d.getMonth();
      const yr = d.getFullYear();
      const label = d.toLocaleString('en-IN', { month: 'short' });
      const amt = bills
        .filter(b => { const bd = b.date ? new Date(b.date) : null; return bd && bd.getMonth() === mo && bd.getFullYear() === yr; })
        .reduce((s, b) => s + (Number(b.amount) || 0), 0);
      months.push({ month: label, amount: amt });
    }
    return range === 'Last 30 days' ? months.slice(-1) : months;
  }, [bills, range, thisMonth, thisYear]);

  // Merchant chart data
  const merchantChartData = useMemo(() => {
    const map = {};
    billsThisMonth.forEach(b => {
      const m = b.vendor || b.merchant || null;
      if (m) map[m] = (map[m] || 0) + (Number(b.amount) || 0);
    });
    return Object.entries(map)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([merchant, amount]) => ({ merchant, amount }));
  }, [billsThisMonth]);

  // Category chart data for bottom panel
  const CATEGORY_COLORS = ['#A78BFA','#67E8F9','#FBBF24','#34D399','#FB7185','#64748B','#F97316','#06B6D4'];
  const categoryChartData = useMemo(() =>
    categoryTotals.slice(0, 8).map(([name, amount], i) => ({
      name, amount, color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
    }))
  , [categoryTotals]);

  const maxCategoryAmt = categoryChartData[0]?.amount || 1;

  const hasData = bills.length > 0;

  return <div className="page"><PageIntro eyebrow="THE BIGGER PICTURE" title="Understand your spending." description="A few patterns make the whole picture clearer." actions={<label className="select-button date-range"><span>◷</span><select value={range} onChange={event => setRange(event.target.value)}><option>Last 6 months</option><option>This year</option><option>Last 30 days</option></select><ChevronDown size={14} /></label>} />
    <div className="insight-stats">
      <div className="insight-stat"><span className="insight-stat-icon violet"><Wallet size={17} /></span><small>Total this month</small><strong>{hasData ? money(totalThisMonth) : '—'}</strong>
        {monthPctChange !== null ? <span className={`stat-sub ${monthPctChange < 0 ? 'good' : ''}`}>{monthPctChange < 0 ? <TrendingDown size={13} /> : <ArrowUpRight size={13} />} {Math.abs(monthPctChange).toFixed(1)}% vs last month</span> : <span className="stat-sub">No prior month data</span>}
      </div>
      <div className="insight-stat"><span className="insight-stat-icon cyan"><BarChart3 size={17} /></span><small>Daily average</small><strong>{hasData ? money(dailyAvg) : '—'}</strong><span className="stat-sub">Across {daysInMonth} days</span></div>
      <div className="insight-stat"><span className="insight-stat-icon amber"><ShoppingBag size={17} /></span><small>Top category</small><strong>{topCategory || '—'}</strong><span className="stat-sub">{topCategory ? `${topCategoryPct}% of your spending` : 'No bills yet'}</span></div>
      <div className="insight-stat"><span className="insight-stat-icon pink"><Activity size={17} /></span><small>Most active merchant</small><strong>{topMerchant || '—'}</strong><span className="stat-sub">{topMerchant ? `${topMerchantVisits} bill${topMerchantVisits !== 1 ? 's' : ''} this month` : 'No bills this month'}</span></div>
    </div>
    <div className="insights-chart-grid"><Panel className="trend-panel"><SectionHeading title="Monthly spending" subtitle="Your spend over time" action={<span className="chart-current-label"><i /> Total spend</span>} /><div className="insight-trend-chart"><Suspense fallback={<div className="chart-skeleton" />}><InsightsChart data={chartData} /></Suspense></div></Panel>
      <Panel className="merchant-chart-panel"><SectionHeading title="Where you shop" subtitle="Top merchants this month" /><div className="merchant-chart">{merchantChartData.length > 0 ? <Suspense fallback={<div className="chart-skeleton" />}><MerchantChart data={merchantChartData} /></Suspense> : <p style={{color:'#6b7280',fontSize:'11px',padding:'24px 0',textAlign:'center'}}>No merchant data for this month yet.</p>}</div></Panel></div>
    <div className="insights-bottom-grid"><Panel className="insight-category-panel"><SectionHeading title="Categories" subtitle="The details behind your spending" /><div className="insight-category-list">{categoryChartData.length > 0 ? categoryChartData.map(item => <div className="insight-category-row" key={item.name}><span className="insight-category-name"><i style={{ background: item.color }} />{item.name}</span><span className="category-bar"><i style={{ width: `${Math.round((item.amount / maxCategoryAmt) * 100)}%`, background: item.color }} /></span><span className="insight-category-amount">{money(item.amount)}</span></div>) : <p style={{color:'#6b7280',fontSize:'11px',padding:'16px 0'}}>Scan and save some bills to see your category breakdown.</p>}</div></Panel><div className="insight-right-stack">
      {hasData && monthPctChange !== null && monthPctChange > 10 && <div className="unusual-alert"><span className="alert-icon"><Zap size={17} /></span><div><span className="panel-kicker">A PATTERN TO NOTICE</span><h3>Spending is up this month.</h3><p>{money(totalThisMonth)} this month — {monthPctChange.toFixed(1)}% more than last month ({money(totalLastMonth)}).</p><button onClick={() => setRange('Last 30 days')}>Take a closer look <ArrowRight size={14} /></button></div></div>}
      <div className="insight-note"><span className="insight-note-icon"><Sparkles size={15} /></span><p>{hasData ? <><strong>Your bills, your numbers.</strong> All figures above are computed from your {bills.length} saved bill{bills.length !== 1 ? 's' : ''}. No sample data is used.</> : <><strong>No bills yet.</strong> Scan your first receipt and all insights will update automatically.</>}</p></div>
    </div></div>
  </div>;
}

const suggestedPrompts = ['How much did I spend this month?', 'Which category costs me the most?', 'Compare with last month', 'Show my top merchants'];

function buildAnswer(prompt, bills) {
  const normalized = prompt.toLowerCase();
  const now = new Date();
  const thisMonth = now.getMonth();
  const thisYear = now.getFullYear();
  const lastMonth = thisMonth === 0 ? 11 : thisMonth - 1;
  const lastMonthYear = thisMonth === 0 ? thisYear - 1 : thisYear;

  if (!bills || bills.length === 0) {
    return 'You haven\u2019t saved any bills yet. Scan your first receipt and I\u2019ll be able to give you real insights about your spending.';
  }

  const billsThis = bills.filter(b => { const d = b.date ? new Date(b.date) : null; return d && d.getMonth() === thisMonth && d.getFullYear() === thisYear; });
  const billsLast = bills.filter(b => { const d = b.date ? new Date(b.date) : null; return d && d.getMonth() === lastMonth && d.getFullYear() === lastMonthYear; });
  const totalThis = billsThis.reduce((s, b) => s + (Number(b.amount) || 0), 0);
  const totalLast = billsLast.reduce((s, b) => s + (Number(b.amount) || 0), 0);
  const thisMonthName = now.toLocaleString('en-IN', { month: 'long' });

  const catMap = {};
  bills.forEach(b => { const c = b.category || 'Uncategorised'; catMap[c] = (catMap[c] || 0) + (Number(b.amount) || 0); });
  const topCats = Object.entries(catMap).sort((a, b) => b[1] - a[1]);
  const topCat = topCats[0];

  const merchantMap = {};
  billsThis.forEach(b => { const m = b.vendor || b.merchant; if (m) merchantMap[m] = (merchantMap[m] || 0) + (Number(b.amount) || 0); });
  const topMerchants = Object.entries(merchantMap).sort((a, b) => b[1] - a[1]);

  const fmt = amt => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(amt);

  if (normalized.includes('this month') || normalized.includes('spend') || normalized.includes('total')) {
    if (billsThis.length === 0) return `No bills recorded for ${thisMonthName} yet. Add some receipts and I'll compute your totals.`;
    const days = new Date(thisYear, thisMonth + 1, 0).getDate();
    const change = totalLast > 0 ? ((totalThis - totalLast) / totalLast * 100).toFixed(1) : null;
    return `You\u2019ve spent ${fmt(totalThis)} across ${billsThis.length} bill${billsThis.length !== 1 ? 's' : ''} in ${thisMonthName}. That\u2019s about ${fmt(totalThis / days)} per day.${change ? ` That\u2019s ${change > 0 ? change + '% more' : Math.abs(change) + '% less'} than last month.` : ''}`;
  }

  if (normalized.includes('category') || normalized.includes('most') || normalized.includes('biggest')) {
    if (!topCat) return 'No category data yet. Make sure your bills have categories assigned when you save them.';
    const total = Object.values(catMap).reduce((s, v) => s + v, 0);
    const pct = total > 0 ? Math.round(topCat[1] / total * 100) : 0;
    return `Your biggest category is ${topCat[0]} at ${fmt(topCat[1])} — about ${pct}% of your total. ${topCats[1] ? `Next up is ${topCats[1][0]} at ${fmt(topCats[1][1])}.` : ''}`;
  }

  if (normalized.includes('last month') || normalized.includes('compare')) {
    if (totalLast === 0) return 'No bills from last month to compare against. Keep scanning receipts and comparisons will appear over time.';
    const diff = totalThis - totalLast;
    const pct = (Math.abs(diff) / totalLast * 100).toFixed(1);
    return `You spent ${fmt(totalThis)} this month vs ${fmt(totalLast)} last month — that\u2019s ${fmt(Math.abs(diff))} ${diff > 0 ? 'more' : 'less'} (${pct}% ${diff > 0 ? 'up' : 'down'}).`;
  }

  if (normalized.includes('merchant') || normalized.includes('shop') || normalized.includes('where') || normalized.includes('top')) {
    if (topMerchants.length === 0) return `No merchant data for ${thisMonthName} yet. Bills with a vendor name will appear here.`;
    const list = topMerchants.slice(0, 3).map(([m, a]) => `${m} (${fmt(a)})`).join(', ');
    return `Your top merchants this month are: ${list}.`;
  }

  const totalAll = bills.reduce((s, b) => s + (Number(b.amount) || 0), 0);
  return `You have ${bills.length} bill${bills.length !== 1 ? 's' : ''} saved, totalling ${fmt(totalAll)}. ${topCat ? `Your biggest category is ${topCat[0]} at ${fmt(topCat[1])}.` : ''} Ask me anything about your spending!`;
}

function AIChat() {
  const { bills } = useApp();
  const [messages, setMessages] = useState(() => readStorage('billsnap-chat', [{ from: 'assistant', text: 'Hi! I can help you make sense of your saved bills. What would you like to know?', time: 'Just now' }]));
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const endRef = useRef(null);
  useEffect(() => { localStorage.setItem('billsnap-chat', JSON.stringify(messages)); endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
  const send = prompt => {
    const text = (prompt || input).trim();
    if (!text || typing) return;
    setMessages(previous => [...previous, { from: 'user', text, time: 'Now' }]);
    setInput('');
    setTyping(true);
    window.setTimeout(() => { setMessages(previous => [...previous, { from: 'assistant', text: buildAnswer(text, bills), time: 'Just now' }]); setTyping(false); }, 700);
  };
  const clear = () => { const fresh = [{ from: 'assistant', text: 'Fresh start. What would you like to know about your spending?', time: 'Just now' }]; setMessages(fresh); localStorage.removeItem('billsnap-chat'); };
  const dateLabel = new Date().toLocaleString('en-IN', { month: 'long', year: 'numeric' });
  return <div className="page chat-page"><PageIntro eyebrow="A FRIENDLY VOICE FOR YOUR FINANCES" title="Meet your expense assistant." description="Ask a question. Get a clearer picture." actions={<button className="text-link clear-chat" onClick={clear}><Trash2 size={14} /> Clear conversation</button>} />
    <div className="chat-layout"><Panel className="chat-panel"><div className="chat-top"><span className="chat-agent-icon"><Sparkles size={17} /></span><span><strong>Bill Snap assistant</strong><small><i /> Here to help · {bills.length} bill{bills.length !== 1 ? 's' : ''} loaded</small></span></div><div className="chat-messages">{messages.map((message, index) => <div className={`chat-message ${message.from === 'user' ? 'message-user' : ''}`} key={`${message.time}-${index}`}><span className={`chat-message-avatar ${message.from === 'user' ? 'user-message-avatar' : ''}`}>{message.from === 'user' ? <User size={15} /> : <Sparkles size={15} />}</span><div className="message-body"><span className="message-author">{message.from === 'user' ? 'You' : 'Bill Snap'}<small>{message.time}</small></span><p>{message.text}</p>{message.from === 'assistant' && index > 0 && <div className="source-card"><span className="source-icon"><Receipt size={14} /></span><span><strong>Based on your bills</strong><small>{bills.length} saved bills · {dateLabel}</small></span><CheckCircle2 size={14} /></div>}</div></div>)}{typing && <div className="chat-message"><span className="chat-message-avatar"><Sparkles size={15} /></span><div className="typing-bubble"><i /><i /><i /></div></div>}<div ref={endRef} /></div><div className="chat-composer"><div className="composer-input"><input value={input} placeholder="Ask about your spending…" onChange={event => setInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') send(); }} /><button onClick={() => send()} disabled={!input.trim() || typing} aria-label="Send message"><Send size={17} /></button></div><span>Answers are computed from your saved bills. No external AI service is used.</span></div></Panel><aside className="chat-sidebar"><Panel className="suggestions-panel"><span className="panel-kicker">NOT SURE WHERE TO START?</span><h3>Try asking…</h3><div className="suggestion-list">{suggestedPrompts.map(prompt => <button key={prompt} onClick={() => send(prompt)}>{prompt}<ArrowUpRight size={14} /></button>)}</div></Panel><Panel className="chat-privacy-note"><ShieldCheck size={17} /><strong>Your numbers stay yours.</strong><p>This assistant reads only your saved bills from this session. No data leaves your device.</p></Panel></aside></div>
  </div>;
}

function SettingsPage() {
  const { preferences, setPreferences, bills, setToast, name, setName, email, setEmail, user } = useApp();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const navigate = useNavigate();
  const initials = getInitials(name, email);
  const update = (key, value) => setPreferences(previous => ({ ...previous, [key]: value }));
  const exportData = () => { const blob = new Blob([JSON.stringify({ bills, preferences }, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'bill-snap-account-data.json'; link.click(); URL.revokeObjectURL(url); setToast('Your account data export is ready.'); };
  const erase = () => { localStorage.removeItem('billsnap-chat'); setToast('Local assistant history cleared. Your server bills were not changed.'); setConfirmDelete(false); };

  const handleSignOut = async () => {
    if (supabase) {
      await supabase.auth.signOut();
      if (setName) setName('');
      if (setEmail) setEmail('');
      setToast('Signed out of your account.');
      navigate('/');
    }
  };

  return <div className="page settings-page"><PageIntro eyebrow="IT’S YOUR INFORMATION" title="Your account. Your control." description="The little details that make Bill Snap yours." />
    <div className="settings-layout"><div className="settings-main">
      <Panel className="settings-section">
        <SectionHeading title="User account" subtitle="Your profile and authentication details." />
        <div className="profile-edit">
          <span className="settings-avatar">{initials}</span>
          <div className="profile-inputs">
            <label>Your name<input value={name || ''} placeholder="Add your name" onChange={event => setName(event.target.value)} /></label>
            <label>Email address<input type="email" value={email || ''} placeholder="Your email address" readOnly /></label>
          </div>
        </div>
        <div style={{ marginTop: '16px', display: 'flex', gap: '12px' }}>
          {user ? (
            <Button variant="secondary" onClick={handleSignOut}>Sign out</Button>
          ) : (
            <Button onClick={() => navigate('/login')}>Sign in / Sign up</Button>
          )}
        </div>
      </Panel>
      <Panel className="settings-section"><SectionHeading title="Your preferences" subtitle="A few things to make it feel familiar." /><div className="preference-row"><span className="preference-icon"><Globe2 size={17} /></span><span className="preference-copy"><strong>Language</strong><small>Choose the language you’re most comfortable with.</small></span><select value={preferences.language} onChange={event => update('language', event.target.value)}><option>English</option><option>Hindi</option><option>Marathi</option></select></div><div className="preference-row"><span className="preference-icon"><Wallet size={17} /></span><span className="preference-copy"><strong>Currency</strong><small>Your expense amounts are shown in Indian rupees.</small></span><select value={preferences.currency} onChange={event => update('currency', event.target.value)}><option value="INR">INR · ₹</option></select></div><div className="preference-row"><span className="preference-icon"><Sparkles size={17} /></span><span className="preference-copy"><strong>Appearance</strong><small>Dark mode, easy on the eyes.</small></span><span className="theme-chip">Dark <span>DEFAULT</span></span></div></Panel>
      <Panel className="settings-section"><SectionHeading title="Privacy & security" subtitle="A little transparency goes a long way." /><div className="security-banner"><span><LockKeyhole size={17} /></span><div><strong>Private by design</strong><p>This is a frontend-only demo. It does not provide production encryption or secure redaction.</p></div></div><div className="preference-row"><span className="preference-icon"><Cloud size={17} /></span><span className="preference-copy"><strong>Cloud sync</strong><small>Demo toggle only. No data will be uploaded.</small></span><button role="switch" aria-checked={preferences.cloudSync} className={`toggle ${preferences.cloudSync ? 'toggle-on' : ''}`} onClick={() => update('cloudSync', !preferences.cloudSync)}><i /></button></div><div className="preference-row"><span className="preference-icon"><Eye size={17} /></span><span className="preference-copy"><strong>Privacy-first previews</strong><small>Show the privacy review before bill details.</small></span><button role="switch" aria-checked={preferences.privacyMode} className={`toggle ${preferences.privacyMode ? 'toggle-on' : ''}`} onClick={() => update('privacyMode', !preferences.privacyMode)}><i /></button></div></Panel>
    </div><aside className="settings-side">    <Panel className="data-panel"><span className="data-icon"><Download size={18} /></span><h3>Your data belongs to you.</h3><p>Download a copy of your saved bills and preferences.</p><Button variant="secondary" icon={Download} onClick={exportData}>Export account data</Button><div className="data-divider" /><button className="danger-link" onClick={() => { localStorage.removeItem('billsnap-chat'); setToast('Chat history cleared on this device.'); }}><Trash2 size={14} /> Clear chat history</button></Panel><Panel className="delete-panel"><span className="delete-panel-icon"><Trash2 size={17} /></span><h3>Clear assistant history</h3><p>Remove the assistant conversation stored in this browser. Server bills are not affected.</p><button onClick={() => setConfirmDelete(true)}>Clear chat history <ArrowRight size={14} /></button></Panel><div className="settings-footnote"><ShieldCheck size={15} /><span>Preferences and assistant history are stored in this browser.</span></div></aside></div>
    {confirmDelete && <div className="modal-backdrop"><motion.div className="modal-card" initial={{ opacity: 0, scale: .96 }} animate={{ opacity: 1, scale: 1 }}><button className="modal-close" onClick={() => setConfirmDelete(false)}><X size={18} /></button><span className="delete-icon"><Trash2 size={19} /></span><div className="modal-kicker">CLEAR LOCAL HISTORY</div><h2>Clear assistant history?</h2><p className="modal-copy">This removes only the assistant conversation on this device. Your saved bills are unchanged.</p><div className="modal-actions"><button className="button button-quiet" onClick={() => setConfirmDelete(false)}>Keep history</button><button className="button button-danger" onClick={erase}>Clear history</button></div></motion.div></div>}
  </div>;
}

export default function App() {
  return <BrowserRouter><AppProvider><Layout /></AppProvider></BrowserRouter>;
}
