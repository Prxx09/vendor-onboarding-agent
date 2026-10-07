const API_BASE = window.location.origin;
const API = `${API_BASE}/api/v1`;

const state = {
  vendors: [],
  queue: [],
  selectedFiles: [],
  currentResult: null,
  currentVendorId: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showView(id) {
  $$(".view").forEach(view => view.classList.toggle("active", view.id === id));
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === id));
  const titles = {
    dashboard: "Dashboard",
    "new-vendor": "New Vendor",
    result: "Verification Result",
    review: "Review Queue",
  };
  $("#viewTitle").textContent = titles[id] || "VendorFlow";
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (id === "dashboard") loadDashboard();
  if (id === "review") loadQueue();
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 3000);
}

function alertMessage(message = "") {
  const el = $("#alert");
  el.textContent = message;
  el.hidden = !message;
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return response.json();
}

function statusClass(status) {
  return String(status || "").toLowerCase().replaceAll("_", "-");
}

function badge(status) {
  return `<span class="status-badge ${statusClass(status)}">${esc(String(status || "").replaceAll("_", " "))}</span>`;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

async function checkHealth() {
  const pill = $("#apiStatus");
  try {
    await request(`${API_BASE}/health`);
    pill.classList.add("online");
    pill.innerHTML = "<span></span>Backend connected";
  } catch {
    pill.classList.remove("online");
    pill.innerHTML = "<span></span>Backend unavailable";
  }
}

async function loadDashboard() {
  try {
    alertMessage("");
    state.vendors = await request(`${API}/vendors`);
    renderDashboard();
  } catch (error) {
    alertMessage(error.message);
  }
}

function renderDashboard() {
  const counts = { APPROVED: 0, ACTION_REQUIRED: 0, REVIEW_REQUIRED: 0, REJECTED: 0 };
  state.vendors.forEach(v => {
    if (counts[v.status] != null) counts[v.status] += 1;
  });
  $("#approvedMetric").textContent = counts.APPROVED;
  $("#actionMetric").textContent = counts.ACTION_REQUIRED;
  $("#reviewMetric").textContent = counts.REVIEW_REQUIRED;
  $("#rejectedMetric").textContent = counts.REJECTED;
  $("#reviewCountBadge").textContent = counts.REVIEW_REQUIRED;

  const filter = $("#dashboardFilter").value;
  const rows = state.vendors.filter(v => filter === "ALL" || v.status === filter);
  $("#vendorTable").innerHTML = rows.map(v => `
    <tr>
      <td><strong>${esc(v.legal_name)}</strong><small>${esc(v.id)}</small></td>
      <td>${badge(v.status)}</td>
      <td>${esc(v.agent_recommendation || "—")}</td>
      <td>${formatDate(v.created_at)}</td>
      <td><button class="link-btn" data-open-vendor="${esc(v.id)}">View</button></td>
    </tr>
  `).join("");
  $("#vendorTableEmpty").hidden = rows.length > 0;
}

function renderFiles() {
  $("#fileList").innerHTML = state.selectedFiles.map((file, index) => `
    <div class="file-row">
      <div><strong>${esc(file.name)}</strong><small>${Math.max(1, Math.round(file.size / 1024))} KB</small></div>
      <button type="button" class="link-btn danger-text" data-remove-file="${index}">Remove</button>
    </div>
  `).join("");
}

async function submitVendor(event) {
  event.preventDefault();
  const legalName = $("#legalName").value.trim();
  if (!legalName) return alertMessage("Legal name is required.");
  if (!state.selectedFiles.length) return alertMessage("Upload at least one vendor document.");

  const button = $("#runVerification");
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Running verification…";
  alertMessage("");

  const formData = new FormData();
  formData.append("legal_name", legalName);
  state.selectedFiles.forEach(file => formData.append("files", file));

  try {
    const result = await request(`${API}/vendors/process`, { method: "POST", body: formData });
    state.currentResult = result;
    state.currentVendorId = result.vendor_id;
    renderResult(result);
    showView("result");
    toast("Verification completed");
  } catch (error) {
    alertMessage(error.message);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function renderResult(result) {
  $("#resultEmpty").hidden = true;
  $("#resultContent").hidden = false;
  $("#resultVendorName").textContent = result.vendor_name || "Vendor";
  $("#resultStatus").className = `status-badge ${statusClass(result.overall_status)}`;
  $("#resultStatus").textContent = String(result.overall_status || "").replaceAll("_", " ");

  const summaries = {
    APPROVED: "All required verification checks passed.",
    ACTION_REQUIRED: `Missing required evidence: ${(result.missing_documents || []).join(", ") || "additional documents"}.`,
    REVIEW_REQUIRED: "Issues detected. This vendor requires human review.",
    REJECTED: "This vendor was rejected.",
  };
  $("#resultSummary").textContent = summaries[result.overall_status] || "Verification completed.";

  $("#extractionList").innerHTML = (result.extractions || []).map(item => {
    const fields = [
      ["Document type", item.document_type],
      ["Legal name", item.legal_name],
      ["Registration no.", item.registration_number],
      ["Tax ID", item.tax_id],
      ["Account holder", item.account_holder_name],
      ["Bank", item.bank_name],
      ["Account number", item.bank_account_number],
      ["IFSC / SWIFT", item.ifsc_swift],
      ["Registered address", item.registered_address],
    ].filter(([, value]) => value);
    return `
      <article class="evidence-item">
        <div class="evidence-head">
          <div><strong>${esc(item.filename)}</strong><small>${esc(item.document_type || "supporting document")}</small></div>
          <span>${item.confidence == null ? "—" : Math.round(Number(item.confidence) * 100) + "% confidence"}</span>
        </div>
        <dl>${fields.map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl>
      </article>
    `;
  }).join("") || '<div class="empty">No extraction data returned.</div>';

  $("#checkList").innerHTML = (result.checks || []).map(check => `
    <article class="check-item">
      <div>
        <strong>${esc(String(check.source || "").replaceAll("_", " "))}</strong>
        <p>${esc(check.message)}</p>
      </div>
      ${badge(check.status)}
    </article>
  `).join("") || '<div class="empty">No checks returned.</div>';

  $("#eventTimeline").innerHTML = (result.events || []).map(event => `
    <article>
      <span class="timeline-dot"></span>
      <div><strong>${esc(String(event.step || "verification").replaceAll("_", " "))}</strong><p>${esc(event.message)}</p></div>
    </article>
  `).join("") || '<div class="empty">No agent activity returned.</div>';

  $("#reasonList").innerHTML = (result.reasons || []).map(reason => `<li>${esc(reason)}</li>`).join("");
}

async function openVendor(vendorId) {
  try {
    alertMessage("");
    const detail = await request(`${API}/vendors/${encodeURIComponent(vendorId)}`);
    const run = detail.agent_runs?.[0] || {};
    const vendor = detail.vendor || {};
    const result = {
      vendor_id: vendor.id,
      vendor_name: vendor.legal_name,
      overall_status: vendor.status,
      recommendation: vendor.agent_recommendation,
      missing_documents: [],
      extractions: (detail.documents || []).map(doc => ({
        filename: doc.filename,
        document_type: doc.document_type,
        confidence: doc.confidence,
        ...(doc.extracted_data || {}),
        bank_account_number: doc.extracted_data?.bank_account_number,
        ifsc_swift: doc.extracted_data?.ifsc_swift,
      })),
      checks: run.checks || [],
      events: run.events || [],
      reasons: vendor.reasons || [],
    };
    state.currentVendorId = vendorId;
    state.currentResult = result;
    renderResult(result);
    showView("result");
  } catch (error) {
    alertMessage(error.message);
  }
}

async function loadQueue() {
  try {
    alertMessage("");
    state.queue = await request(`${API}/vendors/review-queue`);
    $("#reviewCountBadge").textContent = state.queue.length;
    renderQueue();
  } catch (error) {
    alertMessage(error.message);
  }
}

function renderQueue() {
  $("#queueCount").textContent = `${state.queue.length} requiring review`;
  $("#reviewList").innerHTML = state.queue.map(v => `
    <button class="review-row" data-review-id="${esc(v.id)}">
      <div><strong>${esc(v.legal_name)}</strong><small>${esc(v.reasons?.[0] || "Manual review required")}</small></div>
      <span>${esc(v.agent_recommendation || "REVIEW")}</span>
    </button>
  `).join("") || '<div class="empty">No vendors currently require review.</div>';
}

async function openReview(vendorId) {
  try {
    const detail = await request(`${API}/vendors/${encodeURIComponent(vendorId)}`);
    const vendor = detail.vendor;
    const run = detail.agent_runs?.[0] || {};
    const documents = detail.documents || [];
    $("#reviewDetail").innerHTML = `
      <div class="review-head">
        <div><span class="eyebrow">Vendor detail</span><h3>${esc(vendor.legal_name)}</h3><p>${esc(vendor.id)}</p></div>
        ${badge(vendor.status)}
      </div>

      <div class="recommendation">
        <span>Agent recommendation</span>
        <strong>${esc(vendor.agent_recommendation || "—")}</strong>
        <p>${esc(vendor.reasons?.[0] || "Manual review required.")}</p>
      </div>

      <div class="review-section">
        <h4>Evidence</h4>
        <div class="stack">
          ${documents.map(doc => `
            <article class="evidence-item compact">
              <strong>${esc(doc.filename)}</strong>
              <small>${esc(doc.document_type || "supporting document")}</small>
              <dl>${Object.entries(doc.extracted_data || {}).filter(([,v]) => v).map(([k,v]) => `<div><dt>${esc(k.replaceAll("_", " "))}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>
            </article>
          `).join("") || '<div class="empty">No document evidence available.</div>'}
        </div>
      </div>

      <div class="review-section">
        <h4>Verification checks</h4>
        <div class="stack">
          ${(run.checks || []).map(check => `
            <article class="check-item">
              <div><strong>${esc(String(check.source || "").replaceAll("_", " "))}</strong><p>${esc(check.message)}</p></div>
              ${badge(check.status)}
            </article>
          `).join("")}
        </div>
      </div>

      <div class="review-section">
        <label><span>Reviewer comment</span><textarea id="reviewComment" placeholder="Add supporting evidence or decision rationale"></textarea></label>
        <div class="decision-actions">
          <button class="secondary danger" data-decision="REJECT" data-vendor-id="${esc(vendor.id)}">Reject</button>
          <button class="primary" data-decision="APPROVE" data-vendor-id="${esc(vendor.id)}">Approve</button>
        </div>
      </div>
    `;
  } catch (error) {
    alertMessage(error.message);
  }
}

async function submitDecision(button) {
  const vendorId = button.dataset.vendorId;
  const decision = button.dataset.decision;
  const comment = $("#reviewComment")?.value.trim() || "";
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    const result = await request(`${API}/vendors/${encodeURIComponent(vendorId)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision,
        reviewer: "Umang Mittal",
        comment,
      }),
    });
    toast(`Final status: ${result.final_status}`);
    await loadQueue();
    await loadDashboard();
    $("#reviewDetail").innerHTML = `
      <div class="empty-state">
        <h3>Decision saved</h3>
        <p>Agent recommendation: ${esc(result.agent_recommendation)}<br>Human decision: ${esc(result.human_decision)}<br>Final status: ${esc(result.final_status)}</p>
      </div>
    `;
  } catch (error) {
    alertMessage(error.message);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

document.addEventListener("click", event => {
  const nav = event.target.closest("[data-view], [data-view-target]");
  if (nav) showView(nav.dataset.view || nav.dataset.viewTarget);

  const open = event.target.closest("[data-open-vendor]");
  if (open) openVendor(open.dataset.openVendor);

  const remove = event.target.closest("[data-remove-file]");
  if (remove) {
    state.selectedFiles.splice(Number(remove.dataset.removeFile), 1);
    renderFiles();
  }

  const review = event.target.closest("[data-review-id]");
  if (review) openReview(review.dataset.reviewId);

  const decision = event.target.closest("[data-decision]");
  if (decision) submitDecision(decision);
});

$("#files").addEventListener("change", event => {
  state.selectedFiles = [...event.target.files];
  renderFiles();
});

$("#vendorForm").addEventListener("submit", submitVendor);
$("#resetForm").addEventListener("click", () => {
  $("#vendorForm").reset();
  state.selectedFiles = [];
  renderFiles();
  alertMessage("");
});
$("#dashboardFilter").addEventListener("change", renderDashboard);
$("#refreshDashboard").addEventListener("click", loadDashboard);
$("#refreshQueue").addEventListener("click", loadQueue);

checkHealth();
loadDashboard();
