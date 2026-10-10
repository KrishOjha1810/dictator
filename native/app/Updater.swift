// Updates, through Sparkle.
//
// The app checks appcast.xml in the Cloudflare R2 bucket (SUFeedURL, which
// tools/build_dmg.sh writes into the bundle). tools/release.sh publishes that
// feed with every release, and signs the .dmg with the update key whose
// public half is SUPublicEDKey: an update not signed by it is refused,
// whoever hosts it. The new version is signed with the same release
// certificate as this one, so the Microphone and Accessibility grants carry
// over.
//
// Every check is a paid read on the bucket. Sparkle checks on its own every
// two days (SUScheduledCheckInterval), and a person can check by hand at most
// manualLimit times a calendar day. See docs/cloudflare-r2.md.
//
// Sparkle is only linked into the bundle tools/build_dmg.sh makes. A repo
// install compiles native/app/*.swift without it, so the same API is kept and
// does nothing there: updating a checkout is `git pull`, not this.

import AppKit
#if canImport(Sparkle)
import Sparkle
#endif

final class Updater {
    static let shared = Updater()

    #if canImport(Sparkle)
    private let controller: SPUStandardUpdaterController?

    private init() {
        // Never in fake mode: screenshots and design work must not reach out
        // to the bucket or put up an update dialog.
        controller = fake ? nil
            : SPUStandardUpdaterController(startingUpdater: true,
                                           updaterDelegate: nil,
                                           userDriverDelegate: nil)
    }

    func checkForUpdates() {
        guard let controller else { return }
        guard takeManualCheck() else { return refuseCheck() }
        controller.checkForUpdates(nil)
    }

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

    // Hand checks made today, so one person clicking "Check for Updates" in a
    // loop cannot run up the bucket's reads. Local to this Mac: it limits
    // accidents and impatience, not someone set on getting around it.
    static let manualLimit = 10
    private let checksDay = "updateChecksDay"
    private let checksCount = "updateChecksCount"

    /// Counts one hand check against today. False when today's are used up.
    private func takeManualCheck() -> Bool {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        let today = f.string(from: Date())
        let store = Prefs.store
        let used = store.string(forKey: checksDay) == today
            ? store.integer(forKey: checksCount) : 0
        guard used < Self.manualLimit else { return false }
        store.set(today, forKey: checksDay)
        store.set(used + 1, forKey: checksCount)
        return true
    }

    private func refuseCheck() {
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.icon = NSApp.applicationIconImage
        a.messageText = "No more update checks today"
        a.informativeText = "Dictator can check for updates \(Self.manualLimit) times a day, "
            + "and it still checks on its own every two days. Try again tomorrow."
        a.addButton(withTitle: "OK")
        a.runModal()
    }

    var version: String {
        let i = Bundle.main.infoDictionary ?? [:]
        let v = i["CFBundleShortVersionString"] as? String ?? "?"
        let b = i["CFBundleVersion"] as? String ?? "?"
        return "\(v) (\(b))"
    }
}
