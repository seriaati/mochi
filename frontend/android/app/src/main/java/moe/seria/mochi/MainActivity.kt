package moe.seria.mochi

import android.content.Intent
import android.os.Bundle
import android.webkit.CookieManager
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import com.getcapacitor.Bridge
import com.getcapacitor.BridgeActivity
import com.getcapacitor.BridgeWebViewClient
import com.getcapacitor.CapConfig
import org.json.JSONObject
import java.io.File

class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(MochiPlugin::class.java)
        // A recreated activity, or one reopened from Recents, mustn't open the notification's page again.
        val fresh = savedInstanceState == null && (intent.flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY) == 0
        openPath(intent, fresh)
        super.onCreate(savedInstanceState)
        val bridge = bridge ?: return
        bridge.webViewClient = Client(bridge)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        openPath(intent)
    }

    // The WebView writes cookies to disk only every 30 seconds or so, and the login is a cookie:
    // an app killed sooner after logging in would be logged out.
    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush()
    }

    private fun openPath(intent: Intent, fresh: Boolean = true) {
        val path = intent.getStringExtra(MochiPlugin.PATH) ?: return
        if (fresh) MochiPlugin.open(this, path)
        setIntent(Intent(this, MainActivity::class.java))
    }

    // The server isn't in the bundled config but chosen at runtime, so it's added as server.url
    // to a copy of that config, which CapConfig can only read from assets or a file.
    override fun load() {
        val server = Server.url(this) ?: return askServer(unreachable = false)
        val json = JSONObject(assets.open("capacitor.config.json").bufferedReader().use { it.readText() })
        json.put("server", (json.optJSONObject("server") ?: JSONObject()).put("url", server))
        val dir = File(noBackupFilesDir, "capacitor").apply { mkdirs() }
        File(dir, "capacitor.config.json").writeText(json.toString())
        config = CapConfig.loadFromFile(this, dir.path)
        super.load()
    }

    private fun askServer(unreachable: Boolean) {
        startActivity(Intent(this, ServerActivity::class.java).putExtra(ServerActivity.UNREACHABLE, unreachable))
        finish()
    }

    // Shows ServerActivity, with Retry and Change server, instead of the WebView's error page.
    private inner class Client(bridge: Bridge) : BridgeWebViewClient(bridge) {
        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            super.onReceivedError(view, request, error)
            // ERROR_UNKNOWN is also a cancelled load, such as a link handed to the browser.
            if (request.isForMainFrame && error.errorCode != WebViewClient.ERROR_UNKNOWN) unreachable()
        }

        override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, response: WebResourceResponse) {
            super.onReceivedHttpError(view, request, response)
            if (request.isForMainFrame && response.statusCode >= 500) unreachable()
        }

        private fun unreachable() {
            if (!isFinishing) askServer(unreachable = true)
        }
    }
}
