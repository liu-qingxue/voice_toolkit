package com.voicediary

import android.content.Context
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

class HttpServer(port: Int) : NanoHTTPD(port) {

    companion object {
        @Volatile
        var isRunning = false
            private set
        var recorderDir: File? = null
        private var serverInstance: HttpServer? = null

        fun start(ctx: Context) {
            if (isRunning) return
            val port = SettingsManager.getPort(ctx)
            val server = HttpServer(port)
            server.start()
            serverInstance = server
            isRunning = true
        }

        fun stop() {
            serverInstance?.stop()
            serverInstance = null
            isRunning = false
        }

        fun restart(ctx: Context) {
            stop()
            start(ctx)
        }
    }

    override fun serve(session: IHTTPSession): Response {
        val uri = session.uri.trim('/')
        val parts = uri.split("/")

        return try {
            when {
                uri == "status" -> handleStatus()
                parts[0] == "download" && parts.size >= 3 -> handleDownload(parts[1], parts[2])
                uri == "confirm" && session.method == Method.POST -> handleConfirm(session)
                else -> newFixedLengthResponse(Response.Status.NOT_FOUND, "text/plain", "not found")
            }
        } catch (e: Exception) {
            newFixedLengthResponse(
                Response.Status.INTERNAL_ERROR, "application/json",
                """{"error":"${e.message}"}"""
            )
        }
    }

    private fun handleStatus(): Response {
        val files = JSONArray()
        val base = recorderDir?.let { File(it, "raw") } ?: return jsonResponse("""{"files":[],"current_writing":null,"timezone":"+08:00"}""")

        if (base.exists()) {
            val dates = base.listFiles()?.sortedByDescending { it.name }?.take(7) ?: emptyList()
            for (dateDir in dates) {
                dateDir.listFiles()
                    ?.filter { it.name.endsWith(".wav") }
                    ?.sortedBy { it.name }
                    ?.forEach { files.put("${dateDir.name}/${it.name}") }
            }
        }

        val obj = JSONObject().apply {
            put("files", files)
            put("current_writing", JSONObject.NULL)
            put("timezone", "+08:00")
        }
        return jsonResponse(obj.toString())
    }

    private fun handleDownload(date: String, filename: String): Response {
        val file = recorderDir?.let { File(File(it, "raw"), "$date/$filename") }
            ?: return newFixedLengthResponse(Response.Status.NOT_FOUND, "text/plain", "no data dir")

        if (!file.exists()) {
            return newFixedLengthResponse(Response.Status.NOT_FOUND, "text/plain", "file not found")
        }

        val data = file.readBytes()
        val md5 = MessageDigest.getInstance("MD5").digest(data).joinToString("") {
            "%02x".format(it)
        }

        val response = newFixedLengthResponse(
            Response.Status.OK, "audio/wav", data.inputStream(), data.size.toLong()
        )
        response.addHeader("Content-MD5", md5)
        return response
    }

    private fun handleConfirm(session: IHTTPSession): Response {
        val text = try {
            session.inputStream.bufferedReader().readText()
        } catch (_: Exception) {
            "{}"
        }

        val req = JSONObject(text)
        val date = req.optString("date", "")
        val files = req.optJSONArray("files") ?: JSONArray()
        val baseDir = recorderDir?.let { File(it, "raw") } ?: return jsonResponse("""{"ok":false,"deleted":0}""")

        var deleted = 0
        for (i in 0 until files.length()) {
            val f = File(baseDir, "$date/${files.getString(i)}")
            if (f.exists() && f.delete()) deleted++
        }

        return jsonResponse("""{"ok":true,"deleted":$deleted}""")
    }

    private fun jsonResponse(json: String): Response {
        return newFixedLengthResponse(Response.Status.OK, "application/json", json)
    }
}
