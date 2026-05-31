package com.voicediary

import android.content.Context
import android.content.SharedPreferences

object SettingsManager {
    private const val PREFS = "voice_diary_settings"

    fun getPort(ctx: Context): Int = prefs(ctx).getInt("port", 8765)
    fun setPort(ctx: Context, v: Int) = prefs(ctx).edit().putInt("port", v).apply()

    fun getSampleRate(ctx: Context): Int = prefs(ctx).getInt("sample_rate", 16000)
    fun setSampleRate(ctx: Context, v: Int) = prefs(ctx).edit().putInt("sample_rate", v).apply()

    fun getBufferSize(ctx: Context): Int = prefs(ctx).getInt("buffer_size", 4096)
    fun setBufferSize(ctx: Context, v: Int) = prefs(ctx).edit().putInt("buffer_size", v).apply()

    fun getSegmentMs(ctx: Context): Long = prefs(ctx).getLong("segment_ms", 600_000L)
    fun setSegmentMs(ctx: Context, v: Long) = prefs(ctx).edit().putLong("segment_ms", v).apply()

    fun getBootStart(ctx: Context): Boolean = prefs(ctx).getBoolean("boot_start", true)
    fun setBootStart(ctx: Context, v: Boolean) = prefs(ctx).edit().putBoolean("boot_start", v).apply()

    fun getStorageLimitGb(ctx: Context): Int = prefs(ctx).getInt("storage_limit_gb", 40)
    fun setStorageLimitGb(ctx: Context, v: Int) = prefs(ctx).edit().putInt("storage_limit_gb", v).apply()

    private fun prefs(ctx: Context): SharedPreferences =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
