package moe.seria.mochi

import android.content.Context
import com.google.android.gms.tasks.Tasks
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import org.json.JSONException
import org.json.JSONObject
import java.util.concurrent.TimeUnit

// Firebase starts with the settings the server hands out instead of a built-in
// google-services.json, so one APK works with every Mochi server.
object Push {
    private const val PREFS = "mochi"
    private const val FIREBASE = "firebase"
    private const val TOKEN = "fcm_token"

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun app(context: Context) = FirebaseApp.getApps(context).firstOrNull()

    fun options(settings: JSONObject): FirebaseOptions? = try {
        FirebaseOptions.Builder()
            .setProjectId(settings.getString("project_id"))
            .setApplicationId(settings.getString("app_id"))
            .setApiKey(settings.getString("api_key"))
            .setGcmSenderId(settings.getString("sender_id"))
            .build()
    } catch (error: JSONException) {
        null
    }

    fun settings(context: Context): JSONObject? = try {
        prefs(context).getString(FIREBASE, null)?.let(::JSONObject)
    } catch (error: JSONException) {
        null
    }

    fun start(context: Context) {
        val options = settings(context)?.let(::options) ?: return
        if (app(context) == null) FirebaseApp.initializeApp(context, options)
    }

    fun token(context: Context): String? = prefs(context).getString(TOKEN, null)

    fun remember(context: Context, token: String) = prefs(context).edit().putString(TOKEN, token).apply()

    fun renew(context: Context, token: String) {
        if (token(context) != null) remember(context, token)
    }

    // Blocks: call from a background thread.
    @Suppress("DEPRECATION") // see MessagingService.onNewToken
    fun enable(context: Context, settings: JSONObject, options: FirebaseOptions): String {
        // A token from another Firebase project is no use to this server.
        if (app(context)?.options != options) {
            stop(context)
            FirebaseApp.initializeApp(context, options)
        }
        prefs(context).edit().putString(FIREBASE, settings.toString()).apply()
        val token = Tasks.await(FirebaseMessaging.getInstance().token, 30, TimeUnit.SECONDS)
        remember(context, token)
        return token
    }

    // Blocks: call from a background thread.
    @Suppress("DEPRECATION") // see MessagingService.onNewToken
    fun stop(context: Context) {
        app(context)?.let { app ->
            try {
                Tasks.await(FirebaseMessaging.getInstance().deleteToken(), 10, TimeUnit.SECONDS)
            } catch (error: Exception) {
                // Best effort: the server drops a token once FCM reports it gone.
            }
            app.delete()
        }
        prefs(context).edit().remove(FIREBASE).remove(TOKEN).apply()
    }
}
