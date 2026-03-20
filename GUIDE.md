# Claude Student Code Grader

基于 Claude API 的学生代码自动批改系统。教师上传学生代码、填写作业要求，由 Claude 进行结构化评审并给出评分。

## 功能概览

- 支持 **Teacher / Student** 两种批改模式
  - Teacher 模式：专业评分报告，含置信度、评分依据、教师备注
  - Student 模式：鼓励性反馈，侧重学习建议与改进方向
- 自定义评分细则（可选），不填则使用内置默认评分规则
- 批改结果以 Markdown 格式渲染展示，包含分项评分、优缺点分析、改进建议
- 纯 Python 标准库后端，无第三方依赖

## 项目结构

```
competition/
├── app.py                  # 后端服务（HTTP 路由、Claude API 调用、表单解析）
├── .env.example            # 环境变量模板
├── templates/
│   └── index.html          # 前端页面
├── static/
│   ├── app.js              # 前端交互逻辑
│   └── styles.css          # 样式
└── .claude/skills/
    └── student-code-grader/
        └── SKILL.md        # Claude 批改指令（system prompt）
```

## 快速开始

### 1. 配置环境变量

将 `.env.example` 复制为 `.env`，填入你的 API 信息：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
ANTHROPIC_API_KEY=sk-ant-xxxxx    # 你的 Claude API Key
ANTHROPIC_MODEL=你的模型名称         # 使用的模型名称
INVITE_CODES=code-1,code-2        # 可选，逗号分隔的邀请码
INVITE_SESSION_SECRET=随机长字符串  # 配置邀请码后必须同时设置
APP_HOST=0.0.0.0                   # 可选，默认 0.0.0.0
APP_PORT=8000                      # 可选，默认 8000
```

### 2. 启动服务

```bash
python3 app.py
```

### 3. 打开浏览器

访问 [http://127.0.0.1:8000](http://127.0.0.1:8000)（如修改了 `APP_PORT`，按实际端口访问）。

## 使用方式

1. 在左侧面板选择批改模式（Teacher / Student）
2. 填写作业标题、作业要求、任务目标、编程语言
3. 如需自定义评分规则，展开「高级选项」填写
4. 上传学生代码文件（限 1MB 以内）
5. 点击「开始批改」，等待 Claude 返回结果
6. 右侧面板展示渲染后的批改报告

## 默认评分规则

未提供自定义评分细则时，使用以下默认规则（满分 100）：

| 评分维度           | 分值 |
| ------------------ | ---- |
| 任务完成度         | 30   |
| 正确性             | 30   |
| 完整性             | 10   |
| 可读性与结构       | 10   |
| 编码风格与命名     | 10   |
| 鲁棒性与边界处理   | 5    |
| 注释与说明         | 5    |

## 技术说明

- 后端使用 Python 标准库 `http.server.ThreadingHTTPServer`，支持并发请求
- 表单解析基于 `email.parser.BytesParser` 处理 multipart/form-data
- 前端使用 [marked.js](https://github.com/markedjs/marked) 渲染 Markdown 输出
- Claude API 调用使用 `urllib.request`，无需安装 SDK
- 批改指令定义在 `SKILL.md` 中，可根据需要自行修改评分逻辑

## 注意事项

- 代码文件大小上限为 1MB
- 评分基于静态代码审查，不会实际运行学生代码
- 填写作业要求能显著提高评分的准确性和一致性
- 需要可用的网络连接以访问 Claude API
- 如果配置了 `INVITE_CODES`，用户必须先输入正确的邀请码才能进入系统

## 部署到 Render 免费版

### 适配内容

当前项目已经做了以下调整，适合部署到 Render：

- 服务监听 `0.0.0.0`
- 云端优先读取 Render 注入的 `PORT`
- 提供 `/healthz` 健康检查接口
- 提供 `render.yaml` 作为部署描述文件
- `.env` 可继续只用于本地，不需要提交到 GitHub

### 1. 推送到 GitHub

在项目根目录执行：

```bash
git init
git add .
git commit -m "Prepare app for Render deployment"
git branch -M main
git remote add origin 你的仓库地址
git push -u origin main
```

如果你已经有 Git 仓库，只需要正常 `git add`、`commit`、`push` 即可。

### 2. 在 Render 创建服务

推荐用 Blueprint 方式，因为仓库里已经有 `render.yaml`：

1. 登录 Render Dashboard
2. 点击 `New`
3. 选择 `Blueprint`
4. 连接你的 GitHub 账号并选择这个仓库
5. Render 会读取 `render.yaml`
6. 在创建页面填写环境变量：
   - `ANTHROPIC_API_KEY`
   - `ANTHROPIC_MODEL`
   - `INVITE_CODES`（如果要开启邀请码访问）
   - `INVITE_SESSION_SECRET`（如果填写了 `INVITE_CODES`，这一项必填）
7. 确认实例类型是 `free`
8. 点击创建

### 3. 等待首次部署

首次部署完成后，Render 会分配一个类似下面的公网地址：

```text
https://your-service-name.onrender.com
```

你可以直接打开首页，也可以访问：

```text
https://your-service-name.onrender.com/healthz
```

如果返回：

```json
{"ok": true, "status": "healthy"}
```

说明服务本身已经启动成功。

### 4. 后续更新

以后只要你继续往 GitHub 连接的分支 push，Render 就会自动重新部署。

### 5. Render 免费版的实际表现

- 长时间无请求后会休眠
- 再次访问时会有冷启动，通常会慢一些
- 适合演示、小范围使用、轻量工具
- 不适合高并发或严格实时响应场景

## 邀请码访问建议

- `INVITE_CODES` 支持多个邀请码，使用英文逗号分隔
- `INVITE_SESSION_SECRET` 建议使用至少 32 位的随机字符串
- 修改邀请码或密钥后，旧登录状态会失效，用户需要重新输入邀请码
