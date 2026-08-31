# RunningHub 拒绝响应修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 RunningHub 明确拒绝的标准模型请求立即以正确错误结束，不再误报“生成成功但没有返回媒体”。

**Architecture:** 在 `main.py` 增加统一的 RunningHub 标准响应拒绝解析器，提交和轮询链路都先通过该门禁，再判断 taskId 或输出。`40310` 映射为当前站点合规不可用的用户文案，同时保留错误码与截断后的上游原文。

**Tech Stack:** Python、FastAPI `HTTPException`、httpx、现有 RunningHub 官方注册表适配器、`unittest`/`AsyncMock`。

---

## 文件职责

- `main.py`：拒绝解析、40310 文案、提交和轮询门禁。
- `tests/test_model_capabilities.py`：音频复现场景、正常任务和跨媒体拒绝回归。
- `static/js/smart-canvas.js`：读取后端结构化 `detail.message` / `detail.message_en`，按当前界面语言显示。
- `tests/test_smart_node_contract.py`：锁定结构化错误的中英文透传契约。

### Task 1: 用用户响应建立失败测试

**Files:**
- Modify: `tests/test_model_capabilities.py`
- Test: `tests/test_model_capabilities.py`

- [ ] **Step 1: 写音频 `40310` 回归测试**

在现有 RunningHub 音频测试旁增加：

```python
async def test_runninghub_audio_reports_compliance_rejection_instead_of_fake_success(self):
    payload = main.CanvasAudioRequest(prompt="写一首歌", provider_id="runninghub", model="suno-custom-v5")
    provider = {"id":"runninghub", "base_url":"https://www.runninghub.cn", "rh_region":"cn"}

    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {
                "taskId":"", "status":"", "errorCode":"40310",
                "errorMessage":"Due to compliance requirements, this model is no longer available on this site."
            }

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def post(self, *_args, **_kwargs): return Response()

    model_def = {"endpoint":"suno/music", "params":[{"fieldKey":"text", "type":"STRING", "required":True}]}
    with patch.object(main, "runninghub_model_definition", new=AsyncMock(return_value=model_def)), \
         patch.object(main, "runninghub_json_headers", return_value={"Authorization":"Bearer test"}), \
         patch("main.httpx.AsyncClient", return_value=Client()):
        with self.assertRaises(main.HTTPException) as raised:
            await main.generate_runninghub_audio(payload, provider, {})

    self.assertEqual(raised.exception.status_code, 400)
    detail = raised.exception.detail
    self.assertEqual(detail["errorCode"], "40310")
    self.assertIn("当前站点", detail["message"])
    self.assertIn("国际站 Key", detail["message"])
    self.assertNotIn("生成成功", detail["message"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m unittest tests.test_model_capabilities.ModelCapabilityTests.test_runninghub_audio_reports_compliance_rejection_instead_of_fake_success`

Expected: FAIL，当前实现返回“音频生成成功但没有返回音频”。测试固定放在现有 `ModelCapabilityTests` 类中。

### Task 2: 实现统一拒绝解析器

**Files:**
- Modify: `main.py` near `runninghub_fail_reason`
- Test: `tests/test_model_capabilities.py`

- [ ] **Step 1: 增加纯解析函数**

实现：

```python
RUNNINGHUB_COMPLIANCE_ERROR_CODE = "40310"

def runninghub_rejection_detail(raw, media_label="任务"):
    if not isinstance(raw, dict):
        return None
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    code = str(raw.get("errorCode") or data.get("errorCode") or "").strip()
    message = str(raw.get("errorMessage") or data.get("errorMessage") or runninghub_fail_reason(raw) or "").strip()
    if not code and not message:
        return None
    if code in {"", "0"} and not re.search(r"\b(error|failed|unavailable|not available|rejected)\b", message, re.I):
        return None
    if code == RUNNINGHUB_COMPLIANCE_ERROR_CODE:
        user_message = "该模型因合规要求已不在当前站点提供。国内站请更换可用模型；如需尝试国际站，请切换到国际站并使用对应的国际站 Key。"
        user_message_en = "This model is no longer available on the current site due to compliance requirements. Choose another model on the China site, or switch to the international site and use the matching international-site key."
    else:
        user_message = f"RunningHub {media_label}请求被拒绝：{message or f'错误码 {code}'}"
        user_message_en = f"RunningHub request was rejected: {message or f'error code {code}'}"
    return {
        "message": user_message,
        "message_en": user_message_en,
        "errorCode": code,
        "upstreamMessage": message[:500],
    }
```

- [ ] **Step 2: 增加统一抛错函数**

```python
def raise_for_runninghub_rejection(raw, media_label="任务"):
    detail = runninghub_rejection_detail(raw, media_label)
    if detail:
        status_code = 400 if detail.get("errorCode") == RUNNINGHUB_COMPLIANCE_ERROR_CODE else 502
        raise HTTPException(status_code=status_code, detail=detail)
```

- [ ] **Step 3: 运行解析器和音频测试**

Run: `.venv/bin/python -m unittest tests.test_model_capabilities -k runninghub_audio`

Expected: 新 `40310` 测试和已有音频正常路径全部 PASS。

### Task 3: 接入音频、视频、图片提交和轮询

**Files:**
- Modify: `main.py` in `generate_runninghub_audio`
- Modify: `main.py` in `generate_runninghub_video`
- Modify: `main.py` in `generate_runninghub_provider_image`
- Modify: `main.py` in `wait_for_runninghub_openapi_task`
- Test: `tests/test_model_capabilities.py`

- [ ] **Step 1: 提交响应先过门禁**

在每个 `raw = response.json()` 后、提取 taskId 或媒体之前调用：

```python
raise_for_runninghub_rejection(raw, "音频")
raise_for_runninghub_rejection(raw, "视频")
raise_for_runninghub_rejection(raw, "图片")
```

音频和音乐共用音频函数时，根据调用模型能力或传入标签显示“音频/音乐”不影响错误码判定；测试至少锁定用户复现的音频文案。

- [ ] **Step 2: 轮询响应先过门禁**

在 `wait_for_runninghub_openapi_task` 每次读取 `raw` 后调用：

```python
raise_for_runninghub_rejection(raw, output_kind or "任务")
```

随后才读取 status；避免空状态的拒绝响应被轮询到超时。

- [ ] **Step 3: 增加跨媒体测试**

增加纯解析断言：

```python
def test_runninghub_standard_media_share_rejection_parser(self):
    raw = {"errorCode":"49999", "errorMessage":"model rejected"}
    detail = main.runninghub_rejection_detail(raw, "视频")
    self.assertEqual(detail["errorCode"], "49999")
    self.assertIn("视频请求被拒绝", detail["message"])
```

再保留已有视频、图片正常响应测试，证明有效 taskId 和直接输出没有被拦截。

- [ ] **Step 4: 运行定向测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_model_capabilities -k runninghub
.venv/bin/python -m unittest tests.test_api_settings_connection -k runninghub
```

Expected: PASS。

### Task 4: 验证前端错误透传和完整回归

**Files:**
- Modify: `static/js/smart-canvas.js`
- Test: `tests/test_smart_node_contract.py`

- [ ] **Step 1: 写结构化详情透传测试**

当前 `smartResponseErrorMessage` 只处理字符串和数组，先增加失败测试锁定对象型详情：

```python
def test_smart_canvas_reads_structured_runninghub_error_message(self):
    source = (ROOT / "static/js/smart-canvas.js").read_text(encoding="utf-8")
    block = source[source.index("async function smartResponseErrorMessage"):source.index("function smartDropDataTypes")]
    self.assertIn("detail.message", block)
    self.assertIn("detail.message_en", block)
    self.assertIn("capabilityUiText", block)
```

- [ ] **Step 2: 实现对象型详情的双语读取**

在字符串和数组分支之后增加：

```javascript
if(detail && typeof detail === 'object'){
    return capabilityUiText(
        String(detail.message || detail.message_en || fallback),
        String(detail.message_en || detail.message || fallback)
    );
}
```

保留后续响应文本和 `fallback` 回退逻辑。

- [ ] **Step 3: 运行前端定向测试**

Run:

```bash
node --check static/js/smart-canvas.js
.venv/bin/python -m unittest tests.test_smart_node_contract -k structured_runninghub
```

Expected: PASS。

- [ ] **Step 4: 运行完整验证**

Run:

```bash
.venv/bin/python -m py_compile main.py
.venv/bin/python -m unittest discover -s tests
git diff --check
```

Expected: 全部退出码 0。

- [ ] **Step 5: 真实服务验证**

当前 3000 服务处于 Python 自动重载模式。修改 `main.py` 后确认子进程 PID 更新，随后请求 `/api/app-info` 返回 200。不得再次向 RunningHub 发送用户的真实 Suno 任务；用单元测试中的固定响应完成错误验证，避免产生费用。

- [ ] **Step 6: 工作区核对**

Run: `git status --short`

Expected: 不改写 `data/model_capabilities/snapshots/runninghub-cn.json` 等运行时快照；由于 `main.py` 已包含用户当前未提交修改，本任务不单独提交整个 `main.py`，等待用户明确要求发布时统一整理。
