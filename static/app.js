const form = document.getElementById("grader-form");
const fileInput = document.getElementById("student_code");
const fileName = document.getElementById("file-name");
const submitButton = document.getElementById("submit-button");
const statusBox = document.getElementById("status");
const resultBox = document.getElementById("result");
const resultToolbar = document.getElementById("result-toolbar");
const exportLink = document.getElementById("export-link");
const batchSummaryBox = document.getElementById("batch-summary");
const addCaseBtn = document.getElementById("add-test-case");
const casesContainer = document.getElementById("test-cases-container");

let caseCount = 0;

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderMarkdown(markdown) {
  if (window.marked && typeof window.marked.parse === "function") {
    return window.marked.parse(markdown);
  }
  return "<pre>" + escapeHtml(markdown) + "</pre>";
}

function resetBatchUi() {
  resultToolbar.hidden = true;
  exportLink.hidden = true;
  exportLink.removeAttribute("href");
  exportLink.removeAttribute("download");
  batchSummaryBox.hidden = true;
  batchSummaryBox.innerHTML = "";
}

function formatScore(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "未提取";
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function renderMetaPill(label, kind) {
  return '<span class="meta-pill ' + (kind || "") + '">' + escapeHtml(label) + "</span>";
}

// ---------------------------------------------------------------------------
// Test case management
// ---------------------------------------------------------------------------

function addTestCase() {
  caseCount++;
  const card = document.createElement("div");
  card.className = "test-case-card";
  card.innerHTML =
    '<div class="test-case-card-header">' +
    "<span></span>" +
    '<button type="button" class="btn-remove-case" title="删除此样例">&times;</button>' +
    "</div>" +
    '<label class="field">' +
    "<span>输入</span>" +
    '<textarea class="test-input" rows="3" placeholder="程序的标准输入（stdin）"></textarea>' +
    "</label>" +
    '<label class="field">' +
    "<span>期望输出</span>" +
    '<textarea class="test-output" rows="3" placeholder="期望的标准输出（stdout）"></textarea>' +
    "</label>";
  card.querySelector(".btn-remove-case").addEventListener("click", function () {
    card.remove();
    renumberCases();
  });
  casesContainer.appendChild(card);
  renumberCases();
}

function renumberCases() {
  var cards = casesContainer.querySelectorAll(".test-case-card");
  cards.forEach(function (card, i) {
    card.querySelector(".test-case-card-header span").textContent = "样例 " + (i + 1);
  });
  caseCount = cards.length;
}

function collectTestCases() {
  var cases = [];
  casesContainer.querySelectorAll(".test-case-card").forEach(function (card) {
    var input = card.querySelector(".test-input").value;
    var output = card.querySelector(".test-output").value;
    if (input !== "" || output !== "") {
      cases.push({ input: input, expected_output: output });
    }
  });
  return cases;
}

// ---------------------------------------------------------------------------
// Test results rendering
// ---------------------------------------------------------------------------

function renderTestResults(tr) {
  if (!tr || !tr.cases || tr.cases.length === 0) return "";

  var statusLabels = {
    passed: "通过",
    wrong_answer: "答案错误",
    runtime_error: "运行时错误",
    timeout: "超时",
    compile_error: "编译错误",
  };
  var statusClasses = {
    passed: "status-passed",
    wrong_answer: "status-wrong",
    runtime_error: "status-error",
    timeout: "status-timeout",
    compile_error: "status-error",
  };

  var pct = tr.total > 0 ? Math.round((tr.passed / tr.total) * 100) : 0;
  var summaryClass =
    pct === 100 ? "summary-all-pass" : pct > 0 ? "summary-partial" : "summary-all-fail";

  var html = '<div class="test-results-panel">';
  html += "<h3>自动测试结果</h3>";
  html += '<div class="test-summary ' + summaryClass + '">';
  html += "<strong>" + tr.passed + "/" + tr.total + "</strong> 样例通过";
  if (tr.compile_error) html += " · 编译错误";
  html += "</div>";

  html += '<table class="test-results-table">';
  html += "<thead><tr><th>#</th><th>状态</th><th>输入</th><th>期望输出</th><th>实际输出</th></tr></thead>";
  html += "<tbody>";
  for (var i = 0; i < tr.cases.length; i++) {
    var c = tr.cases[i];
    var cls = statusClasses[c.status] || "";
    var label = statusLabels[c.status] || c.status;
    html += '<tr class="' + cls + '">';
    html += "<td>" + c.index + "</td>";
    html += '<td class="status-cell">' + label + "</td>";
    html += "<td><pre>" + escapeHtml(c.input || "") + "</pre></td>";
    html += "<td><pre>" + escapeHtml(c.expected || "") + "</pre></td>";
    html += "<td><pre>" + escapeHtml(c.actual || "") + "</pre></td>";
    html += "</tr>";
    if (c.error_message) {
      html +=
        '<tr class="' +
        cls +
        '"><td colspan="5" class="error-detail">' +
        escapeHtml(c.error_message) +
        "</td></tr>";
    }
  }
  html += "</tbody></table></div>";
  return html;
}

function renderSingleHeader(payload) {
  var bits = [];
  if (typeof payload.score === "number") {
    bits.push(renderMetaPill("分数 " + formatScore(payload.score), "pill-score"));
  }
  if (payload.confidence) {
    bits.push(renderMetaPill("置信度 " + payload.confidence, "pill-muted"));
  }
  if (bits.length === 0) return "";
  return '<div class="result-meta-row">' + bits.join("") + "</div>";
}

function renderDistribution(distribution) {
  var keys = Object.keys(distribution || {});
  if (keys.length === 0) return "";

  var items = keys.map(function (key) {
    return (
      '<li><span class="distribution-label">' +
      escapeHtml(key) +
      '</span><strong>' +
      escapeHtml(distribution[key]) +
      "</strong></li>"
    );
  });
  return '<ul class="distribution-list">' + items.join("") + "</ul>";
}

function renderBatchSummary(summary, archiveName) {
  var metrics = [
    {
      label: "提交数",
      value: summary.total_submissions || 0,
    },
    {
      label: "成功批改",
      value: summary.successful_submissions || 0,
    },
    {
      label: "失败数",
      value: summary.failed_submissions || 0,
    },
    {
      label: "平均分",
      value:
        typeof summary.average_score === "number" ? formatScore(summary.average_score) : "未提取",
    },
  ];

  var html = "";
  html += '<div class="batch-summary-header">';
  html += "<h3>批量批改完成</h3>";
  html += "<p>压缩包：" + escapeHtml(archiveName || "未命名压缩包") + "</p>";
  html += "</div>";
  html += '<div class="summary-metrics">';
  metrics.forEach(function (metric) {
    html +=
      '<div class="summary-metric"><span class="metric-label">' +
      escapeHtml(metric.label) +
      '</span><strong>' +
      escapeHtml(metric.value) +
      "</strong></div>";
  });
  html += "</div>";

  html += '<div class="summary-detail-grid">';
  html += '<section class="summary-panel">';
  html += "<h4>分数分布</h4>";
  html += renderDistribution(summary.score_distribution);
  html += "</section>";

  if (summary.test_summary) {
    html += '<section class="summary-panel">';
    html += "<h4>自动测试汇总</h4>";
    html += '<ul class="distribution-list">';
    html +=
      "<li><span>参与测试的提交</span><strong>" +
      escapeHtml(summary.test_summary.students_with_tests) +
      "</strong></li>";
    html +=
      "<li><span>总样例通过</span><strong>" +
      escapeHtml(summary.test_summary.passed_cases) +
      "/" +
      escapeHtml(summary.test_summary.total_cases) +
      "</strong></li>";
    html +=
      "<li><span>全样例通过提交</span><strong>" +
      escapeHtml(summary.test_summary.full_pass_submissions) +
      "</strong></li>";
    html += "</ul></section>";
  }

  html += "</div>";
  batchSummaryBox.innerHTML = html;
  batchSummaryBox.hidden = false;
}

function renderSubmissionFiles(files) {
  if (!files || files.length === 0) {
    return "";
  }
  return (
    '<div class="submission-files">' +
    files
      .map(function (file) {
        return '<span class="file-chip">' + escapeHtml(file) + "</span>";
      })
      .join("") +
    "</div>"
  );
}

function renderBatchResultCard(item) {
  var headerBits = [];
  if (typeof item.score === "number") {
    headerBits.push(renderMetaPill("分数 " + formatScore(item.score), "pill-score"));
  }
  if (item.confidence) {
    headerBits.push(renderMetaPill("置信度 " + item.confidence, "pill-muted"));
  }
  if (item.test_results) {
    headerBits.push(
      renderMetaPill(
        "测试 " + item.test_results.passed + "/" + item.test_results.total,
        item.test_results.passed === item.test_results.total ? "pill-success" : "pill-warning"
      )
    );
  }
  if (!item.ok) {
    headerBits.push(renderMetaPill("批改失败", "pill-error"));
  }

  var bodyHtml = "";
  if (item.ok) {
    if (item.test_results) {
      bodyHtml += renderTestResults(item.test_results);
    }
    bodyHtml += renderMarkdown(item.result || "");
  } else {
    bodyHtml =
      '<div class="batch-error-card"><strong>错误</strong><p>' +
      escapeHtml(item.error || "未知错误") +
      "</p></div>";
  }

  return (
    '<section class="batch-result-card">' +
    '<div class="batch-result-header">' +
    '<div class="batch-result-title">' +
    "<h3>" +
    escapeHtml(item.submission_name || "未命名提交") +
    "</h3>" +
    "<p>" +
    escapeHtml((item.file_count || 0) + " 个文件") +
    "</p>" +
    "</div>" +
    '<div class="batch-result-badges">' +
    headerBits.join("") +
    "</div>" +
    "</div>" +
    renderSubmissionFiles(item.files) +
    '<div class="batch-result-body">' +
    bodyHtml +
    "</div>" +
    "</section>"
  );
}

function renderBatchResults(results) {
  if (!results || results.length === 0) {
    return "<p>没有可显示的批量结果。</p>";
  }

  return (
    '<div class="batch-result-list">' +
    results.map(renderBatchResultCard).join("") +
    "</div>"
  );
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------

addCaseBtn.addEventListener("click", addTestCase);

fileInput.addEventListener("change", function () {
  var file = fileInput.files[0];
  fileName.textContent = file ? file.name : "尚未选择文件";
});

form.addEventListener("submit", async function (event) {
  event.preventDefault();

  if (!fileInput.files[0]) {
    statusBox.textContent = "请先上传代码文件或 ZIP 压缩包。";
    return;
  }

  submitButton.disabled = true;
  resultBox.classList.add("is-loading");
  resetBatchUi();

  var selectedFile = fileInput.files[0];
  var isBatch = selectedFile.name.toLowerCase().endsWith(".zip");
  var testCases = collectTestCases();
  if (isBatch && testCases.length > 0) {
    statusBox.textContent = "正在批量运行测试并逐份批改 ZIP 中的提交，这可能需要一些时间...";
  } else if (isBatch) {
    statusBox.textContent = "正在批量批改 ZIP 中的学生代码，请稍候...";
  } else if (testCases.length > 0) {
    statusBox.textContent = "正在运行测试样例并等待 AI 分析...";
  } else {
    statusBox.textContent = "Claude 正在批改，请稍候...";
  }
  resultBox.innerHTML = isBatch
    ? "<p>正在上传 ZIP 压缩包并准备批量批改。</p>"
    : "<p>正在发送代码和作业要求到后端。</p>";

  try {
    var formData = new FormData(form);
    if (testCases.length > 0) {
      formData.append("test_cases", JSON.stringify(testCases));
    }

    var response = await fetch("/grade", {
      method: "POST",
      body: formData,
    });

    var payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "批改失败，请稍后重试。");
    }

    if (payload.mode === "batch") {
      statusBox.textContent = "批量批改完成。";
      renderBatchSummary(payload.summary || {}, payload.archive_name || selectedFile.name);
      if (payload.export_url) {
        resultToolbar.hidden = false;
        exportLink.hidden = false;
        exportLink.href = payload.export_url;
        exportLink.download = payload.export_filename || "";
      }
      resultBox.innerHTML = renderBatchResults(payload.results || []);
    } else {
      statusBox.textContent = "批改完成。";

      var output = renderSingleHeader(payload);
      if (payload.test_results) {
        output += renderTestResults(payload.test_results);
      }
      output += renderMarkdown(payload.result || "");
      resultBox.innerHTML = output;
    }
  } catch (error) {
    statusBox.textContent = "批改失败。";
    resultBox.innerHTML = "<p>" + escapeHtml(error.message) + "</p>";
  } finally {
    submitButton.disabled = false;
    resultBox.classList.remove("is-loading");
  }
});
