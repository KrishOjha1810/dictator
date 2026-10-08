// Dictator: the app that owns the permission.
//
// This exists for one reason. macOS grants Accessibility and Microphone PER
// APPLICATION, and a login item started by launchd is not the terminal the
// user granted. So a bare script gets a permission dialog naming something
// like "/usr/bin/env", which the user cannot evaluate and should not have to,
// and which they then have to add by hand through a file picker.
//
// A real bundle gets one entry called "Dictator", with the
// sentences in Info.plist shown as the reason. That is the whole difference,
// and it is the difference between a setup step and no setup step.
//
// It does nothing itself but ask, then run the dictation loop as a child. The
// child inherits the bundle's permissions, which is the point.
//
// Built from a checkout that is still all it does. Inside Dictator.app from
// the .dmg it also has a face: a menu bar item, the onboarding cards and the
// Hub (MenuBar.swift, Onboarding.swift, Hub.swift). Those only ever read
// status.json and run the CLI; see Backend.swift.

import AVFoundation
import AppKit

let home = FileManager.default.homeDirectoryForCurrentUser

func askForAccessibility() -> Bool {
    // The prompting variant: shows the system dialog once, with a button that
    // opens the right pane. Without the option it returns the answer silently,
    // which is how you end up telling a user to go and find a checkbox.
    let opts = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true]
    return AXIsProcessTrustedWithOptions(opts as CFDictionary)
}

func askForMicrophone(_ done: @escaping (Bool) -> Void) {
    switch AVCaptureDevice.authorizationStatus(for: .audio) {
    case .authorized: done(true)
    case .notDetermined:
        AVCaptureDevice.requestAccess(for: .audio) { ok in
            DispatchQueue.main.async { done(ok) }
        }
    default: done(false)
    }
}

func runDictation() {
    // With a UI the child is supervised instead of waited on, so Pause can
    // stop it without taking the menu bar item down with it.
    if showsUI {
        DispatchQueue.main.async { Supervisor.shared.start() }
        return
    }
    // Written into Info.plist by the build, because the app has to be able to
    // find the code it runs and there is no fixed place that code has to live.
    // This was hardcoded once, which meant a bundle that looked right and
    // silently ran a different install's dictation.
    let info = Bundle.main.infoDictionary ?? [:]
    let cli = (info["DictatorCLI"] as? String) ?? ""
    guard FileManager.default.isExecutableFile(atPath: cli) else {
        NSLog("dictator: cannot find the dictator command at \(cli)")
        return
    }
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
    p.arguments = ["python3", cli, "dictate", "fn"]
    var env = ProcessInfo.processInfo.environment
    // launchd hands a process almost no PATH, and both sox and whisper live in
    // Homebrew. This is the most common reason a login item does nothing.
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    p.environment = env
    let log = URL(fileURLWithPath: (info["DictatorLog"] as? String)
        ?? home.appendingPathComponent(".dictator/dictate.log").path)
    FileManager.default.createFile(atPath: log.path, contents: nil)
    if let h = try? FileHandle(forWritingTo: log) {
        h.seekToEndOfFile()
        p.standardOutput = h
        p.standardError = h
    }
    do {
        try p.run()
    } catch {
        NSLog("dictator: could not start dictation: \(error)")
        return
    }
    // If the child dies, so do we, so launchd restarts the pair together
    // rather than leaving a parent supervising nothing.
    p.waitUntilExit()
    exit(p.terminationStatus)
}

// Waiting for a permission used to be one line in a log file: "dictator:
// waiting for Accessibility", repeated forever, next to a ticked checkbox that
// did not count. Nobody reads a log they have not been told to open, so as far
// as the user was concerned dictation had simply died. Everything below exists
// to make that state impossible to sit in without being told.

func statePath() -> String {
    // The same directory everything else uses (Backend.swift's stateDir),
    // DICTATOR_STATE included, which this used to ignore and so wrote into
    // the real ~/.dictator from a run pointed somewhere else.
    return stateDir.appendingPathComponent("permission.json").path
}

/// Write down what THIS process can see, because AXIsProcessTrusted() can only
/// be asked by the process itself and the process that matters is this bundle,
/// not the python that `dictator doctor` runs in. Without this file, a machine
/// whose TCC databases cannot be read has no way at all to tell "waiting for a
/// permission" from "not running".
func publish(trusted: Bool) {
    let payload: [String: Any] = [
        "trusted": trusted,
        "at": Date().timeIntervalSince1970,
        "pid": ProcessInfo.processInfo.processIdentifier,
        "app": Bundle.main.bundlePath,
    ]
    guard let data = try? JSONSerialization.data(withJSONObject: payload) else { return }
    let path = statePath()
    try? FileManager.default.createDirectory(
        atPath: (path as NSString).deletingLastPathComponent,
        withIntermediateDirectories: true)
    let tmp = path + ".tmp"
    try? data.write(to: URL(fileURLWithPath: tmp))
    _ = try? FileManager.default.replaceItemAt(URL(fileURLWithPath: path),
                                               withItemAt: URL(fileURLWithPath: tmp))
}

/// Say it where somebody will see it. A notification is the only surface this
/// app has: it is an accessory with no window and no menu bar item, and the
/// terminal that started it has usually been closed by now.
func notify(_ body: String) {
    // Not while the onboarding cards are up: they are already saying it, on
    // screen, in the place the user is looking.
    if onboarding { return }
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    p.arguments = ["-e", "display notification \(quoted(body)) "
                   + "with title \"Dictator is not working\" "
                   + "subtitle \"Run: dictator permissions\""]
    let err = Pipe()
    p.standardError = err
    do { try p.run() } catch {
        NSLog("dictator: could not post a notification: \(error)")
        return
    }
    // Read before waiting, or a full pipe deadlocks the wait. And say so when
    // it fails: a notification that is silently dropped because Notification
    // Centre has never been allowed to speak for a script is exactly the kind
    // of silence this whole change exists to remove.
    let why = String(data: err.fileHandleForReading.readDataToEndOfFile(),
                     encoding: .utf8) ?? ""
    p.waitUntilExit()
    if p.terminationStatus != 0 {
        NSLog("dictator: the notification did not go out: \(why)")
    }
}

func quoted(_ s: String) -> String {
    return "\"" + s.replacingOccurrences(of: "\\", with: "\\\\")
                   .replacingOccurrences(of: "\"", with: "\\\"") + "\""
}

/// Ask the CLI to work out WHICH way this is broken, and print its answer.
///
/// "Never granted" and "granted to a signature that is no longer ours" look
/// identical from in here and need opposite instructions: one is a switch to
/// flip, the other is an entry that has to be removed with the minus button
/// because its tick is already on. The logic for telling them apart reads the
/// TCC databases and compares code requirements, which belongs in one place,
/// so this shells out to it rather than growing a second copy.
func diagnose() {
    // In a repo install this is `python3 <DictatorCLI> permissions
    // --explain`, as it always was; in the bundle, the bundled Python.
    guard let (exe, argv, e) = cliCommand(["permissions", "--explain"]) else {
        NSLog("dictator: waiting for Accessibility, and cannot find the "
              + "dictator command to explain why")
        return
    }
    let p = Process()
    p.executableURL = exe
    p.arguments = argv
    p.environment = e
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = pipe
    do { try p.run() } catch {
        NSLog("dictator: waiting for Accessibility (could not explain: \(error))")
        return
    }
    let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(),
                     encoding: .utf8) ?? ""
    p.waitUntilExit()
    // straight to the log launchd is already capturing, unprefixed, because
    // NSLog would stamp every one of twenty lines with a pid and a timestamp
    // and make the one readable thing in this file unreadable.
    FileHandle.standardError.write(
        ("\n" + String(repeating: "=", count: 68) + "\n"
         + "DICTATION IS NOT RUNNING. It is waiting for Accessibility.\n"
         + String(repeating: "=", count: 68) + "\n"
         + out + "\n").data(using: .utf8)!)
    notify(out.split(separator: "\n").first.map(String.init)
           ?? "Waiting for Accessibility.")
}

/// Ask for what is missing, wait for Accessibility, then start dictation.
///
/// `prompt` is false on the very first launch of the app with a UI: the
/// onboarding cards ask, one at a time and with a sentence of why, instead of
/// two system dialogs landing on top of each other before anything has been
/// explained. The waiting below is the same either way.
func begin(prompt: Bool) {
    let start: (@escaping (Bool) -> Void) -> Void = prompt
        ? askForMicrophone : { $0(true) }
    start { _ in
        if !(prompt ? askForAccessibility() : AXIsProcessTrusted()) {
            waitForAccessibility()
        } else {
            publish(trusted: true)
            DispatchQueue.global().async { runDictation() }
        }
    }
}

func waitForAccessibility() {
    // First run: the dialog is on screen now. Wait for the answer rather
    // than failing, because the user is in the middle of granting it.
    //
    // But a dialog only appears when macOS has no row for this app at all.
    // If a row exists for an older signature, no dialog ever appears, the
    // checkbox is already ticked, and waiting here is waiting for
    // something that cannot happen. Give it a few seconds for the honest
    // first-run case, then say what is wrong.
    publish(trusted: false)
    NSLog("dictator: waiting for Accessibility")
    var ticks = 0
    Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { t in
        if AXIsProcessTrusted() {
            // Recovering here rather than asking for a restart is the
            // point: the child is spawned fresh, so it is a NEW process,
            // which is the only kind macOS honours a new grant for.
            t.invalidate()
            publish(trusted: true)
            FileHandle.standardError.write(
                "dictator: Accessibility granted, starting dictation.\n"
                    .data(using: .utf8)!)
            notify("Accessibility granted. Hold fn and talk.")
            DispatchQueue.global().async { runDictation() }
            return
        }
        ticks += 1
        // Once at five seconds, then every two minutes. Loud enough that
        // it cannot be sat in, quiet enough that a log left overnight is
        // still readable.
        if ticks == 3 || ticks % 60 == 0 {
            publish(trusted: false)
            DispatchQueue.global().async { diagnose() }
        }
    }
}

/// True while the first-launch cards are on screen.
var onboarding = false

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

if showsUI {
    // The UI decides when to call begin(): straight away on a normal launch,
    // without prompts behind the onboarding cards on the first one, and not
    // at all with DICTATOR_FAKE, which must never start the real thing.
    let ui = UI()
    app.delegate = ui
    app.run()
} else {
    begin(prompt: true)
    app.run()
}
