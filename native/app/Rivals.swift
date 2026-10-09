// Other dictation apps that may be listening to the same key.
//
// Found on this Mac: Wispr Flow also holds fn, so one press made both apps
// listen and both pasted the same sentence. Nothing in either app said why.
// The app now looks for known dictation apps when it starts and each time the
// menu opens, and says so in the menu and on Home while our key is fn. It
// never quits one by itself: the "Quit" button is the user's decision.

import AppKit

struct Rival: Equatable {
    var name: String
    /// Bundle identifiers that mean this app. Checked first.
    var ids: [String]
    /// Names macOS shows for it, for builds whose identifier we do not know.
    var names: [String]
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
    ]

    struct Running: Equatable {
        var rival: Rival
        var pid: pid_t
    }

    /// The first known dictation app that is running now, if any.
    ///
    /// In fake mode DICTATOR_FAKE_RIVAL="Wispr Flow" pretends one is, for
    /// screenshots; the real list is read either way, since reading it
    /// changes nothing.
    static func running() -> Running? {
        if fake, let n = env["DICTATOR_FAKE_RIVAL"], !n.isEmpty {
            let r = known.first { $0.name == n } ?? Rival(name: n, ids: [], names: [n])
            return Running(rival: r, pid: 0)
        }
        let me = NSRunningApplication.current.processIdentifier
        for app in NSWorkspace.shared.runningApplications where app.processIdentifier != me {
            let id = app.bundleIdentifier ?? ""
            let name = app.localizedName ?? ""
            if let r = known.first(where: { r in
                r.ids.contains { $0.caseInsensitiveCompare(id) == .orderedSame }
                    || r.names.contains(name) }) {
                return Running(rival: r, pid: app.processIdentifier)
            }
        }
        return nil
    }

    /// The sentence, the same in the menu and on Home.
    static func warning(_ r: Rival) -> String {
        "\(r.name) is also running and listens to fn, so both will type. "
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
