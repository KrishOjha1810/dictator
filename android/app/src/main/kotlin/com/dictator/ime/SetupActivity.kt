// The app around the keyboard.
//
// It exists for the one thing a keyboard cannot do for itself: raise the
// microphone prompt. A runtime permission dialog belongs to an activity, so
// an IME that asks is an IME that is refused silently, which is how the
// first version of the Mac build spent a week pasting into the void.
//
// Everything else here is signposting. Android hides "add a keyboard" three
// levels into Settings and there is no way to deep link the exact screen on
// every OEM build, so the buttons open the nearest one the system will take
// an intent for and the text says the rest.

package com.dictator.ime

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.speech.SpeechRecognizer
import android.view.Gravity
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.content.ContextCompat

class SetupActivity : Activity() {

    private lateinit var report: TextView

    override fun onCreate(saved: Bundle?) {
        super.onCreate(saved)
        val d = resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()

        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(40), dp(24), dp(32))
            setBackgroundColor(0xFF0F1113.toInt())
        }

        col.addView(TextView(this).apply {
            text = "Dictator"
            textSize = 28f
            setTextColor(0xFFFFFFFF.toInt())
        })
        col.addView(TextView(this).apply {
            text = "Hold a key, talk, the words land where your cursor is. " +
                   "Speech stays on this phone."
            textSize = 15f
            setTextColor(0xFFA8AEB6.toInt())
            setPadding(0, dp(8), 0, dp(24))
        })

        col.addView(step(1, "Allow the microphone", "Allow") {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
        })
        col.addView(step(2, "Turn the keyboard on in Settings", "Open") {
            startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))
        })
        col.addView(step(3, "Pick it while typing", "Pick") {
            (getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager)
                .showInputMethodPicker()
        })

        report = TextView(this).apply {
            textSize = 13f
            setTextColor(0xFFD8DCE1.toInt())
            setPadding(0, dp(24), 0, 0)
            typeface = android.graphics.Typeface.MONOSPACE
        }
        col.addView(Button(this).apply {
            text = "Run the checks"
            setOnClickListener { check() }
        })
        col.addView(report)

        setContentView(ScrollView(this).apply { addView(col) })
        check()
    }

    private fun step(n: Int, title: String, action: String, go: () -> Unit): View {
        val d = resources.displayMetrics.density
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, 0, 0, (10 * d).toInt())
        }
        row.addView(TextView(this).apply {
            text = "$n.  $title"
            textSize = 15f
            setTextColor(0xFFFFFFFF.toInt())
            layoutParams = LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        })
        row.addView(Button(this).apply { text = action; setOnClickListener { go() } })
        return row
    }

    /// Each line is one thing that can be missing, named. A single
    /// "not ready" tells whoever runs this nothing they can act on.
    private fun check() {
        val lines = StringBuilder()
        fun line(ok: Boolean, what: String, detail: String) =
            lines.append(if (ok) "ok   " else "BAD  ").append(what)
                 .append("  ").append(detail).append('\n')

        val mic = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        line(mic, "microphone", if (mic) "allowed" else "not allowed yet")

        val any = SpeechRecognizer.isRecognitionAvailable(this)
        line(any, "a recogniser exists", if (any) "yes" else "none on this phone")

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val on = SpeechRecognizer.isOnDeviceRecognitionAvailable(this)
            line(on, "on-device speech",
                 if (on) "installed" else "missing: Settings, System, Languages, " +
                 "Voice input, Offline speech recognition")
        } else {
            line(true, "on-device speech",
                 "cannot be asked before Android 13; the keyboard will say " +
                 "if a hold is refused")
        }

        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val on = imm.enabledInputMethodList.any { it.packageName == packageName }
        line(on, "keyboard enabled", if (on) "yes" else "step 2 above")

        lines.append("\nAndroid ").append(Build.VERSION.RELEASE)
             .append(" (API ").append(Build.VERSION.SDK_INT).append("), ")
             .append(Build.MANUFACTURER).append(' ').append(Build.MODEL)
        report.text = lines.toString()
    }

    override fun onRequestPermissionsResult(
        code: Int, perms: Array<out String>, results: IntArray
    ) {
        super.onRequestPermissionsResult(code, perms, results)
        check()
    }
}
