# Claude Student Code Grader

一个基于 OpenAI 兼容代理协议的学生代码自动评分 Web 应用。教师可以设定作业要求，学生提交代码后仍然由 Claude 模型进行智能评审并给出结构化的评分与反馈。

## 功能特性

- **智能代码评审** — 调用 OpenAI 兼容的 `chat/completions` 接口，但仍然使用供应商提供的 Claude 模型进行评分（满分 100）
- **双模式反馈** — 支持教师模式（专业决策导向）和学生模式（建设性学习导向）
- **自定义评分标准** — 可使用默认评分维度，也可由教师自定义 Rubric
- **邀请码访问控制** — 可选的邀请码认证机制，基于 HMAC-SHA256 签名的会话管理
- **代理切换支持** — 可通过环境变量切换到 OpenAI 兼容的第三方代理，同时保留 Claude 模型名称
- **零外部依赖** — 纯 Python 标准库实现后端，无需安装第三方包
- **一键部署** — 提供 Render.com 部署配置，开箱即用

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3 标准库（`http.server`、`urllib`、`hmac`） |
| 前端 | HTML5 + CSS3 + Vanilla JS（Markdown 渲染使用 marked.js CDN） |
| AI   | OpenAI 兼容 Chat Completions API + Claude 模型 |
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
- OpenAI 兼容代理 Key

### 本地运行

```bash
# 1. 克隆项目
git clone <repo-url> && cd competition

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key 和模型名称：
#   OPENAI_API_KEY=你的代理 key
#   OPENAI_MODEL=供应商提供的 Claude 模型名
# 如果你用第三方 OpenAI 兼容代理，还可以额外设置：
#   OPENAI_BASE_URL=https://你的代理域名/v1
#   OPENAI_API_PATH=/chat/completions
#   OPENAI_API_AUTH_MODE=bearer

# 3. 启动服务
python3 app.py
```

服务启动后访问 `http://localhost:8000` 即可使用。

### 部署到 Render

1. 将项目推送到 GitHub
2. 在 Render Dashboard 创建 Web Service 并关联仓库
3. 在 Environment 中配置 `OPENAI_API_KEY` 和 `OPENAI_MODEL`
4. 如果使用第三方 OpenAI 兼容代理，再额外配置 `OPENAI_BASE_URL`
4. Render 会根据 `render.yaml` 自动部署

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | 是 | OpenAI 兼容代理密钥 |
| `OPENAI_MODEL` | 是 | 使用的模型名称；这里可以直接填写供应商提供的 Claude 模型名 |
| `OPENAI_BASE_URL` | 否 | OpenAI 兼容 API 根地址，默认 `https://api.openai.com` |
| `OPENAI_API_PATH` | 否 | 请求路径，默认建议 `/v1/chat/completions`；如果 base URL 已带 `/v1`，也可写 `/chat/completions` |
| `OPENAI_API_AUTH_MODE` | 否 | 鉴权方式，默认 `bearer`，也可设为 `x-api-key` |
| `OPENAI_API_AUTH_HEADER` | 否 | 自定义鉴权头名；设置后会覆盖 `OPENAI_API_AUTH_MODE` |
| `OPENAI_API_AUTH_PREFIX` | 否 | 自定义鉴权头前缀，例如 `Bearer` |
| `INVITE_CODES` | 否 | 邀请码列表，逗号或换行分隔；留空则无需登录 |
| `INVITE_SESSION_SECRET` | 否 | 会话签名密钥（设置邀请码时必填） |
| `APP_HOST` | 否 | 监听地址，默认 `0.0.0.0` |
| `APP_PORT` | 否 | 监听端口，默认 `8000` |

## 使用 OpenAI 兼容代理调用 Claude 模型

如果你的第三方服务兼容 OpenAI 的 `/v1/chat/completions` 协议，你只需要改环境变量，不需要改代码：

```env
OPENAI_API_KEY=你的代理key
OPENAI_MODEL=供应商要求的 Claude 模型名
OPENAI_BASE_URL=https://你的代理域名/v1
OPENAI_API_PATH=/chat/completions
OPENAI_API_AUTH_MODE=bearer
```

说明：

- `OPENAI_MODEL` 填的是模型名，不是协议名；所以这里仍然可以写 Claude 模型
- `OPENAI_BASE_URL` 改成代理提供的 OpenAI 兼容地址
- 如果 `OPENAI_BASE_URL` 已经包含 `/v1`，程序会自动避免拼接成重复的 `/v1/v1/chat/completions`
- 默认鉴权是 `Authorization: Bearer <key>`

如果代理要求更特殊的鉴权头，可以直接这样配：

```env
OPENAI_API_AUTH_HEADER=Authorization
OPENAI_API_AUTH_PREFIX=Bearer
```

或者：

```env
OPENAI_API_AUTH_HEADER=X-API-Key
OPENAI_API_AUTH_PREFIX=
```

当 `OPENAI_API_AUTH_HEADER=Authorization` 时，程序会自动在前缀和 key 之间补一个空格，所以你直接填 `Bearer` 就可以，不需要手动输入尾随空格。

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
