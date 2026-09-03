# ============================================================
#  run.ps1 — voice_toolkit Windows 实时模式入口(对标 Linux 的 run.sh)
#
#  把本脚本绑定到全局快捷键: 按一下 = 开始录音; 再按一下 = 停止并转录;
#  转录文本用 SendInput(KEYEVENTF_UNICODE) 直接注入当前光标处, 不碰剪贴板。
#
#  命令行示例(快捷键工具里配置):
#    powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File run.ps1
#    (Windows Terminal / pwsh 7:  pwsh -NoProfile -File run.ps1)
#
#  可选参数:
#    -Python <exe>   显式指定 python 解释器(默认自动探测 venv → PATH)
#    -Silent         关闭提示音
#    -DryRun         不注入光标, 只把转录文本打印到 stdout(调试用)
#
#  依赖:
#    Python 3.12 + venv(内含 PyQt6 等依赖, 见 windows/README.md)
#    后端进程 live/main_daemon.py 的 Qt 托盘图标指示状态(灰=待机/红=录音/绿=转录)
# ============================================================
param(
    [string]$Python,
    [switch]$Silent,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── 提示音(快捷键场景无窗口, 用蜂鸣做反馈) ──────────────────
function Beep-Tone {
    param([int]$Freq, [int]$Ms)
    if (-not $Silent) { [console]::beep($Freq, $Ms) }
}
function Beep-Received  { Beep-Tone 650 90 }                    # 命令已收到(开始录音/忽略)
function Beep-Success   { Beep-Tone 950 70; Start-Sleep -Milliseconds 60; Beep-Tone 1400 140 }  # 已上屏
function Beep-Failed    { Beep-Tone 300 130; Start-Sleep -Milliseconds 90; Beep-Tone 220 160; Start-Sleep -Milliseconds 90; Beep-Tone 180 260 }  # 出错

# ── 定位 Python ─────────────────────────────────────────────
function Find-PythonExe {
    # 1. 显式参数
    if ($Python -and (Test-Path -LiteralPath $Python)) { return (Resolve-Path -LiteralPath $Python).Path }
    # 2. 项目 venv
    foreach ($cand in @("$Root\venv\Scripts\python.exe", "$Root\.venv\Scripts\python.exe")) {
        if (Test-Path -LiteralPath $cand) { return (Resolve-Path -LiteralPath $cand).Path }
    }
    # 3. PATH 里的 python
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # 4. py 启动器(取 -3 实际解释器路径)
    $pyc = Get-Command py -ErrorAction SilentlyContinue
    if ($pyc) {
        $prev = $env:PYTHONIOENCODING; $env:PYTHONIOENCODING = "utf-8"
        try {
            $out = & $pyc.Source -3 -c "import sys; print(sys.executable)" 2>$null
        } finally { $env:PYTHONIOENCODING = $prev }
        if ($out) { return ($out | Select-Object -Last 1).Trim() }
    }
    return $null
}

# ── 执行 python 并捕获 stdout/stderr(无控制台窗口) ──────────
function Invoke-PythonCapture {
    param([string]$PyExe, [string]$ScriptPath, [string]$WorkDir)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $PyExe
    $psi.Arguments = '"' + $ScriptPath + '"'
    $psi.WorkingDirectory = $WorkDir
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    try {
        $p = [System.Diagnostics.Process]::Start($psi)
    } catch {
        return @{ Out = ""; Err = "启动 python 失败: $_"; Code = -1 }
    }
    $out = $p.StandardOutput.ReadToEnd()
    $err = $p.StandardError.ReadToEnd()
    $p.WaitForExit()
    return @{ Out = $out; Err = $err; Code = $p.ExitCode }
}

# ── SendInput 注入(仅在确有文本要上屏时才编译, 平时零开销) ──
function Add-SendInputType {
    $src = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class WinSendInput {
    [StructLayout(LayoutKind.Sequential)]
    public struct INPUT {
        public uint type;
        public InputUnion U;
    }
    [StructLayout(LayoutKind.Explicit)]
    public struct InputUnion {
        [FieldOffset(0)] public KEYBDINPUT ki;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct KEYBDINPUT {
        public ushort wVk;
        public ushort wScan;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }
    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    private const uint INPUT_KEYBOARD = 1;
    private const uint KEYEVENTF_UNICODE = 0x0004;
    private const uint KEYEVENTF_KEYUP = 0x0002;
    private const ushort VK_RETURN = 0x0D;

    private static INPUT KeyUnicode(char ch, bool keyUp) {
        INPUT i = new INPUT();
        i.type = INPUT_KEYBOARD;
        i.U.ki.wVk = 0;
        i.U.ki.wScan = (ushort)ch;                 // KEYEVENTF_UNICODE: wScan 即字符码
        i.U.ki.dwFlags = KEYEVENTF_UNICODE | (keyUp ? KEYEVENTF_KEYUP : 0);
        return i;
    }
    private static INPUT KeyVk(ushort vk, bool keyUp) {
        INPUT i = new INPUT();
        i.type = INPUT_KEYBOARD;
        i.U.ki.wVk = vk;
        i.U.ki.wScan = 0;
        i.U.ki.dwFlags = (keyUp ? KEYEVENTF_KEYUP : 0);
        return i;
    }

    /// 把文本逐字符注入当前键盘焦点。普通字符走 Unicode(绕过输入法, 中文直接上屏);
    /// 换行统一转成回车键(与真实键盘一致, 应用兼容性最好)。成功返回 true。
    public static bool TypeText(string text) {
        string t = text.Replace("\r\n", "\n").Replace('\r', '\n');
        List<INPUT> list = new List<INPUT>();
        foreach (char c in t) {
            if (c == '\n') {
                list.Add(KeyVk(VK_RETURN, false));
                list.Add(KeyVk(VK_RETURN, true));
            } else {
                list.Add(KeyUnicode(c, false));
                list.Add(KeyUnicode(c, true));
            }
        }
        INPUT[] all = list.ToArray();
        const int BATCH = 500;   // SendInput 单次上限较大, 分批发送更稳
        int size = Marshal.SizeOf(typeof(INPUT));
        for (int off = 0; off < all.Length; off += BATCH) {
            int n = Math.Min(BATCH, all.Length - off);
            INPUT[] seg = new INPUT[n];
            Array.Copy(all, off, seg, 0, n);
            if (SendInput((uint)n, seg, size) != n) return false;
        }
        return true;
    }
}
'@
    Add-Type -TypeDefinition $src
}

# ═══════════════════════ 主流程 ══════════════════════════════
$pyExe = Find-PythonExe
if (-not $pyExe -or -not (Test-Path -LiteralPath $pyExe)) {
    Write-Error "未找到 Python。请安装 Python 3.12 或创建 venv, 或用 -Python 显式指定。"
    Beep-Failed
    exit 1
}

# toggle.py: 探测/拉起 daemon → 发 toggle 命令 → 根据 daemon 状态
#   (idle=开始录音, 立即返回空; recording=等待转录结果并打印文本)
$result = Invoke-PythonCapture -PyExe $pyExe -ScriptPath "$Root\live\toggle.py" -WorkDir $Root
$code = [int]$result.Code
$text = $result.Out

if ($code -ne 0) {
    $err = $result.Err
    if ($err) { Write-Host "toggle 失败: $err" }
    Beep-Failed
    exit $code
}

if ([string]::IsNullOrEmpty($text)) {
    # 开始录音 / 转录中忽略 / 转录结果为空 → 只给一声反馈(托盘图标才是状态主力)
    Beep-Received
    exit 0
}

# 转录完成, 有文本 → 注入光标
if ($DryRun) {
    Write-Output $text
    exit 0
}

try {
    Add-SendInputType
    $ok = [WinSendInput]::TypeText($text)
} catch {
    $ok = $false
    Write-Host "注入失败: $_"
}
if ($ok) { Beep-Success } else { Beep-Failed }
exit 0
