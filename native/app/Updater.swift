// Updates, through Sparkle.
//
// The app checks releases/latest/download/appcast.xml on GitHub (SUFeedURL in
// Info.plist). tools/release.sh publishes that feed with every release, and
// signs the .dmg with the update key whose public half is SUPublicEDKey: an
// update not signed by it is refused, whoever hosts it. The new version is
// signed with the same release certificate as this one, so the Microphone and
// Accessibility grants carry over.
//
// Sparkle is only linked into the bundle tools/build_dmg.sh makes. A repo
// install compiles native/app/*.swift without it, so the same API is kept and
// does nothing there: updating a checkout is `git pull`, not this.

import Foundation
#if canImport(Sparkle)
import Sparkle
#endif

final class Updater {
    static let shared = Updater()

    #if canImport(Sparkle)
    private let controller: SPUStandardUpdaterController?

    private init() {
        // Never in fake mode: screenshots and design work must not reach out
        // to GitHub or put up an update dialog.
        controller = fake ? nil
            : SPUStandardUpdaterController(startingUpdater: true,
                                           updaterDelegate: nil,
                                           userDriverDelegate: nil)
    }

    func checkForUpdates() { controller?.checkForUpdates(nil) }

    var automaticallyChecks: Bool {
        get { controller?.updater.automaticallyChecksForUpdates ?? false }
        set { controller?.updater.automaticallyChecksForUpdates = newValue }
    }

    var canCheck: Bool { controller?.updater.canCheckForUpdates ?? false }
    #else
    private init() {}

    func checkForUpdates() {
        NSLog("dictator: updates come from git in a repo install")
    }

    var automaticallyChecks: Bool {
        get { false }
        set { _ = newValue }
    }

    var canCheck: Bool { false }
    #endif

    var version: String {
        let i = Bundle.main.infoDictionary ?? [:]
        let v = i["CFBundleShortVersionString"] as? String ?? "?"
        let b = i["CFBundleVersion"] as? String ?? "?"
        return "\(v) (\(b))"
    }
}
