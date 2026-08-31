# 全站统一弹窗迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用项目级异步弹窗替换所有当前产品页面中的浏览器原生 `alert`、`confirm` 和 `prompt`。

**Architecture:** 在所有页面已加载的 `static/js/theme.js` 中提供全局 `window.StudioDialog`，首次使用时创建遮罩、面板和样式。调用点显式迁移为 Promise API，不覆盖浏览器同步 API；危险确认、普通提示和文本输入使用同一组件但不同类型。

**Tech Stack:** 原生 JavaScript、CSS、现有 `StudioI18n`、Python `unittest`、Node.js 语法与行为探针、应用内浏览器。

---

## 文件职责

- `static/js/theme.js`：统一弹窗实现、队列、焦点、键盘和中英文默认文案。
- `tests/test_site_dialog.py`：弹窗公共契约、原生调用清零和代表性异步迁移检查。
- `static/js/api-settings.js`：API 设置提示、Key 清除、模型风险确认、平台删除。
- `static/js/comfyui-settings.js`：工作流命名、删除、上传和保存提示。
- `static/index.html`：备份选择、回滚和更新检测提示。
- `static/angle.html`、`static/enhance.html`、`static/klein.html`、`static/online.html`、`static/zimage.html`：独立生成页面提示和历史删除确认。
- `static/gpt-chat.html`、`static/js/history-bulk-manager.js`、`static/js/asset-manager.js`：聊天、批量历史和素材删除确认。
- `AGENTS.md`：沉淀禁止新增浏览器原生业务弹窗的项目级规则。

### Task 1: 建立公共弹窗与原生调用清零测试

**Files:**
- Create: `tests/test_site_dialog.py`
- Read: `static/js/theme.js`

- [ ] **Step 1: 写公共组件失败测试**

创建 `tests/test_site_dialog.py`，至少包含：

```python
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SiteDialogTests(unittest.TestCase):
    def test_theme_exposes_shared_async_dialog_api(self):
        source = (ROOT / "static/js/theme.js").read_text(encoding="utf-8")
        self.assertIn("window.StudioDialog", source)
        self.assertIn("alert(message", source)
        self.assertIn("confirm(message", source)
        self.assertIn("prompt(message", source)
        self.assertIn("studio-dialog-overlay", source)
        self.assertIn("aria-modal", source)
        self.assertIn("previousFocus", source)
        self.assertIn("event.key === 'Escape'", source)
        self.assertIn("event.key === 'Tab'", source)

    def test_current_product_has_no_browser_native_dialog_calls(self):
        files = [
            "static/js/api-settings.js", "static/js/comfyui-settings.js",
            "static/index.html", "static/angle.html", "static/enhance.html",
            "static/klein.html", "static/online.html", "static/zimage.html",
            "static/gpt-chat.html", "static/js/history-bulk-manager.js",
            "static/js/asset-manager.js",
        ]
        pattern = re.compile(r"(?<![\w.])(alert|confirm|prompt)\s*\(")
        for relative in files:
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIsNone(pattern.search(source), relative)
            self.assertNotIn("window.alert(", source, relative)
            self.assertNotIn("window.confirm(", source, relative)
            self.assertNotIn("window.prompt(", source, relative)
```

- [ ] **Step 2: 运行失败测试**

Run: `.venv/bin/python -m unittest tests.test_site_dialog`

Expected: FAIL，指出 `window.StudioDialog` 不存在且当前文件仍包含原生调用。

- [ ] **Step 3: 只提交测试基线**

```bash
git add tests/test_site_dialog.py
git commit -m "test: 锁定全站统一弹窗契约"
```

### Task 2: 实现共享 StudioDialog

**Files:**
- Modify: `static/js/theme.js`
- Test: `tests/test_site_dialog.py`

- [ ] **Step 1: 在主题 IIFE 内实现默认语言和样式注入**

增加 `studioDialogText`、`ensureStudioDialogStyle` 和 `ensureStudioDialogRoot`。默认按钮文案按当前语言返回：

```javascript
function studioDialogLanguage(){
    const value = String(window.StudioI18n?.lang?.() || document.documentElement.lang || 'zh').toLowerCase();
    return value.startsWith('en') ? 'en' : 'zh';
}
function studioDialogText(key){
    const copy = {
        confirm:{zh:'确定', en:'Confirm'}, cancel:{zh:'取消', en:'Cancel'},
        info:{zh:'提示', en:'Notice'}, warning:{zh:'请确认', en:'Please confirm'},
        danger:{zh:'危险操作', en:'Dangerous action'}, input:{zh:'请输入内容', en:'Enter a value'}
    };
    return copy[key]?.[studioDialogLanguage()] || copy[key]?.zh || '';
}
```

样式必须包含 `.studio-dialog-overlay`、`.studio-dialog-panel`、`.studio-dialog-title`、`.studio-dialog-message`、`.studio-dialog-input`、`.studio-dialog-actions`、`.studio-dialog-btn.primary`、`.studio-dialog-btn.danger`，并全部依赖现有 `--panel`、`--card`、`--text`、`--muted`、`--line`、`--strong`、`--strong-text`、`--danger` 变量及明确回退值。

- [ ] **Step 2: 实现单队列 Promise API**

公共入口保持以下签名：

```javascript
window.StudioDialog = {
    alert(message, options={}) {
        return enqueueStudioDialog({kind:'alert', message, ...options});
    },
    confirm(message, options={}) {
        return enqueueStudioDialog({kind:'confirm', message, ...options});
    },
    prompt(message, options={}) {
        return enqueueStudioDialog({kind:'prompt', message, ...options});
    }
};
```

`enqueueStudioDialog` 把每个请求加入数组，当前弹窗结束后再显示下一项。返回值固定为：alert `undefined`、confirm `true/false`、prompt 字符串或 `null`。

- [ ] **Step 3: 实现键盘和焦点行为**

- 打开前保存 `document.activeElement` 为 `previousFocus`。
- `Esc` 调用取消。
- `Enter` 在 prompt 输入框或确认弹窗中调用确认。
- `Tab / Shift+Tab` 在弹窗可聚焦元素首尾循环。
- 关闭后删除弹窗根节点并调用 `previousFocus?.focus?.()`。
- 遮罩点击只取消，不确认。

- [ ] **Step 4: 运行公共组件测试与语法检查**

Run:

```bash
node --check static/js/theme.js
.venv/bin/python -m unittest tests.test_site_dialog.SiteDialogTests.test_theme_exposes_shared_async_dialog_api
```

Expected: PASS。

- [ ] **Step 5: 提交公共组件**

```bash
git add static/js/theme.js
git commit -m "feat: 增加全站统一异步弹窗"
```

### Task 3: 迁移 API 设置和 ComfyUI 设置

**Files:**
- Modify: `static/js/api-settings.js`
- Modify: `static/js/comfyui-settings.js`
- Test: `tests/test_site_dialog.py`

- [ ] **Step 1: 增加代表性异步迁移测试**

在 `tests/test_site_dialog.py` 增加：

```python
def test_api_and_comfy_settings_use_shared_dialogs(self):
    api = (ROOT / "static/js/api-settings.js").read_text(encoding="utf-8")
    comfy = (ROOT / "static/js/comfyui-settings.js").read_text(encoding="utf-8")
    self.assertIn("await StudioDialog.confirm(trf('api.rhEnableUnverifiedConfirm'", api)
    self.assertIn("await StudioDialog.prompt(tr('comfy.namePrompt')", comfy)
    self.assertIn("type:'danger'", api)
    self.assertIn("type:'danger'", comfy)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m unittest tests.test_site_dialog.SiteDialogTests.test_api_and_comfy_settings_use_shared_dialogs`

Expected: FAIL，旧调用仍是浏览器原生 API。

- [ ] **Step 3: 迁移 `static/js/api-settings.js` 的 27 处调用**

替换规则：

```javascript
await StudioDialog.alert(message, {type:'warning'});
if(!await StudioDialog.confirm(message, {type:'danger'})) return;
```

模型“可能不可用”使用 `type:'warning'`；退出即梦、清除 Key、删除平台和清除火山密钥使用 `type:'danger'`；缺少地址、Key、目录和上传失败使用 `type:'warning'`。将包含这些调用且尚未异步的函数改为 `async`，内联 `.catch(error => alert(...))` 改成调用命名异步处理函数，避免在模板字符串中塞 Promise 逻辑。

- [ ] **Step 4: 迁移 `static/js/comfyui-settings.js` 的 12 处调用**

工作流导入命名使用：

```javascript
const inputName = await StudioDialog.prompt(tr('comfy.namePrompt'), {
    defaultValue:baseName,
    title:tr('comfy.namePrompt')
});
if(inputName === null || !inputName.trim()) return;
```

工作流删除用危险确认；上传、保存、JSON 校验和运行失败用 warning。文件 input 的 `onchange` 回调改为 `async` 后再等待提示。

- [ ] **Step 5: 运行定向测试与语法检查**

Run:

```bash
node --check static/js/api-settings.js
node --check static/js/comfyui-settings.js
.venv/bin/python -m unittest tests.test_site_dialog.SiteDialogTests.test_api_and_comfy_settings_use_shared_dialogs
```

Expected: PASS。

### Task 4: 迁移首页和独立生成页面

**Files:**
- Modify: `static/index.html`
- Modify: `static/angle.html`
- Modify: `static/enhance.html`
- Modify: `static/klein.html`
- Modify: `static/online.html`
- Modify: `static/zimage.html`
- Test: `tests/test_site_dialog.py`

- [ ] **Step 1: 写失败测试锁定备份 prompt 和云端等待确认**

```python
def test_home_and_legacy_generators_use_async_dialogs(self):
    home = (ROOT / "static/index.html").read_text(encoding="utf-8")
    angle = (ROOT / "static/angle.html").read_text(encoding="utf-8")
    self.assertIn("await StudioDialog.prompt(promptMsg", home)
    self.assertIn("await StudioDialog.confirm", home)
    self.assertIn("await StudioDialog.confirm", angle)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m unittest tests.test_site_dialog.SiteDialogTests.test_home_and_legacy_generators_use_async_dialogs`

Expected: FAIL。

- [ ] **Step 3: 迁移首页回滚和更新提示**

- 备份序号使用 `StudioDialog.prompt`，取消时返回。
- 回滚确认使用 `danger`。
- 回滚完成、已是最新版使用 `info`。
- 网络不可达、检测失败使用 `warning`。
- 保持 `rollbackProjectUpdate` 和更新检测函数为 async，并等待弹窗结果后再继续请求。

- [ ] **Step 4: 迁移五个独立生成页面**

- `angle.html`：300 秒等待确认用 warning，缺图和生成失败用 warning。
- `enhance.html`：生成失败用 warning，并保留 `debugStep`。
- `klein.html`：输入缺失和生成失败用 warning，历史删除用 danger。
- `online.html`：输入缺失、下载失败、生成失败用 warning，删除历史用 danger。
- `zimage.html`：缺提示词、缺 Token 和渲染失败用 warning。

所有原本已是 `async function` 的入口直接 `await`；非 async 回调改为 async，调用方无需同步读取返回值。

- [ ] **Step 5: 运行定向检查**

Run:

```bash
.venv/bin/python -m unittest tests.test_site_dialog.SiteDialogTests.test_home_and_legacy_generators_use_async_dialogs
for file in static/js/theme.js; do node --check "$file"; done
```

Expected: PASS。HTML 内联脚本由后续完整浏览器检查覆盖。

### Task 5: 迁移聊天、历史和素材管理

**Files:**
- Modify: `static/gpt-chat.html`
- Modify: `static/js/history-bulk-manager.js`
- Modify: `static/js/asset-manager.js`
- Test: `tests/test_site_dialog.py`

- [ ] **Step 1: 写失败测试**

```python
def test_chat_history_and_assets_use_shared_dialogs(self):
    chat = (ROOT / "static/gpt-chat.html").read_text(encoding="utf-8")
    history = (ROOT / "static/js/history-bulk-manager.js").read_text(encoding="utf-8")
    assets = (ROOT / "static/js/asset-manager.js").read_text(encoding="utf-8")
    self.assertIn("await StudioDialog.confirm", chat)
    self.assertIn("await StudioDialog.confirm", history)
    self.assertIn("await StudioDialog.confirm", assets)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m unittest tests.test_site_dialog.SiteDialogTests.test_chat_history_and_assets_use_shared_dialogs`

Expected: FAIL。

- [ ] **Step 3: 完成迁移**

- 聊天删除、历史批量删除、素材磁盘删除使用 `danger`。
- 聊天上传失败、历史部分失败使用 `warning`。
- 保留素材库现有 `siteTextInput`，因为它已经是项目自定义输入框，不重复替换。

- [ ] **Step 4: 运行原生调用清零测试**

Run: `.venv/bin/python -m unittest tests.test_site_dialog`

Expected: PASS，当前产品文件无原生调用。

### Task 6: 项目规则、视觉和完整回归

**Files:**
- Modify: `AGENTS.md`
- Test: `tests/test_site_dialog.py`

- [ ] **Step 1: 写入项目级规则**

在界面交互规则中增加：业务提示、确认和输入不得调用浏览器原生 `alert/confirm/prompt`；必须使用 `StudioDialog`，确认和输入调用必须显式 `await`；新增当前产品页面必须加载 `theme.js` 或等价共享组件。

- [ ] **Step 2: 执行静态和完整测试**

Run:

```bash
node --check static/js/theme.js
node --check static/js/api-settings.js
node --check static/js/comfyui-settings.js
node --check static/js/history-bulk-manager.js
node --check static/js/asset-manager.js
.venv/bin/python -m unittest discover -s tests
git diff --check
```

Expected: 全部退出码 0。

- [ ] **Step 3: 浏览器验证代表路径**

在应用内浏览器验证：

1. API 设置选择“可能不可用”模型后应用：显示 warning 弹窗，无浏览器地址标题。
2. 首页回滚：输入弹窗可用，取消不发请求，危险确认独立显示。
3. ComfyUI 导入工作流：输入默认名称，取消返回 `null`。
4. 深色和浅色各检查一次；1280×720 下不溢出。
5. `Esc` 取消、`Enter` 确认、关闭后焦点回到原按钮。

- [ ] **Step 4: 工作区核对**

Run: `git status --short`

Expected: 无临时 QA 文件；运行时快照和用户已有改动保持原状。由于当前工作区已有未提交修改，本任务不批量提交这些重叠文件，等待用户明确要求发布时再按发布规则整理提交。
