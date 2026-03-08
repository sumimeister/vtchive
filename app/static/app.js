const API = '';
const SSE_URL = '/api/logs/stream';

const state = {
  currentPage: 'dashboard',
  archivePage: 1,
  archivePageSize: 20,
  archiveFilter: { status: '', q: '' },
  settings: {},
};

async function apiFetch(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

function toast(msg, type = 'ok') {
  const el = document.createElement('div');
  el.className = `toast${type === 'error' ? ' error' : type === 'warn' ? ' warn' : ''}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function fmtDatetime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('zh-TW', { hour12: false });
}

function fmtTime(iso) {
  if (!iso) return '--:--';
  const d = new Date(iso);
  return d.toLocaleTimeString('zh-TW', { hour12: false, hour: '2-digit', minute: '2-digit' });
}

function statusBadge(status) {
  const map = {
    WAIT: ['badge-wait', '等待中'],
    PENDING: ['badge-wait', '等待中'],
    DOWNLOADING: ['badge-downloading', '下載中'],
    DONE: ['badge-done', '完成'],
    FAILED: ['badge-failed', '失敗'],
  };
  const [cls, label] = map[status] || ['badge-wait', status];
  return `<span class="badge ${cls}"><span class="badge-dot"></span>${label}</span>`;
}

function closeMobileNav() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('active');
}

function navigate(page) {
  state.currentPage = page;
  document.querySelectorAll('.nav-item').forEach((el) => {
    el.classList.toggle('active', el.dataset.page === page);
  });
  document.querySelectorAll('.page').forEach((el) => {
    el.classList.toggle('active', el.id === `page-${page}`);
  });
  closeMobileNav();

  if (page === 'dashboard') loadDashboard();
  if (page === 'archives') loadArchives();
  if (page === 'channels') loadChannels();
  if (page === 'settings') loadSettings();
  if (page === 'logs') ensureWs();
}

document.getElementById('btn-menu').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebar-overlay').classList.toggle('active');
});

document.getElementById('sidebar-overlay').addEventListener('click', closeMobileNav);

document.querySelectorAll('.nav-item').forEach((btn) => {
  btn.addEventListener('click', () => navigate(btn.dataset.page));
});

let es = null;
let esRetry = 0;

function ensureWs() {
  if (es && es.readyState === EventSource.OPEN) return;
  startWs();
}

function startWs() {
  if (es) {
    es.onopen = null;
    es.onerror = null;
    es.close();
  }
  es = new EventSource(SSE_URL);

  es.onopen = () => {
    esRetry = 0;
    removePlaceholderLog();
  };

  es.onmessage = (evt) => {
    const data = JSON.parse(evt.data);
    appendLogLine(data);
    if (state.currentPage === 'dashboard') appendRecentLog(data);
  };

  es.onerror = () => {
    es.close();
    const delay = Math.min(1000 * 2 ** esRetry, 30000);
    esRetry++;
    setTimeout(startWs, delay);
  };
}

function removePlaceholderLog() {
  const empty = document.querySelector('.log-empty');
  if (empty) empty.remove();
}

function appendLogLine(data) {
  const terminal = document.getElementById('log-terminal');
  const div = document.createElement('div');
  div.className = `log-line ${data.level}-line`;
  div.innerHTML = `
    <span class="log-line-time">${fmtTime(data.created_at)}</span>
    <span class="log-line-level ${data.level}">${data.level}</span>
    <span class="log-line-msg">${escHtml(data.message)}</span>`;
  terminal.appendChild(div);
  if (terminal.scrollHeight - terminal.scrollTop - terminal.clientHeight < 80) {
    terminal.scrollTop = terminal.scrollHeight;
  }
  while (terminal.children.length > 500) terminal.removeChild(terminal.firstChild);
}

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function loadDashboard() {
  await Promise.all([loadStats(), loadMonitorStatus(), loadRecentLogs()]);
}

async function loadStats() {
  try {
    const s = await apiFetch('/api/archives/stats');
    document.getElementById('stat-downloading').textContent = s.downloading + s.pending;
    document.getElementById('stat-wait').textContent = s.wait;
    document.getElementById('stat-done').textContent = s.done;
    document.getElementById('stat-failed').textContent = s.failed;
  } catch (e) {
    console.warn('loadStats', e);
  }
}

async function loadMonitorStatus() {
  try {
    const m = await apiFetch('/api/monitor/status');
    document.getElementById('m-running').textContent = m.running ? '● 運行中' : '○ 已停止';
    document.getElementById('m-running').style.color = m.running ? 'var(--accent)' : 'var(--danger)';
    document.getElementById('m-last').textContent = fmtDatetime(m.last_checked);
    document.getElementById('m-next').textContent = fmtDatetime(m.next_check);
    document.getElementById('m-active').textContent = m.active_downloads;

    const badge = document.getElementById('monitor-badge');
    badge.classList.toggle('offline', !m.running);
    document.getElementById('monitor-status-text').textContent = m.running ? '監控中' : '已停止';
    const dot = document.getElementById('mobile-monitor-dot');
    if (dot) dot.classList.toggle('offline', !m.running);
  } catch (e) {
    console.warn('loadMonitorStatus', e);
    document.getElementById('m-running').textContent = '— 後端離線';
    document.getElementById('m-running').style.color = 'var(--text-muted)';
    document.getElementById('m-last').textContent = '—';
    document.getElementById('m-next').textContent = '—';
    document.getElementById('m-active').textContent = '—';

    const badge = document.getElementById('monitor-badge');
    badge.classList.add('offline');
    document.getElementById('monitor-status-text').textContent = '後端離線';
    const dot = document.getElementById('mobile-monitor-dot');
    if (dot) dot.classList.add('offline');
  }
}

async function loadRecentLogs() {
  try {
    const logs = await apiFetch('/api/logs?limit=20');
    const container = document.getElementById('recent-logs');
    if (!logs.length) {
      container.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px 0">尚無日誌</div>';
      return;
    }
    container.innerHTML = [...logs]
      .reverse()
      .map(
        (l) => `
      <div class="recent-log-item level-${l.level}">
        <span class="log-time">${fmtTime(l.created_at)}</span>
        <span class="log-msg">${escHtml(l.message)}</span>
      </div>`,
      )
      .join('');
  } catch (e) {
    console.warn('loadRecentLogs', e);
  }
}

function appendRecentLog(data) {
  const container = document.getElementById('recent-logs');
  const empty = container.querySelector('[style]');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.className = `recent-log-item level-${data.level}`;
  div.innerHTML = `
    <span class="log-time">${fmtTime(data.created_at)}</span>
    <span class="log-msg">${escHtml(data.message)}</span>`;
  container.insertBefore(div, container.firstChild);
  while (container.children.length > 20) container.removeChild(container.lastChild);
}

document.getElementById('btn-trigger').addEventListener('click', async () => {
  try {
    await apiFetch('/api/monitor/trigger', { method: 'POST' });
    toast('已觸發監控輪詢');
    setTimeout(loadDashboard, 2000);
  } catch (e) {
    toast(e.message, 'error');
  }
});

document.querySelectorAll('.stat-card[data-status]').forEach((card) => {
  card.addEventListener('click', () => {
    const status = card.dataset.status;
    document.getElementById('archive-status-filter').value = status;
    document.getElementById('archive-search').value = '';
    state.archiveFilter.status = status;
    state.archiveFilter.q = '';
    state.archivePage = 1;
    navigate('archives');
  });
});

async function loadArchives() {
  const { status, q } = state.archiveFilter;
  const params = new URLSearchParams({
    page: state.archivePage,
    page_size: state.archivePageSize,
  });
  if (status) params.set('status', status);
  if (q) params.set('q', q);

  try {
    const data = await apiFetch(`/api/archives?${params}`);
    renderArchivesTable(data);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderArchivesTable(data) {
  const tbody = document.getElementById('archives-tbody');
  if (!data.items.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:32px">無資料</td></tr>`;
  } else {
    tbody.innerHTML = data.items
      .map(
        (a) => `
      <tr>
        <td class="vid-cell"><a href="https://youtube.com/watch?v=${a.vid}" target="_blank">${a.vid}</a></td>
        <td class="title-cell" title="${escHtml(a.title)}">${escHtml(a.title)}</td>
        <td>${escHtml(a.channel_name)}</td>
        <td>${a.topic ? `<span style="color:var(--info);font-family:var(--font-mono);font-size:11px">${escHtml(a.topic)}</span>` : '—'}</td>
        <td class="time-cell">${fmtDatetime(a.start_at)}</td>
        <td>${statusBadge(a.status)}</td>
        <td>
          <div class="action-btns">
            ${
              a.status === 'FAILED'
                ? `<button class="btn-icon" data-action="retry" data-vid="${a.vid}">↺ 重試</button>
                  <button class="btn-icon success" data-action="mark-done" data-vid="${a.vid}">✔ 標記完成</button>`
                : ''
            }
            <button class="btn-icon danger" data-action="delete" data-vid="${a.vid}">✕</button>
          </div>
        </td>
      </tr>`,
      )
      .join('');
  }

  const totalPages = Math.ceil(data.total / state.archivePageSize);
  const pg = document.getElementById('archives-pagination');
  pg.innerHTML = `
    <span>共 ${data.total} 筆，第 ${data.page} / ${totalPages} 頁</span>
    <button class="btn-sm" id="pg-prev" ${data.page <= 1 ? 'disabled style="opacity:.4"' : ''}>‹ 上一頁</button>
    <button class="btn-sm" id="pg-next" ${data.page >= totalPages ? 'disabled style="opacity:.4"' : ''}>下一頁 ›</button>`;

  document.getElementById('pg-prev')?.addEventListener('click', () => {
    if (state.archivePage > 1) {
      state.archivePage--;
      loadArchives();
    }
  });
  document.getElementById('pg-next')?.addEventListener('click', () => {
    if (state.archivePage < totalPages) {
      state.archivePage++;
      loadArchives();
    }
  });
}

document.getElementById('archives-tbody').addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const { action, vid } = btn.dataset;

  if (action === 'retry') {
    try {
      await apiFetch(`/api/archives/${vid}/retry`, { method: 'POST' });
      toast(`已排程重試 ${vid}`);
      loadArchives();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  if (action === 'mark-done') {
    if (!confirm(`確定要將 ${vid} 標記為「已完成」嗎？`)) return;
    try {
      await apiFetch(`/api/archives/${vid}/mark-done`, { method: 'POST' });
      toast(`已將 ${vid} 標記為完成`);
      loadArchives();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  if (action === 'delete') {
    if (!confirm(`確定要刪除封存紀錄 ${vid} 嗎？`)) return;
    try {
      await apiFetch(`/api/archives/${vid}`, { method: 'DELETE' });
      toast(`已刪除 ${vid}`);
      loadArchives();
    } catch (err) {
      toast(err.message, 'error');
    }
  }
});

let archiveSearchTimer;
document.getElementById('archive-search').addEventListener('input', (e) => {
  clearTimeout(archiveSearchTimer);
  archiveSearchTimer = setTimeout(() => {
    state.archiveFilter.q = e.target.value;
    state.archivePage = 1;
    loadArchives();
  }, 400);
});

document.getElementById('archive-status-filter').addEventListener('change', (e) => {
  state.archiveFilter.status = e.target.value;
  state.archivePage = 1;
  loadArchives();
});

async function loadChannels() {
  try {
    const channels = await apiFetch('/api/channels');
    renderChannels(channels);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderChannels(channels) {
  const grid = document.getElementById('channels-grid');
  if (!channels.length) {
    grid.innerHTML = `<p style="color:var(--text-muted);font-size:13px">尚未新增任何頻道。輸入 Holodex 頻道 ID 來開始監控。</p>`;
    return;
  }
  grid.innerHTML = channels
    .map(
      (ch) => `
    <div class="channel-card">
      ${
        ch.thumbnail_url
          ? `<img class="channel-avatar" src="${ch.thumbnail_url}" alt="${escHtml(ch.channel_name)}" onerror="this.style.display='none'">`
          : `<div class="channel-avatar-placeholder">◈</div>`
      }
      <div class="channel-info">
        <div class="channel-name">${escHtml(ch.channel_name)}</div>
        ${ch.english_name ? `<div class="channel-id">${escHtml(ch.english_name)}</div>` : ''}
        <div class="channel-id">${escHtml(ch.channel_id)}</div>
        ${ch.org ? `<div class="channel-org">${escHtml(ch.org)}</div>` : ''}
      </div>
      <button class="channel-remove" data-channel-id="${ch.channel_id}" title="移除頻道">✕</button>
    </div>`,
    )
    .join('');
}

document.getElementById('channels-grid').addEventListener('click', async (e) => {
  const btn = e.target.closest('.channel-remove');
  if (!btn) return;
  const cid = btn.dataset.channelId;
  if (!confirm(`確定要移除頻道 ${cid} 嗎？`)) return;
  try {
    await apiFetch(`/api/channels/${cid}`, { method: 'DELETE' });
    toast('頻道已移除');
    loadChannels();
  } catch (err) {
    toast(err.message, 'error');
  }
});

document.getElementById('btn-add-channel').addEventListener('click', async () => {
  const input = document.getElementById('new-channel-id');
  const cid = input.value.trim();
  if (!cid) return;
  try {
    await apiFetch('/api/channels', {
      method: 'POST',
      body: JSON.stringify({ channel_id: cid }),
    });
    input.value = '';
    toast('頻道新增成功');
    loadChannels();
  } catch (err) {
    toast(err.message, 'error');
  }
});

const SETTING_LABELS = {
  holodex_token: 'Holodex API Token',
  allowed_topics: '允許的主題',
  monitor_interval: '監控間隔（秒）',
  max_concurrent_downloads: '最大並行下載數',
  schedule_window_before: '預排提前天數',
  schedule_window_after: '過時時數',
  timezone: '時區',
};

async function loadSettings() {
  try {
    const settings = await apiFetch('/api/settings');
    state.settings = Object.fromEntries(settings.map((s) => [s.key, s]));
    renderSettings(settings);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderSettings(settings) {
  const form = document.getElementById('settings-form');
  form.innerHTML = settings
    .map(
      (s) => `
    <div class="setting-row">
      <div class="setting-key">${SETTING_LABELS[s.key] || s.key}</div>
      <div class="setting-desc">${escHtml(s.description || '')}</div>
      <input
        class="input-text full-width"
        type="${s.key.includes('token') ? 'password' : 'text'}"
        data-key="${s.key}"
        value="${escHtml(s.value)}"
      />
    </div>`,
    )
    .join('');
}

document.getElementById('btn-save-settings').addEventListener('click', async () => {
  const inputs = document.querySelectorAll('#settings-form input[data-key]');
  const pairs = {};
  inputs.forEach((inp) => {
    pairs[inp.dataset.key] = inp.value;
  });

  try {
    await apiFetch('/api/settings', {
      method: 'PUT',
      body: JSON.stringify({ settings: pairs }),
    });
    toast('設定已儲存');
  } catch (err) {
    toast(err.message, 'error');
  }
});

document.getElementById('btn-clear-logs').addEventListener('click', () => {
  const terminal = document.getElementById('log-terminal');
  terminal.innerHTML = '<div class="log-empty">已清除</div>';
});

setInterval(() => {
  if (state.currentPage === 'dashboard') loadStats();
}, 10000);

setInterval(() => {
  if (state.currentPage === 'dashboard') loadMonitorStatus();
}, 15000);

startWs();
loadDashboard();
