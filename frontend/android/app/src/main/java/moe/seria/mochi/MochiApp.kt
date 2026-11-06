package moe.seria.mochi

import android.app.Application

// Firebase starts here so FCM works when a message starts the app with no activity. Its own
// start-up, which needs a built-in google-services.json, is removed in the manifest.
class MochiApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Push.start(this)
    }
}
