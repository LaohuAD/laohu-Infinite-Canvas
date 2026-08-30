# 全站统一弹窗与 RunningHub 拒绝错误处理设计

## 目标

1. 清除当前产品所有可访问页面中的浏览器原生 `alert`、`confirm` 和 `prompt`，统一为符合项目视觉调性的弹窗。
2. 修复 RunningHub 返回明确拒绝信息时仍被包装成“生成成功但没有返回音频”的错误状态。
3. 保持 RunningHub 国内站、国际站的目录、请求地址和 Key 严格隔离，不因为某一站拒绝模型而删除另一站的模型能力。

## 范围

### 纳入

- 首页与更新、备份、回滚流程。
- API 设置和模型选择器。
- ComfyUI 设置。
- 智能画布、素材库、画布列表、聊天页。
- 当前仍可访问的独立生成页面：`angle.html`、`enhance.html`、`klein.html`、`online.html`、`zimage.html`。
- 当前页面引用的共享脚本，例如批量历史管理。
- RunningHub 图片、视频、音频、音乐等标准模型提交响应的统一拒绝检查；本次用户复现的音频链路必须有直接回归测试。

### 排除

- 文件名包含 `.broken`、`.stable`、`.mojibake` 的历史快照和备份。
- `static/js/i18n(1)/` 等历史重复目录。
- Photoshop 连接器及其他独立插件内部页面。
- 第三方 vendor 文件。

## 统一弹窗组件

### 接入位置

在所有当前页面都已加载的 `static/js/theme.js` 中提供 `window.StudioDialog`。组件首次调用时再创建 DOM 和样式，不要求每个页面维护一份弹窗 HTML，也不改变页面原有业务结构。

公开接口：

```javascript
await StudioDialog.alert(message, options)
const accepted = await StudioDialog.confirm(message, options)
const value = await StudioDialog.prompt(message, options)
```

- `alert` 返回 `undefined`。
- `confirm` 返回布尔值。
- `prompt` 返回用户文本；取消时返回 `null`，从而与空字符串输入明确区分。
- 多个弹窗同时触发时进入单一队列，不叠加、不互相覆盖。

### 类型与视觉

- `info`：普通说明或成功结果。
- `warning`：可能失败、不可用或需要用户判断的操作。
- `danger`：删除、清除、退出登录、回滚等不可逆或高风险操作。
- `prompt`：带单行输入框的输入弹窗。

弹窗沿用项目现有 CSS 变量和视觉语言：半透明遮罩、轻微模糊、14px 左右圆角、紧凑字号、清晰标题层级、深浅色自动适配。不得显示浏览器生成的“IP 地址显示”标题。危险确认按钮使用克制的危险色，普通确认使用项目强色按钮。

### 文案与交互

- 标题、确认、取消、输入占位必须支持中英文；优先读取当前 `StudioI18n` 语言，无法读取时按页面 `lang` 回退。
- `Esc`：取消或关闭。
- `Enter`：确认；输入框中提交当前内容。
- `Tab / Shift+Tab`：焦点限制在弹窗内部。
- 弹窗关闭后恢复到打开前的焦点元素。
- 点击遮罩视为取消，但危险操作不得因遮罩点击而确认。
- 弹窗打开时设置 `role="dialog"`、`aria-modal="true"` 和可访问标题关联。

## 原生调用迁移

浏览器原生确认和输入是同步 API，而项目弹窗是 Promise，因此不得通过覆盖 `window.confirm` 或 `window.prompt` 伪装同步行为。所有真实调用点必须显式迁移：

- 原 `alert(message)` 改为 `await StudioDialog.alert(message, {type, title})`；不依赖等待顺序的地方可以返回该 Promise。
- 原 `if (!confirm(message)) return` 改为 `if (!await StudioDialog.confirm(message, options)) return`，并把所属处理函数调整为 `async`。
- 原 `prompt(message, defaultValue)` 改为 `await StudioDialog.prompt(message, {defaultValue})`，取消值按 `null` 处理。
- 删除、清除 Key、退出登录、回滚、删除平台等统一使用 `danger`。
- 模型可能不可用、云端等待超时等统一使用 `warning`。
- 缺少输入、上传失败、网络失败等使用 `info` 或 `warning`，不把普通错误伪装成危险操作。

迁移完成后，自动化扫描当前产品文件，确保不存在浏览器原生调用；同名业务函数（例如页面内部名为 `confirm` 的普通函数）不属于浏览器原生调用，测试必须按调用对象和上下文区分。

## RunningHub 错误处理

### 已确认的错误含义

用户复现响应：

```json
{
  "taskId": "",
  "status": "",
  "errorCode": "40310",
  "errorMessage": "Due to compliance requirements, this model is no longer available ..."
}
```

这是提交阶段的明确拒绝，不是生成成功，也不是“没有返回音频”。`40310` 表明当前调用站点因合规原因不再提供该模型；本次复现发生在国内站 Suno。

### 统一响应门禁

新增纯函数解析 RunningHub 标准模型响应：

1. 先提取 `errorCode`、`errorMessage`、通用错误字段和任务状态。
2. 只在存在有效输出或有效 `taskId` 时进入成功/轮询流程。
3. 存在非空错误码或明确错误信息且没有有效任务/输出时，立即抛出结构化 `HTTPException`。
4. 图片、视频、音频、音乐标准模型共用该门禁，避免同一类拒绝在其他媒体链路再次被误报。
5. 最终“成功但没有返回媒体”只用于上游确实报告成功、却缺少输出的异常情况。

### 面向用户的 40310 文案

中文：

> 该模型因合规要求已不在当前站点提供。国内站请更换可用模型；如需尝试国际站，请切换到国际站并使用对应的国际站 Key。

英文：

> This model is no longer available in the current region due to compliance requirements. Choose another model, or switch to the Global site and use the matching Global API key.

错误详情仍保留原始 `errorCode` 和经过长度限制的上游信息，供日志和故障排查使用。前端失败素材节点显示用户可理解的文案，不显示“生成成功”。

### 区域边界

- 不自动切换国内站和国际站。
- 不把国内 Key 发送到国际站，也不把国际 Key 发送到国内站。
- 不因为国内站 `40310` 从官方全球注册表删除 Suno。
- 模型选择器的“可能不可用”仍允许用户主动选择；真实运行收到 `40310` 时，以明确的“当前站点不可用”错误结束任务。

## 测试与验收

### 弹窗

1. 可执行 JavaScript 测试验证 `alert / confirm / prompt` 的返回语义。
2. 验证弹窗队列不会重叠。
3. 验证 `Esc`、`Enter`、焦点恢复和危险按钮样式。
4. 静态扫描全部当前产品页面，确认没有浏览器原生 `window.alert`、`window.confirm`、`window.prompt` 或等价裸调用。
5. 浏览器验证 API 设置中的“可能不可用”确认、首页回滚、ComfyUI 命名输入三条代表路径，并检查深浅色。

### RunningHub

1. 使用用户提供的 `40310` 响应测试音频提交，必须返回明确的当前站点合规拒绝信息。
2. 同一响应不得包含“生成成功但没有返回音频”。
3. 普通任务响应仍可提取 `taskId` 并轮询。
4. 直接返回音频 URL 的响应仍能成功保存。
5. 视频或图片收到同类提交拒绝时也必须在提交阶段失败。
6. 完整测试、JavaScript 语法检查和真实页面验证通过。

## 迁移风险与控制

- 最大风险是把同步 `confirm/prompt` 改成异步后漏掉 `await`。通过逐调用点测试和原生调用扫描控制。
- 页面脚本存在内联函数，修改 `async` 时必须检查事件调用方是否允许 Promise；HTML 事件处理器可以调用异步函数，但业务内部必须显式等待返回值。
- 弹窗组件必须独立于 Tailwind、Lucide 和单页专用 CSS，确保旧独立页面也能加载。
- RunningHub 错误映射不得吞掉未知错误码；未知码仍显示上游错误信息和错误码，不编造含义。
