# 生产部署

- 前端：以 `VITE_BASE_PATH=/aitc/ npm run build` 构建，发布到 `/var/www/aitc`。
- 后端：代码发布到 `/opt/ai-testcase-studio/releases/<timestamp>`，`current` 指向当前版本。
- 数据：SQLite 与 Chroma 持久化到 `/var/lib/ai-testcase-studio`。
- 配置：生产环境变量保存在 `/etc/ai-testcase-studio/aitc.env`，不得提交到 Git。
- 服务：Uvicorn 单 worker 仅监听 `127.0.0.1:8010`，由 Nginx 代理 `/aitc/api/`。
- HTTPS：使用 Let's Encrypt 的 `makeming.site` 证书，Certbot 定时任务负责自动续期；AITC 的 HTTP 请求会跳转到 HTTPS。

生产环境必须设置不少于 16 位的 `AUTH_PASSWORD`，且不能使用源码默认密码。
