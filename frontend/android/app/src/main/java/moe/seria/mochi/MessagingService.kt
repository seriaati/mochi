package moe.seria.mochi

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class MessagingService : FirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        // Turned off in the app, but the server may not have dropped the token yet.
        if (Push.token(this) == null) return
        Notifications.show(this, message.data)
    }

    // Only kept here: native code doesn't know the API's address, so the web app hands the new
    // token to the server at the next start (src/push.ts).
    // Deprecated since firebase-messaging 25.1 in favour of FID registration, which is barely
    // documented yet; tokens still work.
    @Suppress("OVERRIDE_DEPRECATION")
    override fun onNewToken(token: String) {
        Push.renew(this, token)
    }
}
