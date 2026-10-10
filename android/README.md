# Dictator for Android

A keyboard that types what you say, with no speech model of its own yet.

## Why Android before iOS

On iOS the hard part is the sandbox. On Android there is no sandbox to argue
with: an `InputMethodService` is a normal app process, with no extension
memory ceiling, and typing is `commitText` on the connection the host app
already handed over. The 500 lines of synthetic Cmd-V, clipboard saving and
Accessibility pleading that the Mac build needs collapse to one call.

Which means the only real question here is the speech, and that is the
question this build is shaped to answer rather than to assume.

## What this build is for

Three things, in this order:

1. **Can an IME record and type, on a real phone.** Near certain, and still
   unproven until somebody runs it.
2. **What does the phone's own recogniser do to Hinglish.** This is the
   floor. If it is good enough, Android ships without carrying a model.
3. **How long does a hold take.**

It uses Android's recogniser with `EXTRA_PREFER_OFFLINE`, and the app
**declares no `INTERNET` permission at all**. That is deliberate and it is
checkable: the one promise this product makes is that speech stays on the
device, and a build that cannot reach the network cannot break that promise
by accident. If the on-device pack is missing, the keyboard says so and
refuses, rather than quietly uploading your voice.

`en-IN` and not `hi-IN`, for a reason already measured on the Mac: a Hindi
model writes English technical words phonetically in Devanagari ("Slack
summary" came back as `स्लिक समिट`, 69% word error, 9.6% of English words
surviving). This audience says "function", "deploy" and "pull request"
inside Hindi sentences. The numbers are in [`../docs/ios.md`](../docs/ios.md).

## Build it

```bash
android/build.sh            # the debug apk
android/build.sh install    # and push it to a plugged in phone
android/build.sh setup      # just the toolchain
```

No Android Studio: it is about 10GB and this is a two screen app. The command
line tools are 146MB and the SDK pieces another 400 or so. No NDK either,
because this build compiles nothing for the device.

For the phone: Settings, About, tap Build number seven times, then Settings,
System, Developer options, USB debugging. Plug it in and accept the prompt
that appears on its screen.

## Turn it on, on the phone

1. Open Dictator and press **Allow** for the microphone. This is the only
   reason the app exists: a runtime permission dialog belongs to an activity,
   so a keyboard that asks is a keyboard that is refused silently.
2. **Settings, System, Languages, Keyboard, On-screen keyboard, Manage
   keyboards**, and turn Dictator on. The app's step 2 opens the nearest
   screen the system will take an intent for; the rest varies by
   manufacturer.
3. While typing anywhere, switch to Dictator and hold the blue key.

If a hold is refused, the keyboard says which of the microphone, the
recogniser and the offline pack was missing. "It did not work" without a step
name is not a finding, and findings are what this build is for.

## Layout

```
app/src/main/kotlin/com/dictator/ime/
  DictatorIme.kt     the keyboard. Records, types, and reports what refused
  SetupActivity.kt   raises the microphone prompt and runs the same checks
app/src/main/AndroidManifest.xml   note what is NOT in it: INTERNET
app/src/main/res/xml/method.xml    the input method declaration
build.sh                            toolchain, build, install
```

## Known and unverified

Everything. Nothing here has been run on a phone yet, so nothing here should
be described as working.

The question after this one, which this build does not touch: whether
shipping our own model is worth it. `ggml` allocates natively through JNI so
the Java heap cap does not apply, and `whisper.cpp` has an Android example,
but no trustworthy real-time factor exists for any whisper size on a
mid-range phone, and nobody has measured IndicConformer on one at all. That
is written up in issue #19, and the gate there still stands: measure on a
two or three year old mid-range phone, in release mode, before writing a line
of it.
