# Claude Student Code Grader

一个基于 Claude AI 的学生代码自动评分 Web 应用。教师可以设定作业要求，学生提交代码后由 Claude 进行智能评审并给出结构化的评分与反馈。

## 功能特性

- **智能代码评审** — 调用 Anthropic Claude API，从任务完成度、正确性、可读性、风格等多个维度评分（满分 100）
- **双模式反馈** — 支持教师模式（专业决策导向）和学生模式（建设性学习导向）
- **自定义评分标准** — 可使用默认评分维度，也可由教师自定义 Rubric
- **邀请码访问控制** — 可选的邀请码认证机制，基于 HMAC-SHA256 签名的会话管理
- **代理切换支持** — 可通过环境变量切换到 Anthropic 兼容的第三方 Claude API 代理
- **零外部依赖** — 纯 Python 标准库实现后端，无需安装第三方包
- **一键部署** — 提供 Render.com 部署配置，开箱即用

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3 标准库（`http.server`、`urllib`、`hmac`） |
| 前端 | HTML5 + CSS3 + Vanilla JS（Markdown 渲染使用 marked.js CDN） |
| AI   | Anthropic Claude API |
| 部署 | Render.com（Free Tier） |

## 项目结构

```
├── app.py              # 主服务端程序（路由、API 调用、认证）
├── render.yaml         # Render.com 部署配置
├── .env.example        # 环境变量模板
├── static/
│   ├── app.js          # 前端表单交互与结果渲染
│   └── styles.css      # 页面样式
└── templates/
    ├── index.html      # 评分主界面
    └── login.html      # 邀请码登录页
```

## 快速开始

### 前置条件

- Python 3（无需安装额外依赖）
- Anthropic API Key

### 本地运行

```bash
# 1. 克隆项目
git clone <repo-url> && cd competition

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key 和模型名称：
#   ANTHROPIC_API_KEY=sk-ant-... 或代理 key
#   ANTHROPIC_MODEL=你的模型名
# 如果你用第三方 Anthropic 兼容代理，还可以额外设置：
#   CLAUDE_API_BASE_URL=https://你的代理域名
#   CLAUDE_API_PATH=/v1/messages
#   CLAUDE_API_AUTH_MODE=x-api-key
#   CLAUDE_API_VERSION=

# 3. 启动服务
python3 app.py
```

服务启动后访问 `http://localhost:8000` 即可使用。

### 部署到 Render

1. 将项目推送到 GitHub
2. 在 Render Dashboard 创建 Web Service 并关联仓库
3. 在 Environment 中配置 `ANTHROPIC_API_KEY` 和 `ANTHROPIC_MODEL`
4. 如果使用第三方 Anthropic 兼容代理，再额外配置代理环境变量
4. Render 会根据 `render.yaml` 自动部署

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `ANTHROPIC_API_KEY` | 是 | Anthropic API 密钥 |
| `ANTHROPIC_MODEL` | 是 | 使用的 Claude 模型（如 `claude-sonnet-4-6`） |
| `CLAUDE_API_BASE_URL` | 否 | Claude API 根地址，默认 `https://api.anthropic.com` |
| `CLAUDE_API_PATH` | 否 | 请求路径，默认 `/v1/messages` |
| `CLAUDE_API_AUTH_MODE` | 否 | 鉴权方式，默认 `x-api-key`，也可设为 `bearer` |
| `CLAUDE_API_AUTH_HEADER` | 否 | 自定义鉴权头名；设置后会覆盖 `CLAUDE_API_AUTH_MODE` |
| `CLAUDE_API_AUTH_PREFIX` | 否 | 自定义鉴权头前缀，例如 `Bearer ` |
| `CLAUDE_API_VERSION` | 否 | `anthropic-version` 请求头，默认 `2023-06-01`；代理不支持时可留空 |
| `INVITE_CODES` | 否 | 邀请码列表，逗号或换行分隔；留空则无需登录 |
| `INVITE_SESSION_SECRET` | 否 | 会话签名密钥（设置邀请码时必填） |
| `APP_HOST` | 否 | 监听地址，默认 `0.0.0.0` |
| `APP_PORT` | 否 | 监听端口，默认 `8000` |

## 使用第三方 Claude API 代理

如果你的第三方服务兼容 Anthropic 的 `/v1/messages` 协议，你只需要改环境变量，不需要改代码：

```env
ANTHROPIC_API_KEY=你的代理key
ANTHROPIC_MODEL=代理要求的模型名
CLAUDE_API_BASE_URL=https://你的代理域名
CLAUDE_API_PATH=/v1/messages
CLAUDE_API_AUTH_MODE=x-api-key
CLAUDE_API_VERSION=
```

说明：

- `CLAUDE_API_BASE_URL` 改成代理提供的域名
- `CLAUDE_API_PATH` 默认保持 `/v1/messages`
- 如果代理要求 `Authorization: Bearer ...`，把 `CLAUDE_API_AUTH_MODE` 改成 `bearer`
- 如果代理不接受 `anthropic-version` 请求头，就把 `CLAUDE_API_VERSION` 留空

如果代理要求更特殊的鉴权头，可以直接这样配：

```env
CLAUDE_API_AUTH_HEADER=Authorization
CLAUDE_API_AUTH_PREFIX=
```

或者：

```env
CLAUDE_API_AUTH_HEADER=Authorization
CLAUDE_API_AUTH_PREFIX=Bearer 
```

如果你的代理不是 Anthropic 协议，而是 OpenAI 风格的 `/v1/chat/completions`，当前项目还需要额外适配请求体和返回体，不能只靠改环境变量完成。

## 评分维度（默认）

| 维度 | 分值 |
|------|------|
| 任务完成度 | 30 |
| 正确性 | 30 |
| 完整性 | 10 |
| 可读性 | 10 |
| 代码风格 | 10 |
| 健壮性 | 5 |
| 注释 | 5 |
| **总分** | **100** |

## API 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 评分主页面 |
| POST | `/grade` | 提交代码进行评分（返回 JSON） |
| POST | `/login` | 邀请码登录 |
| GET | `/logout` | 注销并清除会话 |
| GET | `/healthz` | 健康检查 |

## 许可证

MIT
