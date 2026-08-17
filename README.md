# 老胡无限画布

这是一个本地运行的 AI 创作工作台。

做 AI 创作久了，时间不一定花在创作上。你会在几个网站之间来回切换，反复上传同一张图，重新填写差不多的参数，过几天又找不到上次那个结果是怎么来的。我想要的是一张真正能继续工作的画布，所以把素材、模型、参数、任务和生成结果放到了一起。

你可以在画布里放文本、图片、视频和音频，连接不同的执行节点，再把一个结果送到下一步。作品长什么样仍然要由创作者判断；无限画布负责保存过程，让一次有效的尝试不必下次从头再来。

当前版本：`v2026.08.17`

[快速开始](#快速开始) · [主要能力](#主要能力) · [支持的平台](#支持的平台) · [本地数据](#本地数据怎么保存) · [项目边界](#使用前知道这些)

## 什么时候值得用它

- 需要同时处理文本、图片、视频、音频或音乐素材。
- 经常在多个平台、模型、价格和参数之间切换。
- 想把一次生成继续接到下一次生成，而不是反复下载、上传和整理。
- 需要在本地保存 API 配置、画布、素材、工作流和结果。
- 想把 AI 调用接进真实作品流程，而不是只做一次模型演示。

如果只是临时试一个模型，直接使用模型平台可能更快。无限画布的价值在于创作过程会变长，节点关系和素材状态值得留下来。

## 主要能力

### 可视化画布

画布由两类节点组成：

- 素材节点：保存文本、图片、视频、音频和已经生成的结果。
- 执行节点：调用文本、图片、视频、音频、音乐生成能力或封装好的 AI 应用。

节点之间通过连接传递素材。多输入会映射到对应的官方字段；每次运行都会留下独立的结果节点，方便并行试不同方案，也方便把满意的结果继续送入下一步。

平台、模型、运行模式和参数由能力档案与接口证据共同决定，不按模型名称猜测一个看似能用的控件。

### 素材和结果管理

- 上传素材保留原始名称和真实比例。
- 系统按文件内容计算 SHA-256，相同内容只保存一份。
- 生成结果独立保存，删除画布不会连带删除结果。
- 文本、图片、视频和音频可以在素材库与画布之间继续复用。
- 浏览器采集插件、Photoshop 连接器和本地素材导入工具位于 `tools/`。

### 参数和运行前检查

执行面板会把平台、模型、运行模式和参数放在一起管理。当前模型只开放接口明确支持的输入组合；处于“使用默认”的参数不会被强行发送给平台。

运行前会检查文本、素材类型、数量、尺寸、时长和必填字段，尽量避免把明显错误的请求直接发到付费接口。价格信息用于比较和定位，最终费用以平台实时页面为准。

### 本地工具

- 支持本地或局域网 ComfyUI。
- 支持图片扩展、裁剪、预览、视频帧提取和音频抽取。
- 支持项目数据的状态检查、备份、迁移和恢复。
- macOS 和 Windows 都提供启动与安装入口。

## 支持的平台

当前正式适配范围包括：

| 平台 | 用途 |
|---|---|
| RunningHub | AI 应用和已同步 Schema 的 ComfyUI 应用 |
| AI MONEY | 已建立适配与能力档案的文本、图片、视频等模型 |
| ModelScope | 已配置的文本与图片模型 |
| 即梦 CLI | 使用本机登录状态的图片与视频生成 |
| GPT CLI | 文本能力；图片可作为文本任务的参考输入 |
| 火山引擎 | 已适配的图片、视频及相关能力 |

“可以配置”不等于“所有模型都已经完成适配”。画布只开放当前用户已启用、能力档案有证据、请求适配器可用的模型。

## 快速开始

### 获取项目

```bash
git clone https://github.com/LaohuAD/laohu-Infinite-Canvas.git
cd laohu-Infinite-Canvas
```

### macOS

第一次使用：

```bash
./mac-安装依赖.sh
```

之后双击 `mac-启动服务.command`，或运行：

```bash
./mac-启动服务.sh
```

### Windows

第一次使用双击 `安装依赖.bat`，之后双击 `run.bat`。

### 打开页面

服务启动后，在浏览器打开 [本地工作台](http://127.0.0.1:3000/)。API Key 通过页面里的“API 设置”保存。

不要把本机的 `API/.env`、`data/api_providers.json` 或包含密钥的备份上传到 GitHub。

## 本地数据怎么保存

程序代码和用户数据分开管理：

| 目录 | 保存什么 | 是否上传 |
|---|---|---|
| `data/` | 设置、索引、画布 JSON 和会话 | 不上传用户运行数据；模型能力档案除外 |
| `assets/input/asset/` | 长期保留的素材 | 不上传 |
| `assets/input/temporary/` | 临时输入素材 | 不上传 |
| `assets/output/` | 图片、视频、音频和文本结果 | 不上传 |
| `workflows/` | ComfyUI 与画布工作流 | 不上传 |
| `API/` | API Key 等密钥 | 不上传真实 `.env` |
| `cache/` | 可重新生成的缓存 | 不上传，可清理 |
| `backups/` | 本地备份包 | 不上传 |

普通备份默认不包含密钥。只有明确使用 `backup --include-secrets` 时，才会把 `API/.env` 放入备份；含密钥的备份应按敏感文件管理。

## 模型能力档案

模型能力与用户自己的 API 设置分开维护：

| 位置 | 作用 |
|---|---|
| `docs/model-capabilities/` | 能力档案和平台适配说明 |
| `data/model_capabilities/capability-vocabulary.json` | 媒体类型、输入角色、参数语义和证据等级 |
| `data/model_capabilities/providers/` | 各平台与模型的字段映射和能力证据 |
| `data/model_capabilities/registry.json` | 程序读取的能力索引 |
| `data/api_providers.json` | 当前用户启用的平台与模型，仅保存在本地 |

新增模型时，需要先核对官方 Schema、官方文档和真实请求适配器。没有接口证据的能力会标记为待确认，不会自动变成可运行控件。

## 数据管理命令

macOS：

```bash
.venv/bin/python tools/data_manager.py status
.venv/bin/python tools/data_manager.py backup
.venv/bin/python tools/data_manager.py migrate
.venv/bin/python tools/data_manager.py restore "backups/备份文件.zip"
```

Windows：

```bat
python\python.exe tools\data_manager.py status
python\python.exe tools\data_manager.py backup
python\python.exe tools\data_manager.py migrate
python\python.exe tools\data_manager.py restore "backups\备份文件.zip"
```

## 更新

页面里的“项目主页”会打开 [GitHub 项目主页](https://github.com/LaohuAD/laohu-Infinite-Canvas)。项目根据根目录的 `VERSION` 检查版本；更新前会创建恢复点，更新程序文件时不应覆盖本地 API Key、画布、素材和生成结果。

## 使用前知道这些

- 这是本地工作台，不是模型本身；你仍然需要配置对应平台的 API 或登录状态。
- 平台支持、模型字段和价格会变化，README 不替代官方文档和当前页面显示。
- 画布只负责组织和执行，生成结果仍然需要创作者自己判断、筛选和修改。
- `data/`、素材、工作流、API 配置和备份默认属于本地数据，不应上传到公开仓库。

## 三个项目怎么配合

- [老胡音乐](https://github.com/LaohuAD/laohu-music)：处理歌曲的选题、歌词、声音方向和归档。
- [老胡 AI 视觉](https://github.com/LaohuAD/laohu-ai-visual)：处理故事、剧本、视觉资产、分镜和视频提示词。

无限画布可以独立使用，也可以作为另外两个项目的执行层。先在作品层确定要做什么，再在画布里选择模型和参数，通常比一开始就试模型更容易得到可复用的结果。

## 可选工具入口

如果你需要比较模型渠道，或直接使用现成的 AI 工作流，可以先从下面几个入口试用：

- [注册 AI MONEY](https://api.laohuaimoney.com/sign-up?aff=460d)
- [使用 RunningHub 海外站](https://www.runninghub.ai?inviteCode=rh-v1001)
- [使用 RunningHub 国内站](https://www.runninghub.cn?inviteCode=rh-v1001)

这些是我的邀请入口，注册或使用可能会给我带来一定回报。是否适合你，建议先按自己的任务试用，再决定是否长期使用。

## 作者与账号

项目由老胡维护。更多 AI 音乐、视觉和内容创作实践可以在 [Bilibili](https://space.bilibili.com/13497214)、[小红书](https://xhslink.com/m/AZo7UbSx1ef) 和 [抖音](https://v.douyin.com/usGF0Kz_Yic/) 查看。

## 授权与来源

本仓库基于原 Infinite-Canvas 项目持续重构，原始作者和历史贡献保留在 Git 提交记录中；当前的智能画布、模型能力档案和维护文档由老胡继续维护。

本项目禁止未经授权把封装后的软件直接修改成商业产品。基于代码二次开发的软件必须保持开源并注明来源作者。详细条款见 [LICENSE](LICENSE)。

## 界面预览

<img width="2079" height="665" alt="无限画布界面" src="https://github.com/user-attachments/assets/8469923b-f7a2-403c-9c37-e6e789211f28" />

<img width="1865" height="1503" alt="无限画布节点与素材" src="https://github.com/user-attachments/assets/f4030201-67c6-4845-b08b-b6fdf304afaa" />

<img width="2196" height="1040" alt="无限画布模型与参数" src="https://github.com/user-attachments/assets/6d823668-cde2-4836-8332-1858efe5f520" />
