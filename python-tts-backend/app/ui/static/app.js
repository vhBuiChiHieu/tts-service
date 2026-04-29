const form = document.getElementById('tts-form');
const fileInput = document.getElementById('file');
const speedInput = document.getElementById('speed');
const submitButton = document.getElementById('submit');
const refreshJobsButton = document.getElementById('refresh-jobs');
const statusFilter = document.getElementById('status-filter');
const pageSizeSelect = document.getElementById('page-size');
const prevPageButton = document.getElementById('prev-page');
const nextPageButton = document.getElementById('next-page');
const pageIndicator = document.getElementById('page-indicator');
const paginationSummary = document.getElementById('pagination-summary');
const trackingDrawer = document.getElementById('tracking-drawer');
const tabButtons = Array.from(document.querySelectorAll('[data-tab]'));
const tabPanels = Array.from(document.querySelectorAll('[data-panel]'));
const jobIdText = document.getElementById('job-id');
const statusText = document.getElementById('status');
const chunksText = document.getElementById('chunks');
const updatedAtText = document.getElementById('updated-at');
const statusBadge = document.getElementById('status-badge');
const progressBar = document.getElementById('progress');
const progressText = document.getElementById('progress-text');
const resultText = document.getElementById('result');
const errorText = document.getElementById('error');
const cancelButton = document.getElementById('cancel-btn');
const retryButton = document.getElementById('retry-btn');
const detailActions = document.getElementById('detail-actions');
const openOutputLink = document.getElementById('open-output-link');
const jobsList = document.getElementById('jobs-list');
const jobsSummary = document.getElementById('jobs-summary');
const jobsEmpty = document.getElementById('jobs-empty');
const jobsStatusSummary = document.getElementById('jobs-status-summary');

let pollTimer = null;
let selectedJobId = null;
let currentPage = 1;
let totalPages = 1;
let currentPageSize = Number(pageSizeSelect.value);
const defaultCollapsedGroups = ['SUCCEEDED', 'CANCELLED'];
const collapsedGroups = new Set(defaultCollapsedGroups);
const storageKey = 'local-tts-app-jobs-ui';
const allowedStatuses = ['ALL', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED'];
const allowedPageSizes = new Set(['10', '20', '50']);

function readStoredUiState() {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function writeStoredUiState() {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify({
      statusFilter: statusFilter.value,
      pageSize: String(currentPageSize),
      collapsedGroups: Array.from(collapsedGroups),
    }));
  } catch {
    // Ignore localStorage failures on unsupported environments.
  }
}

function restoreUiState() {
  const stored = readStoredUiState();
  if (!stored) return;

  if (allowedStatuses.includes(stored.statusFilter)) {
    statusFilter.value = stored.statusFilter;
  }

  if (allowedPageSizes.has(String(stored.pageSize))) {
    pageSizeSelect.value = String(stored.pageSize);
    currentPageSize = Number(stored.pageSize);
  }

  collapsedGroups.clear();
  const storedGroups = Array.isArray(stored.collapsedGroups) ? stored.collapsedGroups : defaultCollapsedGroups;
  storedGroups
    .filter((status) => allowedStatuses.includes(status) && status !== 'ALL')
    .forEach((status) => collapsedGroups.add(status));
}

restoreUiState();

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function activateTab(tabName) {
  tabButtons.forEach((button) => {
    const active = button.dataset.tab === tabName;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-selected', String(active));
  });

  tabPanels.forEach((panel) => {
    panel.classList.toggle('hidden', panel.dataset.panel !== tabName);
  });
}

function setStatusBadge(element, state) {
  const normalizedState = state || 'QUEUED';
  element.textContent = normalizedState;
  element.className = 'badge';

  if (normalizedState === 'RUNNING') {
    element.classList.add('status-running');
    return;
  }
  if (normalizedState === 'SUCCEEDED') {
    element.classList.add('status-succeeded');
    return;
  }
  if (normalizedState === 'FAILED') {
    element.classList.add('status-failed');
    return;
  }
  if (normalizedState === 'CANCELLED') {
    element.classList.add('status-cancelled');
    return;
  }
  element.classList.add('status-queued');
}

function setProgressState(state) {
  progressBar.classList.remove('progress-state-running', 'progress-state-succeeded', 'progress-state-failed', 'progress-state-cancelled');

  if (state === 'RUNNING') progressBar.classList.add('progress-state-running');
  if (state === 'SUCCEEDED') progressBar.classList.add('progress-state-succeeded');
  if (state === 'FAILED') progressBar.classList.add('progress-state-failed');
  if (state === 'CANCELLED') progressBar.classList.add('progress-state-cancelled');
}

function formatDate(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('vi-VN');
}

function fileUrlFromPath(filePath) {
  if (!filePath) return '#';
  const normalized = filePath.replace(/\\/g, '/');
  if (/^[A-Za-z]:\//.test(normalized)) {
    return `file:///${encodeURI(normalized)}`;
  }
  return `file://${encodeURI(normalized)}`;
}

function isRetryable(status) {
  return status === 'FAILED' || status === 'CANCELLED';
}

function isCancellable(status) {
  return status === 'QUEUED' || status === 'RUNNING';
}

function updatePaginationControls(page, pages, total) {
  currentPage = page;
  totalPages = Math.max(1, pages || 1);
  pageIndicator.textContent = `Trang ${currentPage} / ${totalPages}`;
  paginationSummary.textContent = `Tổng ${total} job`;
  prevPageButton.disabled = currentPage <= 1;
  nextPageButton.disabled = currentPage >= totalPages;
}

function highlightSelectedJob() {
  document.querySelectorAll('.job-card').forEach((card) => {
    card.classList.toggle('is-selected', card.dataset.jobId === selectedJobId);
  });
}

function updateTracking(job) {
  selectedJobId = job.job_id;
  trackingDrawer.classList.remove('hidden');
  jobIdText.textContent = job.job_id;
  statusText.textContent = job.status;
  chunksText.textContent = `${job.progress?.processed_chunks ?? 0}/${job.progress?.total_chunks ?? 0}`;
  updatedAtText.textContent = formatDate(job.updated_at);
  setStatusBadge(statusBadge, job.status);

  const progress = Math.max(0, Math.min(100, job.progress?.progress_pct ?? 0));
  progressBar.style.width = `${progress}%`;
  progressText.textContent = `${progress}%`;
  setProgressState(job.status);

  cancelButton.classList.toggle('hidden', !isCancellable(job.status));
  retryButton.classList.toggle('hidden', !isRetryable(job.status));

  if (job.result?.file_path) {
    openOutputLink.href = fileUrlFromPath(job.result.file_path);
    detailActions.classList.remove('hidden');
    resultText.textContent = `Hoàn thành: ${job.result.file_path}`;
    resultText.className = 'message success';
  } else {
    openOutputLink.href = '#';
    detailActions.classList.add('hidden');
    resultText.textContent = '';
    resultText.className = 'message muted';
  }

  if (job.status === 'FAILED') {
    errorText.textContent = job.error?.message || 'Job thất bại';
  } else if (job.status === 'CANCELLED') {
    errorText.textContent = 'Job đã bị hủy';
  } else {
    errorText.textContent = '';
  }

  highlightSelectedJob();
  activateTab('jobs');

  if (isCancellable(job.status)) {
    ensurePolling(job.job_id);
  } else if (selectedJobId === job.job_id) {
    stopPolling();
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || 'Yêu cầu thất bại');
  }
  return response.json();
}

async function fetchJob(jobId) {
  const job = await fetchJson(`/v1/jobs/${jobId}`);
  updateTracking(job);
  await loadJobs(false);
}

function ensurePolling(jobId) {
  stopPolling();
  pollTimer = setInterval(() => {
    fetchJob(jobId).catch((error) => {
      stopPolling();
      errorText.textContent = error.message;
      submitButton.disabled = false;
      submitButton.textContent = 'Tạo job';
    });
  }, 1000);
}

function statusClassName(status) {
  const normalized = (status || 'QUEUED').toLowerCase();
  return `status-${normalized}`;
}

function statusLabel(status) {
  if (status === 'RUNNING') return 'Đang chạy';
  if (status === 'QUEUED') return 'Đang chờ';
  if (status === 'FAILED') return 'Cần xử lý';
  if (status === 'SUCCEEDED') return 'Hoàn tất';
  if (status === 'CANCELLED') return 'Đã hủy';
  return status || 'Khác';
}

function groupOrder(status) {
  if (status === 'RUNNING') return 0;
  if (status === 'QUEUED') return 1;
  if (status === 'FAILED') return 2;
  if (status === 'CANCELLED') return 3;
  if (status === 'SUCCEEDED') return 4;
  return 5;
}

function groupJobs(items) {
  const groups = new Map();

  items.forEach((job) => {
    const key = job.status || 'QUEUED';
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key).push(job);
  });

  return Array.from(groups.entries())
    .sort(([left], [right]) => groupOrder(left) - groupOrder(right))
    .map(([status, jobs]) => ({
      status,
      label: statusLabel(status),
      jobs,
      collapsed: collapsedGroups.has(status),
    }));
}

function jobCounts(items) {
  return ['RUNNING', 'QUEUED', 'FAILED', 'SUCCEEDED', 'CANCELLED'].map((status) => ({
    status,
    label: statusLabel(status),
    count: items.filter((job) => job.status === status).length,
  }));
}

function renderJobsStatusSummary(items) {
  jobsStatusSummary.innerHTML = jobCounts(items)
    .map(({ status, label, count }) => `
      <article class="status-summary-card status-summary-${status.toLowerCase()}">
        <span class="badge ${statusClassName(status)}">${status}</span>
        <strong>${count}</strong>
        <span>${label}</span>
      </article>
    `)
    .join('');
}

function toggleGroup(status) {
  if (collapsedGroups.has(status)) {
    collapsedGroups.delete(status);
    writeStoredUiState();
    return;
  }
  collapsedGroups.add(status);
  writeStoredUiState();
}

function ensureExpandedForSelectedJob(items) {
  if (!selectedJobId) return;
  const selectedJob = items.find((job) => job.job_id === selectedJobId);
  if (!selectedJob) return;
  collapsedGroups.delete(selectedJob.status || 'QUEUED');
}

function groupToggleLabel(group) {
  return group.collapsed ? 'Mở nhóm' : 'Thu gọn';
}

function groupToggleIcon(group) {
  return group.collapsed ? '▸' : '▾';
}

function shouldShowGroupList(group) {
  return !group.collapsed;
}

function shouldShowRunningHint(group) {
  return group.status === 'RUNNING' && !group.collapsed;
}

function shouldShowGroupCount(group) {
  return `${group.jobs.length} job`;
}

function shouldShowSummary(items) {
  return items.length > 0;
}

function updateSummaryVisibility(items) {
  jobsStatusSummary.classList.toggle('hidden', !shouldShowSummary(items));
}

function escapeAttribute(value) {
  return String(value).replace(/"/g, '&quot;');
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function groupToggleButton(group) {
  const expanded = !group.collapsed;
  return `
    <button
      class="secondary-btn queue-group-toggle"
      type="button"
      data-action="toggle-group"
      data-group-status="${escapeAttribute(group.status)}"
      aria-expanded="${String(expanded)}"
      aria-label="${escapeAttribute(groupToggleLabel(group))} ${escapeAttribute(group.label)}"
    >
      <span class="queue-group-toggle-icon">${groupToggleIcon(group)}</span>
      <span>${groupToggleLabel(group)}</span>
    </button>
  `;
}

function groupListMarkup(group) {
  if (!shouldShowGroupList(group)) {
    return '';
  }
  return `<div class="queue-group-list">${group.jobs.map(jobCard).join('')}</div>`;
}

function runningHintMarkup(group) {
  if (!shouldShowRunningHint(group)) {
    return '';
  }
  return '<span class="queue-group-hint">Được ưu tiên hiển thị để theo dõi realtime.</span>';
}

function groupCountMarkup(group) {
  return `<span class="queue-group-count">${shouldShowGroupCount(group)}</span>`;
}

function jobCard(job) {
  const openFile = job.result?.file_path
    ? `<a class="link-btn" href="${fileUrlFromPath(job.result.file_path)}" target="_blank" rel="noopener">Mở file</a>`
    : '';
  const retryButton = isRetryable(job.status)
    ? `<button class="secondary-btn" type="button" data-action="retry" data-job-id="${job.job_id}">Retry</button>`
    : '';
  const cancelButton = isCancellable(job.status)
    ? `<button class="cancel-btn" type="button" data-action="cancel" data-job-id="${job.job_id}">Hủy job</button>`
    : '';
  const progress = Math.max(0, Math.min(100, job.progress?.progress_pct ?? 0));

  return `
    <article class="job-card ${job.job_id === selectedJobId ? 'is-selected' : ''} ${job.status === 'RUNNING' ? 'is-running' : ''}" data-job-id="${job.job_id}">
      <div class="job-head">
        <div>
          <strong>${job.result?.file_name || job.job_id}</strong>
          <div class="helper">${job.job_id}</div>
        </div>
        <span class="badge ${statusClassName(job.status)}">${job.status}</span>
      </div>
      <div class="job-progress-row">
        <div>
          <strong>Tiến độ</strong>
          <span>${progress}%</span>
        </div>
        <div class="job-inline-progress" aria-hidden="true">
          <div class="job-inline-progress-fill ${statusClassName(job.status)}" style="width: ${progress}%"></div>
        </div>
      </div>
      <div class="job-meta">
        <div>
          <strong>Chunks</strong>
          <span>${job.progress?.processed_chunks ?? 0}/${job.progress?.total_chunks ?? 0}</span>
        </div>
        <div>
          <strong>Updated</strong>
          <span>${formatDate(job.updated_at)}</span>
        </div>
        <div>
          <strong>Output</strong>
          <span>${job.result?.file_name || '-'}</span>
        </div>
      </div>
      <div class="job-actions">
        <button class="secondary-btn" type="button" data-action="view" data-job-id="${job.job_id}">Xem chi tiết</button>
        ${retryButton}
        ${cancelButton}
        ${openFile}
      </div>
    </article>
  `;
}

function jobGroupSection(group) {
  return `
    <section class="queue-group queue-group-${group.status.toLowerCase()} ${group.collapsed ? 'is-collapsed' : ''}">
      <div class="queue-group-header">
        <div class="queue-group-title">
          <span class="badge ${statusClassName(group.status)}">${group.status}</span>
          <strong>${group.label}</strong>
          ${runningHintMarkup(group)}
        </div>
        <div class="queue-group-actions">
          ${groupCountMarkup(group)}
          ${groupToggleButton(group)}
        </div>
      </div>
      ${groupListMarkup(group)}
    </section>
  `;
}

async function loadJobs(resetPage = false) {
  if (resetPage) {
    currentPage = 1;
  }

  const payload = await fetchJson(`/v1/jobs?page=${currentPage}&size=${currentPageSize}`);
  const filter = statusFilter.value;
  const items = filter === 'ALL' ? payload.items : payload.items.filter((job) => job.status === filter);

  updateSummaryVisibility(items);
  renderJobsStatusSummary(items);
  ensureExpandedForSelectedJob(items);

  const groups = groupJobs(items);
  jobsSummary.textContent = `Hiển thị ${items.length} job trong ${groups.length} nhóm ở trang hiện tại.`;
  jobsEmpty.classList.toggle('hidden', items.length > 0);
  jobsList.innerHTML = groups.map(jobGroupSection).join('');
  updatePaginationControls(payload.page, payload.pages, payload.total);
  highlightSelectedJob();
}

async function createJobFromForm() {
  const file = fileInput.files[0];
  if (!file) throw new Error('Bạn chưa chọn file TXT');

  const speed = speedInput.value;
  const formData = new FormData();
  formData.append('file', file);

  return fetchJson(`/v1/jobs/tts-file-txt?speed=${encodeURIComponent(speed)}`, {
    method: 'POST',
    body: formData,
  });
}

async function retryJob(jobId) {
  return fetchJson(`/v1/jobs/retry/${jobId}`, { method: 'POST' });
}

async function cancelJob(jobId) {
  return fetchJson(`/v1/jobs/${jobId}/cancel`, { method: 'POST' });
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  stopPolling();
  errorText.textContent = '';
  resultText.textContent = '';
  resultText.className = 'message muted';
  submitButton.disabled = true;
  submitButton.textContent = 'Đang tạo job...';

  try {
    const created = await createJobFromForm();
    submitButton.textContent = 'Tạo job';
    submitButton.disabled = false;
    await fetchJob(created.job_id);
  } catch (error) {
    errorText.textContent = error.message;
    submitButton.textContent = 'Tạo job';
    submitButton.disabled = false;
  }
});

cancelButton.addEventListener('click', async () => {
  if (!selectedJobId) return;
  cancelButton.disabled = true;
  try {
    const job = await cancelJob(selectedJobId);
    updateTracking(job);
    await loadJobs(false);
  } catch (error) {
    errorText.textContent = error.message;
  } finally {
    cancelButton.disabled = false;
  }
});

retryButton.addEventListener('click', async () => {
  if (!selectedJobId) return;
  retryButton.disabled = true;
  try {
    const job = await retryJob(selectedJobId);
    await fetchJob(job.job_id);
  } catch (error) {
    errorText.textContent = error.message;
  } finally {
    retryButton.disabled = false;
  }
});

refreshJobsButton.addEventListener('click', () => {
  loadJobs(false).catch((error) => {
    jobsSummary.textContent = error.message;
  });
});

statusFilter.addEventListener('change', () => {
  writeStoredUiState();
  loadJobs(true).catch((error) => {
    jobsSummary.textContent = error.message;
  });
});

pageSizeSelect.addEventListener('change', () => {
  currentPageSize = Number(pageSizeSelect.value);
  writeStoredUiState();
  loadJobs(true).catch((error) => {
    jobsSummary.textContent = error.message;
  });
});

prevPageButton.addEventListener('click', () => {
  if (currentPage <= 1) return;
  currentPage -= 1;
  loadJobs(false).catch((error) => {
    jobsSummary.textContent = error.message;
  });
});

nextPageButton.addEventListener('click', () => {
  if (currentPage >= totalPages) return;
  currentPage += 1;
  loadJobs(false).catch((error) => {
    jobsSummary.textContent = error.message;
  });
});

tabButtons.forEach((button) => {
  button.addEventListener('click', () => {
    activateTab(button.dataset.tab);
  });
});

jobsList.addEventListener('click', async (event) => {
  const target = event.target.closest('[data-action]');
  if (!target) return;

  const action = target.dataset.action;

  if (action === 'toggle-group') {
    const status = target.dataset.groupStatus;
    if (!status) return;
    toggleGroup(status);
    loadJobs(false).catch((error) => {
      jobsSummary.textContent = error.message;
    });
    return;
  }

  const jobId = target.dataset.jobId;
  if (!jobId) return;

  target.disabled = true;
  try {
    if (action === 'view') {
      await fetchJob(jobId);
      return;
    }
    if (action === 'retry') {
      const job = await retryJob(jobId);
      await fetchJob(job.job_id);
      return;
    }
    if (action === 'cancel') {
      const job = await cancelJob(jobId);
      updateTracking(job);
      await loadJobs(false);
    }
  } catch (error) {
    errorText.textContent = error.message;
  } finally {
    target.disabled = false;
  }
});

activateTab('create');
loadJobs(true).catch((error) => {
  jobsSummary.textContent = error.message;
});
