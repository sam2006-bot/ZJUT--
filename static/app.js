const form = document.getElementById("grader-form");
const fileInput = document.getElementById("student_code");
const fileName = document.getElementById("file-name");
const submitButton = document.getElementById("submit-button");
const statusBox = document.getElementById("status");
const resultBox = document.getElementById("result");
const addCaseBtn = document.getElementById("add-test-case");
const casesContainer = document.getElementById("test-cases-container");

let caseCount = 0;

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escapeHtml(value) {
  return value
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
    statusBox.textContent = "请先上传代码文件。";
    return;
  }

  submitButton.disabled = true;
  resultBox.classList.add("is-loading");

  var testCases = collectTestCases();
  if (testCases.length > 0) {
    statusBox.textContent = "正在运行测试样例并等待 AI 分析...";
  } else {
    statusBox.textContent = "Claude 正在批改，请稍候...";
  }
  resultBox.innerHTML = "<p>正在发送代码和作业要求到后端。</p>";

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

    statusBox.textContent = "批改完成。";

    var output = "";
    if (payload.test_results) {
      output += renderTestResults(payload.test_results);
    }
    output += renderMarkdown(payload.result);
    resultBox.innerHTML = output;
  } catch (error) {
    statusBox.textContent = "批改失败。";
    resultBox.innerHTML = "<p>" + escapeHtml(error.message) + "</p>";
  } finally {
    submitButton.disabled = false;
    resultBox.classList.remove("is-loading");
  }
});
