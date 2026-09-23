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

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

askForMicrophone { _ in
    if !askForAccessibility() {
        // First run: the dialog is on screen now. Wait for the answer rather
        // than failing, because the user is in the middle of granting it.
        NSLog("dictator: waiting for Accessibility")
        Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { t in
            if AXIsProcessTrusted() {
                t.invalidate()
                DispatchQueue.global().async { runDictation() }
            }
        }
    } else {
        DispatchQueue.global().async { runDictation() }
    }
}
app.run()
