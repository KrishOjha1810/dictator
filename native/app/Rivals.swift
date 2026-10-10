// Other dictation apps that may be listening to the same key.
//
// Found on this Mac: Wispr Flow also holds fn, so one press made both apps
// listen and both pasted the same sentence. Nothing in either app said why.
// The app now looks for known dictation apps when it starts and each time the
// menu opens, and says so in the menu and on Home while our key is fn. It
// never quits one by itself: the "Quit" button is the user's decision.
//
// Warp, the terminal, has AI voice input of its own, held on fn by default
// ([agents.voice] voice_input_toggle_key in ~/.warp/settings.toml). With both
// on fn every hold in Warp pasted twice: Dictator's sentence, then Warp's
// rewritten copy of it. Warp is somebody's terminal, so it is never offered a
// Quit button; the fix is a different key in one of the two apps, and it only
// counts as a clash when Warp's voice key is actually ours.

import AppKit

struct Rival: Equatable {
    var name: String
    /// Bundle identifiers that mean this app. Checked first.
    var ids: [String]
    /// Names macOS shows for it, for builds whose identifier we do not know.
    var names: [String]
    /// Quitting it is a reasonable fix. False for an app whose dictation is
    /// a side feature, like a terminal: there the fix is its key.
    var quittable = true
    /// Where to change its key, for an app that is not quittable.
    var keyHint = ""
}

enum Rivals {
    /// The one list. Wispr Flow's identifier was read from
    /// /Applications/Wispr Flow.app/Contents/Info.plist on this Mac; the
    /// others are their published identifiers, with the app's name as a
    /// fallback match, since a guessed identifier that is wrong matches
    /// nothing at all.
    static let known: [Rival] = [
        Rival(name: "Wispr Flow", ids: ["com.electron.wispr-flow"], names: ["Wispr Flow"]),
        Rival(name: "Superwhisper", ids: ["com.superduper.superwhisper"],
              names: ["superwhisper", "Superwhisper"]),
        Rival(name: "MacWhisper", ids: ["com.goodsnooze.MacWhisper", "com.goodsnooze.macwhisper"],
              names: ["MacWhisper"]),
        Rival(name: "Aqua Voice", ids: [], names: ["Aqua Voice"]),
        Rival(name: "Willow", ids: [], names: ["Willow Voice", "Willow"]),
        Rival(name: "Warp", ids: ["dev.warp.Warp-Stable", "dev.warp.Warp-Preview"],
              names: ["Warp"], quittable: false,
              keyHint: "In Warp, open Settings, AI, Voice, and pick another key"),
    ]

    /// The key a rival listens to, in Prefs.keys' names. Dictation apps are
    /// on fn unless we know better; Warp says in its settings file, and
    /// listens to nothing we share when the file does not name a key.
    static func listensTo(_ r: Rival) -> String? {
        guard r.name == "Warp" else { return "fn" }
        let f = home.appendingPathComponent(".warp/settings.toml")
        guard let text = try? String(contentsOf: f, encoding: .utf8) else { return nil }
        for line in text.split(separator: "\n") {
            let l = line.trimmingCharacters(in: .whitespaces)
            guard l.hasPrefix("voice_input_toggle_key"),
                  let eq = l.firstIndex(of: "=") else { continue }
            let v = l[l.index(after: eq)...].lowercased()
                .trimmingCharacters(in: CharacterSet(charactersIn: " \"'"))
            if v.contains("fn") || v.contains("globe") { return "fn" }
            let right = v.contains("right"), left = v.contains("left")
            if right && (v.contains("alt") || v.contains("option")) { return "rightopt" }
            if right && (v.contains("cmd") || v.contains("command") || v.contains("meta")) { return "rightcmd" }
            if left && (v.contains("cmd") || v.contains("command") || v.contains("meta")) { return "leftcmd" }
            return v
        }
        return nil
    }

    struct Running: Equatable {
        var rival: Rival
        var pid: pid_t
    }

    /// The first known dictation app that is running now and listens to
    /// `key`, if any.
    ///
    /// In fake mode DICTATOR_FAKE_RIVAL="Wispr Flow" pretends one is, for
    /// screenshots; the real list is read either way, since reading it
    /// changes nothing.
    static func running(key: String) -> Running? {
        if fake, let n = env["DICTATOR_FAKE_RIVAL"], !n.isEmpty {
            let r = known.first { $0.name == n } ?? Rival(name: n, ids: [], names: [n])
            return Running(rival: r, pid: 0)
        }
        let me = NSRunningApplication.current.processIdentifier
        for app in NSWorkspace.shared.runningApplications where app.processIdentifier != me {
            let id = app.bundleIdentifier ?? ""
            let name = app.localizedName ?? ""
            if let r = known.first(where: { r in
                (r.ids.contains { $0.caseInsensitiveCompare(id) == .orderedSame }
                    || r.names.contains(name)) && listensTo(r) == key }) {
                return Running(rival: r, pid: app.processIdentifier)
            }
        }
        return nil
    }

    /// The sentence, the same in the menu and on Home.
    static func warning(_ r: Rival, key: String) -> String {
        let k = Prefs.keyNames[key] ?? key
        if !r.quittable {
            return "\(r.name)'s voice input also listens to \(k), so both will type. "
                + "\(r.keyHint), or change Dictator's key."
        }
        return "\(r.name) is also running and listens to \(k), so both will type. "
            + "Quit it, or change Dictator's key."
    }

    /// Ask it to quit, the way the Dock's Quit does. Only ever called from
    /// the button. Fake mode quits nothing: the screenshots run on a Mac
    /// where the real Wispr Flow may be open and in use.
    static func quit(_ r: Running) {
        if fake || r.pid == 0 {
            NSLog("dictator (fake): would quit \(r.rival.name)")
            return
        }
        NSRunningApplication(processIdentifier: r.pid)?.terminate()
    }
}
