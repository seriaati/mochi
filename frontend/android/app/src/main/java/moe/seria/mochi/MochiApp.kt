package moe.seria.mochi

import android.app.Application

// The app's process: Firebase starts here, from the settings Mochi gave (Push), so FCM works when
// a message starts the app with no activity. Firebase's own start-up (FirebaseInitProvider, which
// needs a google-services.json built in) is removed in the manifest.
class MochiApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Push.start(this)
    }
}
