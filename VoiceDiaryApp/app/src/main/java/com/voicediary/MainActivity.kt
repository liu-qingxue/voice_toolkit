package com.voicediary

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.voicediary.RecordingService.Companion.isRunning

class MainActivity : AppCompatActivity() {

    private lateinit var btnToggle: Button
    private lateinit var tvStatus: TextView
    private lateinit var tvPort: TextView

    private lateinit var swBootStart: Switch
    private lateinit var etPort: EditText
    private lateinit var etSampleRate: EditText
    private lateinit var etBufferSize: EditText
    private lateinit var etSegmentSec: EditText
    private lateinit var etStorageLimitGb: EditText
    private lateinit var btnSave: Button

    private lateinit var pbStorage: ProgressBar
    private lateinit var tvStorage: TextView

    private val requestPermissions = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { granted ->
        if (granted.values.all { it }) {
            toggleService()
        } else {
            tvStatus.text = "权限被拒绝，无法录音"
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        btnToggle = findViewById(R.id.btnToggle)
        tvStatus = findViewById(R.id.tvStatus)
        tvPort = findViewById(R.id.tvPort)

        swBootStart = findViewById(R.id.swBootStart)
        etPort = findViewById(R.id.etPort)
        etSampleRate = findViewById(R.id.etSampleRate)
        etBufferSize = findViewById(R.id.etBufferSize)
        etSegmentSec = findViewById(R.id.etSegmentSec)
        etStorageLimitGb = findViewById(R.id.etStorageLimitGb)
        btnSave = findViewById(R.id.btnSave)

        pbStorage = findViewById(R.id.pbStorage)
        tvStorage = findViewById(R.id.tvStorage)

        loadSettings()

        btnToggle.setOnClickListener { checkPermissionsAndToggle() }
        btnSave.setOnClickListener { onSave() }

        if (!HttpServer.isRunning) {
            HttpServer.start(this)
        }
        updatePortDisplay()
        updateUI()
        updateStorageDisplay()
    }

    override fun onResume() {
        super.onResume()
        updateUI()
        updateStorageDisplay()
    }

    private fun loadSettings() {
        swBootStart.isChecked = SettingsManager.getBootStart(this)
        etPort.setText(SettingsManager.getPort(this).toString())
        etSampleRate.setText(SettingsManager.getSampleRate(this).toString())
        etBufferSize.setText(SettingsManager.getBufferSize(this).toString())
        etSegmentSec.setText((SettingsManager.getSegmentMs(this) / 1000).toString())
        etStorageLimitGb.setText(SettingsManager.getStorageLimitGb(this).toString())
    }

    private fun onSave() {
        val port = etPort.text.toString().toIntOrNull()
        val sr = etSampleRate.text.toString().toIntOrNull()
        val buf = etBufferSize.text.toString().toIntOrNull()
        val segSec = etSegmentSec.text.toString().toIntOrNull()
        val limitGb = etStorageLimitGb.text.toString().toIntOrNull()

        if (port == null || port !in 1024..65535) {
            etPort.error = "端口范围 1024-65535"
            return
        }
        if (sr == null || sr !in 8000..48000) {
            etSampleRate.error = "采样率 8000-48000"
            return
        }
        if (buf == null || buf < 256) {
            etBufferSize.error = "缓冲区至少 256"
            return
        }
        if (segSec == null || segSec < 10) {
            etSegmentSec.error = "分段时长至少 10 秒"
            return
        }
        if (limitGb == null || limitGb < 1) {
            etStorageLimitGb.error = "容量上限至少 1 GB"
            return
        }

        val oldPort = SettingsManager.getPort(this)
        SettingsManager.setPort(this, port)
        SettingsManager.setSampleRate(this, sr)
        SettingsManager.setBufferSize(this, buf)
        SettingsManager.setSegmentMs(this, segSec * 1000L)
        SettingsManager.setBootStart(this, swBootStart.isChecked)
        SettingsManager.setStorageLimitGb(this, limitGb)

        if (port != oldPort) {
            HttpServer.restart(this)
        }

        updatePortDisplay()
        updateStorageDisplay()
        Toast.makeText(this, "保存成功", Toast.LENGTH_SHORT).show()
    }

    private fun updatePortDisplay() {
        val p = SettingsManager.getPort(this)
        tvPort.text = "HTTP :$p"
    }

    private fun updateStorageDisplay() {
        StorageUtils.getRecordedSizeAsync(this) { bytes ->
            val limitGb = SettingsManager.getStorageLimitGb(this)
            val pct = StorageUtils.percent(bytes, limitGb)
            pbStorage.progress = pct
            tvStorage.text = StorageUtils.formatSize(bytes, limitGb)

            if (StorageUtils.isOverLimit(bytes, limitGb)) {
                tvStorage.setTextColor(Color.RED)
                AlertDialog.Builder(this)
                    .setTitle("存储空间超限")
                    .setMessage("录音文件已超过 %d GB，建议清理旧文件或增大容量上限".format(limitGb))
                    .setPositiveButton("知道了", null)
                    .show()
            } else {
                tvStorage.setTextColor(Color.parseColor("#666666"))
            }
        }
    }

    private fun checkPermissionsAndToggle() {
        val needed = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            needed.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val missing = needed.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) {
            toggleService()
        } else {
            requestPermissions.launch(missing.toTypedArray())
        }
    }

    private fun toggleService() {
        val intent = android.content.Intent(this, RecordingService::class.java)
        if (isRunning) {
            intent.action = RecordingService.ACTION_STOP
            startService(intent)
        } else {
            intent.action = RecordingService.ACTION_START
            ContextCompat.startForegroundService(this, intent)
        }
        updateUI()
    }

    fun updateUI() {
        if (isRunning) {
            btnToggle.text = "⏹ 停止录音"
            tvStatus.text = "录音中..."
        } else {
            btnToggle.text = "⏺ 开始录音"
            tvStatus.text = "已停止"
        }
    }

    companion object {
        var instance: MainActivity? = null
    }
}
