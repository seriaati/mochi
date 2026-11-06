package moe.seria.mochi

import android.app.Activity
import android.content.Context
import android.net.Uri
import android.webkit.CookieManager
import android.webkit.WebStorage
import android.webkit.WebView
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

object Server {
    private const val PREFS = "mochi"
    private const val SERVER = "server"

    fun url(context: Context): String? = prefs(context).getString(SERVER, null)

    fun remember(context: Context, url: String) = prefs(context).edit().putString(SERVER, url).apply()

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun normalize(typed: String): String? {
        val text = typed.trim().let { if ("://" in it) it else "https://$it" }
        val uri = Uri.parse(text)
        val scheme = uri.scheme?.lowercase()
        val authority = uri.encodedAuthority?.substringAfterLast('@')?.lowercase()
        if (scheme !in listOf("https", "http") || uri.host.isNullOrEmpty() || authority.isNullOrEmpty()) return null
        return "$scheme://$authority"
    }

    // The address may serve the web app itself, or only the API, whose /api/health then names the
    // web app hosted apart from it. Blocks: call from a background thread.
    fun find(url: String): String? {
        if (isWebApp(url)) return url
        val web = json("$url/api/health")?.takeIf { it.optString("app") == "mochi" }?.optString("web") ?: return null
        return normalize(web)?.takeIf { it.startsWith("https://") && isWebApp(it) }
    }

    private fun isWebApp(url: String) = json("$url/manifest.webmanifest")?.optString("name") == "Mochi"

    private fun json(url: String): JSONObject? = try {
        val connection = URL(url).openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 8000
            connection.readTimeout = 8000
            if (connection.responseCode == 200) JSONObject(connection.inputStream.use { String(it.readBytes()) }) else null
        } finally {
            connection.disconnect()
        }
    } catch (error: IOException) {
        null
    } catch (error: JSONException) {
        null
    }

    // Everything that belonged to this server goes: its push token, notifications, login and storage.
    fun leave(activity: Activity, done: () -> Unit) {
        thread {
            Push.stop(activity)
            Notifications.forget(activity)
            prefs(activity).edit().remove(SERVER).apply()
            activity.runOnUiThread {
                CookieManager.getInstance().removeAllCookies(null)
                CookieManager.getInstance().flush()
                WebStorage.getInstance().deleteAllData()
                WebView(activity).run {
                    clearCache(true) // shared by all of the app's WebViews
                    destroy()
                }
                done()
            }
        }
    }
}
