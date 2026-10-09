# Dictator for iOS

A custom keyboard that types what you say. The speech model is the one already
on the phone, so this ships no weights and holds none in memory.

What it costs against the Mac build, and why the Hindi locale is not used, is
measured in [`../docs/ios.md`](../docs/ios.md).

## Build it

```bash
ios/build.sh            # simulator, needs nothing but Xcode
ios/build.sh device     # a real phone, needs a team id in ios/team.xcconfig
```

Xcode is required (the Command Line Tools alone cannot build an iOS target).
`build.sh` says so and stops rather than failing somewhere less obvious. It
installs XcodeGen through Homebrew if it is missing, generates
`Dictator.xcodeproj` from `project.yml`, and builds.

A **free** Apple ID is enough for the device build. Xcode signs with a personal
team and the app runs for seven days before it has to be rebuilt, which is
enough to answer the question this exists to answer and costs nothing. The 99
dollars buys TestFlight and the App Store, neither of which is needed yet.

## Turn it on, on the phone

1. Open the Dictator app once and press **Run the checks**. This is what raises
   the microphone prompt: an extension cannot raise it for itself, so skipping
   this leaves the keyboard permanently stuck on "undetermined".
2. **Settings, General, Keyboard, Keyboards, Add New Keyboard, Dictator.**
3. Tap Dictator in that list and turn on **Allow Full Access**. Without it the
   extension is sandboxed away from the microphone, and no amount of tapping
   the button in the keyboard will change that.
4. In any app, switch to the Dictator keyboard and hold the blue key.

Nothing you say leaves the phone. The model runs on it, which is also why Full
Access is being asked for something other than its usual reason.

## Layout

```
Shared/Dictation.swift            microphone to text. The whole engine.
Keyboard/KeyboardViewController.swift   the keyboard, and the probe that
                                        reports what iOS refuses
App/AppMain.swift                 asks for the microphone, downloads the model,
                                  runs the same checks as a baseline
project.yml                       XcodeGen input; the .xcodeproj is generated
                                  and not committed
```

`Shared/` is compiled into both targets rather than made a framework. Two files
and one dependency do not earn a module, and an embedded framework is one more
thing to sign.

## Known and unverified

Whether a keyboard extension can open the microphone at all is **the open
question**, not a detail. The code reports which step refused rather than
failing silently, so running it once on a real phone settles it. Until somebody
does, nothing here should be described as working.
