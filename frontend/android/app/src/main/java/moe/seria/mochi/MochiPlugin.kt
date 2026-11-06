package moe.seria.mochi

import android.Manifest
import android.app.UiModeManager
import android.content.Intent
import android.content.res.Configuration
import android.graphics.Color
import android.os.Build
import androidx.core.app.NotificationManagerCompat
import androidx.core.view.WindowCompat
import com.getcapacitor.BridgeActivity
import com.getcapacitor.JSObject
import com.getcapacitor.PermissionState
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.getcapacitor.annotation.Permission
import com.getcapacitor.annotation.PermissionCallback
import org.json.JSONObject
import kotlin.concurrent.thread

private const val NOTIFICATIONS = "notifications"

@CapacitorPlugin(
    name = "Mochi",
    permissions = [Permission(alias = NOTIFICATIONS, strings = [Manifest.permission.POST_NOTIFICATIONS])],
)
class MochiPlugin : Plugin() {
    companion object {
        const val PATH = "moe.seria.mochi.path"

        // Static so a tapped notification's page survives the server screen and the login.
        private var pending: String? = null

        fun open(activity: BridgeActivity, path: String) {
            synchronized(MochiPlugin) { pending = path }
            (activity.bridge?.getPlugin("Mochi")?.instance as? MochiPlugin)?.opened()
        }
    }

    private var bars: Pair<Int, Boolean>? = null

    private fun opened() = notifyListeners("path", null)

    @PluginMethod
    fun takePath(call: PluginCall) {
        val path = synchronized(MochiPlugin) { pending.also { pending = null } }
        call.resolve(if (path != null) JSObject().put("path", path) else JSObject())
    }

    @PluginMethod
    fun pushState(call: PluginCall) {
        val token = Push.token(context)
        val state = JSObject()
            .put("enabled", token != null)
            .put("allowed", NotificationManagerCompat.from(context).areNotificationsEnabled())
        if (token != null) {
            state.put("token", token)
            Push.settings(context)?.let { state.put("firebase", it) }
        }
        call.resolve(state)
    }

    @PluginMethod
    fun enablePush(call: PluginCall) {
        if (Build.VERSION.SDK_INT >= 33 && getPermissionState(NOTIFICATIONS) != PermissionState.GRANTED) {
            requestPermissionForAlias(NOTIFICATIONS, call, "notificationsAnswered")
        } else {
            enable(call)
        }
    }

    @PermissionCallback
    private fun notificationsAnswered(call: PluginCall) {
        if (getPermissionState(NOTIFICATIONS) == PermissionState.GRANTED) enable(call) else denied(call)
    }

    // Android stops asking after the second no, so from then on only its settings can allow them.
    private fun denied(call: PluginCall) =
        call.reject("Notifications are off for Mochi in Android’s settings. Allow them there, then turn this on.")

    private fun enable(call: PluginCall) {
        if (!NotificationManagerCompat.from(context).areNotificationsEnabled()) return denied(call)
        val settings = JSONObject()
        for (key in listOf("project_id", "app_id", "api_key", "sender_id")) settings.put(key, call.getString(key))
        val options = Push.options(settings) ?: return call.reject("Firebase settings need project_id, app_id, api_key and sender_id.")
        // The permission callback runs on the main thread, and getting a token blocks.
        thread {
            try {
                call.resolve(JSObject().put("token", Push.enable(context, settings, options)))
            } catch (error: Exception) {
                Push.stop(context)
                call.reject("Firebase gave no token: ${error.message}")
            }
        }
    }

    @PluginMethod
    fun disablePush(call: PluginCall) {
        val token = Push.token(context)
        Push.stop(context)
        call.resolve(if (token != null) JSObject().put("token", token) else JSObject())
    }

    @PluginMethod
    fun changeServer(call: PluginCall) {
        val activity = activity
        Server.leave(activity) {
            call.resolve()
            activity.startActivity(Intent(activity, ServerActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        }
    }

    @PluginMethod
    fun setSystemBars(call: PluginCall) {
        val color = try {
            Color.parseColor(call.getString("color"))
        } catch (error: IllegalArgumentException) {
            return call.reject("Not a color: ${call.getString("color")}")
        }
        bars = color to (call.getBoolean("dark") ?: false)
        val night = when (call.getString("mode")) {
            "system" -> UiModeManager.MODE_NIGHT_AUTO
            "light" -> UiModeManager.MODE_NIGHT_NO
            "dark" -> UiModeManager.MODE_NIGHT_YES
            else -> null
        }
        activity.runOnUiThread {
            applyBars()
            // So the splash screen at the next start follows the theme picked in the web app. The
            // activity isn't recreated by it: its configChanges has uiMode.
            if (night != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                context.getSystemService(UiModeManager::class.java).setApplicationNightMode(night)
            }
            call.resolve()
        }
    }

    // Capacitor's SystemBars resets the bars on a configuration change (rotation, dark mode).
    override fun handleOnConfigurationChanged(newConfig: Configuration) {
        super.handleOnConfigurationChanged(newConfig)
        activity.window.decorView.post { applyBars() }
    }

    // On WebViews before 140 the page sits between the bars, so the window's background shows
    // behind them, and below the keyboard.
    private fun applyBars() {
        val (color, dark) = bars ?: return
        val window = activity.window
        window.decorView.setBackgroundColor(color)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = !dark
            isAppearanceLightNavigationBars = !dark
        }
    }
}
