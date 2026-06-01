#!/usr/bin/env bash
# 自动连接指定前缀的 Wi-Fi 热点，并发送桌面通知

PREFIX="voice_diary"          # 热点前缀，可修改或从配置文件读取
NOTIFY_ICON="network-wireless" # 通知图标，可选

# 获取当前连接的 SSID
current_ssid=$(nmcli -t -f ACTIVE,SSID dev wifi list | grep '^yes:' | cut -d: -f2)
if [[ "$current_ssid" == "$PREFIX"* ]]; then
    notify-send -i "$NOTIFY_ICON" "Wi-Fi 状态" "已连接到目标热点 ($current_ssid)\n日志系统已就绪。"
    exit 0
fi

# 扫描并尝试连接到前缀匹配的热点
target_ssid=$(nmcli -t -f SSID dev wifi list | grep -E "^$PREFIX" | head -1)
if [[ -z "$target_ssid" ]]; then
    notify-send -i "error" "Wi-Fi 状态" "未找到前缀为 $PREFIX 的热点。\n请检查手机热点是否开启。"
    exit 1
fi

# 尝试连接（密码已保存过，不需提供）
if nmcli device wifi connect "$target_ssid" &>/dev/null; then
    notify-send -i "$NOTIFY_ICON" "Wi-Fi 状态" "已成功连接 $target_ssid\n日志系统前置条件满足。"
else
    notify-send -i "error" "Wi-Fi 状态" "连接 $target_ssid 失败，请检查密码或信号。"
    exit 1
fi