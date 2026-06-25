// Ranbval Resume Shortlister — vanilla JS frontend

const $ = (id) => document.getElementById(id);
let activeJobId = null;
let threshold = 75;

// ── API helpers ──
async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, opts);
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
async function loadJobs() {
  const jobs = await api('/jobs');
  const list = $('jobList');
  list.innerHTML = '';
  if (jobs.length === 0) {
    list.innerHTML = '<p class="muted" style="padding:4px 6px;">No jobs yet.</p>';
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
  await loadCandidates();
  await loadJobs();
}

// ── Candidates ──
async function loadCandidates() {
  const cands = await api(`/jobs/${activeJobId}/candidates`);
  $('candCount').textContent = cands.length;
  const list = $('candidateList');
  list.innerHTML = '';
  if (cands.length === 0) {
    list.innerHTML = '<p class="muted">No resumes screened yet. Upload one above.</p>';
    return;
  }
  cands.forEach((c) => list.appendChild(renderCandidate(c)));
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

(async function init() {
  await loadHealth();
  await loadJobs();
})();
