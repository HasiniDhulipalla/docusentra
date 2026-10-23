import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, ArrowDownToLine, ArrowUpRight, BadgeCheck, Bell, Check, ChevronDown,
  CircleHelp, Clock3, FileLock2, FileText, FolderClosed, KeyRound, LayoutDashboard,
  LockKeyhole, LogOut, Plus, Search, Settings2, Shield, ShieldCheck, Share2, Trash2,
  UploadCloud, Users, X, Pencil, Eye, UserRound, Mail, AlertCircle, RefreshCw, Sun, Moon,
} from 'lucide-react';

const TOKEN_KEY = 'trustvault_access_token';
const THEME_KEY = 'trustvault_theme';
const DOCUMENT_CATEGORIES = ['HR', 'Finance', 'Legal', 'Personal', 'Education', 'General', 'Others'];
const LEGACY_CATEGORIES = ['Security', 'Contracts', 'Engineering', 'Customer', 'Policy'];
// Use a same-origin /api path locally; in Vercel builds point to the separately hosted API origin.
// Set VITE_API_BASE_URL to e.g. https://docusentra-api.onrender.com (origin only, no /api suffix).
const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '');
const API = `${API_ORIGIN}/api`;

async function apiRequest(path, { token, ...options } = {}) {
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(`${API}${path}`, { ...options, headers });
  if (response.status === 204) {
    if (!response.ok) throw new Error('Request failed');
    return null;
  }
  const type = response.headers.get('content-type') || '';
  const body = type.includes('application/json') ? await response.json().catch(() => ({})) : null;
  if (!response.ok) throw new Error(body?.detail || `Request failed (${response.status})`);
  return body;
}

function prettyBytes(value = 0) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function prettyDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date);
}

function initials(username = '') {
  return username.split(/[._ -]/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('') || 'U';
}

const actionLabel = {
  ACCOUNT_CREATED: 'Account created', LOGIN: 'Signed in', DOCUMENT_UPLOADED: 'Document uploaded',
  DOCUMENT_DOWNLOADED: 'Document downloaded', DOCUMENT_PREVIEWED: 'Document previewed', DOCUMENT_PREVIEW_CONTENT_OPENED: 'Preview content opened', DOCUMENT_RENAMED: 'Document renamed',
  DOCUMENT_DELETED: 'Document deleted', ACCESS_GRANTED: 'Access granted',
  ACCESS_REVOKED: 'Access revoked', PERMISSION_UPDATED: 'Permission updated',
  ACCESS_DENIED: 'Access request denied', ADMIN_ACCESS_DENIED: 'Admin access denied',
  USER_ROLE_CHANGED: 'Account role changed', DEMO_ACCOUNT_SEEDED: 'Demo account created',
  PASSWORD_CHANGED: 'Password changed', PASSWORD_CHANGE_FAILED: 'Password change rejected',
};

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  async function submit(event) {
    event.preventDefault(); setError(''); setSuccess(''); setBusy(true);
    try {
      const payload = mode === 'register'
        ? { username: username.trim(), email: email.trim(), password }
        : { identifier: identifier.trim(), password };
      const result = await apiRequest(`/auth/${mode === 'register' ? 'register' : 'login'}`, {
        method: 'POST', body: JSON.stringify(payload),
      });
      if (mode === 'register') {
        // Account creation and sign-in are separate actions: do not store the registration token.
        setIdentifier(username.trim());
        setPassword(''); setUsername(''); setEmail('');
        setMode('login');
        setSuccess('Account created successfully. Sign in with your new username/email and password.');
        return;
      }
      localStorage.setItem(TOKEN_KEY, result.access_token);
      setSuccess('');
      onAuthenticated(result.user, result.access_token);
    } catch (err) { setError(err.message || 'Unable to sign in.'); }
    finally { setBusy(false); }
  }

  return <div className="auth-page">
    <div className="auth-decoration decor-one" /><div className="auth-decoration decor-two" />
    <div className="auth-brand"><div className="brand-icon"><ShieldCheck size={23} strokeWidth={2.15} /></div><div><div className="brand-name">docusentra<span>.</span></div><div className="brand-caption">SECURE WORKSPACE</div></div></div>
    <div className="auth-layout">
      <section className="auth-intro">
        <div className="eyebrow"><span className="eyebrow-line" /> DOCUMENT SECURITY, SIMPLIFIED</div>
        <h1>Your documents.<br /><span>Your rules.</span></h1>
        <p>Share confidential files with the right people, keep control of access, and see every important action in one secure workspace.</p>
        <div className="auth-points">
          <div><span><ShieldCheck size={18} /></span><div><b>Permission checks on every request</b><small>Access is verified by the server, not just the interface.</small></div></div>
          <div><span><Users size={18} /></span><div><b>Share with selected people</b><small>Give read or edit access, then revoke it whenever needed.</small></div></div>
          <div><span><Activity size={18} /></span><div><b>Accountable activity history</b><small>Uploads, downloads, permission changes and denials are logged.</small></div></div>
        </div>
      </section>
      <section className="auth-card">
        <div className="auth-card-heading"><div className="mini-lock"><LockKeyhole size={19} /></div><h2>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h2><p>{mode === 'login' ? 'Sign in to your private workspace.' : 'Set up an account to start sharing securely.'}</p></div>
        <div className="auth-tabs"><button className={mode === 'login' ? 'selected' : ''} onClick={() => { setMode('login'); setError(''); setSuccess(''); }}>Sign in</button><button className={mode === 'register' ? 'selected' : ''} onClick={() => { setMode('register'); setError(''); setSuccess(''); }}>Create account</button></div>
        <form onSubmit={submit} className="auth-form">
          {mode === 'register' ? <><label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="e.g. jordan.davis" minLength={3} maxLength={32} autoComplete="username" required /></label><label>Email address<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" required /></label></> : <label>Username or email<input value={identifier} onChange={(e) => setIdentifier(e.target.value)} placeholder="Enter username or email" autoComplete="username" required /></label>}
          <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={mode === 'register' ? 'At least 12 characters' : 'Enter your password'} minLength={mode === 'register' ? 12 : 1} maxLength={128} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} required /></label>
          {success && <div className="form-success"><Check size={16} />{success}</div>}
          {error && <div className="form-error"><AlertCircle size={16} />{error}</div>}
          <button className="primary-button auth-submit" type="submit" disabled={busy}>{busy ? <RefreshCw size={17} className="spin" /> : <LockKeyhole size={17} />}{busy ? 'Please wait…' : mode === 'login' ? 'Sign in securely' : 'Create account'}<ArrowUpRight size={16} /></button>
        </form>
        <p className="auth-footnote"><ShieldCheck size={14} /> Private by default. No public document links.</p>
      </section>
    </div>
    <div className="auth-bottom"><span>© {new Date().getFullYear()} DocuSentra</span><span><LockKeyhole size={13} /> Secure document sharing</span><span>Local development MVP</span></div>
  </div>;
}

function Modal({ title, subtitle, onClose, children, width = '520px', wide = false }) {
  useEffect(() => {
    function onKey(event) { if (event.key === 'Escape') onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={`modal-card${wide ? ' modal-preview-card' : ''}`} style={{ maxWidth: wide ? 'none' : width }} role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal-head"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={19} /></button></div>
      {children}
    </section>
  </div>;
}


function ProtectedPreviewPage({ documentId, pageNumber, token }) {
  const containerRef = useRef(null);
  const [source, setSource] = useState('');
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    let active = true;
    let objectUrl = '';
    let observer;
    const controller = new AbortController();

    async function loadPage() {
      try {
        const response = await fetch(`${API}/documents/${documentId}/preview-pages/${pageNumber}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
          cache: 'no-store',
        });
        if (!response.ok) {
          const details = await response.json().catch(() => ({}));
          throw new Error(details.detail || `Page ${pageNumber} could not be loaded.`);
        }
        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        if (active) setSource(objectUrl);
        else URL.revokeObjectURL(objectUrl);
      } catch (error) {
        if (active && error.name !== 'AbortError') setLoadError(error.message || 'Page could not be loaded.');
      }
    }

    const node = containerRef.current;
    if (node && 'IntersectionObserver' in window) {
      observer = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer?.disconnect();
          loadPage();
        }
      }, { rootMargin: '700px 0px' });
      observer.observe(node);
    } else {
      loadPage();
    }

    return () => {
      active = false;
      controller.abort();
      observer?.disconnect();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId, pageNumber, token]);

  return <div
    ref={containerRef}
    className="preview-page-shell preview-protected-surface"
    aria-label={`Read-only page ${pageNumber}`}
    onContextMenu={(event) => event.preventDefault()}
    onDragStart={(event) => event.preventDefault()}
  >
    {source ? <img src={source} alt={`Preview page ${pageNumber}`} draggable="false" /> : loadError ? <div className="preview-page-error">{loadError}</div> : <div className="preview-page-loading">Preparing secure page {pageNumber}…</div>}
    <span className="preview-page-number" aria-hidden="true">Page {pageNumber}</span>
  </div>;
}


function AdminConsole({ token, currentUserId, notify }) {
  const [overview, setOverview] = useState(null);
  const [users, setUsers] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [events, setEvents] = useState([]);
  const [actionFilter, setActionFilter] = useState('');
  const [actorFilter, setActorFilter] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [loading, setLoading] = useState(true);
  const [busyRoleId, setBusyRoleId] = useState(null);
  const [error, setError] = useState('');

  const loadAdmin = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [summary, accountRows, grants, auditRows] = await Promise.all([
        apiRequest('/admin/overview', { token }),
        apiRequest('/admin/users', { token }),
        apiRequest('/admin/permissions', { token }),
        apiRequest('/admin/activity?limit=300', { token }),
      ]);
      setOverview(summary); setUsers(accountRows); setPermissions(grants); setEvents(auditRows);
    } catch (err) { setError(err.message || 'Unable to load administrator console.'); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { loadAdmin(); }, [loadAdmin]);

  async function applyEventFilters(event) {
    event.preventDefault();
    const params = new URLSearchParams({ limit: '300' });
    if (actionFilter.trim()) params.set('action', actionFilter.trim().toUpperCase());
    if (actorFilter.trim()) params.set('actor', actorFilter.trim());
    if (fromDate) params.set('from_date', fromDate);
    if (toDate) params.set('to_date', toDate);
    try { setEvents(await apiRequest(`/admin/activity?${params.toString()}`, { token })); }
    catch (err) { notify(err.message || 'Audit filter failed.', 'error'); }
  }

  async function changeRole(target, nextRole) {
    if (target.system_role === nextRole) return;
    setBusyRoleId(target.id);
    try {
      const updated = await apiRequest(`/admin/users/${target.id}/role`, {
        token, method: 'PATCH', body: JSON.stringify({ system_role: nextRole }),
      });
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      notify(`@${updated.username} is now ${updated.system_role}.`);
      const [summary, auditRows] = await Promise.all([
        apiRequest('/admin/overview', { token }), apiRequest('/admin/activity?limit=300', { token }),
      ]);
      setOverview(summary); setEvents(auditRows);
    } catch (err) { notify(err.message || 'Role change failed.', 'error'); }
    finally { setBusyRoleId(null); }
  }

  async function verifyChain() {
    try {
      const result = await apiRequest('/admin/audit/verify', { token });
      setOverview((current) => current ? { ...current, audit_valid: result.valid, audit_events_checked: result.events_checked } : current);
      notify(result.valid ? `Audit chain valid: ${result.events_checked} events checked.` : `Audit integrity failure at event ${result.failed_event_id ?? 'head'}.`, result.valid ? 'success' : 'error');
    } catch (err) { notify(err.message || 'Audit verification failed.', 'error'); }
  }

  return <section className="admin-console">
    <div className="panel-heading admin-heading"><div><h2>Administrator console</h2><p>Global activity and permission visibility. Admin does not bypass document content grants.</p></div><button className="secondary-button" onClick={loadAdmin}><RefreshCw size={15} /> Refresh</button></div>
    {error && <div className="form-error"><AlertCircle size={16} />{error}</div>}
    {loading && !overview ? <div className="panel-loading"><RefreshCw className="spin" size={19} /> Loading administrator data…</div> : <>
      <div className="admin-stats">
        {[['Accounts', overview?.users ?? 0], ['Active documents', overview?.active_documents ?? 0], ['Active grants', overview?.active_grants ?? 0], ['Audit events', overview?.audit_events ?? 0], ['Denied attempts', overview?.denied_events ?? 0]].map(([label, value]) => <div className="stat-card" key={label}><div className="stat-top"><span>{label}</span><div className="stat-icon stat-blue"><Activity size={17} /></div></div><div className="stat-number">{value}</div></div>)}
      </div>
      <div className={`audit-integrity-card ${overview?.audit_valid ? 'audit-valid' : 'audit-invalid'}`}><div><b>{overview?.audit_valid ? 'Audit chain verified' : 'Audit integrity needs attention'}</b><p>{overview?.audit_events_checked ?? 0} chained events checked. The database blocks normal UPDATE/DELETE operations on audit rows.</p></div><button className="secondary-button" onClick={verifyChain}><ShieldCheck size={15} /> Verify now</button></div>

      <div className="panel admin-panel"><div className="panel-heading"><div><h2>Accounts & roles</h2><p>Account roles are different from per-document Reader/Editor grants.</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>ACCOUNT</th><th>EMAIL</th><th>SYSTEM ROLE</th><th>CREATED</th></tr></thead><tbody>{users.map((account) => <tr key={account.id}><td><b>{account.username}{account.id === currentUserId ? ' (you)' : ''}</b></td><td>{account.email}</td><td><select aria-label={`Role for ${account.username}`} className="admin-role-select" value={account.system_role} disabled={busyRoleId === account.id || account.id === currentUserId} onChange={(e) => changeRole(account, e.target.value)}><option value="admin">Administrator</option><option value="owner">Document owner</option><option value="viewer">Viewer</option></select></td><td>{prettyDate(account.created_at)}</td></tr>)}</tbody></table></div>
      </div>

      <div className="panel admin-panel"><div className="panel-heading"><div><h2>Active permissions</h2><p>Current named-user grants, including who granted access.</p></div></div>
        {permissions.length === 0 ? <div className="empty-state"><h3>No active document grants</h3></div> : <div className="table-wrap"><table><thead><tr><th>DOCUMENT</th><th>OWNER</th><th>GRANTEE</th><th>PERMISSION</th><th>GRANTED BY</th></tr></thead><tbody>{permissions.map((grant) => <tr key={grant.share_id}><td><b>{grant.document_name}</b><span className="admin-cell-sub">{grant.category}</span></td><td>@{grant.owner_username}</td><td>{grant.username}<span className="admin-cell-sub">{grant.email}</span></td><td><span className={`role-tag ${grant.permission}`}>{grant.permission}</span></td><td>@{grant.granted_by}</td></tr>)}</tbody></table></div>}
      </div>

      <div className="panel admin-panel"><div className="panel-heading"><div><h2>Global audit trail</h2><p>Denied attempts remain visible here; ordinary users do not receive another document's metadata.</p></div></div>
        <form className="admin-filter-form" onSubmit={applyEventFilters}><label>Action<input value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} placeholder="ACCESS_DENIED" /></label><label>Actor<input value={actorFilter} onChange={(e) => setActorFilter(e.target.value)} placeholder="username" /></label><label>From<input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} /></label><label>To<input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} /></label><button className="primary-button" type="submit"><Search size={15} /> Filter</button></form>
        {events.length === 0 ? <div className="empty-state"><h3>No audit events match those filters.</h3></div> : <div className="activity-table">{events.map((event) => <div className="activity-row" key={event.id}><div className={`activity-symbol ${event.action.includes('DENIED') ? 'activity-block' : event.action.includes('ACCESS') || event.action.includes('PERMISSION') ? 'activity-share' : 'activity-upload'}`}><Activity size={15} /></div><div className="activity-row-copy"><b>{actionLabel[event.action] || event.action}</b><p>{event.document_name || event.document_ref || 'Account/system event'}{event.target_username ? ` · @${event.target_username}` : ''} — {event.details}</p><span><Clock3 size={12} /> {prettyDate(event.created_at)} · @{event.actor_username} · hash {String(event.event_hash || '').slice(0, 12)}…</span></div><span className={`activity-status ${event.action.includes('DENIED') ? 'blocked' : 'recorded'}`}>{event.action.includes('DENIED') ? 'Blocked' : 'Recorded'}</span></div>)}</div>}
      </div>
    </>}
  </section>;
}

function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '');
  const [user, setUser] = useState(null);
  const [authChecking, setAuthChecking] = useState(Boolean(localStorage.getItem(TOKEN_KEY)));
  const [activeNav, setActiveNav] = useState('Overview');
  const [categoriesOpen, setCategoriesOpen] = useState(false);
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'; } catch { return 'light'; } });
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [activity, setActivity] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [categoryMotion, setCategoryMotion] = useState(-1);
  const [fromDateFilter, setFromDateFilter] = useState('');
  const [toDateFilter, setToDateFilter] = useState('');
  const [serverSearchResults, setServerSearchResults] = useState(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [shares, setShares] = useState([]);
  const [shareInput, setShareInput] = useState('');
  const [shareRole, setShareRole] = useState('reader');
  const [shareBusy, setShareBusy] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadCategory, setUploadCategory] = useState('General');
  const [busy, setBusy] = useState(false);
  const [renameTitle, setRenameTitle] = useState('');
  const [previewBlocks, setPreviewBlocks] = useState([]);
  const [previewType, setPreviewType] = useState('blocks');
  const [previewPageCount, setPreviewPageCount] = useState(0);
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');

  useEffect(() => {
    if (!previewUrl) return undefined;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);


  useEffect(() => {
    if (modal !== 'preview') return undefined;
    const stopBrowserAction = (event) => {
      event.preventDefault();
      event.stopPropagation();
    };
    const stopRestrictedKeys = (event) => {
      const key = String(event.key || '').toLowerCase();
      const modifier = event.ctrlKey || event.metaKey;
      const blockedCombos = modifier && ['c', 'x', 's', 'p', 'a', 'u'].includes(key);
      if (key === 'printscreen' || blockedCombos) stopBrowserAction(event);
    };
    document.addEventListener('contextmenu', stopBrowserAction, true);
    document.addEventListener('copy', stopBrowserAction, true);
    document.addEventListener('cut', stopBrowserAction, true);
    document.addEventListener('dragstart', stopBrowserAction, true);
    document.addEventListener('selectstart', stopBrowserAction, true);
    document.addEventListener('keydown', stopRestrictedKeys, true);
    return () => {
      document.removeEventListener('contextmenu', stopBrowserAction, true);
      document.removeEventListener('copy', stopBrowserAction, true);
      document.removeEventListener('cut', stopBrowserAction, true);
      document.removeEventListener('dragstart', stopBrowserAction, true);
      document.removeEventListener('selectstart', stopBrowserAction, true);
      document.removeEventListener('keydown', stopRestrictedKeys, true);
    };
  }, [modal]);

  useEffect(() => {
    try { localStorage.setItem(THEME_KEY, theme); } catch { /* storage can be disabled */ }
    document.documentElement.dataset.trustvaultTheme = theme;
  }, [theme]);

  const notify = useCallback((message, type = 'success') => {
    setNotice({ message, type });
    window.setTimeout(() => setNotice(null), 4500);
  }, []);

  const loadWorkspace = useCallback(async (accessToken = token) => {
    setLoading(true);
    try {
      const [docs, events] = await Promise.all([
        apiRequest('/documents', { token: accessToken }),
        apiRequest('/activity?limit=100', { token: accessToken }),
      ]);
      setDocuments(docs); setActivity(events);
    } catch (error) {
      notify(error.message || 'Could not load workspace.', 'error');
      if (/session|sign in|expired/i.test(error.message)) signOut();
    } finally { setLoading(false); }
  }, [token, notify]);

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY); setToken(''); setUser(null); setDocuments([]); setActivity([]); setModal(null); setSelectedDoc(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const current = localStorage.getItem(TOKEN_KEY);
    if (!current) { setAuthChecking(false); return; }
    apiRequest('/auth/me', { token: current }).then((foundUser) => {
      if (cancelled) return;
      setToken(current); setUser(foundUser); setAuthChecking(false);
    }).catch(() => {
      if (!cancelled) { localStorage.removeItem(TOKEN_KEY); setToken(''); setAuthChecking(false); }
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => { if (user && token) loadWorkspace(token); }, [user, token, loadWorkspace]);

  function onAuthenticated(nextUser, nextToken) { setToken(nextToken); setUser(nextUser); }

  const owned = documents.filter((doc) => doc.is_owner);
  const shared = documents.filter((doc) => !doc.is_owner);
  const activeCategory = activeNav.startsWith('Category: ') ? activeNav.slice('Category: '.length) : '';
  const categoryCounts = useMemo(() => {
    const counts = Object.fromEntries(DOCUMENT_CATEGORIES.map((category) => [category, 0]));
    documents.forEach((doc) => {
      const documentCategory = DOCUMENT_CATEGORIES.find((category) => category.toLowerCase() === String(doc.category || 'General').toLowerCase());
      if (documentCategory) counts[documentCategory] += 1;
    });
    return counts;
  }, [documents]);
  const peopleWithAccess = useMemo(() => new Set(shares.map((share) => share.user_id)).size, [shares]);
  const visibleDocs = useMemo(() => {
    let items = serverSearchResults ?? documents;
    if (activeNav === 'My documents') items = items.filter((doc) => doc.is_owner);
    if (activeNav === 'Shared with me') items = items.filter((doc) => !doc.is_owner);
    if (activeCategory) items = items.filter((doc) => (doc.category || 'General').toLowerCase() === activeCategory.toLowerCase());
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter((doc) => `${doc.filename} ${doc.owner_username} ${doc.access_role} ${doc.category || ''}`.toLowerCase().includes(term));
    }
    return items;
  }, [documents, serverSearchResults, activeNav, activeCategory, searchTerm]);
  // Overview is a dashboard snapshot; document management pages show the full result set.
  const displayDocs = activeNav === 'Overview' ? visibleDocs.slice(0, 5) : visibleDocs;

  async function changePassword(event) {
    event.preventDefault();
    if (newPassword !== confirmPassword) { notify('New password and confirmation do not match.', 'error'); return; }
    if (newPassword.length < 12) { notify('New password must contain at least 12 characters.', 'error'); return; }
    setPasswordBusy(true);
    try {
      const result = await apiRequest('/auth/change-password', {
        token, method: 'POST',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword('');
      notify(result.message || 'Password changed successfully.');
    } catch (error) { notify(error.message || 'Password change failed.', 'error'); }
    finally { setPasswordBusy(false); }
  }

  async function refresh() { await loadWorkspace(token); }

  async function applyDocumentFilters(event) {
    event.preventDefault();
    const params = new URLSearchParams();
    if (searchTerm.trim()) params.set('q', searchTerm.trim());
    if (ownerFilter.trim()) params.set('owner', ownerFilter.trim());
    if (categoryFilter) params.set('category', categoryFilter);
    if (fromDateFilter) params.set('from_date', fromDateFilter);
    if (toDateFilter) params.set('to_date', toDateFilter);
    setSearchBusy(true);
    try {
      const result = await apiRequest(`/documents${params.size ? `?${params.toString()}` : ''}`, { token });
      setServerSearchResults(result);
      notify(`Search returned ${result.length} authorized document${result.length === 1 ? '' : 's'}.`);
    } catch (error) { notify(error.message || 'Document search failed.', 'error'); }
    finally { setSearchBusy(false); }
  }

  function clearDocumentFilters() {
    setOwnerFilter(''); setCategoryFilter(activeCategory || ''); setFromDateFilter(''); setToDateFilter(''); setSearchTerm(''); setServerSearchResults(null);
  }

  async function doUpload(event) {
    event.preventDefault();
    if (!uploadFile) { notify('Choose a file to upload.', 'error'); return; }
    if (uploadFile.size > 15 * 1024 * 1024) { notify('File must be 15 MB or smaller.', 'error'); return; }
    const form = new FormData(); form.append('file', uploadFile); if (uploadTitle.trim()) form.append('title', uploadTitle.trim()); form.append('category', uploadCategory);
    setBusy(true);
    try {
      await apiRequest('/documents', { token, method: 'POST', body: form });
      setModal(null); setUploadFile(null); setUploadTitle(''); setUploadCategory('General'); setServerSearchResults(null); setActiveNav('My documents'); await refresh(); notify('Document uploaded to private storage.');
    } catch (error) { notify(error.message || 'Upload failed.', 'error'); }
    finally { setBusy(false); }
  }

  async function downloadDoc(doc) {
    try {
      const response = await fetch(`${API}/documents/${doc.id}/download`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.detail || 'Download failed.'); }
      const blob = await response.blob(); const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = doc.filename; document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
      await loadWorkspace(token); notify('Download authorized and recorded.');
    } catch (error) { notify(error.message, 'error'); }
  }

  async function openPreview(doc) {
    setSelectedDoc(doc); setPreviewBlocks([]); setPreviewType('blocks'); setPreviewPageCount(0); setPreviewUrl(''); setPreviewError(''); setPreviewLoading(true); setModal('preview');
    try {
      const result = await apiRequest(`/documents/${doc.id}/preview`, { token });
      setPreviewType(result.preview_type || 'blocks');
      setPreviewPageCount(Number(result.page_count) || 0);
      setPreviewBlocks(result.blocks || []);
      if (result.preview_type === 'image') {
        const response = await fetch(`${API}/documents/${doc.id}/preview-content`, { headers: { Authorization: `Bearer ${token}` } });
        if (!response.ok) {
          const details = await response.json().catch(() => ({}));
          throw new Error(details.detail || `Preview failed (${response.status}).`);
        }
        const previewBlob = await response.blob();
        setPreviewUrl(URL.createObjectURL(previewBlob));
      }
      await loadWorkspace(token);
    } catch (error) {
      setPreviewError(error.message || 'This document could not be previewed.');
    } finally { setPreviewLoading(false); }
  }

  async function openShares(doc) {
    setSelectedDoc(doc); setShares([]); setShareInput(''); setShareRole('reader'); setModal('shares');
    try { setShares(await apiRequest(`/documents/${doc.id}/shares`, { token })); }
    catch (error) { notify(error.message || 'Unable to load permissions.', 'error'); }
  }

  async function grantAccess(event) {
    event.preventDefault(); if (!selectedDoc || !shareInput.trim()) return;
    setShareBusy(true);
    try {
      const share = await apiRequest(`/documents/${selectedDoc.id}/shares`, { token, method: 'POST', body: JSON.stringify({ user_identifier: shareInput.trim(), role: shareRole }) });
      setShares((current) => [...current.filter((item) => item.id !== share.id), share].sort((a, b) => a.username.localeCompare(b.username)));
      setShareInput(''); await refresh(); notify(`Access set for @${share.username}.`);
    } catch (error) { notify(error.message || 'Unable to grant access.', 'error'); }
    finally { setShareBusy(false); }
  }

  async function revokeAccess(share) {
    if (!selectedDoc || !window.confirm(`Revoke ${share.role} access for @${share.username}?`)) return;
    try {
      await apiRequest(`/documents/${selectedDoc.id}/shares/${share.id}`, { token, method: 'DELETE' });
      setShares((current) => current.filter((item) => item.id !== share.id)); await refresh(); notify(`Access revoked for @${share.username}.`);
    } catch (error) { notify(error.message || 'Unable to revoke access.', 'error'); }
  }

  async function doRename(event) {
    event.preventDefault(); if (!selectedDoc || !renameTitle.trim()) return;
    setBusy(true);
    try {
      await apiRequest(`/documents/${selectedDoc.id}`, { token, method: 'PATCH', body: JSON.stringify({ filename: renameTitle.trim() }) });
      setModal(null); await refresh(); notify('Document name updated.');
    } catch (error) { notify(error.message || 'Rename failed.', 'error'); }
    finally { setBusy(false); }
  }

  async function deleteDoc(doc) {
    if (!window.confirm(`Permanently delete “${doc.filename}”? This removes the stored file and all current sharing permissions.`)) return;
    try { await apiRequest(`/documents/${doc.id}`, { token, method: 'DELETE' }); await refresh(); notify('Document and its current access permissions deleted.'); }
    catch (error) { notify(error.message || 'Delete failed.', 'error'); }
  }

  if (authChecking) return <div className="loading-screen"><div className="brand-icon"><ShieldCheck size={23} strokeWidth={2.15} /></div><span>Checking your secure session…</span></div>;
  if (!user || !token) return <AuthScreen onAuthenticated={onAuthenticated} />;

  const navItems = [
    { group: 'WORKSPACE', items: [
      { name: 'Overview', label: 'Overview', icon: LayoutDashboard }, { name: 'My documents', label: 'My documents', icon: FolderClosed },
      { name: 'Shared with me', label: 'Shared with me', icon: Share2 },
    ] },
    { group: 'DOCUMENT CATEGORIES', items: [] },
    { group: 'ACCOUNT', items: [
      { name: 'Activity history', label: 'Activity history', icon: Activity }, { name: 'Settings', label: 'Settings', icon: Settings2 },
    ] },
  ];
  if (user.system_role === 'admin') navItems.push({ group: 'ADMINISTRATION', items: [{ name: 'Admin console', label: 'Admin console', icon: ShieldCheck }] });

  return <div className="app-shell" data-theme={theme}>
    <aside className="sidebar">
      <div className="brand-row"><div className="brand-icon"><ShieldCheck size={23} strokeWidth={2.15} /></div><div><div className="brand-name">docusentra<span>.</span></div><div className="brand-caption">SECURE WORKSPACE</div></div></div>
      <div className="workspace-switch"><span className="workspace-avatar">{initials(user.username)}</span><span className="workspace-copy"><b>{user.username}'s workspace</b><small>Private workspace</small></span><ChevronDown size={15} /></div>
      {user.system_role !== 'viewer' && <button className="new-document" onClick={() => { setUploadFile(null); setUploadTitle(''); setUploadCategory(activeCategory || 'General'); setModal('upload'); }}><Plus size={17} /> New document <span>＋</span></button>}
      {navItems.map((group) => group.group === 'DOCUMENT CATEGORIES' ? <div className="nav-group category-nav-group" key={group.group}>
        <button className={`nav-item category-parent ${categoriesOpen ? 'expanded' : ''} ${activeCategory ? 'has-active-category' : ''}`} type="button" aria-expanded={categoriesOpen} aria-controls="document-category-subnav" onClick={() => setCategoriesOpen((open) => !open)}>
          <FolderClosed size={17} strokeWidth={1.8} /><span>Document Categories</span><ChevronDown className={`category-chevron ${categoriesOpen ? 'rotated' : ''}`} size={15} />
        </button>
        {categoriesOpen && <div className="category-subnav" id="document-category-subnav">
          {DOCUMENT_CATEGORIES.map((category) => {
            const name = `Category: ${category}`;
            const count = categoryCounts[category] || 0;
            return <button key={name} title={`${category}, ${count} ${count === 1 ? 'document' : 'documents'}`} className={`nav-item category-nav-item ${activeNav === name ? 'active' : ''}`} onClick={() => { setActiveNav(name); setCategoriesOpen(true); setSearchTerm(''); setServerSearchResults(null); setCategoryFilter(category); setOwnerFilter(''); setFromDateFilter(''); setToDateFilter(''); }}>
              <FolderClosed size={16} strokeWidth={1.8} /><span>{category}</span><small className="category-count">{count} {count === 1 ? 'document' : 'documents'}</small>
            </button>;
          })}
        </div>}
      </div> : <div className="nav-group" key={group.group}><div className="nav-label">{group.group}</div>{group.items.map(({ name, label, icon: Icon }) => <button key={name} title={label || name} className={`nav-item ${activeNav === name ? 'active' : ''}`} onClick={() => { setActiveNav(name); setSearchTerm(''); setServerSearchResults(null); setCategoryFilter(''); setOwnerFilter(''); setFromDateFilter(''); setToDateFilter(''); }}><Icon size={17} strokeWidth={1.8} /><span>{label || name}</span>{name === 'Activity history' && <i className="nav-dot" />}</button>)}</div>)}
      <button className="nav-item theme-toggle" type="button" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} aria-pressed={theme === 'dark'} onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')}><span className="theme-toggle-icon">{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}</span><span>Switch to {theme === 'dark' ? 'light' : 'dark'} theme</span><span className="theme-toggle-pill">{theme === 'dark' ? 'DARK' : 'LIGHT'}</span></button>
      <div className="sidebar-spacer" />
      <div className="security-note"><div className="security-note-icon"><Shield size={17} /></div><div><b>Your files, your rules.</b><p>Access is checked by the server every time a document is requested.</p></div></div>
      <button className="profile-row" onClick={signOut}><div className="profile-avatar">{initials(user.username)}</div><div className="profile-copy"><b>{user.username}</b><small>{user.email}</small></div><LogOut size={17} /></button>
    </aside>

    <main className="main-area">
      <header className="topbar"><div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><b>{activeCategory || activeNav}</b></div><div className="topbar-actions"><div className="search-box"><Search size={16} /><input value={searchTerm} onChange={(e) => { setSearchTerm(e.target.value); setServerSearchResults(null); }} placeholder="Search documents…" aria-label="Search documents" /><kbd>⌕</kbd></div><button className="icon-button" aria-label="Refresh workspace" title="Refresh" onClick={refresh}><RefreshCw size={17} /></button><div className="top-avatar">{initials(user.username)}</div></div></header>
      <div className="page-content" key={activeNav}>
        {activeNav !== 'Admin console' && <section className="welcome-row"><div><div className="eyebrow"><span className="eyebrow-line" /> YOUR SECURE WORKSPACE</div><h1>{activeCategory ? `${activeCategory} documents` : activeNav === 'Activity history' ? 'Activity history' : activeNav === 'Shared with me' ? 'Shared with you' : activeNav === 'My documents' ? 'My documents' : activeNav === 'Settings' ? 'Settings' : `Welcome back, ${user.username}`} <span>✦</span></h1><p className="page-subtitle">{activeCategory ? `Browse documents filed under ${activeCategory}.` : activeNav === 'Activity history' ? 'A clear record of important security events.' : activeNav === 'My documents' ? 'Manage your files, organize categories, and control who can access them.' : activeNav === 'Shared with me' ? 'Review documents other people have explicitly shared with you.' : activeNav === 'Settings' ? 'Manage your password and workspace appearance.' : 'A live snapshot of your documents, sharing, and security activity.'}</p></div>{user.system_role !== 'viewer' && <button className="primary-button" onClick={() => { setUploadFile(null); setUploadTitle(''); setUploadCategory(activeCategory || 'General'); setModal('upload'); }}><Plus size={17} /> Upload document</button>}</section>}

        {notice && <div className={`notice-bar ${notice.type === 'error' ? 'notice-error' : ''}`}><span className="notice-icon">{notice.type === 'error' ? <AlertCircle size={17} /> : <Check size={17} />}</span>{notice.message}<button onClick={() => setNotice(null)} aria-label="Dismiss notice"><X size={15} /></button></div>}

        {activeNav === 'Admin console' && user.system_role === 'admin' ? <AdminConsole token={token} currentUserId={user.id} notify={notify} /> : activeNav === 'Settings' ? <section className="settings-grid">
          <form className="panel password-change-panel" onSubmit={changePassword}><div className="password-panel-heading"><div className="setting-icon"><KeyRound size={21} /></div><div><h2>Change password</h2><p>Confirm your current password, then choose a new password of at least 12 characters.</p></div></div><div className="password-form-grid"><label>Current password<input type="password" autoComplete="current-password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} maxLength={128} required /></label><label>New password<input type="password" autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} minLength={12} maxLength={128} required /></label><label>Confirm new password<input type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} minLength={12} maxLength={128} required /></label></div><div className="password-form-footer"><span><LockKeyhole size={14} /> Your current password is required.</span><button className="primary-button" type="submit" disabled={passwordBusy || !currentPassword || !newPassword || !confirmPassword}>{passwordBusy ? <RefreshCw size={15} className="spin" /> : <Check size={15} />}{passwordBusy ? 'Updating…' : 'Update password'}</button></div></form>
          <div className="panel setting-card"><div className="setting-icon"><ShieldCheck size={21} /></div><h2>Permission enforcement</h2><p>Document access is checked on protected API requests. UI controls alone are not used as a security boundary.</p><span className="setting-status"><i className="api-dot online" /> Enabled</span></div>
          <div className="panel setting-card"><div className="setting-icon"><LockKeyhole size={21} /></div><h2>Private file storage</h2><p>Uploaded files are kept outside the public frontend directory and downloaded through an authenticated API.</p><span className="setting-status"><i className="api-dot online" /> Enabled</span></div>
          <div className="panel setting-card"><div className="setting-icon"><KeyRound size={21} /></div><h2>Session security</h2><p>Signed bearer tokens expire after eight hours by default. Production should use a managed identity flow and hardened secrets.</p><span className="setting-status"><i className="api-dot online" /> Active session</span></div>
          <div className="panel setting-card"><div className="setting-icon"><Activity size={21} /></div><h2>Audit trail</h2><p>Important actions and rejected document access attempts are recorded for review.</p><button className="text-button" onClick={() => setActiveNav('Activity history')}>Review activity <ArrowUpRight size={15} /></button></div>
          <p className="security-disclaimer"><AlertCircle size={15} /> This is a project MVP. Before public or sensitive use, configure strong secrets, HTTPS, rate limits, malware scanning, database migrations, backups, and a security review.</p>
        </section> : activeNav === 'Activity history' ? <section className="panel activity-full-panel"><div className="panel-heading"><div><h2>Security activity</h2><p>Actions you performed and events on documents you own.</p></div><button className="secondary-button" onClick={refresh}><RefreshCw size={15} /> Refresh</button></div>
          {loading ? <div className="panel-loading"><RefreshCw className="spin" size={19} /> Loading activity…</div> : activity.length === 0 ? <div className="empty-state"><div className="empty-icon"><Activity size={24} /></div><h3>No activity yet</h3><p>Upload a document or share access to start building the audit history.</p></div> : <div className="activity-table">{activity.map((event) => <div className="activity-row" key={event.id}><div className={`activity-symbol ${event.action === 'ACCESS_DENIED' ? 'activity-block' : event.action.includes('ACCESS') || event.action.includes('PERMISSION') ? 'activity-share' : 'activity-upload'}`}>{event.action === 'ACCESS_DENIED' ? <Shield size={15} /> : event.action.includes('ACCESS') || event.action.includes('PERMISSION') ? <Users size={15} /> : <FileText size={15} />}</div><div className="activity-row-copy"><b>{actionLabel[event.action] || event.action}</b><p>{event.details}{event.target_username ? ` · @${event.target_username}` : ''}</p><span><Clock3 size={12} /> {prettyDate(event.created_at)} · {event.actor_username}</span></div><span className={`activity-status ${event.action === 'ACCESS_DENIED' ? 'blocked' : 'recorded'}`}>{event.action === 'ACCESS_DENIED' ? 'Blocked' : 'Recorded'}</span></div>)}</div>}
        </section> : <>
          {activeNav === 'Overview' && <section className="stats-grid" aria-label="Workspace summary">
            <div className="stat-card"><div className="stat-top"><span>Total documents</span><div className="stat-icon stat-blue"><FileText size={18} /></div></div><div className="stat-number">{owned.length}</div><div className="stat-foot"><span className="stat-neutral">Documents you own</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Shared with me</span><div className="stat-icon stat-purple"><Share2 size={18} /></div></div><div className="stat-number">{shared.length}</div><div className="stat-foot"><span className="status-good"><span className="tiny-check">✓</span> Permission controlled</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Recent activity</span><div className="stat-icon stat-teal"><Activity size={18} /></div></div><div className="stat-number">{activity.length}</div><div className="stat-foot"><span className="stat-neutral">Events visible to you</span></div></div>
            <div className="stat-card"><div className="stat-top"><span>Security status</span><div className="stat-icon stat-green"><ShieldCheck size={18} /></div></div><div className="stat-number security-number">Protected <span className="pulse-dot" /></div><div className="stat-foot"><span className="stat-neutral">Server-side checks enabled</span></div></div>
          </section>}

          <section className={`content-grid ${activeNav === 'Overview' ? 'overview-content-grid' : 'management-content-grid'}`}>
            <div className="panel documents-panel"><div className="panel-heading"><div><h2>{activeCategory ? `${activeCategory} documents` : activeNav === 'Overview' ? 'Recent documents' : activeNav === 'Shared with me' ? 'Documents shared with me' : 'All my documents'}</h2><p>{activeCategory ? `Files categorized as ${activeCategory}.` : activeNav === 'Overview' ? 'A quick look at the latest files in your workspace.' : activeNav === 'Shared with me' ? 'Only files another owner has explicitly shared with your account.' : 'Search, filter, rename, delete, and manage access to your uploads.'}</p></div><button className="text-button" onClick={() => setActiveNav(activeNav === 'Overview' ? 'My documents' : activeNav === 'My documents' ? 'Overview' : 'My documents')}>{activeNav === 'Overview' ? 'Manage all documents' : activeNav === 'Shared with me' ? 'My documents' : activeCategory ? 'View all my documents' : 'Back to overview'} <ArrowUpRight size={15} /></button></div>
              {activeNav !== 'Overview' && <form className={`document-filter-form ${activeCategory ? 'category-fixed-filter-form' : ''}`} onSubmit={applyDocumentFilters}>
                <label>Owner<input value={ownerFilter} onChange={(e) => setOwnerFilter(e.target.value)} placeholder="Username" /></label>
                {activeCategory ? <label className="fixed-category-filter"><span>Category</span><output aria-label={`Category: ${activeCategory}`}>{activeCategory}</output></label> : <label>Category<select className={categoryMotion < 0 ? 'category-select' : `category-select category-pulse-${categoryMotion % 2}`} value={categoryFilter} onChange={(e) => { setCategoryFilter(e.target.value); setCategoryMotion((current) => current < 0 ? 0 : current + 1); }}><option value="">All categories</option>{[...DOCUMENT_CATEGORIES, ...LEGACY_CATEGORIES].map((category) => <option key={category}>{category}</option>)}</select></label>}
                <label>From date<input type="date" value={fromDateFilter} onChange={(e) => setFromDateFilter(e.target.value)} /></label>
                <label>To date<input type="date" value={toDateFilter} onChange={(e) => setToDateFilter(e.target.value)} /></label>
                <div className="document-filter-actions"><button className="primary-button" type="submit" disabled={searchBusy}>{searchBusy ? <RefreshCw className="spin" size={14} /> : <Search size={14} />} Filter</button><button className="secondary-button" type="button" onClick={clearDocumentFilters}>Clear</button></div>
              </form>}
              {activeNav !== 'Overview' && <div className="filter-hint">Search is applied by the server and only searches documents your account is authorized to access.</div>}
              {loading ? <div className="panel-loading"><RefreshCw className="spin" size={19} /> Loading documents…</div> : visibleDocs.length === 0 ? <div className="empty-state"><div className="empty-icon"><FolderClosed size={24} /></div><h3>{searchTerm || serverSearchResults !== null ? 'No matching documents' : activeNav === 'Shared with me' ? 'Nothing shared with you yet' : 'Your vault is ready'}</h3><p>{searchTerm || serverSearchResults !== null ? 'Try another name, owner, category, or date range.' : activeNav === 'Shared with me' ? 'When someone grants your account access, their documents will appear here.' : 'Upload your first document to start using your secure workspace.'}</p>{!searchTerm && activeNav !== 'Shared with me' && user.system_role !== 'viewer' && <button className="primary-button" onClick={() => { setUploadCategory(activeCategory || 'General'); setModal('upload'); }}><Plus size={16} /> Upload first document</button>}</div> : <div className="table-wrap"><table><thead><tr><th>DOCUMENT</th><th>LAST UPDATED</th><th>ACCESS</th><th className="action-head">ACTIONS</th></tr></thead><tbody>{displayDocs.map((doc) => <tr key={doc.id}><td><div className="file-cell"><div className={`file-icon ${doc.content_type?.includes('pdf') ? 'file-blue' : doc.content_type?.startsWith('image/') ? 'file-orange' : 'file-purple'}`}><FileText size={18} /><small>{(doc.filename.split('.').pop() || 'FILE').slice(0, 4).toUpperCase()}</small></div><div className="file-name-wrap"><b title={doc.filename}>{doc.filename}</b><span>{doc.is_owner ? 'Owned by you' : `Shared by @${doc.owner_username}`} <i>·</i> {doc.category || 'General'} <i>·</i> {prettyBytes(doc.size_bytes)}</span></div></div></td><td><span className="updated-text">{prettyDate(doc.updated_at || doc.created_at)}</span></td><td><span className={`access-pill ${doc.is_owner ? (doc.shares_count > 0 ? 'shared' : 'private') : 'shared'}`}>{doc.is_owner ? (doc.shares_count > 0 ? <Users size={12} /> : <LockKeyhole size={12} />) : <Eye size={12} />}{doc.is_owner ? (doc.shares_count > 0 ? `Shared · ${doc.shares_count}` : 'Private') : doc.access_role}</span></td><td><div className="row-actions">{(doc.is_owner || doc.access_role === 'editor') ? <button className="row-action" title="Download" aria-label={`Download ${doc.filename}`} onClick={() => downloadDoc(doc)}><ArrowDownToLine size={16} /></button> : <button className="row-action" title="Read-only preview" aria-label={`Preview ${doc.filename}`} onClick={() => openPreview(doc)}><Eye size={16} /></button>}{(doc.is_owner || doc.access_role === 'editor') && <button className="row-action" title="Rename" aria-label={`Rename ${doc.filename}`} onClick={() => { setSelectedDoc(doc); setRenameTitle(doc.filename); setModal('rename'); }}><Pencil size={15} /></button>}{doc.is_owner && <button className="row-action" title="Manage access" aria-label={`Manage access to ${doc.filename}`} onClick={() => openShares(doc)}><Users size={16} /></button>}{doc.is_owner && <button className="row-action row-danger" title="Delete document" aria-label={`Delete ${doc.filename}`} onClick={() => deleteDoc(doc)}><Trash2 size={15} /></button>}</div></td></tr>)}</tbody></table></div>}
              {displayDocs.length > 0 && <div className="panel-footer"><span>{activeNav === 'Overview' ? `Showing ${displayDocs.length} recent document${displayDocs.length === 1 ? '' : 's'}` : `Showing ${displayDocs.length} document${displayDocs.length === 1 ? '' : 's'} in this view`}</span><span><LockKeyhole size={13} /> Reader downloads are blocked by the server</span></div>}
            </div>
            {activeNav === 'Overview' && <div className="right-column">
              <div className="panel activity-panel"><div className="panel-heading compact"><div><h2>Security activity</h2><p>Latest workspace events</p></div><button className="more-button" aria-label="Refresh activity" onClick={refresh}><RefreshCw size={15} /></button></div>
                {activity.length === 0 ? <div className="activity-empty">Your upload, download, and sharing events will appear here.</div> : <div className="activity-list">{activity.slice(0, 4).map((event) => <div className="activity-item" key={event.id}><div className={`activity-symbol ${event.action === 'ACCESS_DENIED' ? 'activity-block' : event.action.includes('ACCESS') || event.action.includes('PERMISSION') ? 'activity-share' : 'activity-upload'}`}>{event.action === 'ACCESS_DENIED' ? <Shield size={15} /> : event.action.includes('ACCESS') || event.action.includes('PERMISSION') ? <Users size={15} /> : <FileText size={15} />}</div><div className="activity-copy"><b>{actionLabel[event.action] || event.action}</b><p>{event.document_name || event.details}</p><span><Clock3 size={12} /> {prettyDate(event.created_at)}</span></div><span className={`activity-status ${event.action === 'ACCESS_DENIED' ? 'blocked' : 'recorded'}`}>{event.action === 'ACCESS_DENIED' ? 'Blocked' : 'Saved'}</span></div>)}</div>}
                <button className="activity-link" onClick={() => setActiveNav('Activity history')}>View activity history <ArrowUpRight size={14} /></button>
              </div>
              <div className="protection-card"><div className="protection-graphic"><div className="protection-orbit orbit-one" /><div className="protection-orbit orbit-two" /><div className="protection-shield"><ShieldCheck size={28} /></div><span className="orbit-point point-one" /><span className="orbit-point point-two" /><span className="orbit-point point-three" /></div><div className="protection-copy"><div className="protection-label"><BadgeCheck size={14} /> DOCUSENTRA PROTECTION</div><h3>Security at every step.</h3><p>Private files, controlled permissions, and recorded activity.</p><button onClick={() => setActiveNav('Settings')}>Explore security <ArrowUpRight size={14} /></button></div></div>
            </div>}
          </section>
        </>}
        <footer className="page-footer"><span><LockKeyhole size={13} /> Your workspace is private by default</span><span className="footer-status"><span className="api-dot online" /> Signed in <span className="footer-separator">·</span><span className="api-dot online" /> API-backed workspace</span><span>DocuSentra <b>·</b> Local MVP</span></footer>
      </div>
    </main>

    {modal === 'upload' && <Modal title="Upload a document" subtitle="Files remain private until you explicitly share them." onClose={() => { if (!busy) setModal(null); }}>
      <form className="modal-form" onSubmit={doUpload}><label>Document name <span className="optional-label">Optional</span><input value={uploadTitle} onChange={(e) => setUploadTitle(e.target.value)} placeholder="Keep original filename if blank" maxLength={200} /></label><label>Document category<select value={uploadCategory} onChange={(e) => setUploadCategory(e.target.value)} required>{DOCUMENT_CATEGORIES.map((category) => <option key={category} value={category}>{category}</option>)}</select><small className="field-help">Choose the category before sharing this document with another person.</small></label><label className="upload-drop"><UploadCloud size={27} /><b>{uploadFile ? uploadFile.name : 'Choose a file to upload'}</b><span>{uploadFile ? prettyBytes(uploadFile.size) : 'PDF, Office, TXT, CSV, PNG or JPG · Max 15 MB'}</span><input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.png,.jpg,.jpeg" onChange={(e) => setUploadFile(e.target.files?.[0] || null)} required /></label><div className="modal-note"><LockKeyhole size={15} /> Original files stay private. Readers can preview PDF, Office documents, images, TXT and CSV; the download API blocks Reader downloads.</div><div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setModal(null)} disabled={busy}>Cancel</button><button className="primary-button" type="submit" disabled={busy || !uploadFile}>{busy ? <RefreshCw className="spin" size={16} /> : <UploadCloud size={16} />}{busy ? 'Uploading…' : 'Upload securely'}</button></div></form>
    </Modal>}

    {modal === 'preview' && selectedDoc && <Modal title="Read-only document preview" subtitle={selectedDoc.filename} onClose={() => { setModal(null); setSelectedDoc(null); setPreviewUrl(''); setPreviewPageCount(0); }} wide>
      <div className="preview-body">
        <div className="modal-note"><Eye size={15} /> Reader download/print controls are removed from the preview. Copy, selection and context-menu shortcuts are blocked as deterrents. Standard browsers cannot reliably prevent OS screenshots or screen recording, and visible content can still be captured.</div>
        {previewLoading ? <div className="panel-loading"><RefreshCw className="spin" size={19} /> Preparing read-only preview…</div> : previewError ? <div className="form-error"><AlertCircle size={16} />{previewError}</div> : previewType === 'pages' && previewPageCount > 0 ? <div className="preview-pages-stage" onContextMenu={(event) => event.preventDefault()} onDragStart={(event) => event.preventDefault()}>{Array.from({ length: previewPageCount }, (_, index) => <ProtectedPreviewPage key={`${selectedDoc.id}-${index + 1}`} documentId={selectedDoc.id} pageNumber={index + 1} token={token} />)}</div> : previewType === 'image' && previewUrl ? <div className="preview-image-stage preview-protected-surface" onContextMenu={(event) => event.preventDefault()} onDragStart={(event) => event.preventDefault()}><img src={previewUrl} alt={`Preview of ${selectedDoc.filename}`} draggable="false" /></div> : previewBlocks.length === 0 ? <div className="share-empty"><FileText size={22} /><b>No readable content found</b><span>This document may be empty or contain content the preview cannot extract.</span></div> : <div className="document-preview-content preview-protected-surface" onCopy={(event) => event.preventDefault()} onCut={(event) => event.preventDefault()} onContextMenu={(event) => event.preventDefault()} onDragStart={(event) => event.preventDefault()}><div className="preview-text-content">{previewBlocks.map((block, index) => block.type === 'table' ? <div className="preview-table-wrap" key={`table-${index}`}><table className="preview-table"><tbody>{block.rows.map((row, rowIndex) => <tr key={`row-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`cell-${rowIndex}-${cellIndex}`}>{cell}</td>)}</tr>)}</tbody></table></div> : <p className="preview-paragraph" key={`paragraph-${index}`}>{block.text}</p>)}</div></div>}
        <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => { setModal(null); setSelectedDoc(null); setPreviewUrl(''); setPreviewPageCount(0); }}>Close preview</button></div>
      </div>
    </Modal>}

    {modal === 'shares' && selectedDoc && <Modal title="Access & people" subtitle={selectedDoc.filename} onClose={() => setModal(null)} width="590px">
      <div className="share-body"><form className="grant-form" onSubmit={grantAccess}><label>Share with username or email<input value={shareInput} onChange={(e) => setShareInput(e.target.value)} placeholder="Enter an existing TrustVault user" required /></label><div className="grant-controls"><label>Permission<select value={shareRole} onChange={(e) => setShareRole(e.target.value)}><option value="reader">Reader — preview only, no download</option><option value="editor">Editor — preview, download & rename</option></select></label><button type="submit" className="primary-button" disabled={shareBusy || !shareInput.trim()}>{shareBusy ? <RefreshCw className="spin" size={15} /> : <Plus size={16} />}{shareBusy ? 'Saving…' : 'Grant access'}</button></div></form><div className="share-list-heading"><b>People with access</b><span>{shares.length} {shares.length === 1 ? 'person' : 'people'}</span></div>{shares.length === 0 ? <div className="share-empty"><Users size={22} /><b>Only you have access</b><span>Grant access above to share this document.</span></div> : <div className="share-list">{shares.map((share) => <div className="share-person" key={share.id}><div className="person-avatar">{initials(share.username)}</div><div className="person-copy"><b>{share.username}</b><span>{share.email}</span></div><span className={`role-tag ${share.role}`}>{share.role}</span><button className="row-action row-danger" title={`Revoke ${share.username}'s access`} onClick={() => revokeAccess(share)}><X size={15} /></button></div>)}</div>}<div className="modal-note"><ShieldCheck size={15} /> Readers can preview supported formats but cannot download the original. Revocation blocks future access; it cannot erase files previously downloaded by someone who had download permission.</div></div>
    </Modal>}

    {modal === 'rename' && selectedDoc && <Modal title="Rename document" subtitle="Editors can rename; only the owner can manage access." onClose={() => { if (!busy) setModal(null); }} width="460px"><form className="modal-form" onSubmit={doRename}><label>Document name<input value={renameTitle} onChange={(e) => setRenameTitle(e.target.value)} maxLength={200} required autoFocus /></label><div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setModal(null)} disabled={busy}>Cancel</button><button type="submit" className="primary-button" disabled={busy || !renameTitle.trim()}>{busy ? <RefreshCw className="spin" size={16} /> : <Check size={16} />}{busy ? 'Saving…' : 'Save name'}</button></div></form></Modal>}
  </div>;
}

export default App;
