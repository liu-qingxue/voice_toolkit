#!/usr/bin/env bash
# 自动连接指定前缀的 Wi-Fi 热点，并发送桌面通知

PREFIX="voice_diary"
NOTIFY_ICON="network-wireless"

# 获取当前活动 WiFi 连接的 SSID（连接名）
current_ssid=$(nmcli -t connection show --active | grep ':wifi$' | cut -d: -f1)
if [[ "$current_ssid" == "$PREFIX"* ]]; then
    notify-send -i "$NOTIFY_ICON" "Wi-Fi 状态" "已连接到目标热点 ($current_ssid)"
    exit 0
fi

# 2. 扫描并尝试连接到前缀匹配的热点
target_ssid=$(nmcli -t -f SSID dev wifi list | grep -E "^$PREFIX" | head -1)
if [[ -z "$target_ssid" ]]; then
    notify-send -i "error" "Wi-Fi 状态" "未找到前缀为 $PREFIX 的热点。\n请检查手机热点是否开启。"
    exit 1
fi

# 3. 尝试连接（密码已保存过，不需提供）
if nmcli device wifi connect "$target_ssid" &>/dev/null; then
    # 4. 等待网络稳定：循环检测直到 SSID 匹配或超时（最多 5 秒）
    for _ in {1..50}; do
        sleep 0.1
        current_ssid=$(iwgetid -r)
        if [[ "$current_ssid" == "$PREFIX"* ]]; then
            notify-send -i "$NOTIFY_ICON" "Wi-Fi 状态" "已成功连接 $target_ssid\n日志系统前置条件满足。"
            exit 0
        fi
    done
    # 超时未稳定
    notify-send -i "error" "Wi-Fi 状态" "连接 $target_ssid 成功但网络未稳定，请稍后手动检查。"
    exit 1
else
    notify-send -i "error" "Wi-Fi 状态" "连接 $target_ssid 失败，请检查密码或信号。"
    exit 1
fi