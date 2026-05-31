package com.voicediary

import android.content.Context
import android.os.Handler
import android.os.Looper
import java.io.File

object StorageUtils {

    fun getRecordedSizeAsync(ctx: Context, onResult: (Long) -> Unit) {
        Thread {
            val dir = File(ctx.filesDir, "raw")
            val bytes = if (!dir.exists()) 0L
            else dir.walkTopDown().filter { it.isFile }.sumOf { it.length() }
            Handler(Looper.getMainLooper()).post { onResult(bytes) }
        }.start()
    }

    fun formatSize(bytes: Long, limitGb: Int): String {
        val gb = bytes / 1_000_000_000.0
        return "已用 %.1f GB / %d GB".format(gb, limitGb)
    }

    fun percent(bytes: Long, limitGb: Int): Int {
        val l = limitGb * 1_000_000_000L
        if (l <= 0) return 0
        return ((bytes.toDouble() / l) * 100).toInt().coerceIn(0, 100)
    }

    fun isOverLimit(bytes: Long, limitGb: Int): Boolean {
        return bytes > limitGb * 1_000_000_000L
    }
}
