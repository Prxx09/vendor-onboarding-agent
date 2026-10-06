const state = {
  cases: [],
  audit: [],
  selectedCase: null,
  threshold: 82,
  documentName: "",
};

const fallbackCases = [
  {
    id: "VO-OFFLINE",
    vendor_name: "Offline Demo Vendor",
    category: "General",
    status: "HUMAN_REVIEW",
    confidence: 76,
    risk_level: "Medium",
    document: "offline-demo.pdf",
    submitted_at: new Date().toISOString(),
    assigned_to: "Vendor Risk Reviewer",
    extracted_fields: {
      legal_name: "Offline Demo Vendor",
      tax_id: "27ABCDE1234F1Z5",
      pan: "ABCDE1234F",
      bank_account: "XXXXXX1234",
      ifsc: "HDFC0001342",
      registered_address: "Noida, Uttar Pradesh",
      contact_email: "accounts@offline.example",
    },
    checks: [
      { name: "Document completeness", score: 82, result: "Pass", detail: "Offline fallback data loaded." },
      { name: "Tax ID verification", score: 78, result: "Review", detail: "API is unavailable, manual review required." },
    ],
  },
];

const qs = (selector) => document.querySelector(selector);
const qsa = (selector) => [...document.querySelectorAll(selector)];

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json();
}

function showToast(message) {
  const toast = qs("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.setTimeout(() => toast.classList.remove("visible"), 2800);
}

function setApiStatus(online) {
  const status = qs("#apiStatus");
  status.textContent = online ? "API online" : "Offline demo";
  status.classList.toggle("online", online);
  status.classList.toggle("offline", !online);
}

function switchView(viewId) {
  qsa(".view").forEach((view) => view.classList.toggle("active", view.id === viewId));
  qsa(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === viewId));
}

function statusBadge(status) {
  return `<span class="status ${status}">${status.replaceAll("_", " ")}</span>`;
}

function renderMetrics() {
  const total = state.cases.length;
  const approved = state.cases.filter((item) => ["AUTO_APPROVED", "APPROVED"].includes(item.status)).length;
  const review = state.cases.filter((item) => item.status === "HUMAN_REVIEW" || item.status === "NEEDS_INFO").length;
  const avg = total ? Math.round(state.cases.reduce((sum, item) => sum + item.confidence, 0) / total) : 0;
  qs("#metricTotal").textContent = total;
  qs("#metricApproved").textContent = approved;
  qs("#metricReview").textContent = review;
  qs("#metricConfidence").textContent = `${avg}%`;
}

function renderCaseTable() {
  const table = qs("#caseTable");
  table.innerHTML = state.cases.map((item) => `
    <tr>
      <td><strong>${item.id}</strong></td>
      <td>${item.vendor_name}</td>
      <td>${item.category}</td>
      <td>${item.confidence}%</td>
      <td>${statusBadge(item.status)}</td>
      <td><button class="ghost-btn" data-open-case="${item.id}">Open</button></td>
    </tr>
  `).join("");
}

function renderReviewQueue() {
  const reviewCases = state.cases.filter((item) => !["AUTO_APPROVED", "APPROVED"].includes(item.status));
  const list = qs("#reviewList");
  if (!reviewCases.length) {
    list.innerHTML = `<div class="empty-state">No cases need human review right now.</div>`;
    return;
  }

  list.innerHTML = reviewCases.map((item) => `
    <article class="review-card">
      <div class="review-card-header">
        <div>
          <span>${item.id}</span>
          <strong>${item.vendor_name}</strong>
        </div>
        ${statusBadge(item.status)}
      </div>
      <div class="confidence-bar"><div style="width:${item.confidence}%"></div></div>
      <p>${item.category} • ${item.risk_level} risk • ${item.confidence}% confidence</p>
      <button class="secondary-btn" data-open-case="${item.id}">Review evidence</button>
    </article>
  `).join("");
}

function renderCaseDetail(item) {
  state.selectedCase = item;
  const detail = qs("#caseDetail");
  if (!item) {
    detail.innerHTML = `<div class="empty-state">Select a case to inspect validation evidence.</div>`;
    return;
  }

  detail.innerHTML = `
    <div class="review-card">
      <div class="review-card-header">
        <div>
          <span>${item.id}</span>
          <strong>${item.vendor_name}</strong>
        </div>
        ${statusBadge(item.status)}
      </div>
      <p>${item.document} • assigned to ${item.assigned_to}</p>
      <div class="checks-list">
        ${item.checks.map((check) => `
          <div class="check-row">
            <span>${check.name}</span>
            <strong>${check.score}% ${statusBadge(check.result)}</strong>
            <p>${check.detail}</p>
          </div>
        `).join("")}
      </div>
      <div class="decision-actions">
        <textarea id="decisionNotes" placeholder="Reviewer notes"></textarea>
        <div class="decision-buttons">
          <button class="primary-btn" data-decision="APPROVED">Approve</button>
          <button class="secondary-btn" data-decision="NEEDS_INFO">Need info</button>
          <button class="ghost-btn" data-decision="REJECTED">Reject</button>
        </div>
      </div>
    </div>
  `;
}

function renderAudit() {
  const timeline = qs("#auditTimeline");
  if (!state.audit.length) {
    timeline.innerHTML = `<div class="empty-state">No audit events yet.</div>`;
    return;
  }

  timeline.innerHTML = state.audit.map((event) => `
    <article class="audit-event">
      <span>${new Date(event.timestamp).toLocaleString()} • ${event.case_id}</span>
      <strong>${event.event_type.replaceAll("_", " ")}</strong>
      <p>${event.actor}: ${event.message}</p>
    </article>
  `).join("");
}

function renderExtractionPreview(fields) {
  const preview = qs("#extractionPreview");
  if (!fields) {
    preview.innerHTML = "Upload a document to see extracted fields.";
    preview.className = "empty-state";
    return;
  }

  preview.className = "field-preview";
  preview.innerHTML = Object.entries(fields).map(([key, value]) => `
    <div>
      <span>${key.replaceAll("_", " ")}</span>
      <strong>${value}</strong>
    </div>
  `).join("");
}

function renderAll() {
  renderMetrics();
  renderCaseTable();
  renderReviewQueue();
  renderAudit();
}

async function loadConfig() {
  try {
    const config = await api("/api/config");
    state.threshold = config.approval_threshold;
    qs("#thresholdValue").textContent = `${state.threshold}%`;
  } catch {
    qs("#thresholdValue").textContent = `${state.threshold}%`;
  }
}

async function loadCases() {
  try {
    state.cases = await api("/api/demo-cases");
    setApiStatus(true);
  } catch {
    state.cases = fallbackCases;
    setApiStatus(false);
  }
  renderAll();
}

async function loadAudit() {
  try {
    state.audit = await api("/api/audit-events");
  } catch {
    state.audit = [];
  }
  renderAudit();
}

function fillForm(fields, extra = {}) {
  const form = qs("#intakeForm");
  Object.entries({ ...fields, ...extra }).forEach(([key, value]) => {
    const input = form.elements[key];
    if (input) input.value = value;
  });
}

async function simulateExtraction() {
  const input = qs("#documentInput");
  const file = input.files[0];
  if (!file) {
    showToast("Upload or choose a vendor document first.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("category", qs("#intakeForm").elements.category.value);

  try {
    const result = await api("/api/upload/simulate", { method: "POST", body: formData });
    state.documentName = result.document_name;
    fillForm(result.extracted_fields, { category: result.category });
    renderExtractionPreview(result.extracted_fields);
    qs("#uploadHint").textContent = result.message;
    showToast("Extraction complete. Review and submit the form.");
  } catch (error) {
    showToast("Extraction failed. You can still enter details manually.");
  }
}

async function submitIntake(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.compliance_confirmed = form.elements.compliance_confirmed.checked;
  payload.document_name = state.documentName || qs("#documentInput").files[0]?.name || "manual-entry.pdf";
  payload.submitted_by = "Portal User";

  try {
    const created = await api("/api/intake/submit", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.cases.unshift(created);
    await loadAudit();
    renderAll();
    renderCaseDetail(created);
    switchView(created.status === "AUTO_APPROVED" ? "dashboard" : "review");
    showToast(`Case ${created.id} created with ${created.confidence}% confidence.`);
  } catch (error) {
    showToast("Could not submit intake. Check required fields and API status.");
  }
}

async function openCase(caseId) {
  try {
    const item = await api(`/api/demo-cases/${caseId}`);
    renderCaseDetail(item);
  } catch {
    const item = state.cases.find((candidate) => candidate.id === caseId);
    renderCaseDetail(item);
  }
  switchView("review");
}

async function submitDecision(decision) {
  if (!state.selectedCase) return;
  const notes = qs("#decisionNotes")?.value || "";
  try {
    const updated = await api(`/api/demo-cases/${state.selectedCase.id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, reviewer: "Procurement Reviewer", notes }),
    });
    state.cases = state.cases.map((item) => item.id === updated.id ? updated : item);
    await loadAudit();
    renderAll();
    renderCaseDetail(updated);
    showToast(`Case ${updated.id} marked as ${decision.replaceAll("_", " ")}.`);
  } catch {
    showToast("Decision could not be saved.");
  }
}

function bindEvents() {
  qsa(".nav-item").forEach((item) => item.addEventListener("click", () => switchView(item.dataset.view)));
  qsa("[data-view-target]").forEach((item) => item.addEventListener("click", () => switchView(item.dataset.viewTarget)));
  qs("#refreshCases").addEventListener("click", loadCases);
  qs("#refreshAudit").addEventListener("click", loadAudit);
  qs("#simulateExtraction").addEventListener("click", simulateExtraction);
  qs("#intakeForm").addEventListener("submit", submitIntake);
  qs("#resetIntake").addEventListener("click", () => {
    qs("#intakeForm").reset();
    state.documentName = "";
    renderExtractionPreview(null);
    qs("#uploadHint").textContent = "Demo extraction will populate the fields below.";
  });
  qs("#documentInput").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) qs("#uploadHint").textContent = `${file.name} selected. Run extraction to auto-populate the form.`;
  });
  document.addEventListener("click", (event) => {
    const openButton = event.target.closest("[data-open-case]");
    if (openButton) openCase(openButton.dataset.openCase);

    const decisionButton = event.target.closest("[data-decision]");
    if (decisionButton) submitDecision(decisionButton.dataset.decision);
  });
}

async function boot() {
  bindEvents();
  await loadConfig();
  await loadCases();
  await loadAudit();
}

boot();
