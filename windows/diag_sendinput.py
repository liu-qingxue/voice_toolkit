"""SendInput 失败诊断: 打印结构体大小 + GetLastError 错误码"""
import ctypes
from ctypes import wintypes

INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


class _UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


print("sizeof KEYBDINPUT =", ctypes.sizeof(KEYBDINPUT))
print("sizeof MOUSEINPUT =", ctypes.sizeof(MOUSEINPUT))
print("sizeof INPUT      =", ctypes.sizeof(INPUT))

user32 = ctypes.WinDLL("user32", use_last_error=True)   # use_last_error → 可查 GetLastError
send = user32.SendInput
send.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
send.restype = wintypes.UINT


def one(ch: str, up: bool) -> INPUT:
    i = INPUT()
    i.type = INPUT_KEYBOARD
    i.ki.wVk = 0
    i.ki.wScan = ord(ch)
    i.ki.dwFlags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return i


arr = (INPUT * 2)()
arr[0] = one("A", False)
arr[1] = one("A", True)

ctypes.set_last_error(0)
n = send(2, arr, ctypes.sizeof(INPUT))
err = ctypes.get_last_error()
print("SendInput 返回:", n, " GetLastError:", err, hex(err))
if n == 2:
    print("[PASS] SendInput 调用成功(返回 2/2)")
else:
    known = {5: "ERROR_ACCESS_DENIED(UIPI)", 87: "ERROR_INVALID_PARAMETER(cbSize/结构)"}
    print("[FAIL] 含义:", known.get(err, "未知, 见 MSDN system-error-codes"))
