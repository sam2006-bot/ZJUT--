from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
import csv
import datetime as dt
import hashlib
import hmac
import html
import io
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import urllib.error
import urllib.request
import urllib.parse
import zipfile
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Dict, Optional

import code_runner


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"
SKILL_PATH = ROOT / ".claude" / "skills" / "student-code-grader" / "SKILL.md"
LOGIN_TEMPLATE_PATH = TEMPLATES_DIR / "login.html"
ENV_PATH = ROOT / ".env"
MAX_SINGLE_UPLOAD_BYTES = 1024 * 1024
MAX_BATCH_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_BATCH_EXTRACTED_BYTES = 40 * 1024 * 1024
MAX_SOURCE_FILE_BYTES = 1024 * 1024
MAX_ARCHIVE_SOURCE_FILES = 500
MAX_BATCH_SUBMISSIONS = 200
MAX_FORM_BYTES = MAX_BATCH_UPLOAD_BYTES + 256 * 1024
SESSION_COOKIE_NAME = "invite_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
SUPPORTED_SOURCE_EXTENSIONS = {".py", ".c", ".cpp", ".cxx", ".cc", ".java"}
EXPORT_CACHE_LIMIT = 24
MACHINE_TAG_PATTERN = re.compile(
    r"^\[\[(FINAL_SCORE|CONFIDENCE):\s*(.*?)\]\]\s*$",
    re.MULTILINE,
)
FALLBACK_SCORE_PATTERN = re.compile(
    r"(?:最终分数|最终得分|Final Score|Score)[^0-9]{0,20}([0-9]{1,3}(?:\.\d+)?)",
    re.IGNORECASE,
)


@dataclass
class UploadedFile:
    filename: str
    content: bytes


@dataclass
class MultipartForm:
    fields: Dict[str, str]
    files: Dict[str, UploadedFile]


@dataclass
class SubmissionFile:
    relative_path: str
    content: str


@dataclass
class SubmissionPackage:
    identifier: str
    display_name: str
    files: list[SubmissionFile]


@dataclass
class ExportBundle:
    filename: str
    content_type: str
    content: bytes


EXPORT_CACHE: Dict[str, ExportBundle] = {}
EXPORT_CACHE_LOCK = threading.Lock()


def load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def read_skill_prompt() -> str:
    if SKILL_PATH.exists():
        return SKILL_PATH.read_text(encoding="utf-8")
    return (
        "Grade the student's code fairly based on the assignment requirements. "
        "Explain strengths, weaknesses, score breakdown, and final score."
    )


def build_user_prompt(fields: Dict[str, str], file_name: str, code_text: str, test_results_text: str = "") -> str:
    base = f"""[Mode]
{fields.get("mode", "Teacher")}

[Assignment Title]
{fields.get("assignment_title", "").strip() or "未提供"}

[Assignment Requirements]
{fields.get("assignment_requirements", "").strip() or "未提供，需根据代码内容做合理假设并明确写出假设。"}

[Task Goal]
{fields.get("task_goal", "").strip() or "未提供"}

[Programming Language]
{fields.get("programming_language", "").strip() or "请根据代码自动判断"}

[Optional Rubric]
{fields.get("rubric", "").strip() or "未提供，默认使用 skill 中的评分规则"}

[Student File Name]
{file_name}

[Student Code]
{code_text}"""

    if test_results_text:
        base += f"""

[Automated Test Results]
以下是系统自动运行学生代码后得到的测试结果，请将其作为判断正确性的首要依据。

{test_results_text}"""

        base += """

请严格依据上述信息进行批改，并使用中文输出。
输出时请使用以下结构：
1. 总评
2. 自动测试结果分析（逐个分析失败样例的原因）
3. 分项评分
4. 主要优点
5. 主要问题与错误原因分析
6. 改进建议
7. 最终分数（0-100）
8. 置信度

最后请在回复末尾额外追加以下两行机器读取标记，不要放进代码块，也不要省略：
[[FINAL_SCORE: 0-100 的整数]]
[[CONFIDENCE: 高/中/低]]"""
    else:
        base += """

请严格依据上述信息进行批改，并使用中文输出。
输出时请使用以下结构：
1. 总评
2. 分项评分
3. 主要优点
4. 主要问题
5. 改进建议
6. 最终分数（0-100）
7. 置信度

最后请在回复末尾额外追加以下两行机器读取标记，不要放进代码块，也不要省略：
[[FINAL_SCORE: 0-100 的整数]]
[[CONFIDENCE: 高/中/低]]"""

    return base.strip()


def format_test_results_for_prompt(results: dict) -> str:
    """Format test suite results as text for inclusion in the AI prompt."""
    compare_mode_labels = {
        "strict": "严格匹配（去除首尾空白）",
        "numbers_only": "仅比较数字（忽略文字描述）",
        "contains": "包含匹配（期望出现在实际输出中）",
    }
    lines = [
        f"总样例数: {results['total']}",
        f"通过: {results['passed']}",
        f"失败: {results['failed']}",
    ]
    mode = results.get("compare_mode")
    if mode:
        lines.append(f"输出比较模式: {compare_mode_labels.get(mode, mode)}")
    if results.get("compile_error"):
        lines.append(f"编译错误: {results['compile_error']}")
    lines.append("")

    status_labels = {
        "passed": "通过",
        "wrong_answer": "答案错误",
        "runtime_error": "运行时错误",
        "timeout": "超时",
        "compile_error": "编译错误",
    }
    for case in results["cases"]:
        label = status_labels.get(case["status"], case["status"])
        lines.append(f"--- 样例 {case['index']} [{label}] ---")
        lines.append(f"输入:\n{case['input']}")
        lines.append(f"期望输出:\n{case['expected']}")
        lines.append(f"实际输出:\n{case['actual']}")
        if case.get("error_message"):
            lines.append(f"错误信息: {case['error_message']}")
        lines.append("")

    return "\n".join(lines)


def extract_text_from_openai_response(payload: Dict) -> str:
    choices = payload.get("choices", [])
    if not isinstance(choices, list):
        return ""

    for choice in choices:
        if not isinstance(choice, dict):
            continue

        message = choice.get("message", {})
        if not isinstance(message, dict):
            continue

        content = message.get("content", "")
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):
            texts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "text":
                    continue
                text_value = block.get("text", "")
                if isinstance(text_value, str) and text_value.strip():
                    texts.append(text_value.strip())
            if texts:
                return "\n".join(texts).strip()

        refusal = message.get("refusal", "")
        if isinstance(refusal, str) and refusal.strip():
            return refusal.strip()

    return ""


def get_invite_codes() -> list[str]:
    raw_values = [os.getenv("INVITE_CODES", ""), os.getenv("INVITE_CODE", "")]
    codes = []
    for raw_value in raw_values:
        for chunk in raw_value.replace("\n", ",").split(","):
            code = chunk.strip()
            if code:
                codes.append(code)
    return codes


def auth_enabled() -> bool:
    return bool(get_invite_codes())


def get_session_secret() -> str:
    return os.getenv("INVITE_SESSION_SECRET", "").strip()


def validate_auth_configuration() -> None:
    if auth_enabled() and not get_session_secret():
        raise RuntimeError("配置了 INVITE_CODES 后，必须同时配置 INVITE_SESSION_SECRET。")


def hash_invite_code(invite_code: str) -> str:
    return hashlib.sha256(invite_code.encode("utf-8")).hexdigest()


def sign_value(value: str) -> str:
    secret = get_session_secret().encode("utf-8")
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(invite_code: str) -> str:
    digest = hash_invite_code(invite_code)
    return f"{digest}.{sign_value(digest)}"


def is_valid_invite_code(invite_code: str) -> bool:
    for allowed_code in get_invite_codes():
        if hmac.compare_digest(invite_code, allowed_code):
            return True
    return False


def is_valid_session_token(token: str) -> bool:
    if not token or "." not in token:
        return False

    digest, signature = token.split(".", 1)
    if not digest or not signature:
        return False
    if not hmac.compare_digest(signature, sign_value(digest)):
        return False

    allowed_digests = {hash_invite_code(code) for code in get_invite_codes()}
    return digest in allowed_digests


def parse_urlencoded_form(headers, rfile) -> Dict[str, str]:
    content_type = headers.get("Content-Type", "")
    if "application/x-www-form-urlencoded" not in content_type:
        raise ValueError("请求格式错误，请使用邀请码表单登录。")

    try:
        content_length = int(headers.get("Content-Length", ""))
    except ValueError as error:
        raise ValueError("请求缺少有效的 Content-Length。") from error

    if content_length <= 0 or content_length > 8192:
        raise ValueError("邀请码请求无效。")

    body = rfile.read(content_length).decode("utf-8", errors="replace")
    parsed = urllib.parse.parse_qs(body, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


def parse_multipart_form(headers, rfile) -> MultipartForm:
    content_type = headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ValueError("请求格式错误，请使用表单上传代码文件。")

    try:
        content_length = int(headers.get("Content-Length", ""))
    except ValueError as error:
        raise ValueError("请求缺少有效的 Content-Length。") from error

    if content_length <= 0:
        raise ValueError("请求体为空。")
    if content_length > MAX_FORM_BYTES:
        raise ValueError("上传内容过大，请控制单个代码文件在 1MB 以内、ZIP 压缩包在 20MB 以内。")

    body = rfile.read(content_length)
    if len(body) != content_length:
        raise ValueError("请求体不完整。")

    # The email parser expects MIME headers before the multipart body.
    parser_input = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    message = BytesParser(policy=policy.default).parsebytes(parser_input)
    if not message.is_multipart():
        raise ValueError("请求格式错误，请使用表单上传代码文件。")

    fields: Dict[str, str] = {}
    files: Dict[str, UploadedFile] = {}
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue

        name = part.get_param("name", header="content-disposition")
        if not name:
            continue

        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename:
            files[name] = UploadedFile(filename=filename, content=payload)
            continue

        charset = part.get_content_charset() or "utf-8"
        fields[name] = payload.decode(charset, errors="replace")

    return MultipartForm(fields=fields, files=files)


def build_openai_endpoint(api_base_url: str, api_path: str) -> str:
    normalized_base = api_base_url.rstrip("/")
    normalized_path = f"/{api_path.lstrip('/')}"
    if normalized_base.endswith("/v1") and normalized_path.startswith("/v1/"):
        normalized_path = normalized_path.removeprefix("/v1")
    return f"{normalized_base}{normalized_path}"


def normalize_compare_mode(raw_value: str) -> str:
    compare_mode = raw_value.strip() or "strict"
    if compare_mode not in {"strict", "numbers_only", "contains"}:
        return "strict"
    return compare_mode


def build_grading_fields(raw_fields: Dict[str, str]) -> Dict[str, str]:
    return {
        "mode": str(raw_fields.get("mode", "Teacher")),
        "assignment_title": str(raw_fields.get("assignment_title", "")),
        "assignment_requirements": str(raw_fields.get("assignment_requirements", "")),
        "task_goal": str(raw_fields.get("task_goal", "")),
        "programming_language": str(raw_fields.get("programming_language", "")),
        "rubric": str(raw_fields.get("rubric", "")),
    }


def parse_test_cases(raw_cases: str) -> list[dict]:
    raw_cases = raw_cases.strip()
    if not raw_cases:
        return []

    try:
        loaded = json.loads(raw_cases)
    except (json.JSONDecodeError, TypeError):
        return []

    test_cases = []
    if not isinstance(loaded, list):
        return test_cases

    for raw_case in loaded:
        if not isinstance(raw_case, dict):
            continue
        if "input" not in raw_case and "expected_output" not in raw_case:
            continue
        test_cases.append(
            {
                "input": str(raw_case.get("input", "")),
                "expected_output": str(raw_case.get("expected_output", "")),
            }
        )

    return test_cases


def decode_text_content(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("utf-8", errors="replace")


def format_submission_code(files: list[SubmissionFile]) -> str:
    if len(files) == 1:
        return files[0].content

    chunks = []
    for submission_file in files:
        chunks.append(
            f"===== 文件: {submission_file.relative_path} =====\n{submission_file.content}"
        )
    return "\n\n".join(chunks)


def build_submission_summary(submission: SubmissionPackage) -> str:
    if len(submission.files) == 1:
        return submission.files[0].relative_path
    return f"{submission.display_name}（{len(submission.files)} 个文件）"


def sanitize_submission_identifier(value: str) -> str:
    identifier = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return identifier or "submission"


def build_single_submission(upload: UploadedFile) -> SubmissionPackage:
    if not upload.filename:
        raise ValueError("上传文件缺少文件名。")

    if len(upload.content) > MAX_SINGLE_UPLOAD_BYTES:
        raise ValueError("上传文件过大，请控制在 1MB 以内。")

    code_text = decode_text_content(upload.content)
    if not code_text.strip():
        raise ValueError("上传的代码文件内容为空。")

    return SubmissionPackage(
        identifier=sanitize_submission_identifier(Path(upload.filename).stem or upload.filename),
        display_name=upload.filename,
        files=[SubmissionFile(relative_path=upload.filename, content=code_text)],
    )


def is_supported_source_file(path: PurePosixPath) -> bool:
    return path.suffix.lower() in SUPPORTED_SOURCE_EXTENSIONS


def normalize_archive_member_path(name: str) -> Optional[PurePosixPath]:
    normalized = PurePosixPath(name.replace("\\", "/"))
    if normalized.is_absolute():
        return None

    clean_parts = []
    for part in normalized.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            return None
        if part == "__MACOSX" or part.startswith("."):
            return None
        clean_parts.append(part)

    if not clean_parts:
        return None

    return PurePosixPath(*clean_parts)


def strip_common_archive_root(paths: list[PurePosixPath]) -> list[PurePosixPath]:
    trimmed = list(paths)
    while trimmed and all(len(path.parts) > 1 for path in trimmed):
        first_component = trimmed[0].parts[0]
        if not all(path.parts[0] == first_component for path in trimmed):
            break
        trimmed = [PurePosixPath(*path.parts[1:]) for path in trimmed]
    return trimmed


def build_batch_submissions(upload: UploadedFile) -> list[SubmissionPackage]:
    if len(upload.content) > MAX_BATCH_UPLOAD_BYTES:
        raise ValueError("ZIP 压缩包过大，请控制在 20MB 以内。")

    source_entries: list[tuple[PurePosixPath, str]] = []
    total_uncompressed_bytes = 0
    try:
        with zipfile.ZipFile(io.BytesIO(upload.content)) as archive:
            for file_info in archive.infolist():
                if file_info.is_dir():
                    continue

                normalized_path = normalize_archive_member_path(file_info.filename)
                if normalized_path is None:
                    continue

                total_uncompressed_bytes += file_info.file_size
                if total_uncompressed_bytes > MAX_BATCH_EXTRACTED_BYTES:
                    raise ValueError("ZIP 解压后的内容过大，请减少文件数量或压缩包体积。")

                if file_info.file_size > MAX_SOURCE_FILE_BYTES:
                    raise ValueError(f"压缩包内文件过大：{normalized_path.name} 超过 1MB。")

                if not is_supported_source_file(normalized_path):
                    continue

                content = decode_text_content(archive.read(file_info))
                source_entries.append((normalized_path, content))
    except zipfile.BadZipFile as error:
        raise ValueError("上传的 ZIP 压缩包无效。") from error

    if not source_entries:
        raise ValueError("ZIP 压缩包中没有找到可批改的源代码文件。")

    if len(source_entries) > MAX_ARCHIVE_SOURCE_FILES:
        raise ValueError("ZIP 中的源代码文件数量过多，请控制在 500 个以内。")

    normalized_paths = strip_common_archive_root([path for path, _ in source_entries])
    grouped_files: Dict[str, list[SubmissionFile]] = {}
    for (_, content), normalized_path in zip(source_entries, normalized_paths):
        if len(normalized_path.parts) > 1:
            group_name = normalized_path.parts[0]
            relative_path = PurePosixPath(*normalized_path.parts[1:])
        else:
            group_name = normalized_path.name
            relative_path = normalized_path

        grouped_files.setdefault(group_name, []).append(
            SubmissionFile(relative_path=str(relative_path), content=content)
        )

    if len(grouped_files) > MAX_BATCH_SUBMISSIONS:
        raise ValueError("批量批改的提交数量过多，请控制在 200 份以内。")

    submissions = []
    for display_name in sorted(grouped_files):
        files = sorted(grouped_files[display_name], key=lambda item: item.relative_path)
        submissions.append(
            SubmissionPackage(
                identifier=sanitize_submission_identifier(display_name),
                display_name=display_name,
                files=files,
            )
        )
    return submissions


def extract_review_metadata(review_text: str) -> tuple[Optional[float], str, str]:
    metadata: Dict[str, str] = {}
    for key, value in MACHINE_TAG_PATTERN.findall(review_text):
        metadata[key] = value.strip()

    cleaned = MACHINE_TAG_PATTERN.sub("", review_text).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    confidence = metadata.get("CONFIDENCE", "")

    score: Optional[float] = None
    raw_score = metadata.get("FINAL_SCORE", "")
    if raw_score:
        match = re.search(r"[0-9]{1,3}(?:\.\d+)?", raw_score)
        if match:
            score = max(0.0, min(100.0, float(match.group(0))))

    if score is None:
        fallback = FALLBACK_SCORE_PATTERN.search(cleaned)
        if fallback:
            score = max(0.0, min(100.0, float(fallback.group(1))))

    return score, confidence, cleaned


def grade_submission(
    submission: SubmissionPackage,
    fields: Dict[str, str],
    test_cases: list[dict],
    compare_mode: str,
    system_prompt: str,
) -> dict:
    code_text = format_submission_code(submission.files)
    if not code_text.strip():
        raise ValueError("提交内容为空。")

    test_results = None
    test_results_text = ""
    if test_cases:
        suite = code_runner.run_submission_test_cases(
            [{"path": file.relative_path, "content": file.content} for file in submission.files],
            fields["programming_language"],
            test_cases,
            compare_mode=compare_mode,
        )
        test_results = suite.to_dict()
        test_results["compare_mode"] = compare_mode
        test_results_text = format_test_results_for_prompt(test_results)

    user_prompt = build_user_prompt(
        fields,
        build_submission_summary(submission),
        code_text,
        test_results_text,
    )
    raw_review = call_openai_compatible_api(system_prompt, user_prompt)
    score, confidence, review_text = extract_review_metadata(raw_review)

    result = {
        "ok": True,
        "submission_id": submission.identifier,
        "submission_name": submission.display_name,
        "file_count": len(submission.files),
        "files": [file.relative_path for file in submission.files],
        "result": review_text,
        "confidence": confidence,
    }
    if score is not None:
        result["score"] = round(score, 2)
    if test_results is not None:
        result["test_results"] = test_results
    return result


def build_failed_submission_result(submission: SubmissionPackage, error: Exception) -> dict:
    return {
        "ok": False,
        "submission_id": submission.identifier,
        "submission_name": submission.display_name,
        "file_count": len(submission.files),
        "files": [file.relative_path for file in submission.files],
        "error": str(error),
    }


def build_score_distribution(scores: list[float]) -> Dict[str, int]:
    buckets = {
        "90-100": 0,
        "80-89": 0,
        "70-79": 0,
        "60-69": 0,
        "0-59": 0,
    }
    for score in scores:
        if score >= 90:
            buckets["90-100"] += 1
        elif score >= 80:
            buckets["80-89"] += 1
        elif score >= 70:
            buckets["70-79"] += 1
        elif score >= 60:
            buckets["60-69"] += 1
        else:
            buckets["0-59"] += 1
    return buckets


def build_batch_summary(results: list[dict]) -> dict:
    successful_results = [result for result in results if result.get("ok")]
    scores = [
        float(result["score"])
        for result in successful_results
        if isinstance(result.get("score"), (int, float))
    ]
    test_results = [result["test_results"] for result in successful_results if result.get("test_results")]

    test_summary = None
    if test_results:
        total_cases = sum(result["total"] for result in test_results)
        passed_cases = sum(result["passed"] for result in test_results)
        test_summary = {
            "students_with_tests": len(test_results),
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": total_cases - passed_cases,
            "full_pass_submissions": sum(
                1 for result in test_results if result["total"] > 0 and result["passed"] == result["total"]
            ),
        }

    summary = {
        "total_submissions": len(results),
        "successful_submissions": len(successful_results),
        "failed_submissions": len(results) - len(successful_results),
        "scored_submissions": len(scores),
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
        "max_score": max(scores) if scores else None,
        "min_score": min(scores) if scores else None,
        "score_distribution": build_score_distribution(scores) if scores else {},
    }
    if test_summary is not None:
        summary["test_summary"] = test_summary
    return summary


def safe_export_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return cleaned or fallback


def build_batch_export_report(result: dict) -> str:
    lines = [f"# {result['submission_name']}", ""]
    lines.append(f"状态：{'批改成功' if result.get('ok') else '批改失败'}")
    lines.append(f"文件数：{result.get('file_count', 0)}")
    lines.append(f"文件列表：{', '.join(result.get('files', [])) or '无'}")
    if result.get("score") is not None:
        lines.append(f"最终分数：{result['score']}")
    if result.get("confidence"):
        lines.append(f"置信度：{result['confidence']}")

    test_results = result.get("test_results")
    if isinstance(test_results, dict):
        lines.append(
            f"自动测试：{test_results.get('passed', 0)}/{test_results.get('total', 0)} 通过"
        )

    lines.append("")
    if result.get("ok"):
        lines.append(result.get("result", ""))
    else:
        lines.append(f"错误：{result.get('error', '未知错误')}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_batch_export_bundle(
    archive_name: str,
    fields: Dict[str, str],
    compare_mode: str,
    results: list[dict],
    summary: dict,
) -> ExportBundle:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "submission_name",
            "status",
            "score",
            "confidence",
            "file_count",
            "files",
            "passed_tests",
            "total_tests",
            "error",
        ]
    )
    for result in results:
        test_results = result.get("test_results") or {}
        writer.writerow(
            [
                result.get("submission_name", ""),
                "success" if result.get("ok") else "failed",
                result.get("score", ""),
                result.get("confidence", ""),
                result.get("file_count", 0),
                " | ".join(result.get("files", [])),
                test_results.get("passed", ""),
                test_results.get("total", ""),
                result.get("error", ""),
            ]
        )

    package_manifest = {
        "archive_name": archive_name,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "fields": fields,
        "compare_mode": compare_mode,
        "summary": summary,
        "results": results,
    }

    archive_buffer = io.BytesIO()
    archive_stem = Path(archive_name).stem or "batch_grading_results"
    export_basename = f"{safe_export_name(archive_stem, 'batch_grading_results')}_grading_export"
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as export_zip:
        export_zip.writestr("grading_results.csv", output.getvalue())
        export_zip.writestr(
            "statistics.json",
            json.dumps(summary, ensure_ascii=False, indent=2),
        )
        export_zip.writestr(
            "grading_results.json",
            json.dumps(package_manifest, ensure_ascii=False, indent=2),
        )
        export_zip.writestr(
            "README.txt",
            "\n".join(
                [
                    "批量批改导出文件说明",
                    "",
                    "grading_results.csv  : 结果总表",
                    "statistics.json     : 汇总统计信息",
                    "grading_results.json: 完整导出数据",
                    "reports/*.md        : 每位学生的批改报告",
                ]
            ),
        )

        for index, result in enumerate(results, start=1):
            report_name = safe_export_name(
                result.get("submission_name", ""),
                f"submission_{index}",
            )
            export_zip.writestr(
                f"reports/{index:03d}_{report_name}.md",
                build_batch_export_report(result),
            )

    return ExportBundle(
        filename=f"{export_basename}.zip",
        content_type="application/zip",
        content=archive_buffer.getvalue(),
    )


def store_export_bundle(bundle: ExportBundle) -> str:
    token = secrets.token_urlsafe(24)
    with EXPORT_CACHE_LOCK:
        EXPORT_CACHE[token] = bundle
        while len(EXPORT_CACHE) > EXPORT_CACHE_LIMIT:
            oldest_token = next(iter(EXPORT_CACHE))
            EXPORT_CACHE.pop(oldest_token, None)
    return token


def get_export_bundle(token: str) -> Optional[ExportBundle]:
    with EXPORT_CACHE_LOCK:
        return EXPORT_CACHE.get(token)


def build_content_disposition(filename: str) -> str:
    ascii_fallback = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename).strip("._") or "download"
    quoted_name = urllib.parse.quote(filename)
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quoted_name}"


def call_openai_compatible_api(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip()
    api_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com").strip()
    api_path = os.getenv("OPENAI_API_PATH", "/v1/chat/completions").strip() or "/v1/chat/completions"
    auth_mode = os.getenv("OPENAI_API_AUTH_MODE", "bearer").strip().lower() or "bearer"
    auth_header = os.getenv("OPENAI_API_AUTH_HEADER", "").strip()
    auth_prefix = os.getenv("OPENAI_API_AUTH_PREFIX", "").strip()

    if not api_key:
        raise ValueError(
            "未配置 OPENAI_API_KEY。请在项目根目录新建 .env 文件，填入你的 OpenAI 兼容代理 key。"
        )

    if not model:
        raise ValueError(
            "未配置 OPENAI_MODEL。请在 .env 中填入你要使用的模型名称。这里仍然可以填写 Claude 模型名。"
        )

    if not api_base_url:
        raise ValueError("未配置有效的 OPENAI_BASE_URL。")

    endpoint = build_openai_endpoint(api_base_url, api_path)

    request_body = {
        "model": model,
        "max_tokens": 4000,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    request_data = json.dumps(request_body).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    if auth_header:
        normalized_prefix = auth_prefix
        if auth_header.lower() == "authorization" and normalized_prefix and not normalized_prefix.endswith(" "):
            normalized_prefix = f"{normalized_prefix} "
        auth_value = f"{normalized_prefix}{api_key}" if normalized_prefix else api_key
        headers[auth_header] = auth_value
    elif auth_mode == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["x-api-key"] = api_key

    request = urllib.request.Request(
        url=endpoint,
        data=request_data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI 兼容代理请求失败（HTTP {error.code}）：{details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"OpenAI 兼容代理网络请求失败：{error.reason}") from error

    text = extract_text_from_openai_response(payload)
    if not text:
        raise RuntimeError("OpenAI 兼容代理返回成功，但响应内容为空。")
    return text


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.route_request(send_body=True)

    def do_HEAD(self) -> None:
        self.route_request(send_body=False)

    def route_request(self, send_body: bool) -> None:
        request_path = urllib.parse.urlparse(self.path).path

        if request_path == "/healthz":
            self.send_json(HTTPStatus.OK, {"ok": True, "status": "healthy"}, send_body=send_body)
            return

        if request_path == "/logout":
            self.clear_session_and_redirect("/")
            return

        if request_path == "/":
            if not self.is_authenticated():
                self.serve_login_page(send_body=send_body)
                return
            self.serve_file(
                TEMPLATES_DIR / "index.html",
                "text/html; charset=utf-8",
                send_body=send_body,
            )
            return

        if request_path.startswith("/exports/"):
            self.handle_export_request(request_path, send_body=send_body)
            return

        if request_path.startswith("/static/"):
            relative_path = request_path.removeprefix("/static/")
            file_path = STATIC_DIR / relative_path
            self.serve_static(file_path, send_body=send_body)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        request_path = urllib.parse.urlparse(self.path).path

        if request_path == "/login":
            self.handle_login_request()
            return

        if request_path != "/grade":
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        if not self.is_authenticated():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "请先输入邀请码。"})
            return

        try:
            response = self.handle_grade_request()
            self.send_json(HTTPStatus.OK, response)
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
        except RuntimeError as error:
            self.send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
        except Exception as error:  # pragma: no cover
            self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": f"服务器内部错误：{error}"},
            )

    def handle_grade_request(self) -> dict:
        form = parse_multipart_form(self.headers, self.rfile)

        upload = form.files.get("student_code")
        if upload is None:
            raise ValueError("请先上传学生代码文件。")

        if not upload.filename:
            raise ValueError("上传文件缺少文件名。")

        fields = build_grading_fields(form.fields)
        compare_mode = normalize_compare_mode(self._get_field_value(form.fields, "compare_mode", "strict"))
        test_cases = parse_test_cases(form.fields.get("test_cases", ""))
        system_prompt = read_skill_prompt()

        if upload.filename.lower().endswith(".zip"):
            submissions = build_batch_submissions(upload)
            results = []
            for submission in submissions:
                try:
                    results.append(
                        grade_submission(
                            submission=submission,
                            fields=fields,
                            test_cases=test_cases,
                            compare_mode=compare_mode,
                            system_prompt=system_prompt,
                        )
                    )
                except Exception as error:
                    results.append(build_failed_submission_result(submission, error))

            summary = build_batch_summary(results)
            bundle = build_batch_export_bundle(
                archive_name=upload.filename,
                fields=fields,
                compare_mode=compare_mode,
                results=results,
                summary=summary,
            )
            export_token = store_export_bundle(bundle)
            return {
                "ok": True,
                "mode": "batch",
                "archive_name": upload.filename,
                "summary": summary,
                "results": results,
                "export_url": f"/exports/{export_token}",
                "export_filename": bundle.filename,
            }

        submission = build_single_submission(upload)
        graded = grade_submission(
            submission=submission,
            fields=fields,
            test_cases=test_cases,
            compare_mode=compare_mode,
            system_prompt=system_prompt,
        )
        response = {
            "ok": True,
            "mode": "single",
            "result": graded["result"],
        }
        if graded.get("score") is not None:
            response["score"] = graded["score"]
        if graded.get("confidence"):
            response["confidence"] = graded["confidence"]
        if graded.get("test_results") is not None:
            response["test_results"] = graded["test_results"]
        return response

    def handle_login_request(self) -> None:
        if not auth_enabled():
            self.redirect("/")
            return

        try:
            fields = parse_urlencoded_form(self.headers, self.rfile)
        except ValueError as error:
            self.serve_login_page(str(error), status=HTTPStatus.BAD_REQUEST)
            return

        invite_code = fields.get("invite_code", "").strip()
        if not invite_code:
            self.serve_login_page("请输入邀请码。", status=HTTPStatus.BAD_REQUEST)
            return

        if not is_valid_invite_code(invite_code):
            self.serve_login_page("邀请码无效，请重试。", status=HTTPStatus.UNAUTHORIZED)
            return

        token = create_session_token(invite_code)
        self.redirect("/", extra_headers={"Set-Cookie": self.build_session_cookie(token)})

    def handle_export_request(self, request_path: str, send_body: bool = True) -> None:
        if not self.is_authenticated():
            self.send_error(HTTPStatus.UNAUTHORIZED, "Unauthorized")
            return

        token = request_path.removeprefix("/exports/").strip("/")
        if not token:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        bundle = get_export_bundle(token)
        if bundle is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Export Not Found")
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", bundle.content_type)
        self.send_header("Content-Disposition", build_content_disposition(bundle.filename))
        self.send_header("Content-Length", str(len(bundle.content)))
        self.end_headers()
        if send_body:
            self.wfile.write(bundle.content)

    def _get_field_value(self, fields: Dict[str, str], name: str, default: str = "") -> str:
        return str(fields.get(name, default))

    def is_authenticated(self) -> bool:
        if not auth_enabled():
            return True
        return is_valid_session_token(self.get_cookie_value(SESSION_COOKIE_NAME))

    def get_cookie_value(self, cookie_name: str) -> str:
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return ""
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get(cookie_name)
        return morsel.value if morsel else ""

    def is_secure_request(self) -> bool:
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def build_session_cookie(self, token: str) -> str:
        parts = [
            f"{SESSION_COOKIE_NAME}={token}",
            "Path=/",
            f"Max-Age={SESSION_MAX_AGE}",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if self.is_secure_request():
            parts.append("Secure")
        return "; ".join(parts)

    def build_clear_cookie(self) -> str:
        parts = [
            f"{SESSION_COOKIE_NAME}=",
            "Path=/",
            "Max-Age=0",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if self.is_secure_request():
            parts.append("Secure")
        return "; ".join(parts)

    def clear_session_and_redirect(self, location: str) -> None:
        self.redirect(location, extra_headers={"Set-Cookie": self.build_clear_cookie()})

    def redirect(self, location: str, extra_headers: Optional[Dict[str, str]] = None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()

    def serve_login_page(
        self,
        error_message: str = "",
        status: HTTPStatus = HTTPStatus.OK,
        send_body: bool = True,
    ) -> None:
        template = LOGIN_TEMPLATE_PATH.read_text(encoding="utf-8")
        error_block = ""
        if error_message:
            error_block = (
                '<div class="invite-error">'
                f"{html.escape(error_message)}"
                "</div>"
            )
        content = template.replace("__ERROR_BLOCK__", error_block).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if send_body:
            self.wfile.write(content)

    def serve_file(self, file_path: Path, content_type: str, send_body: bool = True) -> None:
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if send_body:
            self.wfile.write(content)

    def serve_static(self, file_path: Path, send_body: bool = True) -> None:
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        mime_type, _ = mimetypes.guess_type(file_path.name)
        self.serve_file(file_path, mime_type or "application/octet-stream", send_body=send_body)

    def send_json(self, status: int, payload: Dict, send_body: bool = True) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        sys.stdout.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))


def main() -> None:
    load_dotenv(ENV_PATH)
    validate_auth_configuration()
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("PORT") or os.getenv("APP_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Student code grader is running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
