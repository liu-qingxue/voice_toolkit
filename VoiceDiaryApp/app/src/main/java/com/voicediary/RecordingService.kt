package com.voicediary

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class RecordingService : Service() {

    private var isRecording = false
    private var audioRecord: AudioRecord? = null
    private var thread: Thread? = null

    private var sampleRate = 16000
    private var segmentMs = 600_000L
    private var bufferSize = 4096

    companion object {
        const val NOTIFY_ID = 1
        const val CHANNEL_ID = "voice_diary_recording"
        const val ACTION_START = "com.voicediary.START"
        const val ACTION_STOP = "com.voicediary.STOP"
        @Volatile
        var isRunning = false
            private set
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startRecording()
            ACTION_STOP -> stopRecording()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopRecording()
        super.onDestroy()
    }

    private fun startRecording() {
        if (isRecording) return
        isRecording = true
        isRunning = true

        sampleRate = SettingsManager.getSampleRate(this)
        segmentMs = SettingsManager.getSegmentMs(this)
        bufferSize = SettingsManager.getBufferSize(this)

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("语音日记")
            .setContentText("正在录音...")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .setSilent(true)
            .build()

        startForeground(NOTIFY_ID, notification)
        MainActivity.instance?.updateUI()

        val minBuf = AudioRecord.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            minBuf * 4
        )

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            stopRecording()
            return
        }

        val buf = ByteArray(bufferSize)
        audioRecord?.startRecording()

        val sr = sampleRate
        val seg = segmentMs

        thread = Thread {
            val dataDir = File(filesDir, "raw")
            var segBuf = java.io.ByteArrayOutputStream()
            var segStart = System.currentTimeMillis()

            while (isRecording) {
                val read = audioRecord?.read(buf, 0, bufferSize) ?: -1
                if (read <= 0) continue

                segBuf.write(buf, 0, read)

                if (System.currentTimeMillis() - segStart >= seg) {
                    flushSegment(segBuf, segStart, dataDir, sr)
                    segBuf = java.io.ByteArrayOutputStream()
                    segStart = System.currentTimeMillis()
                }
            }

            flushSegment(segBuf, segStart, dataDir, sr)
            cleanup()
        }
        thread?.start()

        HttpServer.recorderDir = filesDir
    }

    private fun flushSegment(buf: java.io.ByteArrayOutputStream, startTime: Long, dataDir: File, sr: Int) {
        val pcm = buf.toByteArray()
        if (pcm.isEmpty()) return

        val sdf = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault())
        val stf = SimpleDateFormat("HH_mm_ss", Locale.getDefault())
        val dateStr = sdf.format(Date(startTime))
        val timeStr = stf.format(Date(startTime))

        val dir = File(dataDir, dateStr)
        dir.mkdirs()
        val file = File(dir, "$timeStr.wav")

        writeWav(file, pcm, sr)
    }

    private fun writeWav(file: File, pcm: ByteArray, sr: Int) {
        val dataSize = pcm.size
        val total = 44 + dataSize

        val header = ByteArray(44).apply {
            this[0] = 'R'.code.toByte(); this[1] = 'I'.code.toByte()
            this[2] = 'F'.code.toByte(); this[3] = 'F'.code.toByte()
            writeLE32(this, 4, total - 8)
            this[8] = 'W'.code.toByte(); this[9] = 'A'.code.toByte()
            this[10] = 'V'.code.toByte(); this[11] = 'E'.code.toByte()
            this[12] = 'f'.code.toByte(); this[13] = 'm'.code.toByte()
            this[14] = 't'.code.toByte(); this[15] = ' '.code.toByte()
            writeLE32(this, 16, 16)
            writeLE16(this, 20, 1)
            writeLE16(this, 22, 1)
            writeLE32(this, 24, sr)
            writeLE32(this, 28, sr * 2)
            writeLE16(this, 32, 2)
            writeLE16(this, 34, 16)
            this[36] = 'd'.code.toByte(); this[37] = 'a'.code.toByte()
            this[38] = 't'.code.toByte(); this[39] = 'a'.code.toByte()
            writeLE32(this, 40, dataSize)
        }

        FileOutputStream(file).use { fos ->
            fos.write(header)
            fos.write(pcm)
        }
    }

    private fun writeLE16(arr: ByteArray, off: Int, v: Int) {
        arr[off] = (v and 0xFF).toByte()
        arr[off + 1] = ((v shr 8) and 0xFF).toByte()
    }

    private fun writeLE32(arr: ByteArray, off: Int, v: Int) {
        arr[off] = (v and 0xFF).toByte()
        arr[off + 1] = ((v shr 8) and 0xFF).toByte()
        arr[off + 2] = ((v shr 16) and 0xFF).toByte()
        arr[off + 3] = ((v shr 24) and 0xFF).toByte()
    }

    private fun stopRecording() {
        isRecording = false
        isRunning = false
        thread?.join(3000)
        thread = null
        cleanup()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
        MainActivity.instance?.updateUI()
    }

    private fun cleanup() {
        try {
            audioRecord?.stop()
        } catch (_: Exception) {}
        try {
            audioRecord?.release()
        } catch (_: Exception) {}
        audioRecord = null
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(
                CHANNEL_ID, "录音状态", NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "语音日记正在后台录音"
                setSound(null, null)
            }
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(ch)
        }
    }
}
