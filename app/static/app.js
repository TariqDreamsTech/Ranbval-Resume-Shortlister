// Ranbval Resume Shortlister — vanilla JS frontend

const $ = (id) => document.getElementById(id);
let activeJobId = null;
let threshold = 75;

// ── Auth state (token kept in localStorage) ──
const auth = {
  get token() { return localStorage.getItem('rs_token') || ''; },
  get role() { return localStorage.getItem('rs_role') || ''; },
  get name() { return localStorage.getItem('rs_name') || ''; },
  set(token, name, role) {
    localStorage.setItem('rs_token', token);
    localStorage.setItem('rs_name', name);
    localStorage.setItem('rs_role', role);
  },
  clear() {
    localStorage.removeItem('rs_token');
    localStorage.removeItem('rs_name');
    localStorage.removeItem('rs_role');
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
      body: JSON.stringify({ title, description }),
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
  $('threshNote').textContent = `Shortlist threshold: ${threshold}/100`;
  resetFilters();
  await loadCandidates();
  await loadJobs();
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

function renderCandidate(c) {
  const el = document.createElement('div');
  el.className = 'cand' + (c.recommended ? ' rec' : '');

  const badgeColor = scoreColor(c.score);
  const matched = (c.matched_requirements || []).map((m) => `<li class="li-good">${escapeHtml(m)}</li>`).join('');
  const missing = (c.missing_requirements || []).map((m) => `<li class="li-bad">${escapeHtml(m)}</li>`).join('');
  const flags = (c.red_flags || []).map((m) => `<li class="li-flag">${escapeHtml(m)}</li>`).join('');
  const skills = (c.key_skills || []).map((s) => `<span class="chip">${escapeHtml(s)}</span>`).join('');
  const years = c.years_experience != null ? `${c.years_experience} yrs exp` : 'exp N/A';

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
      <div class="detail-grid">
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

// ── Upload ──
async function uploadResume(file) {
  const status = $('uploadStatus');
  status.className = 'upload-status loading';
  status.classList.remove('hidden');
  status.textContent = `Screening "${file.name}" against the JD…`;

  const form = new FormData();
  form.append('file', file);
  try {
    await api(`/jobs/${activeJobId}/resumes`, { method: 'POST', body: form });
    status.classList.add('hidden');
    await loadCandidates();
    await loadJobs();
  } catch (e) {
    status.className = 'upload-status error';
    status.textContent = e.message;
  }
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
$('toggleJD').onclick = () => {
  const box = $('jvDesc');
  box.classList.toggle('hidden');
  $('toggleJD').textContent = box.classList.contains('hidden') ? 'View JD' : 'Hide JD';
};
$('fileInput').onchange = (e) => {
  const file = e.target.files[0];
  if (file) uploadResume(file);
  e.target.value = '';
};

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
  $('logoutBtn').classList.add('hidden');
  $('whoami').textContent = '';
  const err = $('loginError');
  if (msg) { err.textContent = msg; err.classList.remove('hidden'); }
  else { err.classList.add('hidden'); }
  setTimeout(() => $('loginName').focus(), 50);
}

function hideLogin() {
  $('loginOverlay').style.display = 'none';
  $('logoutBtn').classList.remove('hidden');
  $('whoami').textContent = `${auth.name} · ${auth.role}`;
  if (auth.role === 'admin') $('usersBtn').classList.remove('hidden');
  else $('usersBtn').classList.add('hidden');
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
      body: JSON.stringify({ name, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Login failed');
    auth.set(data.token, data.name, data.role);
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
    row.innerHTML = `
      <input class="u-name" value="${escapeAttr(u.name)}" />
      <input class="u-pass" value="${escapeAttr(u.password)}" />
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
  if (!name || !password) { alert('Enter a username and password.'); return; }
  try {
    await api('/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, password, role }),
    });
    $('newUserName').value = ''; $('newUserPass').value = '';
    await loadUsers();
  } catch (e) { alert(e.message); }
}

function escapeAttr(s) { return String(s ?? '').replace(/"/g, '&quot;'); }

// auth wiring
$('loginForm').onsubmit = doLogin;
$('logoutBtn').onclick = logout;
$('usersBtn').onclick = openUsers;
$('closeUsers').onclick = () => $('usersModal').classList.add('hidden');
$('addUserBtn').onclick = addUser;

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
