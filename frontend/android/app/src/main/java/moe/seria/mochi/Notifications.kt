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

object Notifications {
    private const val CHANNEL = "reminders"
    private const val CLIENT = "client"
    private const val TEST = "test"

    fun show(context: Context, data: Map<String, String>) {
        // Tagged by client, so a newer reminder for a client replaces the last one.
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

    fun forget(context: Context) = NotificationManagerCompat.from(context).cancelAll()

    private fun channel(context: Context): String {
        val channel = NotificationChannelCompat.Builder(CHANNEL, NotificationManagerCompat.IMPORTANCE_DEFAULT)
            .setName("Maintenance reminders")
            .setDescription("A client's fee is due or overdue")
            .build()
        NotificationManagerCompat.from(context).createNotificationChannel(channel)
        return CHANNEL
    }

    private fun allowed(context: Context) =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    // [request] keeps each notification's PendingIntent apart, as differing extras don't.
    private fun open(context: Context, path: String, request: Int): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).putExtra(MochiPlugin.PATH, path)
        return PendingIntent.getActivity(context, request, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }
}
