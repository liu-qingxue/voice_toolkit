# 开发日志：fcitx5 文本注入插件

## 背景

项目需要将 ASR 转录结果直接注入到当前焦点输入框的光标位置。之前尝试了 `ydotool type`（不支持中文）、`wl-copy + ydotool key Ctrl+V`（依赖 ydotoold 守护进程，不稳定），最终决定通过 fcitx5 插件的方式实现——利用 fcitx5 的 `commitString` API 直接向焦点应用提交文本。

## 整体架构

```
守护进程 (main_daemon.py)
  ↓ dispatch(output_mode="fcitx5")
  ↓ 写入 /tmp/voxtype/result（转录文本）
  ↓ 写入 /tmp/voxtype/commit（触发信号）
fcitx5 插件 (commit-bridge)
  ↓ inotify 检测到 commit 文件写入
  ↓ 读取 /tmp/voxtype/result
  ↓ ic->commitString(text) → 输入框光标处
```

## 关键 API

### fcitx5 Addon 框架

| API | 头文件 | 用途 |
|-----|--------|------|
| `AddonInstance` | `fcitx/addoninstance.h` | 插件基类，所有 fcitx5 插件继承自此 |
| `AddonFactory` | `fcitx/addonfactory.h` | 插件工厂，AddonManager 通过它创建插件实例 |
| `FCITX_ADDON_FACTORY_V2(name, factory)` | `fcitx/addoninstance.h` | 宏，注册插件工厂，生成符号 `fcitx_addon_factory_instance_##name` |

### 事件系统

| API | 头文件 | 用途 |
|-----|--------|------|
| `instance_->watchEvent(EventType, phase, callback)` | `fcitx/event.h` | 注册事件处理器 |
| `EventType::InputContextKeyEvent` | `fcitx/event.h` | 按键事件，可获取当前焦点 InputContext |
| `EventType::InputContextFocusIn` | `fcitx/event.h` | 焦点进入事件，可获取 InputContext |
| `keyEvent.inputContext()` | `fcitx/event.h` | 从按键事件获取 InputContext 引用 |
| `inputContext()->watch()` | `fcitx/inputcontext.h` | 创建 InputContext 的弱引用（TrackableObjectReference） |

### 文本提交

| API | 头文件 | 用途 |
|-----|--------|------|
| `ic->commitString(text)` | `fcitx/inputcontext.h` | 向焦点应用提交文本，**核心 API** |
| `instance_->mostRecentInputContext()` | `fcitx/instance.h` | 获取最近使用的输入上下文（不可靠，可能为空） |
| `instance_->inputContextManager().foreachFocused(callback)` | `fcitx/inputcontextmanager.h` | 遍历当前有焦点的输入上下文 |

### 文件系统事件（替代定时器轮询）

| API | 头文件 | 用途 |
|-----|--------|------|
| `inotify_init()` | `sys/inotify.h` | 创建 inotify 文件描述符 |
| `inotify_add_watch(fd, path, mask)` | `sys/inotify.h` | 添加文件/目录监听 |
| `instance_->eventLoop().addIOEvent(fd, flags, callback)` | `fcitx-utils/event.h` | 将文件描述符注册到 fcitx5 事件循环 |
| `IOEventFlag::In` | `fcitx-utils/eventloopinterface.h` | IO 读事件标志 |

### 构建系统

| 组件 | 用途 |
|------|------|
| `find_package(Fcitx5Core REQUIRED)` | 引入 fcitx5 核心库 |
| `find_package(Fcitx5Utils REQUIRED)` | 引入 fcitx5 工具库 |
| `target_link_libraries(... Fcitx5::Core Fcitx5::Utils)` | 链接 fcitx5 库 |
| 安装路径 `/usr/lib/fcitx5/` | `.so` 插件安装目录 |
| 安装路径 `/usr/share/fcitx5/addon/` | `.conf` 插件元数据安装目录 |

## 配置文件格式

`/usr/share/fcitx5/addon/commitbridge.conf`:
```ini
[Addon]
Name=Commit Bridge
Comment=Commit text from file to focused input via fcitx5
Category=Module
Version=1.0
Library=libcommitbridge
Type=SharedLibrary
OnDemand=False
Configurable=False

[Addon/Dependencies]
0=core
```

## 遇到的坑和解决方案

### 1. 符号未定义：fcitx_addon_factory_instance

**现象：**
```
Failed to initialize addon factory for addon commit-bridge.
undefined symbol: fcitx_addon_factory_instance
```

**原因：** `.conf` 文件名中的连字符 `-` 导致加载器查找的符号名与 `FCITX_ADDON_FACTORY_V2` 宏生成的符号名不匹配。

宏生成：`fcitx_addon_factory_instance_commitbridge`
加载器查找：`fcitx_addon_factory_instance_commit-bridge`（从 conf 文件名推导）

**解决：** `.conf` 文件名必须与 `FCITX_ADDON_FACTORY_V2` 的第一个参数完全一致，不能含有连字符。

`commit-bridge.conf` → `commitbridge.conf`

同时 CMakeLists.txt 中的 `install(FILES ...)` 也要对应修改。

### 2. 定时器只触发一次

**现象：** `addTimeEvent` 创建的定时器只触发一次就停止了，导致文件轮询中断。

```cpp
timer_ = instance_->eventLoop().addTimeEvent(
    CLOCK_MONOTONIC, interval, interval, callback);  // 只触发一次
```

**原因：** `addTimeEvent` 创建的定时器非持久性（non-persistent），触发一次后需要手动重新调度。`callback` 返回 `true` 表示继续，但底层 EventLoop 实现可能不保证持续性。

**解决：** 放弃定时器轮询，改用 `inotify` + `EventLoop::addIOEvent` 实现事件驱动。后端写入文件时，inotify 立即通知插件，没有轮询间隔。

### 3. `mostRecentInputContext()` 返回空

**现象：** 插件通过 `mostRecentInputContext()` 获取 InputContext 失败，无法调用 `commitString`。

**原因：** fcitx5 只在应用注册了输入上下文时才会有记录。仅在用户通过 fcitx5 输入法操作过（如按键）后，`mostRecentInputContext()` 才有值。

**解决：** 监听 `InputContextKeyEvent` 和 `InputContextFocusIn`，在事件触发时通过 `watch()` 创建 `TrackableObjectReference<InputContext>` 弱引用保存。需要提交时优先使用这个保存的引用，无效时再回退到 `mostRecentInputContext()`。

```cpp
eventHandlers_.emplace_back(instance_->watchEvent(
    EventType::InputContextKeyEvent, EventWatcherPhase::Default,
    [this](Event &event) {
        auto &keyEvent = static_cast<KeyEvent &>(event);
        if (keyEvent.isRelease()) return;
        lastFocusedIc_ = keyEvent.inputContext()->watch();
    }));
```

### 4. inotify 事件被吞

**现象：** 调试日志显示只收到 `result` 文件的 inotify 事件，`commit` 文件的事件从未出现。

**原因：** `read(fd, buf, size)` 一次可以读取多个排队中的 inotify 事件。`result` 和 `commit` 是连续写入的，它们的事件被批量交付，但代码只检查了缓冲区中的第一个事件（`result`），后面的 `commit` 事件被跳过。

```cpp
// 错误：只处理第一个事件
auto *event = reinterpret_cast<struct inotify_event *>(buf);
if (event->name == "commit") { ... }

// 正确：遍历所有事件
size_t offset = 0;
while (offset < len) {
    auto *ev = reinterpret_cast<struct inotify_event *>(buf + offset);
    offset += sizeof(struct inotify_event) + ev->len;
    if (ev->name == "commit") { ...; break; }
}
```

### 5. 析构时 /tmp/voxtype/ 目录不存在导致错误

**现象：** fcitx5 退出时输出 `touch: 无法 touch '/tmp/voxtype/dtor_called': 没有那个文件或目录`。

**原因：** 调试用的标记文件在析构函数中创建，但 `/tmp/voxtype/` 目录可能已被用户删除。该目录不是插件运行的必要条件。

**解决：** 在 `touch` 前确保目录存在。正式版中已移除所有调试代码，不依赖任何外部目录。

## 最终项目结构

```
voice_toolkit/
├── live/
│   ├── main_daemon.py     ← 守护进程（录音+转录）
│   ├── dispatcher.py      ← 输出分发（新增 fcitx5 模式）
│   └── ...
├── config/
│   ├── config.py          ← 配置类（fcitx5 模式支持）
│   └── config.yaml        ← 配置（output_mode: fcitx5）
├── fcitx5-commit/
│   ├── CMakeLists.txt     ← 构建
│   ├── commit-bridge.cpp  ← 插件核心
│   ├── commit-bridge.h    ← 插件头文件
│   └── commitbridge.conf  ← 插件元数据
└── DEVELOPMENT_LOG.md     ← 本文件
```

---

# 2026-08-26 Qwen3-ASR 高精度模型接入

## 背景

paraformer_v1/v2 精度不够(纯净 CER 7.68% / 11.42%),换用 Qwen3-ASR(纯净 CER 0.56%)。
利用 AMD RX 9060 XT 16GB 显存,走 llama.cpp Vulkan GPU 加速。

## 架构

```
voice_toolkit (core/models.py QwenTranscriber)
    │ sys.path 指向
    ▼
~/Public/Qwen3-ASR-GGUF/ (独立后端仓库, git 可更新)
    ├─ qwen_asr_gguf/inference/llama.py  ← ctypes 翻译官(打过补丁, 对齐 llama.cpp b10566)
    ├─ qwen_asr_gguf/inference/bin/      ← 冻结的 llama.cpp 库(复制非软链, 系统更新不影响)
    └─ ~/models/qwen3-asr-gguf/          ← 模型(ONNX Encoder int4 ×2 + GGUF Decoder q4_k)
```

## 混合推理链路

- **ONNX Encoder**(CPU): 音频 → 特征。119s 音频约 1.7s(计算量小, AMD 无 DML/CUDA, 用 CPU 足够)
- **GGUF Decoder**(Vulkan GPU): 特征 → 文本。预填充 5231 tokens/s, 生成 158 tokens/s
- 实测 RTF 0.038(119s 音频 4.4s 完成), 比作者 RTX 5050 的 0.052 更快

## 踩坑记录

### 1. llama.py ctypes 结构体与系统 llama.cpp b10566 不匹配
**现象**: 引擎初始化时 `llama_init_from_model` 返回 NULL。
**原因**: llama.py 绑定的 llama.cpp 版本略旧, 而系统 b10566 更新:
- `llama_model_params` 新增 `load_mode`/`load_mtp`, 删除 `use_mmap`/`use_direct_io`/`use_mlock`
- `llama_context_params` 新增 `n_rs_seq`/`n_outputs_max`/`n_outputs_max_per_seq`/`ctx_type`
结构体错位 → C 侧读到垃圾参数。
**解决**: 修改 llama.py 两处结构体定义对齐 b10566(带注释标记)。

### 2. 系统 ggml 新旧架构文件冲突
**现象**: `pacman -S ggml` 报文件冲突(/usr/lib/libggml.so 被旧 libggml 0.15.1 占用)。
**原因**: 之前 AUR 装的 whisper.cpp 依赖旧 libggml。
**解决**: 卸载 whisper.cpp + libggml, 换装官方 ggml/ggml-cpu/ggml-vulkan/llama-cpp(znver4)。

### 3. 上游 duration=0.0 bug
**现象**: `engine.transcribe(audio_file)` 返回空结果。
**原因**: 上游 `load_audio` 把 `duration=0` 解释为"读 0 帧"。
**解决**: 接入层统一走 `engine.asr(audio=np.ndarray)` 数组接口, 绕开文件接口。

### 4. 库冻结策略
**背景**: 翻译层(llama.py 补丁)与 llama.cpp 版本强耦合, 系统更新可能破坏。
**解决**: 把 /usr/lib 的 libggml/libggml-base/libllama 复制到
`qwen_asr_gguf/inference/bin/`(真实文件 + 版本软链), 与系统解耦。
升级时手动复制新库 + 检查补丁。

## 配置示例

```yaml
models:
  qwen3_asr:
    dir: ~/models/qwen3-asr-gguf/
    params:
      onnx_provider: CPU
      llm_use_gpu: true
      enable_aligner: false
      n_ctx: 2048
      chunk_size: 40.0
      memory_num: 1
      language: Chinese
      context: ""          # 上下文增强提示(专业术语场景强烈建议填写)
      verbose: false
```

## 性能对比(本机 9600X + 9060 XT)

| 模型 | 纯净 CER | RTF | 显存 |
|:---|:---|:---|:---|
| paraformer_v1 (旧) | 7.68% | 0.19 | CPU |
| paraformer_v2 (旧) | 11.42% | 0.14 | CPU |
| **Qwen3-ASR 1.7B (新)** | **0.56%** | **0.04** | ~1.6GB |
