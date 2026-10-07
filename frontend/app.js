const state = {
  cases: [],
  audit: [],
  selectedCase: null,
  threshold: null,
  config: null,
  documentName: "",
  documents: [],
  extracted: false,
  extractionResult: null,
  caseDetailTab: "overview",
  openAuditCases: new Set(),
};

const viewTitles = {
  dashboard: "Overview",
  intake: "New intake",
  review: "Review queue",
  audit: "Audit trail",
};

const qs = (selector, root = document) => root.querySelector(selector);
const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeStatus(value) {
  return String(value ?? "").toLowerCase().replaceAll("_", "-").replaceAll(" ", "-");
}

function statusLabel(value) {
  const labels = {
    AUTO_APPROVED: "Auto-approved",
    APPROVED: "Approved",
    HUMAN_REVIEW: "Needs review",
    NEEDS_INFO: "Needs information",
    REJECTED: "Rejected",
    Pass: "Passed",
    Review: "Review",
    Fail: "Failed",
  };
  return labels[value] || String(value ?? "").replaceAll("_", " ");
}

function statusBadge(status) {
  return `<span class="status ${normalizeStatus(status)}">${escapeHtml(statusLabel(status))}</span>`;
}

function formatDate(value, includeTime = false) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(includeTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
}

function formatConfidence(value) {
  return value == null ? "Not scored" : `${Number(value)}%`;
}

function meterWidth(value) {
  return value == null ? 0 : Math.max(0, Math.min(100, Number(value) || 0));
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "Ready for extraction";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      const body = await response.text();
      if (body) message = body;
    }
    throw new Error(message);
  }
  return response.json();
}

function showToast(message) {
  const toast = qs("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => toast.classList.remove("visible"), 3200);
}

function showAlert(message = "") {
  const alert = qs("#appAlert");
  alert.textContent = message;
  alert.hidden = !message;
}

function setBusy(button, busy, busyLabel = "Working") {
  if (!button) return;
  if (busy) {
    button.dataset.originalHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="button-spinner" aria-hidden="true"></span>${escapeHtml(busyLabel)}`;
  } else {
    button.innerHTML = button.dataset.originalHtml || button.innerHTML;
    button.disabled = false;
    delete button.dataset.originalHtml;
  }
}

function setApiStatus(online) {
  const status = qs("#apiStatus");
  status.lastChild.textContent = online ? "API online" : "API unavailable";
  status.classList.toggle("online", online);
  status.classList.toggle("offline", !online);
}

function closeSidebar() {
  qs("#sidebar").classList.remove("open");
  qs("#scrim").classList.remove("visible");
}

function switchView(viewId) {
  qsa(".view").forEach((view) => view.classList.toggle("active", view.id === viewId));
  qsa(".nav-item").forEach((item) => {
    const active = item.dataset.view === viewId;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  qs("#topbarTitle").textContent = viewTitles[viewId] || "Vendor operations";
  showAlert();
  closeSidebar();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function casesNeedingAttention() {
  return state.cases.filter((item) => ["HUMAN_REVIEW", "NEEDS_INFO"].includes(item.status));
}

function renderMetrics() {
  const total = state.cases.length;
  const approved = state.cases.filter((item) => ["AUTO_APPROVED", "APPROVED"].includes(item.status)).length;
  const review = casesNeedingAttention().length;
  const scored = state.cases.filter((item) => item.confidence != null);
  const average = scored.length ? Math.round(scored.reduce((sum, item) => sum + Number(item.confidence), 0) / scored.length) : null;
  qs("#metricTotal").textContent = total;
  qs("#metricApproved").textContent = approved;
  qs("#metricReview").textContent = review;
  qs("#metricConfidence").textContent = formatConfidence(average);
  qs("#metricApprovalRate").textContent = `${total ? Math.round((approved / total) * 100) : 0}% approval rate`;
  qs("#metricThresholdCopy").textContent = state.threshold == null ? "Target unavailable" : `Target ${state.threshold}%`;
  qs("#reviewNavCount").textContent = review;
  qs("#lastUpdated").textContent = `Updated ${new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit" }).format(new Date())}`;
}

function filteredCases() {
  const query = qs("#caseSearch").value.trim().toLowerCase();
  const status = qs("#caseStatusFilter").value;
  return state.cases.filter((item) => {
    const matchesQuery = !query || `${item.vendor_name} ${item.id} ${item.category}`.toLowerCase().includes(query);
    const matchesStatus = status === "ALL" || item.status === status;
    return matchesQuery && matchesStatus;
  });
}

function renderCaseTable() {
  const items = filteredCases();
  const table = qs("#caseTable");
  qs("#caseTableEmpty").hidden = items.length > 0;
  table.innerHTML = items.map((item) => `
    <tr>
      <td><div class="vendor-cell"><strong>${escapeHtml(item.vendor_name)}</strong><small>${escapeHtml(item.region || "Not provided")}</small></div></td>
      <td><strong>${escapeHtml(item.id)}</strong></td>
      <td>${escapeHtml(item.category)}</td>
      <td>${escapeHtml(formatDate(item.submitted_at))}</td>
      <td><div class="confidence-cell"><strong>${formatConfidence(item.confidence)}</strong><span class="mini-meter" aria-hidden="true"><span style="width:${formatConfidence(item.confidence)}"></span></span></div></td>
      <td>${statusBadge(item.status)}</td>
      <td><button class="icon-btn row-action" data-open-case="${escapeHtml(item.id)}" type="button" aria-label="Open ${escapeHtml(item.vendor_name)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg></button></td>
    </tr>
  `).join("");
}

function filteredReviewCases() {
  const query = qs("#reviewSearch").value.trim().toLowerCase();
  return casesNeedingAttention().filter((item) => !query || `${item.vendor_name} ${item.id} ${item.category}`.toLowerCase().includes(query));
}

function renderReviewQueue({ preserveSelection = true } = {}) {
  const reviewCases = filteredReviewCases();
  qs("#reviewCount").textContent = `${reviewCases.length} ${reviewCases.length === 1 ? "case" : "cases"}`;
  const list = qs("#reviewList");
  if (!reviewCases.length) {
    list.innerHTML = `<div class="queue-empty">No cases match this queue.</div>`;
    if (!preserveSelection) renderCaseDetail(null);
    return;
  }

  const selectedStillExists = state.selectedCase && state.cases.some((item) => item.id === state.selectedCase.id);
  if (!preserveSelection || !selectedStillExists) {
    state.selectedCase = reviewCases[0];
    state.caseDetailTab = "overview";
  }

  list.innerHTML = reviewCases.map((item) => `
    <button class="queue-case ${state.selectedCase?.id === item.id ? "active" : ""}" data-open-case="${escapeHtml(item.id)}" type="button">
      <div class="queue-case-top"><strong>${escapeHtml(item.vendor_name)}</strong>${statusBadge(item.status)}</div>
      <div class="queue-case-meta"><span>${escapeHtml(item.id)} · ${escapeHtml(item.category)}</span><span class="risk-label ${normalizeStatus(item.risk_level)}">${escapeHtml(item.risk_level)} risk</span></div>
      <div class="queue-case-score"><span class="mini-meter" aria-hidden="true"><span style="width:${formatConfidence(item.confidence)}"></span></span><strong>${formatConfidence(item.confidence)}</strong></div>
    </button>
  `).join("");
  renderCaseDetail(state.selectedCase);
}

function renderCaseDetail(item) {
  state.selectedCase = item;
  const detail = qs("#caseDetail");
  if (!item) {
    detail.innerHTML = `<div class="detail-empty"><div class="empty-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg></div><strong>Select a case</strong><p>Choose a case from the queue to inspect validation evidence.</p></div>`;
    return;
  }

  const belowThreshold = item.confidence != null && item.confidence < state.threshold;
  const missingChecks = item.checks.filter((check) => ["Review", "Fail"].includes(check.result));
  const history = state.audit.filter((event) => event.case_id === item.id);
  const criticalFailures = item.checks.filter((check) => check.result === "Fail").map((check) => check.name);
  const decisionReason = getDecisionReason(item, criticalFailures);
  const activeTab = ["overview", "submission", "scorecard", "history"].includes(state.caseDetailTab) ? state.caseDetailTab : "overview";
  detail.innerHTML = `
    <div class="case-detail">
      <div class="detail-header">
        <div><span class="case-id">${escapeHtml(item.id)}</span><h2>${escapeHtml(item.vendor_name)}</h2><p>${escapeHtml(item.document)}</p></div>
        ${statusBadge(item.status)}
      </div>
      <div class="case-tabs" role="tablist" aria-label="${escapeHtml(item.id)} details">
        <button class="case-tab ${activeTab === "overview" ? "active" : ""}" data-case-tab="overview" role="tab" aria-selected="${activeTab === "overview"}">Overview</button>
        <button class="case-tab ${activeTab === "submission" ? "active" : ""}" data-case-tab="submission" role="tab" aria-selected="${activeTab === "submission"}">Submitted form &amp; documents</button>
        <button class="case-tab ${activeTab === "scorecard" ? "active" : ""}" data-case-tab="scorecard" role="tab" aria-selected="${activeTab === "scorecard"}">Scorecard <span>${item.checks.length}</span></button>
        <button class="case-tab ${activeTab === "history" ? "active" : ""}" data-case-tab="history" role="tab" aria-selected="${activeTab === "history"}">History <span>${history.length}</span></button>
      </div>
      ${activeTab === "overview" ? renderCaseOverview(item, missingChecks, decisionReason) : ""}
      ${activeTab === "submission" ? renderCaseSubmission(item) : ""}
      ${activeTab === "scorecard" ? renderCaseScorecard(item) : ""}
      ${activeTab === "history" ? renderCaseHistory(item, history) : ""}
      ${activeTab === "overview" ? `
      <div class="detail-summary">
        <div><span>Category</span><strong>${escapeHtml(item.category)}</strong></div>
        <div><span>Risk level</span><strong>${escapeHtml(item.risk_level)}</strong></div>
        <div><span>Submitted</span><strong>${escapeHtml(formatDate(item.submitted_at))}</strong></div>
        <div><span>Assigned to</span><strong>${escapeHtml(item.assigned_to)}</strong></div>
      </div>
      <section class="confidence-overview">
        <div><div><h3>Decision confidence</h3><p>${item.confidence == null ? "No confidence score recorded" : (belowThreshold ? "Below the auto-approval threshold" : "Meets the auto-approval threshold")}</p></div><strong>${formatConfidence(item.confidence)}</strong></div>
        <div class="threshold-meter" aria-label="Confidence ${Number(item.confidence)} percent; threshold ${state.threshold} percent"><div class="score-fill" style="width:${formatConfidence(item.confidence)}"></div><span class="threshold-marker" style="left:${state.threshold}%" data-label="${state.threshold}% threshold"></span></div>
      </section>
      <section class="checks-section">
        <h3>Validation evidence</h3>
        <div class="checks-list">
          ${item.checks.map((check) => `
            <div class="check-row">
              <strong>${escapeHtml(check.name)}</strong>
              <div class="check-result"><strong>${Number(check.score)}%</strong>${statusBadge(check.result)}</div>
              <p>${escapeHtml(check.detail)}</p>
            </div>
          `).join("")}
        </div>
      </section>
      <section class="decision-section">
        <h3>Record decision</h3>
        <p>Add a short rationale so the decision remains traceable.</p>
        <textarea id="decisionNotes" aria-label="Reviewer notes" placeholder="Add reviewer notes"></textarea>
        <div class="decision-actions">
          <button class="tertiary-btn danger-btn" data-decision="REJECTED" type="button">Reject</button>
          <button class="secondary-btn" data-decision="NEEDS_INFO" type="button">Request information</button>
          <button class="primary-btn" data-decision="APPROVED" type="button">Approve vendor</button>
        </div>
      </section>
      ` : ""}
    </div>
  `;
}

function getDecisionReason(item, criticalFailures = []) {
  if (item.confidence == null) return `This synthetic sample has no calculated confidence score. Its recorded status is ${item.source_status || statusLabel(item.status)}.`;
  const failedText = criticalFailures.length ? ` Critical checks failed: ${criticalFailures.join(", ")}.` : "";
  if (item.status === "AUTO_APPROVED") return `Confidence score ${item.confidence} meets the ${state.threshold}% threshold and all critical checks passed.`;
  if (item.status === "APPROVED") return `Reviewer approved the vendor after reviewing the evidence. Confidence score was ${item.confidence}% against a ${state.threshold}% threshold.`;
  if (item.status === "REJECTED") return `Confidence score ${item.confidence}% is below the ${state.threshold}% threshold.${failedText}`;
  if (item.status === "NEEDS_INFO") return "The reviewer requested additional information before a final approval decision.";
  return `Confidence score ${item.confidence}% is below the ${state.threshold}% threshold, so the case was routed to human review.${failedText}`;
}

function renderCaseOverview(item, missingChecks, decisionReason) {
  return `
    <div class="decision-reason ${item.status === "AUTO_APPROVED" || item.status === "APPROVED" ? "positive" : "attention"}">
      <div class="reason-icon" aria-hidden="true">${item.status === "AUTO_APPROVED" || item.status === "APPROVED" ? "✓" : "!"}</div>
      <div><span>Decision rationale</span><strong>${escapeHtml(statusLabel(item.status))}</strong><p>${escapeHtml(decisionReason)}</p></div>
    </div>
    ${missingChecks.length ? `<div class="missing-info"><div class="missing-icon" aria-hidden="true">!</div><div><strong>Missing or unresolved information</strong><p>${missingChecks.map((check) => `<span>${escapeHtml(check.name)}: ${escapeHtml(check.detail)}</span>`).join("")}</p></div></div>` : `<div class="complete-info"><span aria-hidden="true">✓</span><div><strong>All validation sections resolved</strong><p>No missing information was flagged for this case.</p></div></div>`}
    <div class="score-summary"><div><span>Overall confidence</span><strong>${formatConfidence(item.confidence)}</strong></div><div><span>Approval threshold</span><strong>${state.threshold}%</strong></div><div><span>Sections reviewed</span><strong>${item.checks.length}</strong></div></div>
  `;
}

function renderCaseSubmission(item) {
  const labels = {
    legal_name: "Legal name", supplier_name: "Supplier name", supplier_type: "Supplier type",
    tax_id: "Tax ID / GSTIN", pan: "PAN", bank_account: "Bank account",
    ifsc: "IFSC", registered_address: "Registered address", address: "Address",
    contact_email: "Contact email", category: "Category", region: "Region",
    country: "Country", compliance_confirmed: "Compliance declaration",
    description: "Purchase description", estimated_annual_spend: "Estimated annual spend",
    currency: "Currency", payment_terms: "Payment terms",
    requesting_department: "Requesting department", budget_owner: "Budget owner",
    procurement_owner: "Procurement owner", submitted_by: "Submitted by"
  };
  const fields = item.submitted_form || item.extracted_fields || {};
  const rows = Object.entries(fields).filter(([key, value]) => value !== null && value !== "" && typeof value !== "object");
  const documents = item.documents || [];
  return `<section class="submission-section">
    <div class="scorecard-heading"><div><h3>Submitted form</h3><p>Values recorded when this case was submitted.</p></div></div>
    <dl class="submitted-grid">${rows.length ? rows.map(([key, value]) => `
      <div><dt>${escapeHtml(labels[key] || key.replaceAll("_", " "))}</dt><dd>${escapeHtml(typeof value === "boolean" ? (value ? "Yes" : "No") : value)}</dd></div>
    `).join("") : '<div>No submitted form is available for this case.</div>'}</dl>
    <div class="scorecard-heading documents-heading"><div><h3>Documents</h3><p>Files attached to this case.</p></div><strong>${documents.length} ${documents.length === 1 ? "file" : "files"}</strong></div>
    <div class="document-list">${documents.length ? documents.map((doc) => `
      <div class="document-row"><div><strong>${escapeHtml(doc.name)}</strong><small>${escapeHtml(doc.type || "Document")}${doc.uploaded_at ? " · " + escapeHtml(formatDate(doc.uploaded_at, true)) : ""}</small></div>
        ${doc.available ? `<a class="secondary-btn" href="/api/demo-cases/${encodeURIComponent(item.id)}/documents/${encodeURIComponent(doc.id)}" target="_blank" rel="noopener">Open file</a>` : '<span class="document-unavailable">File not stored</span>'}
      </div>`).join("") : '<p class="document-empty">No documents were recorded for this case.</p>'}</div>
  </section>`;
}

function renderCaseScorecard(item) {
  return `
    <section class="scorecard-section"><div class="scorecard-heading"><div><h3>Validation scorecard</h3><p>Each section contributes to the final confidence score.</p></div><strong>${formatConfidence(item.confidence)} overall</strong></div>
      <div class="scorecard-grid">${item.checks.map((check) => {
        const resultClass = check.result === "Pass" ? "pass" : (check.result === "Review" ? "review" : "fail");
        return `<article class="score-card ${resultClass}"><div class="score-card-top"><span>${escapeHtml(check.name)}</span>${statusBadge(check.result)}</div><div class="score-number">${Number(check.score)}<small>/100</small></div><div class="score-line"><span style="width:${Number(check.score)}%"></span></div><p>${escapeHtml(check.detail)}</p></article>`;
      }).join("")}</div>
    </section>
  `;
}

function renderCaseHistory(item, history) {
  if (!history.length) return `<div class="case-history-empty">No case-specific audit events are available yet.</div>`;
  return `<section class="case-history"><div class="scorecard-heading"><div><h3>Case history</h3><p>Every event is linked to ${escapeHtml(item.id)} and shown in order.</p></div><strong>${history.length} events</strong></div><div class="case-timeline">${history.slice().reverse().map((event) => `<article><span class="timeline-dot" aria-hidden="true"></span><div><div class="timeline-event-top"><strong>${escapeHtml(statusLabel(event.event_type))}</strong><time datetime="${escapeHtml(event.timestamp)}">${escapeHtml(formatDate(event.timestamp, true))}</time></div><p>${escapeHtml(event.message)}</p><small>${escapeHtml(event.actor)}</small></div></article>`).join("")}</div></section>`;
}

function populateAuditTypes() {
  const select = qs("#auditTypeFilter");
  const selected = select.value;
  const values = [...new Set(state.audit.map((item) => item.event_type))].sort();
  select.innerHTML = `<option value="ALL">All event types</option>${values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(statusLabel(value))}</option>`).join("")}`;
  if (["ALL", ...values].includes(selected)) select.value = selected;
}

function renderAudit() {
  populateAuditTypes();
  const query = qs("#auditSearch").value.trim().toLowerCase();
  const type = qs("#auditTypeFilter").value;
  const groups = new Map();
  for (const event of state.audit) {
    if (!groups.has(event.case_id)) groups.set(event.case_id, []);
    groups.get(event.case_id).push(event);
  }
  const cases = [...groups.entries()].filter(([caseId, history]) => {
    const matchesType = type === "ALL" || history.some((event) => event.event_type === type);
    const matchesQuery = !query || history.some((event) =>
      `${event.case_id} ${event.actor} ${event.event_type} ${statusLabel(event.event_type)} ${event.message}`.toLowerCase().includes(query)
    ) || state.cases.some((item) => item.id === caseId &&
      `${item.vendor_name} ${item.status}`.toLowerCase().includes(query));
    return matchesType && matchesQuery;
  }).sort((a, b) => Math.max(...b[1].map((event) => Date.parse(event.timestamp) || 0)) -
                       Math.max(...a[1].map((event) => Date.parse(event.timestamp) || 0)));
  const timeline = qs("#auditTimeline");
  if (!cases.length) {
    timeline.innerHTML = `<div class="table-empty">No cases match the selected audit filters.</div>`;
    return;
  }
  timeline.innerHTML = cases.map(([caseId, history]) => {
    const item = state.cases.find((candidate) => candidate.id === caseId);
    const ordered = history.slice().sort((a, b) => (Date.parse(a.timestamp) || 0) - (Date.parse(b.timestamp) || 0));
    const latest = ordered[ordered.length - 1];
    return `
      <details class="audit-case" data-audit-case="${escapeHtml(caseId)}" ${state.openAuditCases.has(caseId) ? "open" : ""}>
        <summary class="audit-case-summary">
          <span class="audit-case-identity"><strong>${escapeHtml(caseId)}</strong><span>${escapeHtml(item?.vendor_name || "Vendor case")}</span></span>
          <span class="audit-case-status">${item ? statusBadge(item.status) : escapeHtml(statusLabel(latest.event_type))}</span>
          <span class="audit-case-count">${history.length} ${history.length === 1 ? "event" : "events"}</span>
          <time datetime="${escapeHtml(latest.timestamp)}">${escapeHtml(formatDate(latest.timestamp, true))}</time>
          <span class="audit-chevron" aria-hidden="true">⌄</span>
        </summary>
        <div class="audit-case-content">
          <div class="audit-case-caption">Case journey · oldest to newest <button class="tertiary-btn audit-view-case" type="button" data-open-case="${escapeHtml(caseId)}">View submitted form &amp; documents</button></div>
          <div class="case-timeline">
            ${ordered.map((event) => `<article>
              <span class="timeline-dot" aria-hidden="true"></span>
              <div><div class="timeline-event-top"><strong>${escapeHtml(statusLabel(event.event_type))}</strong><time datetime="${escapeHtml(event.timestamp)}">${escapeHtml(formatDate(event.timestamp, true))}</time></div>
              <p>${escapeHtml(event.message)}</p><small>${escapeHtml(event.actor)}</small></div>
            </article>`).join("")}
          </div>
        </div>
      </details>`;
  }).join("");
}

function renderExtractionPreview(fields, result = null) {
  const preview = qs("#extractionPreview");
  if (!fields) {
    preview.className = "evidence-empty";
    preview.innerHTML = `<div class="empty-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M9 13h6M9 17h4"/></svg></div><strong>No document processed</strong><p>Upload a document and run extraction to review source values.</p>`;
    return;
  }
  preview.className = "evidence-list";
  preview.innerHTML = Object.entries(fields).map(([key, value], index) => `
    <div class="evidence-row"><div><span>${escapeHtml(key.replaceAll("_", " "))}</span><span class="confidence-tag">${Number(result?.field_confidence?.[key] || 0)}% match</span></div><strong>${escapeHtml(value)}</strong><small>Source: ${escapeHtml(result?.field_sources?.[key] || "Manual entry")}</small></div>
  `).join("");
}

function renderSelectedFiles() {
  const files = state.documents;
  qs("#fileSummary").hidden = !files.length;
  qs("#fileName").textContent = `${files.length} ${files.length === 1 ? "document" : "documents"} selected`;
  qs("#selectedFileList").innerHTML = files.map((file) => `
    <div class="selected-file-row"><span class="file-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg></span><div><strong>${escapeHtml(file.name)}</strong><small>${formatBytes(file.size)}</small></div></div>
  `).join("");
  const total = files.reduce((sum, file) => sum + file.size, 0);
  qs("#fileMeta").textContent = files.length ? `${formatBytes(total)} combined · Ready for extraction` : "Ready for extraction";
}

function renderRequirementCoverage(documents = []) {
  const found = new Set(documents.flatMap((document) => document.detected_types || [document.document_type]));
  qsa("[data-requirement]").forEach((item) => {
    const complete = found.has(item.dataset.requirement);
    item.classList.toggle("complete", complete);
    const marker = qs("i", item);
    marker.textContent = complete ? "✓" : marker.dataset.number || marker.textContent;
    if (!marker.dataset.number && !complete) marker.dataset.number = marker.textContent;
  });
}

function renderExtractionScore(result = null) {
  const scoreCard = qs("#extractionScore");
  scoreCard.hidden = !result;
  if (!result) return;
  const score = Number(result.extraction_confidence || 0);
  qs("#extractionScoreValue").textContent = `${score}%`;
  qs("#extractionScoreBar").style.width = `${meterWidth(score)}%`;
  const missing = result.missing_fields || [];
  qs("#extractionScoreMessage").textContent = missing.length
    ? `${missing.length} field${missing.length === 1 ? "" : "s"} need manual completion before submission.`
    : "All required fields were found. Verify the values before submission.";
}

function renderAll() {
  renderMetrics();
  renderCaseTable();
  renderReviewQueue();
  renderAudit();
}

async function loadConfig() {
  try {
    state.config = await api("/api/config");
    state.threshold = state.config.approval_threshold;
  } catch (error) {
    state.config = null;
    state.threshold = null;
    setApiStatus(false);
    showAlert(`Configuration could not be loaded: ${error.message}`);
  }
  qs("#thresholdValue").textContent = state.threshold == null ? "Unavailable" : `${state.threshold}%`;
  qs("#thresholdTrack").style.width = `${meterWidth(state.threshold)}%`;
}

async function loadCases() {
  const button = qs("#refreshCases");
  setBusy(button, true, "Refreshing");
  try {
    state.cases = await api("/api/demo-cases");
    setApiStatus(true);
  } catch (error) {
    state.cases = [];
    setApiStatus(false);
    showAlert(`Cases could not be loaded: ${error.message}`);
  } finally {
    setBusy(button, false);
  }
  renderAll();
}

async function loadAudit() {
  const button = qs("#refreshAudit");
  setBusy(button, true, "Refreshing");
  try {
    state.audit = await api("/api/audit-events");
  } catch {
    state.audit = [];
  } finally {
    setBusy(button, false);
  }
  renderAudit();
}

function fillForm(fields, extra = {}) {
  const form = qs("#intakeForm");
  Object.entries({ ...fields, ...extra }).forEach(([key, value]) => {
    const input = form.elements[key];
    if (input) {
      input.value = value;
      input.setAttribute("data-extracted", "true");
    }
  });
}

function setIntakeStep(step) {
  const steps = [qs("#stepUpload"), qs("#stepVerify"), qs("#stepSubmit")];
  steps.forEach((item, index) => {
    item.classList.toggle("done", index < step);
    item.classList.toggle("active", index === step);
  });
}

function handleSelectedFiles(selected) {
  const files = [...(selected || [])];
  if (!files.length) return false;
  const limits = state.config?.upload_limits;
  if (!limits) {
    showAlert("Upload configuration is unavailable. Refresh the page and try again.");
    return false;
  }
  if (files.length > limits.max_documents) {
    qs("#documentInput").value = "";
    showAlert(`A maximum of ${limits.max_documents} documents can be processed in one intake.`);
    return false;
  }
  const oversized = files.find((file) => file.size > limits.max_file_size_bytes);
  if (oversized) {
    qs("#documentInput").value = "";
    showAlert(`${oversized.name} exceeds the ${formatBytes(limits.max_file_size_bytes)} per-file limit.`);
    return false;
  }
  const total = files.reduce((sum, file) => sum + file.size, 0);
  if (total > limits.max_total_size_bytes) {
    qs("#documentInput").value = "";
    showAlert(`The selected documents exceed the ${formatBytes(limits.max_total_size_bytes)} combined limit.`);
    return false;
  }
  state.documents = files;
  renderSelectedFiles();
  qs("#uploadHint").textContent = `${files.length} document${files.length === 1 ? "" : "s"} selected`;
  qs("#simulateExtraction").disabled = false;
  state.documentName = files[0].name;
  state.extracted = false;
  state.extractionResult = null;
  renderExtractionScore(null);
  renderRequirementCoverage();
  setIntakeStep(0);
  showAlert();
  return true;
}

function clearDocument() {
  qs("#documentInput").value = "";
  state.documents = [];
  renderSelectedFiles();
  qs("#uploadHint").textContent = "or click to select multiple files";
  qs("#simulateExtraction").disabled = true;
  qs("#extractionBadge").textContent = "Manual entry";
  qs("#extractionBadge").classList.remove("complete");
  state.documentName = "";
  state.extracted = false;
  state.extractionResult = null;
  renderExtractionPreview(null);
  renderExtractionScore(null);
  renderRequirementCoverage();
  setIntakeStep(0);
}

async function simulateExtraction() {
  if (!state.documents.length) {
    showAlert("Choose one or more vendor documents before running extraction.");
    return;
  }
  const button = qs("#simulateExtraction");
  const formData = new FormData();
  state.documents.forEach((file) => formData.append("files", file));
  formData.append("category", qs("#intakeForm").elements.category.value);
  setBusy(button, true, "Extracting");
  showAlert();
  try {
    const result = await api("/api/upload/extract", { method: "POST", body: formData });
    state.documentName = state.documents[0].name;
    state.extracted = true;
    state.extractionResult = result;
    fillForm(result.extracted_fields, { category: result.category });
    renderExtractionPreview(result.extracted_fields, result);
    renderExtractionScore(result);
    renderRequirementCoverage(result.documents);
    qs("#fileMeta").textContent = `${state.documents.length} document${state.documents.length === 1 ? "" : "s"} · Extraction complete`;
    qs("#extractionBadge").textContent = "AI extracted";
    qs("#extractionBadge").classList.add("complete");
    setIntakeStep(1);
    showToast(`Extraction complete with ${result.extraction_confidence}% confidence. Verify the highlighted details.`);
  } catch (error) {
    showAlert(`Extraction failed: ${error.message}. You can enter the details manually.`);
  } finally {
    setBusy(button, false);
  }
}

function validateForm(form) {
  let valid = true;
  qsa("input[required], textarea[required]", form).forEach((input) => {
    const error = input.closest("label")?.querySelector(".field-error");
    let message = "";
    if (!input.value.trim()) message = "This field is required.";
    else if (!input.checkValidity()) message = "Enter a valid value.";
    input.setAttribute("aria-invalid", String(Boolean(message)));
    if (error) error.textContent = message;
    if (message) valid = false;
  });
  return valid;
}

async function submitIntake(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (!state.documentName) {
    showAlert("Upload at least one vendor document before submitting this intake.");
    qs("#uploadZone").scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  if (!validateForm(form)) {
    showAlert("Complete the required vendor details before running validation.");
    qs('[aria-invalid="true"]', form)?.focus();
    return;
  }

  const button = qs("#submitIntakeBtn");
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.compliance_confirmed = form.elements.compliance_confirmed.checked;
  payload.document_name = state.documentName;
  payload.extraction_confidence = state.extractionResult?.extraction_confidence ?? null;
  setIntakeStep(2);
  setBusy(button, true, "Running validation");
  showAlert();

  try {
    const submission = new FormData();
    submission.append("payload", JSON.stringify(payload));
    state.documents.forEach((file) => submission.append("files", file));
    const created = await api("/api/intake/submit", { method: "POST", body: submission });
    state.cases.unshift(created);
    await loadAudit();
    state.selectedCase = created;
    renderAll();
    renderCaseDetail(created);
    switchView(created.status === "AUTO_APPROVED" ? "dashboard" : "review");
    showToast(`${created.id} created with ${created.confidence}% confidence.`);
  } catch (error) {
    showAlert(`The intake could not be submitted: ${error.message}`);
    setIntakeStep(1);
  } finally {
    setBusy(button, false);
  }
}

async function openCase(caseId) {
  try {
    state.selectedCase = await api(`/api/demo-cases/${encodeURIComponent(caseId)}`);
  } catch {
    state.selectedCase = state.cases.find((candidate) => candidate.id === caseId) || null;
  }
  state.caseDetailTab = "submission";
  switchView("review");
  renderReviewQueue();
}

async function submitDecision(decision, button) {
  if (!state.selectedCase) return;
  const notes = qs("#decisionNotes")?.value.trim() || "";
  if (["REJECTED", "NEEDS_INFO"].includes(decision) && !notes) {
    showAlert("Add reviewer notes before rejecting a vendor or requesting information.");
    qs("#decisionNotes")?.focus();
    return;
  }
  setBusy(button, true, "Saving");
  showAlert();
  try {
    const updated = await api(`/api/demo-cases/${encodeURIComponent(state.selectedCase.id)}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, notes }),
    });
    state.cases = state.cases.map((item) => item.id === updated.id ? updated : item);
    state.selectedCase = updated;
    await loadAudit();
    renderAll();
    renderCaseDetail(updated);
    showToast(`${updated.id} marked as ${statusLabel(decision)}.`);
  } catch (error) {
    showAlert(`The decision could not be saved: ${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

function resetIntake() {
  qs("#intakeForm").reset();
  qsa("[aria-invalid]", qs("#intakeForm")).forEach((input) => input.removeAttribute("aria-invalid"));
  qsa(".field-error").forEach((element) => { element.textContent = ""; });
  clearDocument();
  showAlert();
}

function bindEvents() {
  qsa(".nav-item").forEach((item) => item.addEventListener("click", () => switchView(item.dataset.view)));
  qsa("[data-view-target]").forEach((item) => item.addEventListener("click", () => switchView(item.dataset.viewTarget)));
  qs("#openSidebar").addEventListener("click", () => { qs("#sidebar").classList.add("open"); qs("#scrim").classList.add("visible"); });
  qs("#closeSidebar").addEventListener("click", closeSidebar);
  qs("#scrim").addEventListener("click", closeSidebar);
  qs("#refreshCases").addEventListener("click", loadCases);
  qs("#refreshAudit").addEventListener("click", loadAudit);
  qs("#caseSearch").addEventListener("input", renderCaseTable);
  qs("#caseStatusFilter").addEventListener("change", renderCaseTable);
  qs("#reviewSearch").addEventListener("input", () => renderReviewQueue({ preserveSelection: false }));
  qs("#auditSearch").addEventListener("input", renderAudit);
  qs("#auditTypeFilter").addEventListener("change", renderAudit);
  qs("#auditTimeline").addEventListener("toggle", (event) => {
    const group = event.target.closest("details[data-audit-case]");
    if (!group || event.target !== group) return;
    if (group.open) state.openAuditCases.add(group.dataset.auditCase);
    else state.openAuditCases.delete(group.dataset.auditCase);
  }, true);
  qs("#simulateExtraction").addEventListener("click", simulateExtraction);
  qs("#intakeForm").addEventListener("submit", submitIntake);
  qs("#resetIntake").addEventListener("click", resetIntake);
  qs("#removeDocument").addEventListener("click", clearDocument);
  qs("#documentInput").addEventListener("change", (event) => {
    if (handleSelectedFiles(event.target.files)) simulateExtraction();
  });

  const uploadZone = qs("#uploadZone");
  ["dragenter", "dragover"].forEach((name) => uploadZone.addEventListener(name, (event) => { event.preventDefault(); uploadZone.classList.add("dragging"); }));
  uploadZone.addEventListener("dragleave", () => uploadZone.classList.remove("dragging"));
  uploadZone.addEventListener("drop", (event) => {
    event.preventDefault();
    uploadZone.classList.remove("dragging");
    if (handleSelectedFiles(event.dataTransfer.files)) simulateExtraction();
  });

  document.addEventListener("click", (event) => {
    const openButton = event.target.closest("[data-open-case]");
    if (openButton) openCase(openButton.dataset.openCase);
    const caseTab = event.target.closest("[data-case-tab]");
    if (caseTab && state.selectedCase) {
      state.caseDetailTab = caseTab.dataset.caseTab;
      renderCaseDetail(state.selectedCase);
    }
    const decisionButton = event.target.closest("[data-decision]");
    if (decisionButton) submitDecision(decisionButton.dataset.decision, decisionButton);
  });
}

async function boot() {
  bindEvents();
  await loadConfig();
  await loadCases();
  await loadAudit();
}

boot();
