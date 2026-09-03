# voice_toolkit — Windows 部署与使用

> 项目本体已做跨平台适配(单仓库, 平台自动分流)。本文只讲 **Windows 侧**要做的事。
> Linux 用法不变, 见仓库根 [README.md](../README.md)。

## 架构对应(看懂本页的前提)

Linux 的"前端"是两段: 入口 `run.sh`(唤醒 daemon + 发 toggle) + fcitx5 插件(光标注入)。
Windows 把它们合并进一个 **pythonw 无窗口入口**:

```
快捷键 → pythonw.exe windows/run_hotkey.py     (GUI 子系统, 永不弹终端)
          ├─ live/toggle.py: 探测/拉起 daemon, 发 toggle 命令
          ├─ daemon(Qt 托盘): 录音 → 转录 → 写 result 文件 + 托盘气泡/弹窗
          └─ 读到转录文本 → ctypes 直调 SendInput 注入当前光标 + 蜂鸣反馈
```

- **为什么不用 .ps1**: 脚本必须有宿主进程执行, PowerShell 宿主是控制台子系统程序,
  被快捷键拉起必然闪终端窗口。`pythonw.exe` 是 Python 官方"无窗口解释器"
  (GUI 子系统), 绑定快捷键 = 永不弹窗, 相当于免打包的 exe。前端逻辑本来就全在
  Python 仓库里, 无需引入 PowerShell。
- **`live/toggle.py`** 已跨平台: Linux 用 fcntl 探测 daemon; Windows 用 PID 文件 +
  OpenProcess。它读 daemon 的 **state 文件**(idle/recording/transcribing)决定
  "本次该立即返回(开始录音)"还是"等转录结果"——旧版无条件空等 5s、长录音丢结果
  的问题已一并修掉(Linux 同样受益)。
- **光标注入不碰剪贴板**: SendInput 的 `KEYEVENTF_UNICODE` 直接把 UTF-16 字符交给
  焦点应用, 绕过输入法, 中文直接上屏; 换行转为回车键。
- `windows/legacy/run.ps1` 是早期 PowerShell 方案(快捷键冒烟测试), 已废弃仅供参考。

## 一次性部署

### 1. Python 环境

要求 **Python 3.12**(3.13/3.14 需自行验证依赖兼容)。以 3.12 为例:

```powershell
cd <本项目目录>                        # 如 D:\Projects\voice_toolkit
py -3.12 -m venv venv
venv\Scripts\pip install -r requirements.txt
```

> `requirements.txt` 里的 `torch==2.13.0` 默认装的是 **CUDA 版**(Windows pip 默认源),
> 你的机器是 AMD 显卡、qwen3_asr 走 ONNX+llama.cpp 时**根本不需要 torch**——
> 只有用 funasr(paraformer 路线)才要 torch。两条路:
> - 只用 qwen3_asr → 不装 torch, 删掉 requirements.txt 里的 torch 行再装;
> - 需要 paraformer → 装 CPU 版 torch: `pip install --index-url https://download.pytorch.org/whl/cpu torch`
>
> PyQt6(托盘/弹窗)必须装。

### 2. Qwen3-ASR-GGUF 后端仓库(独立, 可单独更新)

Windows 上用环境变量指定位置(代替 Linux 的 `~/Public` 约定):

```powershell
# 假设克隆到 D:\Models\Qwen3-ASR-GGUF
setx QWEN_BACKEND_DIR "D:\Models\Qwen3-ASR-GGUF"
# setx 只对之后新开的终端生效; 改完重开 PowerShell
```

后端在 Windows 上的依赖(onnxruntime **DirectML** 版、llama.cpp 的 GPU 后端等)
按其仓库 README 操作。注意: Linux 上用"标准 onnxruntime", Windows 用后端 README 的
directml 版——别装反。

### 3. 模型文件(共享分区, 双系统共用)

qwen3_asr 三件套(≈1.4GB)与 paraformer 四件套放共享 NTFS 分区, 例:

```powershell
D:\Models\qwen3-asr-gguf\    qwen3_asr_encoder_frontend.int4.onnx
                             qwen3_asr_encoder_backend.int4.onnx
                             qwen3_asr_llm.q4_k.gguf
```

### 4. 配置

```powershell
mkdir $env:APPDATA\voice_toolkit\hotwords
copy config\config.example.yaml $env:APPDATA\voice_toolkit\config.yaml
notepad $env:APPDATA\voice_toolkit\config.yaml
```

Windows 配置要点(模板注释里也有):

| 字段 | Windows 建议 |
|:---|:---|
| `models.qwen3_asr.dir` | 你的实际模型目录(本机: `E:/Models/qwen3-asr-gguf`) |
| `models.qwen3_asr.params.onnx_provider` | `DirectML`(AMD 显卡; 不行就 `CPU`) |
| `models.qwen3_asr.params.llm_use_gpu` | `true`(llama.cpp 的 GPU 后端) |
| `live.model` | `qwen3_asr`; 调试前端链路用 `mock`(不碰模型, 固定返回测试文本) |
| `live.output_mode` | `notification`(托盘气泡预览)或 `window`(全文弹窗)——**上屏由 run_hotkey 负责, 与它无关** |
| `lock_file`/`result_file` | 默认已平台自适应, **别抄模板里的 Linux 路径**, 保持注释即可 |

模型目录不存在时 daemon 启动会直接失败, 可用 `batch` 模式或日志快速验证路径。

### 5. 绑定快捷键

把 **pythonw.exe + run_hotkey.py** 绑到全局快捷键。因为 pythonw 是 GUI 子系统程序,
无论怎么启动都**不会弹终端窗口**。

**PowerToys Keyboard Manager**(推荐, 免装额外软件):
1. PowerToys → Keyboard Manager → 重映射快捷键 → 添加;
2. 快捷键: 自定义(如 `Ctrl+Alt+V`) → 操作选 **"运行程序"**;
3. 程序填: `E:\Projects\voice_toolkit\venv\Scripts\pythonw.exe`
   参数填: `E:\Projects\voice_toolkit\windows\run_hotkey.py`

**AutoHotkey**(老玩家):
```autohotkey
; voice_toolkit.ahk, 双击运行(或放启动项)
^!v::Run "E:\Projects\voice_toolkit\venv\Scripts\pythonw.exe" "E:\Projects\voice_toolkit\windows\run_hotkey.py"
```

> 校验快捷键通不通: 按一下应有短"滴"声(开始录音)且**无任何窗口闪现**;
> 那就是整条链路正常工作的直接证据, 不需要额外的弹窗测试。

## 使用

- 按一次快捷键 → **滴**(一声短音) → 开始录音, 托盘图标变**红**;
- 再按一次 → 停止并转录 → 完成后 **叮-叮**(两声音高), 文本已落在光标处; 托盘图标回灰。
- 转录中再按 → daemon 忽略并弹提示。
- 长按不放可能导致快捷键重复触发, 请用单击。

蜂鸣含义: 一声短 = 命令收到; 双高音 = 上屏成功; 三声低音 = 出错(看日志)。

排查注入/链路问题(前台跑, 看控制台输出):
```
venv\Scripts\python windows\run_hotkey.py --dry-run
```
`--dry-run` 只走 toggle 链路不注入不上屏, 便于区分"转录没结果"还是"注入失败"。

## 状态与日志

- daemon 是 Qt 托盘进程(**live/main_daemon.py**), 首次按快捷键时由 run_hotkey 自动拉起,
  之后常驻。托盘右键菜单可退出。
- 日志: `%LOCALAPPDATA%\voice_toolkit\live_transcriber.log`(daemon/toggle 都写这里)。
  级别在项目根 `log.py` 调整。

## 常见问题

- **按快捷键没声音也不响** → 检查 PowerToys 里 pythonw/脚本路径是否正确;
  手动在终端跑一次 `python windows\run_hotkey.py --dry-run` 看报错。
- **三声低音(失败)** → 手动前台跑 `--dry-run`; 看日志尾部; 多半是: venv 缺依赖、
  模型路径不对(`models.qwen3_asr.dir`)、`QWEN_BACKEND_DIR` 没设或没重开终端。
- **转录成功但没上屏(双高音后无字)** → 目标窗口可能是**管理员权限**窗口(SendInput 需要
  同权限); 或焦点在别处。先手动点一下目标输入框再按快捷键。
- **daemon 起不来 / 托盘没图标** → `live/main_daemon.py` 的 stderr 在首次启动时被 toggle
  捕获; 手动 `venv\Scripts\python live\main_daemon.py` 前台跑一次看报错。
- **录音没声音** → sounddevice 默认输入设备不是你想要的麦, 在 Windows 声音设置里把
  默认输入设备设对。
- **想用剪贴板+Ctrl+V 方案** → 本项目用 SendInput, 不需要; 若个别应用收不到 Unicode
  注入(游戏/特殊控件), 再考虑把文本塞剪贴板手动粘贴, 不冲突。
