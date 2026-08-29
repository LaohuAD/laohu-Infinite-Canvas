# Director Timeline Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有视频导演台升级为可移动、可缩放、Clip 状态完全独立，并能选择本地 ComfyUI 或 RunningHub AI 应用的单轨生成工作台。

**Architecture:** 时间运算与 Clip 创建放进可独立执行的 `smart-director-core.js`，画布层只负责把指针事件换算为毫秒并渲染共享状态。通用导演台继续复用视频能力档案；个性化导演台只增加本地工作流与 RunningHub AI 应用适配层，不复制第三套运行协议。

**Tech Stack:** 原生 JavaScript、HTML/CSS、Python `unittest` 驱动的 Node.js 可执行测试、现有智能画布状态与 RunningHub Schema 规范化函数。

---

## 文件职责

- `static/js/smart-director-core.js`：无 DOM 的时间轴移动、时长约束、右推碰撞、新 Clip 创建和状态归一化。
- `static/js/smart-canvas.js`：导演台渲染、拖动/缩放/滚轮事件、Clip 选择与输入隔离、下载入口、个性化适配器与真实运行调用。
- `static/css/smart-canvas.css`：导演台顶部工具栏、共享滚动时间轴、三列 Clip 工作区、逐行参数和快捷键弹层。
- `static/js/api-settings.js`、`static/api-settings.html`：把历史 RunningHub 工作流明确标记为废弃，同时保持旧画布兼容数据可读。
- `tests/test_smart_director_core.py`：时间运算、独立状态和迁移的可执行单元测试。
- `tests/test_smart_node_contract.py`：导演台 DOM 契约、RunningHub AI 应用来源、下载文案和事件绑定的回归检查。
- `tests/test_api_settings_connection.py`：API 设置只公开 AI 应用并标注旧工作流废弃。

### Task 1: 建立时间轴纯函数和新 Clip 独立契约

**Files:**
- Modify: `static/js/smart-director-core.js`
- Test: `tests/test_smart_director_core.py`

- [ ] **Step 1: 写失败测试，覆盖新建独立、右推、缩短不回弹、删除留白和视口范围**

```python
def test_fresh_clip_is_selected_without_inheriting_previous_state(self):
    data = run_node("""
const d=require('./static/js/smart-director-core.js');
const source=d.normalizeDirector({clips:[{id:'a',startMs:0,durationMs:8000,prompt:'旧提示',inputRefs:[{id:'img'}],generation:{providerId:'p',model:'m',params:{seed:1}},results:[{id:'r'}]}],selectedClipId:'a'});
const result=d.appendFreshOrdinaryClip(source,{id:'b',durationMs:8000});
console.log(JSON.stringify(result));
""")
    self.assertEqual(data["selectedClipId"], "b")
    self.assertEqual(data["clips"][1]["prompt"], "")
    self.assertEqual(data["clips"][1]["inputRefs"], [])
    self.assertEqual(data["clips"][1]["generation"]["model"], "")
    self.assertEqual(data["clips"][0]["inputRefs"], [{"id": "img", "kind": "file"}])

def test_resize_pushes_right_but_shrink_keeps_gap(self):
    data = run_node("""
const d=require('./static/js/smart-director-core.js');
const clips=[{id:'a',startMs:0,durationMs:8000},{id:'b',startMs:8000,durationMs:8000}];
const grown=d.resizeOrdinaryClip(clips,'a',{edge:'right',timeMs:15000});
const shrunk=d.resizeOrdinaryClip(grown,'a',{edge:'right',timeMs:8000});
console.log(JSON.stringify({grown,shrunk,extent:d.timelineExtentMs(shrunk,{minimumMs:16000,viewportEndMs:30000})}));
""")
    self.assertEqual(data["grown"][1]["startMs"], 15000)
    self.assertEqual(data["shrunk"][1]["startMs"], 15000)
    self.assertGreaterEqual(data["extent"], 30000)
```

- [ ] **Step 2: 运行测试并确认因函数不存在而失败**

Run: `.venv/bin/python -m unittest tests.test_smart_director_core`

Expected: FAIL，错误包含 `appendFreshOrdinaryClip is not a function` 或 `resizeOrdinaryClip is not a function`。

- [ ] **Step 3: 实现时间轴纯函数**

```javascript
function timelineExtentMs(clips, {minimumMs=16000, viewportEndMs=0, paddingMs=4000}={}){
    const right = Math.max(0, ...(clips || []).map(clipEndMs));
    return Math.max(nonNegativeMs(minimumMs), nonNegativeMs(viewportEndMs), right + nonNegativeMs(paddingMs));
}
function pushOrdinaryClipsRight(clips, changedId){
    const result=(clips || []).map(normalizeClip);
    const changed=result.find(clip => clip.id === changedId);
    if(!changed || changed.type === 'connection') return result;
    let cursor=clipEndMs(changed);
    result.filter(clip => clip.type !== 'connection' && clip.id !== changedId && clip.startMs >= changed.startMs)
        .sort((a,b)=>a.startMs-b.startMs)
        .forEach(clip => { if(clip.startMs < cursor) clip.startMs=cursor; cursor=clipEndMs(clip); });
    return result;
}
function appendFreshOrdinaryClip(value, options={}){
    const director=normalizeDirector(value);
    const startMs=Math.max(0,...director.clips.filter(c=>c.type!=='connection').map(clipEndMs));
    const clip=normalizeClip({id:options.id,startMs,durationMs:options.durationMs || 8000,prompt:'',inputRefs:[],generation:{providerId:'',model:'',mode:'',params:{},parameterDrafts:{}},results:[],currentResultId:''},director.clips.length);
    director.clips.push(clip);
    director.selectedClipId=clip.id;
    return director;
}
```

同时实现 `moveOrdinaryClip()`、`resizeOrdinaryClip()`、整秒与模型时长选项约束，并导出这些函数。移动向左时夹紧前一个普通 Clip，移动或延长向右时调用 `pushOrdinaryClipsRight()`；缩短不调用回填逻辑。

- [ ] **Step 4: 运行核心测试**

Run: `.venv/bin/python -m unittest tests.test_smart_director_core`

Expected: 全部 PASS。

- [ ] **Step 5: 提交核心契约**

```bash
git add static/js/smart-director-core.js tests/test_smart_director_core.py
git commit -m "feat: 建立导演台时间轴核心契约"
```

### Task 2: 接通普通 Clip 移动、时长双向同步和时间轴视口

**Files:**
- Modify: `static/js/smart-canvas.js`
- Modify: `static/css/smart-canvas.css`
- Test: `tests/test_smart_node_contract.py`

- [ ] **Step 1: 写失败契约测试**

```python
def test_director_timeline_uses_shared_scroll_viewport_and_core_mutations(self):
    source=(ROOT / "static/js/smart-canvas.js").read_text()
    self.assertIn('data-director-timeline-scroll', source)
    self.assertIn('SMART_DIRECTOR_CORE.moveOrdinaryClip', source)
    self.assertIn('SMART_DIRECTOR_CORE.resizeOrdinaryClip', source)
    self.assertIn('timelineScrollMs', source)
    self.assertNotIn('smartMinimaxCompactSegments(node);', source[source.index("[data-minimax-delete-segment]"):source.index("[data-minimax-number]")])
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `.venv/bin/python -m unittest tests.test_smart_node_contract.SmartNodeContractTests.test_director_timeline_uses_shared_scroll_viewport_and_core_mutations`

Expected: FAIL，缺少共享滚动容器或纯函数调用。

- [ ] **Step 3: 改造渲染状态**

在 `smartMinimaxEnsureSegment()` 中同步 `start/startMs`、`duration/durationMs`，初始化 `timelineZoom`、`timelineScrollMs`、`timelineMinViewMs`；`smartMinimaxTimelineTotal()` 改用 `SMART_DIRECTOR_CORE.timelineExtentMs()`。标尺与轨道放入同一个横向滚动视口，内容像素宽度由总毫秒和缩放值统一计算。

```javascript
const timelineState=SMART_DIRECTOR_CORE.timelineViewport({
  clips:node.segments, zoom:node.timelineZoom, scrollMs:node.timelineScrollMs,
  minimumMs:node.timelineMinViewMs, viewportWidth:timelineViewportWidth
});
```

- [ ] **Step 4: 接通拖动与拖边**

Clip 主体 `pointerdown` 记录开始毫秒；移动时按整秒调用 `moveOrdinaryClip()`。左右边缘调用 `resizeOrdinaryClip()`，再用兼容层回写 `start/duration` 与 `startMs/durationMs`。连接 Clip 保留现有覆盖拖动并重新执行 `smartDirectorApplyConnectionDerivation()`。

```javascript
const next=SMART_DIRECTOR_CORE.resizeOrdinaryClip(node.segments, seg.id, {
  edge, timeMs:smartDirectorSnapTimelineMs(pointerMs), durationConstraint
});
smartDirectorReplaceSegments(node,next);
```

删除 Clip 时移除 `smartMinimaxCompactSegments(node)`；新建普通 Clip 使用纯函数创建结果并立即设置 `selectedSegmentId`，不读取 `current` 的提示词、素材、模型或参数。

- [ ] **Step 5: 接通滚轮作用域和锚点缩放**

```javascript
timelineViewport.addEventListener('wheel', event => {
  if(!smartDirectorTimelineOwnsEvent(node, timelineViewport, event)) return;
  event.preventDefault(); event.stopPropagation();
  if(event.ctrlKey) smartDirectorZoomAtPointer(node,timelineViewport,event);
  else smartDirectorScrollByWheel(node,timelineViewport,event);
}, {passive:false});
```

只有节点已选中且指针位于时间轴时捕获；`Control + wheel` 保持指针下时间不变，普通滚轮只更新 `timelineScrollMs` 和视口 `scrollLeft`。

- [ ] **Step 6: 运行测试并提交**

Run: `node --check static/js/smart-canvas.js && .venv/bin/python -m unittest tests.test_smart_director_core tests.test_smart_node_contract`

Expected: PASS。

```bash
git add static/js/smart-canvas.js static/css/smart-canvas.css tests/test_smart_node_contract.py
git commit -m "feat: 接通导演台可缩放时间轴"
```

### Task 3: 重排导演台工具栏与三列 Clip 工作区

**Files:**
- Modify: `static/js/smart-canvas.js`
- Modify: `static/css/smart-canvas.css`
- Test: `tests/test_smart_node_contract.py`

- [ ] **Step 1: 写失败测试**

```python
def test_director_toolbar_and_workspace_follow_approved_layout(self):
    source=(ROOT / "static/js/smart-canvas.js").read_text()
    toolbar=source[source.index('<div class="minimax-wb-toolbar">'):source.index('<div class="minimax-wb-body"')]
    self.assertIn('data-minimax-add-segment', toolbar)
    self.assertIn('data-minimax-add-connection', toolbar)
    self.assertIn('data-director-shortcuts', toolbar)
    self.assertIn("下载当前 Clip", toolbar)
    self.assertNotIn("导出当前 Clip", toolbar)
    self.assertIn('director-clip-assets-column', source)
    self.assertIn('director-prompt-column', source)
    self.assertIn('director-settings-column', source)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `.venv/bin/python -m unittest tests.test_smart_node_contract.SmartNodeContractTests.test_director_toolbar_and_workspace_follow_approved_layout`

Expected: FAIL，按钮仍在时间轴或仍使用“导出”。

- [ ] **Step 3: 移动工具栏操作并增加快捷键弹层**

把两个新增按钮放入 `.minimax-top-actions`；下载按钮使用“下载 / Download”文案。增加锚定 `.director-shortcuts-popover`，显示滚轮、`Control + 滚轮`、Clip 拖动和边缘调整说明；点击外部或 `Esc` 关闭，中英文同步。

- [ ] **Step 4: 重排三列工作区和逐行参数**

```html
<div class="director-clip-workspace">
  <section class="director-clip-assets-column">…垂直素材组…</section>
  <section class="director-prompt-column">…提示词与连接状态…</section>
  <section class="director-settings-column">…平台/模型/运行模式/逐行参数…</section>
</div>
```

CSS 使用 `grid-template-columns:minmax(210px,.85fr) minmax(300px,1.25fr) minmax(300px,1fr)`；窄宽度时保持列最小宽度并由当前面板横向滚动，设置列内部纵向滚动。动态参数每项一行，弹层层级沿用现有执行面板规范。

- [ ] **Step 5: 运行测试并提交**

Run: `node --check static/js/smart-canvas.js && .venv/bin/python -m unittest tests.test_smart_node_contract`

Expected: PASS。

```bash
git add static/js/smart-canvas.js static/css/smart-canvas.css tests/test_smart_node_contract.py
git commit -m "feat: 优化导演台工作区布局"
```

### Task 4: 接入个性化导演台二级来源并废弃旧 RunningHub 工作流

**Files:**
- Modify: `static/js/smart-canvas.js`
- Modify: `static/js/api-settings.js`
- Modify: `static/api-settings.html`
- Test: `tests/test_smart_node_contract.py`
- Test: `tests/test_api_settings_connection.py`

- [ ] **Step 1: 写失败测试**

```python
def test_minimax_director_uses_local_workflows_or_runninghub_apps_only(self):
    source=(ROOT / "static/js/smart-canvas.js").read_text()
    block=source[source.index("function smartDirectorPersonalizedAdapter"):source.index("function smartMinimaxBodyHtml")]
    self.assertIn("runningHubEntries('app')", block)
    self.assertIn('comfyWorkflows', block)
    self.assertNotIn("runningHubEntries('workflow')", block)

def test_legacy_runninghub_workflow_is_marked_deprecated(self):
    html=(ROOT / "static/api-settings.html").read_text()
    script=(ROOT / "static/js/api-settings.js").read_text()
    self.assertIn('已废弃', html + script)
    self.assertIn('Deprecated', html + script)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `.venv/bin/python -m unittest tests.test_smart_node_contract tests.test_api_settings_connection`

Expected: FAIL，个性化导演台尚无 AI 应用二级来源或废弃标记。

- [ ] **Step 3: 实现适配器选择与字段映射**

`smartDirectorPersonalizedAdapter(node, seg)` 返回：

```javascript
{
  engine:'local-comfyui'|'runninghub-app',
  options: engine==='runninghub-app' ? runningHubEntries('app') : comfyWorkflows,
  selectedId:'',
  fields: engine==='runninghub-app' ? sortRunningHubFields(rhFieldsForEntry(entry)) : comfyWorkflowFields(workflow)
}
```

RunningHub 媒体字段按 `nodeId::fieldName` 映射到 Clip 素材，设置字段复用 `renderRhSettingField()` 的类型、选项和真实值语义；运行时复用 `rhBuildNodeInfoList()` 与 `/api/runninghub/submit`。本地工作流复用现有 `comfyWorkflowCache`、字段配置和本地执行接口。每个 Clip 独立保存 `adapter.engine`、`adapter.selectedId`、字段参数和绑定。

- [ ] **Step 4: 标记旧入口废弃并保持兼容**

API 设置当前公开页继续只展示 RunningHub AI 应用。在历史工作流编辑器和兼容分支文案中加入“已废弃 / Deprecated，仅用于旧画布兼容”，不删除读取函数和旧数据；新导演台候选和提交代码不得调用 `runningHubEntries('workflow')`。

- [ ] **Step 5: 运行测试并提交**

Run: `node --check static/js/smart-canvas.js && node --check static/js/api-settings.js && .venv/bin/python -m unittest tests.test_smart_director_core tests.test_smart_node_contract tests.test_api_settings_connection`

Expected: PASS。

```bash
git add static/js/smart-canvas.js static/js/api-settings.js static/api-settings.html tests/test_smart_node_contract.py tests/test_api_settings_connection.py
git commit -m "feat: 接入导演台个性化生成来源"
```

### Task 5: 全链路验证与浏览器交互验收

**Files:**
- Modify only if verification finds a reproducible defect

- [ ] **Step 1: 运行静态与定向测试**

Run: `git diff --check && node --check static/js/smart-director-core.js && node --check static/js/smart-canvas.js && node --check static/js/api-settings.js`

Expected: 全部退出码 0。

Run: `.venv/bin/python -m unittest tests.test_smart_director_core tests.test_smart_node_contract tests.test_api_settings_connection`

Expected: 全部 PASS。

- [ ] **Step 2: 运行完整测试**

Run: `.venv/bin/python -m unittest discover -s tests`

Expected: 全部 PASS。

- [ ] **Step 3: 在真实画布验证核心路径**

使用现有本机服务打开智能画布，验证：

1. 新增 Clip 后立即选中，设置和素材为空；切回旧 Clip 数据仍在。
2. 两个 8 秒 Clip，前者延长到 15 秒后后者移到 15 秒；缩回后不回退。
3. 删除前一个 Clip 后空白保留。
4. `Control + 滚轮` 只缩放导演台时间轴，普通滚轮只横移；鼠标离开导演台后画布行为正常。
5. RunningHub 只显示已同步 AI 应用，字段顺序与 API 设置一致。
6. 顶部按钮、三列布局、快捷键说明和“下载”中英文文案正确。

- [ ] **Step 4: 最终提交**

如验证阶段有修复：

```bash
git add <本轮实际修复文件>
git commit -m "fix: 完成导演台全链路验收"
```

若没有新增修复，则不制造空提交。
