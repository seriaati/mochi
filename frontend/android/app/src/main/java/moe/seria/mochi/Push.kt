package moe.seria.mochi

import android.content.Context
import com.google.android.gms.tasks.Tasks
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import org.json.JSONException
import org.json.JSONObject
import java.util.concurrent.TimeUnit

// Firebase, which FCM needs, started with the settings the Mochi server hands out (GET
// /api/notifications/firebase, from its FIREBASE_ANDROID_CONFIG) rather than a
// google-services.json built in: one app for every server. The web app fetches them and turns
// push on (MochiPlugin.enablePush), as only it knows the API's address; they're kept for the next
// starts, with the FCM token the server has.
object Push {
    private const val PREFS = "mochi"
    private const val FIREBASE = "firebase" // the server's JSON: project_id, app_id, api_key, sender_id
    private const val TOKEN = "fcm_token"

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    // Only the default app is ever made.
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

    /** The kept settings, as the server gave them. */
    fun settings(context: Context): JSONObject? = try {
        prefs(context).getString(FIREBASE, null)?.let(::JSONObject)
    } catch (error: JSONException) {
        null
    }

    /** Starts Firebase with the kept settings, at each start of the app's process (MochiApp): an
     * FCM message can start it with no activity. */
    fun start(context: Context) {
        val options = settings(context)?.let(::options) ?: return
        if (app(context) == null) FirebaseApp.initializeApp(context, options)
    }

    /** The FCM token the server has, while push is on in this app. */
    fun token(context: Context): String? = prefs(context).getString(TOKEN, null)

    fun remember(context: Context, token: String) = prefs(context).edit().putString(TOKEN, token).apply()

    /** Firebase replaced the token: kept, while push is on. The web app hands it to the server
     * when the app next starts. */
    fun renew(context: Context, token: String) {
        if (token(context) != null) remember(context, token)
    }

    /** Starts Firebase with [settings] and keeps them, then resolves the FCM token, kept as the
     * one the server gets. Another Firebase project replaces the running one, as its token is no
     * use. Call from a background thread. */
    @Suppress("DEPRECATION") // getToken: see MessagingService.onNewToken
    fun enable(context: Context, settings: JSONObject, options: FirebaseOptions): String {
        if (app(context)?.options != options) {
            stop(context)
            FirebaseApp.initializeApp(context, options)
        }
        prefs(context).edit().putString(FIREBASE, settings.toString()).apply()
        val token = Tasks.await(FirebaseMessaging.getInstance().token, 30, TimeUnit.SECONDS)
        remember(context, token)
        return token
    }

    /** Stops Firebase and forgets its settings and the token, which FCM deletes too (best
     * effort), so nothing reaches this app anymore: push is off. Call from a background thread. */
    @Suppress("DEPRECATION") // deleteToken: as getToken, see MessagingService.onNewToken
    fun stop(context: Context) {
        app(context)?.let { app ->
            try {
                Tasks.await(FirebaseMessaging.getInstance().deleteToken(), 10, TimeUnit.SECONDS)
            } catch (error: Exception) {
                // Offline or slow: FCM drops a token unused for long, and the server drops one
                // FCM no longer knows.
            }
            app.delete()
        }
        prefs(context).edit().remove(FIREBASE).remove(TOKEN).apply()
    }
}
