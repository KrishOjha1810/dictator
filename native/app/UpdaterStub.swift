// A stand-in for native/app/Updater.swift, which wraps Sparkle and is being
// written separately. Same API, doing nothing, so the app builds and the
// update controls can be wired and looked at. Delete this file when the real
// Updater.swift lands; nothing else needs to change.

import Foundation

final class Updater {
    static let shared = Updater()

    func checkForUpdates() {
        NSLog("dictator: check for updates (stub, no updater yet)")
    }

    var automaticallyChecks: Bool = true

    var canCheck: Bool { true }

    var version: String {
        let info = Bundle.main.infoDictionary ?? [:]
        return (info["CFBundleShortVersionString"] as? String) ?? "dev"
    }
}
