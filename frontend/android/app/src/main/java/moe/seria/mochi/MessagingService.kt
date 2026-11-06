package moe.seria.mochi

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

// FCM's data messages from Mochi (backend app/push.py). Runs on a background thread, even with the
// app closed; the notification is built in Notifications.
class MessagingService : FirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        // Off in Settings: Mochi may not have dropped the token yet.
        if (Push.token(this) == null) return
        Notifications.show(this, message.data)
    }

    // Firebase replaced the app's token: kept, and the web app hands it to Mochi when the app next
    // starts (src/push.ts), as only it knows the API's address. The old one is dropped when FCM
    // reports it gone.
    // Deprecated since firebase-messaging 25.1 for FID registration (register() and
    // onRegistered), which is new and barely documented yet; tokens still work.
    @Suppress("OVERRIDE_DEPRECATION")
    override fun onNewToken(token: String) {
        Push.renew(this, token)
    }
}
