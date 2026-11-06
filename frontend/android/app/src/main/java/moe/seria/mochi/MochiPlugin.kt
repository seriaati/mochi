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

// The app's own bridge to the web app (src/native.ts).
@CapacitorPlugin(
    name = "Mochi",
    permissions = [Permission(alias = NOTIFICATIONS, strings = [Manifest.permission.POST_NOTIFICATIONS])],
)
class MochiPlugin : Plugin() {
    companion object {
        const val PATH = "moe.seria.mochi.path" // extra: the page a notification opens

        // The page a tapped notification opens, until the web app takes it (takePath). Static,
        // so it waits through the server screen and the login, while the app's process lives.
        private var pending: String? = null

        /** Holds [path] for the web app, then tells the page in [activity] to take it (the `path`
         * event). Before the page is up, the web app takes it once it is. */
        fun open(activity: BridgeActivity, path: String) {
            synchronized(MochiPlugin) { pending = path }
            (activity.bridge?.getPlugin("Mochi")?.instance as? MochiPlugin)?.opened()
        }
    }

    private var bars: Pair<Int, Boolean>? = null

    private fun opened() = notifyListeners("path", null)

    /** The page a tapped notification opens ({ path }), once; nothing when there's none. */
    @PluginMethod
    fun takePath(call: PluginCall) {
        val path = synchronized(MochiPlugin) { pending.also { pending = null } }
        call.resolve(if (path != null) JSObject().put("path", path) else JSObject())
    }

    // Plugin methods run on Capacitor's own background thread: they can wait for Firebase.

    /** Maintenance reminders on this phone (src/push.ts): `enabled` while the server has the
     * token, with the Firebase settings it came with; `allowed` while Android lets the app notify. */
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

    /** Turns push on with the server's Firebase settings ({ project_id, app_id, api_key,
     * sender_id }), after asking for permission to notify (Android 13+), and resolves with the FCM
     * token for the server. Rejects when notifying isn't allowed. */
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

    // Android 13+ stops asking after the second no; before 13, they're off in Android's settings.
    private fun denied(call: PluginCall) =
        call.reject("Notifications are off for Mochi in Android’s settings. Allow them there, then turn this on.")

    private fun enable(call: PluginCall) {
        if (!NotificationManagerCompat.from(context).areNotificationsEnabled()) return denied(call)
        val settings = JSONObject()
        for (key in listOf("project_id", "app_id", "api_key", "sender_id")) settings.put(key, call.getString(key))
        val options = Push.options(settings) ?: return call.reject("Firebase settings need project_id, app_id, api_key and sender_id.")
        // The permission's answer comes on the main thread.
        thread {
            try {
                call.resolve(JSObject().put("token", Push.enable(context, settings, options)))
            } catch (error: Exception) {
                Push.stop(context)
                call.reject("Firebase gave no token: ${error.message}")
            }
        }
    }

    /** Turns push off, and resolves with the token it had ({ token }), for the server to drop. */
    @PluginMethod
    fun disablePush(call: PluginCall) {
        val token = Push.token(context)
        Push.stop(context)
        call.resolve(if (token != null) JSObject().put("token", token) else JSObject())
    }

    /** Leaves this Mochi server for the screen that asks for one (ServerActivity): its login and
     * notifications go. */
    @PluginMethod
    fun changeServer(call: PluginCall) {
        val activity = activity
        Server.leave(activity) {
            call.resolve()
            activity.startActivity(Intent(activity, ServerActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        }
    }

    /** The status and navigation bars take the page's color, with icons for a light or dark page.
     * The theme picked in the web app (mode: system, light or dark) becomes the app's own night
     * mode, so the splash screen has it at the next start. */
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
            // Android 12 and later; Android keeps it, and AUTO follows the system. A new mode is a
            // configuration change, which MainActivity takes without being recreated (its
            // configChanges has uiMode), and the WebView's prefers-color-scheme follows it: the
            // page's data-theme wins all the same. The same mode again changes nothing.
            if (night != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                context.getSystemService(UiModeManager::class.java).setApplicationNightMode(night)
            }
            call.resolve()
        }
    }

    // Capacitor's SystemBars resets them to the system theme when the configuration changes
    // (rotation, dark mode): put the page's back after it.
    override fun handleOnConfigurationChanged(newConfig: Configuration) {
        super.handleOnConfigurationChanged(newConfig)
        activity.window.decorView.post { applyBars() }
    }

    // The page has viewport-fit=cover, so on WebView 140 and later SystemBars lets it draw behind
    // the bars itself (its env(safe-area-inset-*) then hold the bars' sizes). On older WebViews it
    // keeps the WebView between them instead, and what shows behind them is the window's own
    // background, as it is below the keyboard: both get the page's color.
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
