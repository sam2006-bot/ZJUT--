from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
import hashlib
import hmac
import html
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import urllib.parse
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"
SKILL_PATH = ROOT / ".claude" / "skills" / "student-code-grader" / "SKILL.md"
LOGIN_TEMPLATE_PATH = TEMPLATES_DIR / "login.html"
ENV_PATH = ROOT / ".env"
MAX_UPLOAD_BYTES = 1024 * 1024
MAX_FORM_BYTES = MAX_UPLOAD_BYTES + 256 * 1024
SESSION_COOKIE_NAME = "invite_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30


@dataclass
class UploadedFile:
    filename: str
    content: bytes


@dataclass
class MultipartForm:
    fields: Dict[str, str]
    files: Dict[str, UploadedFile]


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


def build_user_prompt(fields: Dict[str, str], file_name: str, code_text: str) -> str:
    return f"""
[Mode]
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
{code_text}

请严格依据上述信息进行批改，并使用中文输出。
输出时请使用以下结构：
1. 总评
2. 分项评分
3. 主要优点
4. 主要问题
5. 改进建议
6. 最终分数（0-100）
7. 置信度
""".strip()


def extract_text_from_claude_response(payload: Dict) -> str:
    blocks = payload.get("content", [])
    texts = []
    for block in blocks:
        if block.get("type") == "text":
            texts.append(block.get("text", ""))
    return "\n".join(part for part in texts if part).strip()


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
        raise ValueError("上传内容过大，请控制代码文件在 1MB 以内。")

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


def call_claude(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    model = os.getenv("ANTHROPIC_MODEL", "").strip()
    api_base_url = os.getenv("CLAUDE_API_BASE_URL", "https://api.anthropic.com").strip()
    api_path = os.getenv("CLAUDE_API_PATH", "/v1/messages").strip() or "/v1/messages"
    auth_mode = os.getenv("CLAUDE_API_AUTH_MODE", "x-api-key").strip().lower() or "x-api-key"
    auth_header = os.getenv("CLAUDE_API_AUTH_HEADER", "").strip()
    auth_prefix = os.getenv("CLAUDE_API_AUTH_PREFIX", "").strip()
    api_version = os.getenv("CLAUDE_API_VERSION", "2023-06-01").strip()

    if not api_key:
        raise ValueError(
            "未配置 ANTHROPIC_API_KEY。请在项目根目录新建 .env 文件，填入你的 Claude API key 或代理 key。"
        )

    if not model:
        raise ValueError(
            "未配置 ANTHROPIC_MODEL。请在 .env 中填入你要使用的 Claude 模型名称。"
        )

    if not api_base_url:
        raise ValueError("未配置有效的 CLAUDE_API_BASE_URL。")

    endpoint = f"{api_base_url.rstrip('/')}/{api_path.lstrip('/')}"

    request_body = {
        "model": model,
        "max_tokens": 1800,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    request_data = json.dumps(request_body).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    if auth_header:
        auth_value = f"{auth_prefix}{api_key}" if auth_prefix else api_key
        headers[auth_header] = auth_value
    elif auth_mode == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["x-api-key"] = api_key

    if api_version:
        headers["anthropic-version"] = api_version

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
        raise RuntimeError(f"Claude API/代理请求失败（HTTP {error.code}）：{details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Claude API/代理网络请求失败：{error.reason}") from error

    text = extract_text_from_claude_response(payload)
    if not text:
        raise RuntimeError("Claude API 返回成功，但响应内容为空。")
    return text


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.route_request(send_body=True)

    def do_HEAD(self) -> None:
        self.route_request(send_body=False)

    def route_request(self, send_body: bool) -> None:
        if self.path == "/healthz":
            self.send_json(HTTPStatus.OK, {"ok": True, "status": "healthy"}, send_body=send_body)
            return

        if self.path == "/logout":
            self.clear_session_and_redirect("/")
            return

        if self.path == "/":
            if not self.is_authenticated():
                self.serve_login_page(send_body=send_body)
                return
            self.serve_file(
                TEMPLATES_DIR / "index.html",
                "text/html; charset=utf-8",
                send_body=send_body,
            )
            return

        if self.path.startswith("/static/"):
            relative_path = self.path.removeprefix("/static/")
            file_path = STATIC_DIR / relative_path
            self.serve_static(file_path, send_body=send_body)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        if self.path == "/login":
            self.handle_login_request()
            return

        if self.path != "/grade":
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        if not self.is_authenticated():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "请先输入邀请码。"})
            return

        try:
            result = self.handle_grade_request()
            self.send_json(HTTPStatus.OK, {"ok": True, "result": result})
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
        except RuntimeError as error:
            self.send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
        except Exception as error:  # pragma: no cover
            self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": f"服务器内部错误：{error}"},
            )

    def handle_grade_request(self) -> str:
        form = parse_multipart_form(self.headers, self.rfile)

        upload = form.files.get("student_code")
        if upload is None:
            raise ValueError("请先上传学生代码文件。")

        if not upload.filename:
            raise ValueError("上传文件缺少文件名。")

        file_bytes = upload.content
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise ValueError("上传文件过大，请控制在 1MB 以内。")

        try:
            code_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            code_text = file_bytes.decode("utf-8", errors="replace")

        if not code_text.strip():
            raise ValueError("上传的代码文件内容为空。")

        fields = {
            "mode": self._get_field_value(form.fields, "mode", "Teacher"),
            "assignment_title": self._get_field_value(form.fields, "assignment_title"),
            "assignment_requirements": self._get_field_value(form.fields, "assignment_requirements"),
            "task_goal": self._get_field_value(form.fields, "task_goal"),
            "programming_language": self._get_field_value(form.fields, "programming_language"),
            "rubric": self._get_field_value(form.fields, "rubric"),
        }
        system_prompt = read_skill_prompt()
        user_prompt = build_user_prompt(fields, upload.filename, code_text)
        return call_claude(system_prompt, user_prompt)

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

    def send_json(self, status: int, payload: Dict[str, str], send_body: bool = True) -> None:
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
