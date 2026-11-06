package moe.seria.mochi

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationChannelCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

// Maintenance reminders, drawn from the backend's FCM data messages (app/push.py): "reminder",
// one per client, which a newer reminder for the client replaces, and "test", from Settings.
object Notifications {
    private const val CHANNEL = "reminders"
    private const val CLIENT = "client" // tag of a client's reminder, its id the client's
    private const val TEST = "test" // tag of the test message, id 0

    fun show(context: Context, data: Map<String, String>) {
        val (tag, id) = when (data["type"]) {
            "reminder" -> CLIENT to (data["client_id"]?.toIntOrNull() ?: return)
            "test" -> TEST to 0
            else -> return
        }
        if (!allowed(context)) return
        val body = data["body"].orEmpty()
        val notification = NotificationCompat.Builder(context, channel(context))
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(data["title"])
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setContentIntent(open(context, data["path"] ?: "/", "$tag-$id".hashCode()))
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(tag, id, notification)
    }

    /** Removes them all: they belong to a server the app is leaving. */
    fun forget(context: Context) = NotificationManagerCompat.from(context).cancelAll()

    private fun channel(context: Context): String {
        val channel = NotificationChannelCompat.Builder(CHANNEL, NotificationManagerCompat.IMPORTANCE_DEFAULT)
            .setName("Maintenance reminders")
            .setDescription("A client's fee is due or overdue")
            .build()
        NotificationManagerCompat.from(context).createNotificationChannel(channel) // or renames it
        return CHANNEL
    }

    private fun allowed(context: Context) =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    /** Opens [path] (a page of the web app) in the app: MainActivity hands it to MochiPlugin,
     * which holds it for the web app. [request] tells one notification's intent from another's,
     * as extras don't. */
    private fun open(context: Context, path: String, request: Int): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).putExtra(MochiPlugin.PATH, path)
        return PendingIntent.getActivity(context, request, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }
}
