const form = document.getElementById("grader-form");
const fileInput = document.getElementById("student_code");
const fileName = document.getElementById("file-name");
const submitButton = document.getElementById("submit-button");
const statusBox = document.getElementById("status");
const resultBox = document.getElementById("result");

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderResult(markdown) {
  if (window.marked && typeof window.marked.parse === "function") {
    return window.marked.parse(markdown);
  }
  return "<pre>" + escapeHtml(markdown) + "</pre>";
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  fileName.textContent = file ? file.name : "尚未选择文件";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!fileInput.files[0]) {
    statusBox.textContent = "请先上传代码文件。";
    return;
  }

  submitButton.disabled = true;
  statusBox.textContent = "Claude 正在批改，请稍候...";
  resultBox.classList.add("is-loading");
  resultBox.innerHTML = "<p>正在发送代码和作业要求到后端。</p>";

  try {
    const response = await fetch("/grade", {
      method: "POST",
      body: new FormData(form),
    });

    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "批改失败，请稍后重试。");
    }

    statusBox.textContent = "批改完成。";
    resultBox.innerHTML = renderResult(payload.result);
  } catch (error) {
    statusBox.textContent = "批改失败。";
    resultBox.innerHTML = "<p>" + escapeHtml(error.message) + "</p>";
  } finally {
    submitButton.disabled = false;
    resultBox.classList.remove("is-loading");
  }
});
