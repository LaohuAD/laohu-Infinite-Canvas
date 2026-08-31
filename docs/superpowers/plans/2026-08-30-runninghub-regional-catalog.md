# RunningHub Regional Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 使 RunningHub 模型拉取严格依据官方注册表，同时正确区分国内站与国际站的公开可用性。

**Architecture:** 将“Schema 事实”和“地区公开状态”分层：官方 public registry 提供 endpoint/参数/输出，官方两站目录提供可验证的公开状态。标准模型与 LLM 分开拉取，远程失败时回退到已校验官方快照。

**Tech Stack:** FastAPI/Python, httpx, 静态 JavaScript, unittest, JSON 能力快照。

---

### Task 1: 官方注册表解析与快照回退

**Files:**
- Modify: `main.py`
- Create: `data/model_capabilities/snapshots/runninghub-official-public.json`
- Test: `tests/test_api_settings_connection.py`

- [x] 先写失败测试：官方 `models` 数组可解析，非官方结构不充当完整目录，远程失败读取本地官方快照。
- [x] 运行定向测试并确认失败原因。
- [x] 实现严格解析、注册表版本/来源元数据和本地回退。
- [x] 再次运行定向测试。

### Task 2: 地区公开状态与 LLM 网关

**Files:**
- Modify: `main.py`
- Test: `tests/test_api_settings_connection.py`

- [x] 先写失败测试：两站目录状态独立，未匹配项为 `unverified`，国内/国际 LLM URL 分别使用 `.cn`/`.ai`。
- [x] 运行测试确认失败。
- [x] 实现 Nuxt 公开页面数据的受限解析、精确标识匹配和分区 LLM 拉取。
- [x] 实现“标准目录成功不受 LLM 失败影响”并通过测试。

### Task 3: 移除非官方模型列表端点与误导文案

**Files:**
- Modify: `main.py`
- Modify: `static/js/api-settings.js`
- Modify: `static/js/i18n.js`
- Test: `tests/test_api_settings_connection.py`
- Test: `tests/test_smart_node_contract.py`

- [x] 先写失败测试：代码不再构造 `/openapi/v2/models`，连接检查不声称 Key 已验证。
- [x] 运行测试确认失败。
- [x] 调整 RunningHub 连接检查返回和中英文提示。
- [x] 运行定向测试并检查 JavaScript 语法。

### Task 4: API 设置的地区状态展示

**Files:**
- Modify: `static/js/api-settings.js`
- Modify: `static/css/api-settings.css`
- Modify: `static/js/i18n.js`
- Test: `tests/test_smart_node_contract.py`

- [x] 先写失败测试：模型选择器消费 `model_availability`，并区分 confirmed/unverified。
- [x] 运行测试确认失败。
- [x] 在选择器添加“目录已列出 / 目录未列出”状态徽标、当前站点统计和选择提示，同步中英文。
- [x] 将国内/国际区域与官方域名、独立 Key 强绑定，并阻止旧通用 Key 被国内站新设置覆盖或被国际站误读。
- [x] 运行定向测试和 JavaScript 语法检查。

### Task 5: 端到端验证

**Files:**
- Modify: `README.md` 仅在现有 RunningHub 说明处补充地区语义

- [x] 运行 RunningHub/API 设置/能力档案定向测试。
- [x] 运行全量 unittest、`node --check`、`git diff --check`。
- [x] 启动本地服务，分别切换国内站和国际站拉取，核对数量、状态徽标和用户已启用清单不变。
- [x] 检查 macOS 真实路径及 Windows 无 POSIX 专用假设。
