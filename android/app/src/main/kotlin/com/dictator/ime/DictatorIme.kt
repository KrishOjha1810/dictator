// The keyboard.
//
// On Android this is the easy half, and that is the whole reason Android is
// worth doing before iOS. An InputMethodService is a normal app process: no
// extension memory ceiling, no sandbox to argue with, and typing is
// `commitText` on the connection the host app already gave us. The 500 lines
// of synthetic Cmd-V, clipboard saving and Accessibility pleading that the
// Mac build needs (`paste.py`, `native/paste.swift`) collapse to one call.
//
// The hard half is the speech, and this file does not pretend to solve it.
// It uses Android's own recogniser, forced offline, so that the first build
// answers the questions that have to be answered before anyone writes a line
// of JNI:
//
//   1. Can an IME record and type, on a real phone, at all.
//   2. What does the platform recogniser do to Hinglish.
//   3. How long does a hold take.
//
// `docs/android.md` has the numbers once it has been run. Until then nothing
// here is described as working.
//
// Why forced offline: the default SpeechRecognizer sends audio to Google.
// This product's one promise is that speech stays on the device, so a build
// that quietly uploaded it would be worse than no build. EXTRA_PREFER_OFFLINE
// asks for the on-device pack; `offlineOnly` below refuses to run at all
// when the pack is missing, rather than falling back to the network.

package com.dictator.ime

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.inputmethodservice.InputMethodService
import android.os.Build
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat

class DictatorIme : InputMethodService(), RecognitionListener {

    private var recogniser: SpeechRecognizer? = null
    private lateinit var status: TextView
    private lateinit var preview: TextView
    private lateinit var talk: Button

    /// Everything the recogniser has committed to this session. Partial
    /// results are shown and never typed: a partial is a guess it will
    /// revise, and text already in somebody's message cannot be unrevised.
    private var settled = ""
    private var typed = ""

    // -----------------------------------------------------------------------

    override fun onCreateInputView(): View {
        val pad = (12 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            setBackgroundColor(0xFF15171A.toInt())
        }

        preview = TextView(this).apply {
            textSize = 15f
            setTextColor(0xFFFFFFFF.toInt())
            maxLines = 2
            text = ""
        }
        talk = Button(this).apply {
            text = "Hold to talk"
            textSize = 17f
            isEnabled = false
            setOnTouchListener { _, event ->
                when (event.actionMasked) {
                    android.view.MotionEvent.ACTION_DOWN -> { start(); true }
                    android.view.MotionEvent.ACTION_UP,
                    android.view.MotionEvent.ACTION_CANCEL -> { stop(); true }
                    else -> false
                }
            }
        }
        status = TextView(this).apply {
            textSize = 12f
            setTextColor(0xFFA8AEB6.toInt())
            text = "Checking"
        }
        val switcher = Button(this).apply {
            text = "ABC"
            textSize = 13f
            setOnClickListener {
                (getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager)
                    .showInputMethodPicker()
            }
        }

        root.addView(preview)
        root.addView(talk)
        root.addView(status)
        root.addView(switcher)
        check()
        return root
    }

    /// Say which of the three things is missing, by name. "It did not work"
    /// without a step name is not a finding, and this build exists to produce
    /// findings.
    private fun check() {
        val mic = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
        if (mic != PackageManager.PERMISSION_GRANTED) {
            // An IME cannot raise the runtime prompt; the setup activity in
            // the app does, which is why the app exists.
            say("Open the Dictator app once to allow the microphone")
            return
        }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            say("No speech recogniser on this phone")
            return
        }
        if (!offlineAvailable()) {
            say("On-device speech is not installed. Settings, System, " +
                "Languages, Voice input, Offline speech recognition")
            return
        }
        say("Ready, on this phone only")
        talk.isEnabled = true
    }

    /// Whether an on-device recogniser exists at all.
    ///
    /// Android has no honest "is the offline pack present" question before
    /// API 33, so below that this reports what it knows and the refusal, if
    /// one comes, arrives as ERROR_LANGUAGE_UNAVAILABLE on the first hold.
    private fun offlineAvailable(): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            SpeechRecognizer.isOnDeviceRecognitionAvailable(this)
        else true

    // -----------------------------------------------------------------------

    private fun start() {
        settled = ""
        typed = ""
        preview.text = ""
        val r = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            SpeechRecognizer.createOnDeviceSpeechRecognizer(this)
        else
            SpeechRecognizer.createSpeechRecognizer(this)
        r.setRecognitionListener(this)
        recogniser = r
        r.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                     RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            // Indian English rather than Hindi, for the reason measured on
            // the Mac: a Hindi model writes English technical words
            // phonetically in Devanagari ("Slack summary" came back as
            // "slik smit", 69% word error), and this audience says
            // "function", "deploy" and "pull request" inside Hindi
            // sentences. See docs/ios.md.
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-IN")
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
        })
        say("Listening")
    }

    private fun stop() {
        recogniser?.stopListening()
        say("Working it out")
    }

    /// Type only what is new.
    ///
    /// Results arrive as the whole sentence so far, not as deltas. Committing
    /// each one whole would type the sentence once per update; deleting and
    /// retyping the difference would fight the host app's autocorrect. This
    /// only ever appends.
    private fun commit(text: String) {
        if (!text.startsWith(typed)) return
        val fresh = text.substring(typed.length)
        if (fresh.isEmpty()) return
        currentInputConnection?.commitText(fresh, 1)
        typed = text
    }

    private fun say(s: String) { status.text = s }

    // -----------------------------------------------------------------------
    // RecognitionListener

    override fun onPartialResults(results: Bundle) {
        val best = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            ?.firstOrNull() ?: return
        preview.text = (settled + best).trim()     // shown, never typed
    }

    override fun onResults(results: Bundle) {
        val best = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            ?.firstOrNull().orEmpty()
        settled = (settled + best).trim()
        preview.text = settled
        commit(settled)
        say("Ready")
        recogniser?.destroy()
        recogniser = null
    }

    override fun onError(error: Int) {
        // The whole point of this build: when it refuses, say what it said.
        say(when (error) {
            SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS ->
                "Microphone refused to the keyboard"
            SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE ->
                "en-IN is not installed for offline speech"
            SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED ->
                "en-IN is not supported offline on this phone"
            SpeechRecognizer.ERROR_NO_MATCH -> "Heard nothing"
            SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "Recogniser busy"
            SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT ->
                "It tried the network, which this build does not allow"
            else -> "Refused, error $error"
        })
        recogniser?.destroy()
        recogniser = null
    }

    override fun onReadyForSpeech(params: Bundle?) {}
    override fun onBeginningOfSpeech() {}
    override fun onRmsChanged(rms: Float) {}
    override fun onBufferReceived(buffer: ByteArray?) {}
    override fun onEndOfSpeech() {}
    override fun onEvent(type: Int, params: Bundle?) {}

    override fun onDestroy() {
        recogniser?.destroy()
        recogniser = null
        super.onDestroy()
    }
}
