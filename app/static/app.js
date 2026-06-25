// Ranbval Resume Shortlister — vanilla JS frontend

const $ = (id) => document.getElementById(id);
let activeJobId = null;
let threshold = 75;

// ── Auth state (token kept in localStorage) ──
const auth = {
  get token() { return localStorage.getItem('rs_token') || ''; },
  get role() { return localStorage.getItem('rs_role') || ''; },
  get name() { return localStorage.getItem('rs_name') || ''; },
  get accountType() { return localStorage.getItem('rs_account_type') || 'recruiter'; },
  set(token, name, role, accountType) {
    localStorage.setItem('rs_token', token);
    localStorage.setItem('rs_name', name);
    localStorage.setItem('rs_role', role);
    localStorage.setItem('rs_account_type', accountType);
  },
  clear() {
    localStorage.removeItem('rs_token');
    localStorage.removeItem('rs_name');
    localStorage.removeItem('rs_role');
    localStorage.removeItem('rs_account_type');
  },
};

// ── API helpers ──
async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (auth.token) headers['Authorization'] = `Bearer ${auth.token}`;
  const res = await fetch(`/api${path}`, { ...opts, headers });
  if (res.status === 401) {
    auth.clear();
    showLogin('Session expired — please sign in again.');
    throw new Error('Not authenticated');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

async function loadHealth() {
  try {
    const h = await (await fetch('/health')).json();
    threshold = h.shortlist_threshold ?? 75;
    if (!h.openai_configured) {
      alert('Heads up: OPENAI_API_KEY is not set in .env — scoring will fail until you add it.');
    }
  } catch { /* ignore */ }
}

// ── Jobs ──
let allJobs = [];

async function loadJobs() {
  allJobs = await api('/jobs');
  renderJobs();
}

function renderJobs() {
  const q = ($('jobSearch').value || '').trim().toLowerCase();
  const jobs = q ? allJobs.filter((j) => j.title.toLowerCase().includes(q)) : allJobs;
  const list = $('jobList');
  list.innerHTML = '';
  if (allJobs.length === 0) {
    list.innerHTML = '<p class="muted" style="padding:4px 6px;">No jobs yet.</p>';
    return;
  }
  if (jobs.length === 0) {
    list.innerHTML = '<p class="muted" style="padding:4px 6px;">No jobs match.</p>';
    return;
  }
  jobs.forEach((j) => {
    const el = document.createElement('div');
    el.className = 'job-item' + (j.id === activeJobId ? ' active' : '');
    el.innerHTML = `<div class="ji-title">${escapeHtml(j.title)}</div>
      <div class="ji-meta">${j.candidate_count} candidate${j.candidate_count === 1 ? '' : 's'}</div>`;
    el.onclick = () => openJob(j.id);
    list.appendChild(el);
  });
}

function showJobForm() {
  $('jobForm').classList.remove('hidden');
  $('emptyState').classList.add('hidden');
  $('jobView').classList.add('hidden');
  $('jobTitle').value = '';
  $('jobDesc').value = '';
  $('jobThreshold').value = 90;
  $('jobThresholdVal').textContent = '90';
  $('jobTitle').focus();
}

async function saveJob() {
  const title = $('jobTitle').value.trim();
  const description = $('jobDesc').value.trim();
  if (title.length < 2 || description.length < 20) {
    alert('Enter a title and a real job description (at least a few lines).');
    return;
  }
  const btn = $('saveJobBtn');
  btn.disabled = true; btn.textContent = 'Creating…';
  try {
    const job = await api('/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description, threshold: Number($('jobThreshold').value) }),
    });
    await loadJobs();
    openJob(job.id);
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Create job';
  }
}

async function openJob(jobId) {
  activeJobId = jobId;
  $('jobForm').classList.add('hidden');
  $('emptyState').classList.add('hidden');
  $('jobView').classList.remove('hidden');

  const job = await api(`/jobs/${jobId}`);
  $('jvTitle').textContent = job.title;
  $('jvMeta').textContent = `Created ${job.created_at} · ${job.candidate_count} screened`;
  $('jvDesc').textContent = job.description;
  $('jvDesc').classList.add('hidden');
  $('toggleJD').textContent = 'View JD';
  $('threshNote').textContent = `Shortlist threshold: ${job.threshold ?? threshold}/100 (90+ = interview-ready only)`;
  resetFilters();
  await loadCandidates();
  await loadJobs();
  await refreshPendingButton();
}

function resetFilters() {
  $('candSearch').value = '';
  $('filterVerdict').value = '';
  $('filterDate').value = '';
  $('filterSort').value = 'best';
}

// ── Candidates ──
let allCandidates = [];

async function loadCandidates() {
  allCandidates = await api(`/jobs/${activeJobId}/candidates`);
  renderCandidates();
}

function filteredCandidates() {
  const q = ($('candSearch').value || '').trim().toLowerCase();
  const verdict = $('filterVerdict').value;
  const dateSel = $('filterDate').value;
  const sort = $('filterSort').value;

  let list = allCandidates.slice();

  // text search across name, filename, summary
  if (q) {
    list = list.filter((c) =>
      [c.candidate_name, c.filename, c.summary]
        .filter(Boolean)
        .some((v) => v.toLowerCase().includes(q))
    );
  }

  // verdict / recommended
  if (verdict === 'recommended') list = list.filter((c) => c.recommended);
  else if (verdict) list = list.filter((c) => c.verdict === verdict);

  // date added
  if (dateSel) {
    const now = Date.now();
    const cutoff = dateSel === 'today'
      ? new Date(new Date().toDateString()).getTime()
      : now - Number(dateSel) * 86400000;
    list = list.filter((c) => {
      const t = Date.parse(c.created_at);
      return !isNaN(t) && t >= cutoff;
    });
  }

  // sort
  const ts = (c) => Date.parse(c.created_at) || 0;
  if (sort === 'newest') list.sort((a, b) => ts(b) - ts(a));
  else if (sort === 'oldest') list.sort((a, b) => ts(a) - ts(b));
  else if (sort === 'score_asc') list.sort((a, b) => a.score - b.score);
  else list.sort((a, b) => (b.recommended - a.recommended) || (b.score - a.score)); // best

  return list;
}

function renderCandidates() {
  const list = $('candidateList');
  list.innerHTML = '';
  if (allCandidates.length === 0) {
    $('candCount').textContent = '0';
    list.innerHTML = '<p class="muted">No resumes screened yet. Upload one above.</p>';
    return;
  }
  const shown = filteredCandidates();
  $('candCount').textContent = shown.length === allCandidates.length
    ? String(allCandidates.length)
    : `${shown.length} / ${allCandidates.length}`;
  if (shown.length === 0) {
    list.innerHTML = '<p class="muted">No candidates match these filters.</p>';
    return;
  }
  shown.forEach((c) => list.appendChild(renderCandidate(c)));
}

function scoreColor(score) {
  if (score >= 80) return 'var(--green)';
  if (score >= 60) return 'var(--amber)';
  return 'var(--red)';
}

// Rich JD-grounded insights block for a scored candidate.
function renderInsights(c) {
  let html = '';

  // seniority + years vs JD
  const chips = [];
  if (c.seniority_required || c.seniority_detected) {
    chips.push(`<div class="ins-chip"><span class="muted">Seniority:</span> ${escapeHtml(c.seniority_detected || '—')} <span class="muted">vs JD</span> ${escapeHtml(c.seniority_required || '—')}</div>`);
  }
  if (c.years_required != null || c.years_experience != null) {
    const ye = c.years_experience != null ? c.years_experience : '—';
    const yr = c.years_required != null ? c.years_required : '—';
    chips.push(`<div class="ins-chip"><span class="muted">Experience:</span> ${ye} yrs <span class="muted">vs JD</span> ${yr} yrs</div>`);
  }
  if (chips.length) html += `<div class="ins-chips">${chips.join('')}</div>`;

  // JD requirements scorecard
  const reqs = c.requirements || [];
  if (reqs.length) {
    const icon = { met: '✓', partial: '≈', missing: '✗' };
    const met = reqs.filter((r) => r.status === 'met').length;
    const rows = reqs.map((r) => `
      <div class="req-row req-${r.status}">
        <span class="req-ic">${icon[r.status] || '✗'}</span>
        <span class="req-text"><b>${escapeHtml(r.requirement)}</b>${r.evidence ? `<span class="muted req-ev"> — ${escapeHtml(r.evidence)}</span>` : ''}</span>
      </div>`).join('');
    html += `<div class="detail-block" style="margin-top:14px;"><h4>JD requirements — ${met}/${reqs.length} met</h4><div class="req-list">${rows}</div></div>`;
  }

  // interview focus areas
  const foc = c.interview_focus || [];
  if (foc.length) {
    html += `<div class="detail-block" style="margin-top:14px;"><h4>Interview focus (probe these)</h4><ul>${foc.map((f) => `<li>${escapeHtml(f)}</li>`).join('')}</ul></div>`;
  }
  return html;
}

function renderCandidate(c) {
  // Not-yet-scored states get a compact card.
  if (c.status === 'queued' || c.status === 'processing') {
    const el = document.createElement('div');
    el.className = 'cand cand-pending';
    const label = c.status === 'processing' ? 'Scoring…' : 'Queued';
    el.innerHTML = `
      <div class="cand-top">
        <div class="score-badge" style="background:rgba(255,255,255,.05);color:var(--muted);">⏳</div>
        <div class="cand-main">
          <div class="cand-name">${escapeHtml(c.filename)}</div>
          <div class="cand-file">${label}</div>
        </div>
        <span class="verdict v-maybe">${label}</span>
      </div>`;
    return el;
  }
  if (c.status === 'error') {
    const el = document.createElement('div');
    el.className = 'cand cand-error';
    el.innerHTML = `
      <div class="cand-top">
        <div class="score-badge" style="background:rgba(248,113,113,.14);color:var(--red);">⚠</div>
        <div class="cand-main">
          <div class="cand-name">${escapeHtml(c.filename)}</div>
          <div class="cand-file">Scoring failed: ${escapeHtml(c.error || 'unknown error')}</div>
        </div>
        <button class="btn btn-ghost" data-retry="${c.id}">Retry</button>
      </div>`;
    el.querySelector('[data-retry]').onclick = async () => {
      await api(`/jobs/${activeJobId}/candidates/${c.id}/retry`, { method: 'POST' });
      await runProcessing();
    };
    return el;
  }

  const el = document.createElement('div');
  el.className = 'cand' + (c.recommended ? ' rec' : '');

  const badgeColor = scoreColor(c.score);
  const matched = (c.matched_requirements || []).map((m) => `<li class="li-good">${escapeHtml(m)}</li>`).join('');
  const missing = (c.missing_requirements || []).map((m) => `<li class="li-bad">${escapeHtml(m)}</li>`).join('');
  const flags = (c.red_flags || []).map((m) => `<li class="li-flag">${escapeHtml(m)}</li>`).join('');
  const skills = (c.key_skills || []).map((s) => `<span class="chip">${escapeHtml(s)}</span>`).join('');
  const years = c.years_experience != null ? `${c.years_experience} yrs exp` : 'exp N/A';

  const measureLabels = {
    skills_match: 'Skills', experience_match: 'Experience', education_match: 'Education',
    seniority_fit: 'Seniority', domain_relevance: 'Domain', responsibility_match: 'Responsibilities',
    tools_match: 'Tools', communication: 'Communication',
  };
  const m = c.measurements || {};
  const measureBars = Object.keys(measureLabels)
    .filter((k) => k in m)
    .map((k) => {
      const v = m[k];
      const col = v >= 80 ? 'var(--green)' : v >= 60 ? 'var(--amber)' : 'var(--red)';
      return `<div class="meas">
        <div class="meas-top"><span>${measureLabels[k]}</span><span style="color:${col}">${v}</span></div>
        <div class="meas-bar"><div class="meas-fill" style="width:${v}%;background:${col}"></div></div>
      </div>`;
    }).join('');

  el.innerHTML = `
    <div class="cand-top">
      <div class="score-badge" style="background:${hexFade(badgeColor)};color:${badgeColor};">${c.score}</div>
      <div class="cand-main">
        <div class="cand-name">${escapeHtml(c.candidate_name || 'Unknown candidate')}</div>
        <div class="cand-file">${escapeHtml(c.filename)} · ${years}</div>
        <div class="cand-summary">${escapeHtml(c.summary || '')}</div>
      </div>
      <span class="verdict v-${c.verdict}">${c.recommended ? '★ ' : ''}${c.verdict}</span>
    </div>
    <div class="cand-detail">
      ${measureBars ? `<div class="detail-block"><h4>Measurements</h4><div class="meas-grid">${measureBars}</div></div>` : ''}
      ${renderInsights(c)}
      <div class="detail-grid" style="margin-top:14px;">
        <div class="detail-block">
          <h4>✓ Matched (${(c.matched_requirements || []).length})</h4>
          <ul>${matched || '<li class="muted">—</li>'}</ul>
        </div>
        <div class="detail-block">
          <h4>✗ Missing (${(c.missing_requirements || []).length})</h4>
          <ul>${missing || '<li class="muted">—</li>'}</ul>
        </div>
      </div>
      ${flags ? `<div class="detail-block" style="margin-top:14px;"><h4>⚠ Red flags</h4><ul>${flags}</ul></div>` : ''}
      ${skills ? `<div class="detail-block" style="margin-top:14px;"><h4>Key skills</h4><div class="chips">${skills}</div></div>` : ''}
      <div class="cand-actions">
        <button class="link-danger" data-del="${c.id}">Delete</button>
      </div>
    </div>`;

  el.querySelector('.cand-top').onclick = () => el.classList.toggle('open');
  el.querySelector('[data-del]').onclick = async (ev) => {
    ev.stopPropagation();
    if (!confirm('Delete this candidate?')) return;
    await api(`/jobs/${activeJobId}/candidates/${c.id}`, { method: 'DELETE' });
    await loadCandidates();
    await loadJobs();
  };
  return el;
}

// ── Upload + scoring at scale ──
const UPLOAD_CONCURRENCY = 4;     // parallel upload requests from this browser
let busy = false;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function showProgress(text, pct) {
  $('batchProgress').classList.remove('hidden');
  $('bpFill').style.width = `${Math.max(2, Math.min(100, pct))}%`;
  $('bpText').textContent = text;
}
function hideProgressSoon() {
  setTimeout(() => $('batchProgress').classList.add('hidden'), 1500);
}

async function handleFiles(fileList) {
  const files = Array.from(fileList);
  if (!files.length || busy || !activeJobId) return;
  busy = true;
  $('uploadStatus').classList.add('hidden');

  // ── Phase 1: upload (enqueue) with a small concurrency pool ──
  const total = files.length;
  let uploaded = 0, uploadFailed = 0, idx = 0;
  showProgress(`Uploading 0 / ${total}…`, 0);

  async function uploadWorker() {
    while (idx < files.length) {
      const file = files[idx++];
      const form = new FormData();
      form.append('file', file);
      try {
        await api(`/jobs/${activeJobId}/resumes`, { method: 'POST', body: form });
      } catch { uploadFailed++; }
      uploaded++;
      showProgress(`Uploading ${uploaded} / ${total}…`, Math.round((uploaded / total) * 100));
    }
  }
  await Promise.all(
    Array.from({ length: Math.min(UPLOAD_CONCURRENCY, files.length) }, uploadWorker)
  );
  await loadCandidates();

  // ── Phase 2: drain the scoring queue ──
  await runProcessing();

  if (uploadFailed) {
    const s = $('uploadStatus');
    s.className = 'upload-status error';
    s.classList.remove('hidden');
    s.textContent = `${uploadFailed} file(s) couldn't be read (scanned/empty?) and were skipped.`;
  }
  busy = false;
}

// Repeatedly claim+score batches until this job's queue is empty.
async function runProcessing() {
  let stuck = 0;
  for (;;) {
    let res;
    try {
      res = await api(`/jobs/${activeJobId}/process`, { method: 'POST' });
    } catch (e) {
      showProgress(`Paused: ${e.message}`, 100);
      break;
    }
    const st = await api(`/jobs/${activeJobId}/queue-status`);
    const finished = st.done + st.error;
    const pct = st.total ? Math.round((finished / st.total) * 100) : 100;
    showProgress(
      `Scored ${finished} / ${st.total}${st.error ? ` · ${st.error} failed` : ''}` +
        (st.queued + st.processing ? '…' : ' ✓'),
      pct
    );
    await loadCandidates();

    if (st.queued === 0) break; // others may still finish their own claimed rows
    if (res.processed === 0 && res.failed === 0) {
      // nothing claimable right now (another worker holds them) — wait & retry
      if (++stuck >= 5) break;
      await sleep(1500);
    } else {
      stuck = 0;
    }
  }
  hideProgressSoon();
  await loadCandidates();
  await loadJobs();
  await refreshPendingButton();
}

async function refreshPendingButton() {
  if (!activeJobId) return;
  try {
    const st = await api(`/jobs/${activeJobId}/queue-status`);
    const pending = st.queued + st.processing;
    const btn = $('resumeBtn');
    if (pending > 0 && !busy) {
      btn.textContent = `▶ Score ${pending} pending`;
      btn.classList.remove('hidden');
    } else {
      btn.classList.add('hidden');
    }
  } catch { /* ignore */ }
}

// ── Utils ──
function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}
function hexFade(color) {
  // turn a CSS var color into a faint background
  const map = {
    'var(--green)': 'rgba(54,211,153,.16)',
    'var(--amber)': 'rgba(251,191,36,.16)',
    'var(--red)': 'rgba(248,113,113,.16)',
  };
  return map[color] || 'rgba(255,255,255,.06)';
}

// ── Wire up ──
$('newJobBtn').onclick = showJobForm;
$('cancelJobBtn').onclick = () => {
  $('jobForm').classList.add('hidden');
  if (activeJobId) $('jobView').classList.remove('hidden');
  else $('emptyState').classList.remove('hidden');
};
$('saveJobBtn').onclick = saveJob;
$('jobThreshold').oninput = (e) => { $('jobThresholdVal').textContent = e.target.value; };
$('toggleJD').onclick = () => {
  const box = $('jvDesc');
  box.classList.toggle('hidden');
  $('toggleJD').textContent = box.classList.contains('hidden') ? 'View JD' : 'Hide JD';
};
$('fileInput').onchange = (e) => {
  if (e.target.files.length) handleFiles(e.target.files);
  e.target.value = '';
};
$('resumeBtn').onclick = () => { if (!busy) runProcessing(); };

// Job search (sidebar)
$('jobSearch').oninput = renderJobs;

// Candidate filters
$('candSearch').oninput = renderCandidates;
$('filterVerdict').onchange = renderCandidates;
$('filterDate').onchange = renderCandidates;
$('filterSort').onchange = renderCandidates;
$('clearFilters').onclick = () => { resetFilters(); renderCandidates(); };

// ── Auth UI ──
function showLogin(msg) {
  $('loginOverlay').style.display = 'flex';
  $('usersBtn').classList.add('hidden');
  $('dashBtn').classList.add('hidden');
  $('logoutBtn').classList.add('hidden');
  // reflect last-used login tab
  document.querySelectorAll('#loginMode .seg-btn').forEach((b) =>
    b.classList.toggle('active', b.dataset.mode === getLoginTab()));
  $('whoami').textContent = '';
  const err = $('loginError');
  if (msg) { err.textContent = msg; err.classList.remove('hidden'); }
  else { err.classList.add('hidden'); }
  setTimeout(() => $('loginName').focus(), 50);
}

function hideLogin() {
  $('loginOverlay').style.display = 'none';
  $('logoutBtn').classList.remove('hidden');
  const acct = auth.accountType;
  $('whoami').textContent = `${auth.name} · ${acct}`;
  applyMode(acct);
}

// ── Mode is fixed by the logged-in account type (no free switching) ──
// The login-screen tab selects which account TYPE you authenticate as.
function getLoginTab() { return localStorage.getItem('rs_login_tab') || 'recruiter'; }
function setLoginTab(m) { localStorage.setItem('rs_login_tab', m); }

function applyMode(mode) {
  const student = mode === 'student';
  $('recruiterMain').classList.toggle('hidden', student);
  $('studentMain').classList.toggle('hidden', !student);
  // admin tools only for recruiter admins
  const isAdmin = auth.role === 'admin' && !student;
  $('dashBtn').classList.toggle('hidden', !isAdmin);
  $('usersBtn').classList.toggle('hidden', !isAdmin);
}

async function doLogin(e) {
  e.preventDefault();
  const name = $('loginName').value.trim();
  const password = $('loginPass').value;
  const btn = $('loginBtn');
  btn.disabled = true; btn.textContent = 'Signing in…';
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, password, account_type: getLoginTab() }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Login failed');
    auth.set(data.token, data.name, data.role, data.account_type);
    $('loginPass').value = '';
    hideLogin();
    await startApp();
  } catch (err) {
    showLogin(err.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Sign in';
  }
}

function logout() {
  auth.clear();
  activeJobId = null;
  $('jobView').classList.add('hidden');
  $('jobForm').classList.add('hidden');
  $('emptyState').classList.remove('hidden');
  showLogin();
}

// ── Admin: Users management ──
async function openUsers() {
  $('usersModal').classList.remove('hidden');
  await loadUsers();
}

async function loadUsers() {
  const users = await api('/admin/users');
  const list = $('usersList');
  list.innerHTML = '';
  users.forEach((u) => {
    const row = document.createElement('div');
    row.className = 'user-row';
    const t = u.account_type || 'recruiter';
    row.innerHTML = `
      <input class="u-name" value="${escapeAttr(u.name)}" />
      <input class="u-pass" value="${escapeAttr(u.password)}" />
      <select class="u-type">
        <option value="recruiter" ${t === 'recruiter' ? 'selected' : ''}>recruiter</option>
        <option value="student" ${t === 'student' ? 'selected' : ''}>student</option>
      </select>
      <select class="u-role">
        <option value="user" ${u.role === 'user' ? 'selected' : ''}>user</option>
        <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>admin</option>
      </select>
      <button class="btn btn-ghost u-save">Save</button>
      <button class="link-danger u-del">Delete</button>`;
    row.querySelector('.u-save').onclick = async () => {
      try {
        await api(`/admin/users/${u.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: row.querySelector('.u-name').value.trim(),
            password: row.querySelector('.u-pass').value,
            role: row.querySelector('.u-role').value,
            account_type: row.querySelector('.u-type').value,
          }),
        });
        await loadUsers();
      } catch (e) { alert(e.message); }
    };
    row.querySelector('.u-del').onclick = async () => {
      if (!confirm(`Delete user "${u.name}"?`)) return;
      try { await api(`/admin/users/${u.id}`, { method: 'DELETE' }); await loadUsers(); }
      catch (e) { alert(e.message); }
    };
    list.appendChild(row);
  });
}

async function addUser() {
  const name = $('newUserName').value.trim();
  const password = $('newUserPass').value;
  const role = $('newUserRole').value;
  const account_type = $('newUserType').value;
  if (!name || !password) { alert('Enter a username and password.'); return; }
  try {
    await api('/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, password, role, account_type }),
    });
    $('newUserName').value = ''; $('newUserPass').value = '';
    await loadUsers();
  } catch (e) { alert(e.message); }
}

function escapeAttr(s) { return String(s ?? '').replace(/"/g, '&quot;'); }

// ── Admin: Dashboard ──
async function openDashboard() {
  $('dashModal').classList.remove('hidden');
  await loadDashboard();
}

async function loadDashboard() {
  $('dashStats').innerHTML = '<p class="muted">Loading…</p>';
  $('dashJobs').innerHTML = '';
  let d;
  try { d = await api('/admin/dashboard'); }
  catch (e) { $('dashStats').innerHTML = `<p class="login-error">${escapeHtml(e.message)}</p>`; return; }

  const card = (value, label, color) =>
    `<div class="dstat"><div class="dstat-num" style="color:${color}">${value.toLocaleString()}</div>
     <div class="dstat-label">${label}</div></div>`;

  $('dashStats').innerHTML =
    card(d.total_users, 'Users', 'var(--accent-2)') +
    card(d.total_jobs, 'Jobs', '#60a5fa') +
    card(d.total_candidates, 'Resumes', '#e7e9ee') +
    card(d.shortlisted, '★ Shortlisted', 'var(--green)') +
    card(d.maybe, 'Maybe', 'var(--amber)') +
    card(d.rejected, 'Rejected', 'var(--red)') +
    card(d.pending, 'Pending', 'var(--accent)') +
    card(d.errors, 'Errors', 'var(--red)');

  if (!d.jobs.length) { $('dashJobs').innerHTML = '<p class="muted">No jobs yet.</p>'; return; }
  const rows = d.jobs.map((j) => {
    const rate = j.total ? Math.round((j.shortlisted / j.total) * 100) : 0;
    return `<div class="djob-row">
      <span class="djob-title">${escapeHtml(j.title)}</span>
      <span class="djob-cell">${j.total} resumes</span>
      <span class="djob-cell" style="color:var(--green)">${j.shortlisted} shortlisted</span>
      <span class="djob-cell">${j.pending ? `⏳ ${j.pending} pending` : '✓ done'}</span>
      <span class="djob-cell djob-rate">${rate}%</span>
    </div>`;
  }).join('');
  $('dashJobs').innerHTML =
    `<div class="djob-row djob-head">
       <span>Job</span><span class="djob-cell">Total</span>
       <span class="djob-cell">Shortlisted</span><span class="djob-cell">Status</span>
       <span class="djob-cell djob-rate">Pass rate</span>
     </div>` + rows;
}

// auth wiring
$('loginForm').onsubmit = doLogin;
$('logoutBtn').onclick = logout;
$('usersBtn').onclick = openUsers;
$('closeUsers').onclick = () => $('usersModal').classList.add('hidden');
$('addUserBtn').onclick = addUser;
$('dashBtn').onclick = openDashboard;
$('closeDash').onclick = () => $('dashModal').classList.add('hidden');
$('dashRefresh').onclick = loadDashboard;

// login tab wiring — picks which account TYPE you authenticate as
document.querySelectorAll('#loginMode .seg-btn').forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll('#loginMode .seg-btn').forEach((x) => x.classList.remove('active'));
    b.classList.add('active');
    setLoginTab(b.dataset.mode);
    stErr2(b.dataset.mode);
  };
});

// hint which seeded account to use per tab (optional helper)
function stErr2(mode) {
  $('loginName').placeholder = mode === 'student' ? 'student' : 'username';
}

// ════════════ STUDENT COACH FLOW ════════════
const student = { cvText: '', cvName: '', questions: [] };

function stErr(msg) {
  const e = $('stError');
  if (!msg) { e.classList.add('hidden'); return; }
  e.textContent = msg; e.classList.remove('hidden');
}

function liList(el, items, cls) {
  el.innerHTML = items.length
    ? items.map((t) => `<li${cls ? ` class="${cls}"` : ''}>${escapeHtml(t)}</li>`).join('')
    : '<li class="muted">—</li>';
}

async function stUploadCv(file) {
  $('stCvName').textContent = `Reading ${file.name}…`;
  const form = new FormData();
  form.append('file', file);
  try {
    const data = await api('/student/cv', { method: 'POST', body: form });
    student.cvText = data.cv_text;
    student.cvName = data.filename;
    $('stCvName').textContent = `✓ ${data.filename}`;
    stErr('');
  } catch (e) {
    student.cvText = '';
    $('stCvName').textContent = 'No CV uploaded yet.';
    stErr(e.message);
  }
}

async function stAnalyze() {
  const jd = $('stJd').value.trim();
  if (jd.length < 20) return stErr('Paste the target job description first.');
  if (student.cvText.length < 20) return stErr('Upload your CV first.');
  stErr('');
  const btn = $('stAnalyzeBtn');
  btn.disabled = true; btn.textContent = 'Analyzing…';
  try {
    const a = await api('/student/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jd, cv_text: student.cvText }),
    });
    renderAnalysis(a);
  } catch (e) { stErr(e.message); }
  finally { btn.disabled = false; btn.textContent = 'Analyze my CV'; }
}

function renderAnalysis(a) {
  $('stAnalysis').classList.remove('hidden');
  const color = a.match_score >= 75 ? 'var(--green)' : a.match_score >= 50 ? 'var(--amber)' : 'var(--red)';
  const badge = $('stScoreBadge');
  badge.textContent = a.match_score;
  badge.style.background = hexFade(color); badge.style.color = color;
  const vmap = { strong: 'Strong match', needs_work: 'Needs work', weak: 'Weak match' };
  $('stVerdict').textContent = vmap[a.verdict] || a.verdict;
  $('stSummary').textContent = a.summary;
  liList($('stStrengths'), a.strengths, 'li-good');
  liList($('stGaps'), a.gaps, 'li-bad');
  liList($('stSuggest'), a.suggestions);
  $('stKeywords').innerHTML = a.missing_keywords.length
    ? a.missing_keywords.map((k) => `<span class="chip">${escapeHtml(k)}</span>`).join('')
    : '<span class="muted">—</span>';

  // clarifying questions
  student.questions = a.clarifying_questions || [];
  if (student.questions.length) {
    $('stQuestions').classList.remove('hidden');
    $('stQList').innerHTML = student.questions.map((q, i) => `
      <div class="st-q">
        <div class="st-q-label">${i + 1}. ${escapeHtml(q)}</div>
        <textarea class="st-q-input" data-qi="${i}" rows="2" placeholder="Your answer (optional)…"></textarea>
      </div>`).join('');
  } else {
    $('stQuestions').classList.add('hidden');
  }
  $('stAnalysis').scrollIntoView({ behavior: 'smooth' });
}

async function stTailor() {
  const jd = $('stJd').value.trim();
  const answers = student.questions.map((q, i) => ({
    question: q,
    answer: (document.querySelector(`.st-q-input[data-qi="${i}"]`)?.value || '').trim(),
  }));
  const btn = $('stTailorBtn');
  btn.disabled = true; btn.textContent = 'Rewriting…';
  try {
    const t = await api('/student/tailor', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jd, cv_text: student.cvText, answers }),
    });
    $('stResume').classList.remove('hidden');
    $('stResumeText').textContent = t.resume_markdown;
    liList($('stChanges'), t.change_notes);
    $('stResume').scrollIntoView({ behavior: 'smooth' });
  } catch (e) { stErr(e.message); }
  finally { btn.disabled = false; btn.textContent = 'Tailor my resume'; }
}

async function stPrep() {
  const jd = $('stJd').value.trim();
  if (jd.length < 20) return stErr('Paste the target job description first.');
  const btn = $('stPrepBtn');
  btn.disabled = true; btn.textContent = 'Generating…';
  try {
    const p = await api('/student/prep', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jd, cv_text: student.cvText }),
    });
    $('stPrep').classList.remove('hidden');
    $('stConcepts').innerHTML = p.key_concepts.length
      ? p.key_concepts.map((c) => `<div class="prep-item"><b>${escapeHtml(c.topic)}</b>${c.why ? ` — <span class="muted">${escapeHtml(c.why)}</span>` : ''}</div>`).join('')
      : '<p class="muted">—</p>';
    $('stQuestionsPrep').innerHTML = p.questions.length
      ? p.questions.map((q) => `<div class="prep-item">• ${escapeHtml(q.question)}${q.answer_hint ? `<div class="muted prep-hint">↳ ${escapeHtml(q.answer_hint)}</div>` : ''}</div>`).join('')
      : '<p class="muted">—</p>';
    liList($('stProjectTips'), p.project_tips);
  } catch (e) { stErr(e.message); }
  finally { btn.disabled = false; btn.textContent = 'Generate prep'; }
}

// student wiring
$('stCvInput').onchange = (e) => { if (e.target.files[0]) stUploadCv(e.target.files[0]); e.target.value = ''; };
$('stAnalyzeBtn').onclick = stAnalyze;
$('stTailorBtn').onclick = stTailor;
$('stPrepBtn').onclick = stPrep;
$('stCopyResume').onclick = () => navigator.clipboard.writeText($('stResumeText').textContent || '');
$('stDownloadResume').onclick = () => {
  const blob = new Blob([$('stResumeText').textContent || ''], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'tailored-resume.md'; a.click();
  URL.revokeObjectURL(a.href);
};

// ── Boot ──
async function startApp() {
  await loadHealth();
  await loadJobs();
}

(async function init() {
  if (auth.token) {
    hideLogin();
    try { await startApp(); }
    catch { /* 401 handler already showed login */ }
  } else {
    showLogin();
  }
})();
