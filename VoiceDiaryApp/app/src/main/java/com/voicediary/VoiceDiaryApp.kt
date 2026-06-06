package com.voicediary

import android.app.Application

class VoiceDiaryApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // 必须在任何网络操作之前设置，强制整个应用使用 IPv4
        System.setProperty("java.net.preferIPv4Stack", "true")
        System.setProperty("java.net.preferIPv6Addresses", "false")
    }
}