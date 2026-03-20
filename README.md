# Claude Student Code Grader

一个最小本地 Web 应用：

- 左侧上传学生代码并填写作业背景
- 后端读取你写的 `.claude/skills/student-code-grader/SKILL.md`
- 调用 Claude 进行批改
- 右侧展示批改结果

## 你需要填写的地方

项目里已经留了空位，请自己填写：

1. 复制 `.env.example` 为 `.env`
2. 在 `.env` 中填入：

```env
ANTHROPIC_API_KEY=你的_claude_api_key
ANTHROPIC_MODEL=你要使用的_claude_模型名
APP_HOST=0.0.0.0
INVITE_CODES=你的邀请码1,你的邀请码2
INVITE_SESSION_SECRET=一段足够长的随机字符串
```

## 启动方式

```bash
python3 app.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

如果你修改了 `APP_PORT`，则按你设置的端口访问。

## Render 部署

仓库已经包含 `render.yaml`，可以直接按 Blueprint 方式部署：

1. 把项目推到 GitHub
2. 登录 Render
3. 选择 `New` -> `Blueprint`
4. 选择这个仓库
5. 按提示填写 `ANTHROPIC_API_KEY` 和 `ANTHROPIC_MODEL`
6. 点击创建并等待首次部署完成

部署成功后，Render 会给你一个公网地址。

如果你想限制只有收到邀请码的人才能访问，还需要在 Render 环境变量中设置：

```env
INVITE_CODES=your-code-1,your-code-2
INVITE_SESSION_SECRET=your-long-random-secret
```

## 说明

- 后端没有依赖第三方库，直接使用 Python 标准库。
- 默认只接受 1MB 以内的代码文件。
- 如果没有填写作业要求，程序仍然会请求 Claude，但评分会更依赖模型推断。
- 已兼容云端环境，会优先读取平台提供的 `PORT`。
- 当配置了 `INVITE_CODES` 后，未输入正确邀请码的用户将无法访问首页和批改接口。
