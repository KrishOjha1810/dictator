// The menu bar item, and the one object every window reads from.
//
// The status dot is the same truth as `doctor`: what status.json says, except
// where this process knows better. Only this process can ask
// AXIsProcessTrusted() about itself, and only it knows it paused the child, so
// those two win over whatever the loop last wrote.

import AVFoundation
import AppKit
import SwiftUI

enum Page: String, CaseIterable, Identifiable {
    case home = "Home", words = "Words", snippets = "Snippets", style = "Style"
    case review = "Review", meetings = "Meetings", settings = "Settings", help = "Help"
    var id: String { rawValue }

    /// The pages in the top of the sidebar; Settings and Help sit at the bottom.
    static let main: [Page] = [.home, .words, .snippets, .style, .review, .meetings]

    var symbol: String {
        switch self {
        case .home: return "house"
        case .words: return "character.book.closed"
        case .snippets: return "text.badge.plus"
        case .style: return "textformat"
        case .review: return "checkmark.seal"
        case .meetings: return "person.2"
        case .settings: return "gearshape"
        case .help: return "questionmark.circle"
        }
    }
}

final class AppModel: ObservableObject {
    static let shared = AppModel()

    @Published var status = Status()
    @Published var trusted = AXIsProcessTrusted()
    @Published var mic = AVCaptureDevice.authorizationStatus(for: .audio)
    @Published var paused = false
    @Published var failure: String? = nil
    @Published var running = false
    @Published var page: Page = .home
    @Published var language = "english"
    @Published var key = Prefs.key
    /// The last hold, from last.json. Read every second with the rest.
    @Published var last: Last? = Last.read()

    func refresh() {
        let s = Status.read()
        if s != status { status = s }
        let t = AXIsProcessTrusted()
        if t != trusted { trusted = t }
        let m = AVCaptureDevice.authorizationStatus(for: .audio)
        if m != mic { mic = m }
        if Supervisor.shared.paused != paused { paused = Supervisor.shared.paused }
        if Supervisor.shared.failure != failure { failure = Supervisor.shared.failure }
        if Supervisor.shared.running != running { running = Supervisor.shared.running }
        let l = Last.read()
        if l != last { last = l }
    }

    /// What the dot shows. See the top of this file for why two things
    /// override the file.
    var state: String {
        if paused { return "paused" }
        if fake { return status.state }
        if !trusted { return "needs_permission" }
        if failure != nil { return "error" }
        // A file from an earlier run, or from a loop that is no longer
        // there, is not the present. Its "ready" would promise a key that
        // does nothing; what it says about a permission or an error, the
        // loop wrote on its way out and is still true.
        let current = running && status.updated >= Supervisor.shared.startedAt.rounded(.down)
        if !current && !["error", "needs_permission"].contains(status.state) {
            return "starting"
        }
        return status.state
    }

    var shown: Status {
        var s = status
        s.state = state
        if let f = failure, state == "error" { s.error = f }
        return s
    }

    func loadLanguage() {
        if fake { return }
        CLI.load({ CLI.text(["language"]) }) { out in
            // "  language: hinglish" is the first line `dictator language` prints.
            if out.contains("language: hinglish") { self.language = "hinglish" }
            else if out.contains("language: english") { self.language = "english" }
        }
    }

    func setLanguage(_ l: String) {
        language = l
        CLI.load({ CLI.act(["language", l]) }) { _ in self.loadLanguage() }
    }

    /// Change the hold key and restart the loop for it, once. Callers apply a
    /// choice, never every press of a picker: the onboarding card used to call
    /// this on each key tried, and each restart killed the model download.
    func setKey(_ k: String) {
        guard Prefs.keys.contains(k), k != Prefs.key else { return }
        Prefs.key = k
        key = k
        Supervisor.shared.restart()
    }
}


final class UI: NSObject, NSApplicationDelegate, NSMenuDelegate, NSWindowDelegate {
    let model = AppModel.shared
    var item: NSStatusItem!
    var windows: [String: NSWindow] = [:]
    var timer: Timer?

    func applicationDidFinishLaunching(_ note: Notification) {
        // Light, whatever the system is set to. The palette in Theme.swift
        // is drawn for one appearance only.
        NSApp.appearance = NSAppearance(named: .aqua)
        applyDockPolicy()
        NSApp.mainMenu = mainMenu()
        if fake, let path = env["DICTATOR_SNAPSHOT"], !path.isEmpty { snapshot(to: path) }

        // Before anything starts: a copy running from the disk image is
        // killed by Gatekeeper a few seconds in, so starting dictation there
        // would only start something that is about to die.
        if offerMove() { return }

        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        let menu = NSMenu()
        menu.delegate = self
        menu.autoenablesItems = false
        item.menu = menu
        model.refresh()
        model.loadLanguage()
        drawIcon()
        Supervisor.shared.onChange = { [weak self] in
            self?.model.refresh()
            self?.drawIcon()
        }
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.model.refresh()
            self?.drawIcon()
        }

        let first = !Prefs.onboarded || env["DICTATOR_ONBOARDING"] == "1"
        if !fake { begin(prompt: !first) }
        if fake, let p = env["DICTATOR_SHOW"].flatMap({ Page(rawValue: $0.capitalized) }) {
            // For screenshots of one page: DICTATOR_SHOW=words, settings, ...
            showHub(p)
        } else if first {
            showOnboarding()
        } else if NSApp.activationPolicy() == .regular {
            // Opened from Finder or the Dock: something should appear. As a
            // login item with no Dock icon it stays in the menu bar.
            showHub(.home)
        }
    }

    /// Fake mode only: draw the front window into a PNG, then quit. For
    /// checking the screens without Screen Recording permission, which a
    /// terminal running screencapture usually does not have.
    func snapshot(to path: String) {
        DispatchQueue.main.asyncAfter(deadline: .now() + (Double(env["DICTATOR_SNAPSHOT_AFTER"] ?? "") ?? 2.5)) {
            guard let w = NSApp.windows.first(where: { $0.isVisible && $0.contentView != nil
                                                       && $0.frame.height > 100 }),
                  let v = w.contentView?.superview ?? w.contentView,
                  let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) else {
                NSLog("dictator (fake): nothing to snapshot")
                NSApp.terminate(nil)
                return
            }
            v.cacheDisplay(in: v.bounds, to: rep)
            try? rep.representation(using: .png, properties: [:])?
                .write(to: URL(fileURLWithPath: path))
            NSApp.terminate(nil)
        }
    }

    func applicationWillTerminate(_ note: Notification) {
        Supervisor.shared.stopAndWait()
    }

    /// Closing the last window leaves the app running; it is the key, not
    /// the window. Quit is in the app menu, the Dock and the menu bar item.
    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { false }

    /// A click on the Dock icon with nothing open opens the Hub.
    func applicationShouldHandleReopen(_ app: NSApplication, hasVisibleWindows: Bool) -> Bool {
        if !hasVisibleWindows {
            if windows["onboarding"] != nil { showOnboarding() } else { showHub(model.page) }
        }
        return true
    }

    // -----------------------------------------------------------------------
    // Dock and app menu.

    /// A regular app with a Dock icon, so it can be quit and force quit like
    /// any other; or, with Show in Dock off, a menu bar item only.
    func applyDockPolicy() {
        let want: NSApplication.ActivationPolicy = Prefs.showInDock ? .regular : .accessory
        guard NSApp.activationPolicy() != want else { return }
        NSApp.setActivationPolicy(want)
        // Turning the Dock icon off hides the app's windows with it; bring
        // back the one the switch was flipped in.
        DispatchQueue.main.async {
            NSApp.activate(ignoringOtherApps: true)
            self.windows.values.first { $0.isVisible }?.makeKeyAndOrderFront(nil)
        }
    }

    func mainMenu() -> NSMenu {
        let bar = NSMenu()
        func sub(_ title: String, _ items: [NSMenuItem]) -> NSMenu {
            let top = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            let m = NSMenu(title: title)
            items.forEach { m.addItem($0) }
            top.submenu = m
            bar.addItem(top)
            return m
        }
        func i(_ t: String, _ a: Selector?, _ k: String = "",
               _ mods: NSEvent.ModifierFlags = .command, target: AnyObject? = nil) -> NSMenuItem {
            let x = NSMenuItem(title: t, action: a, keyEquivalent: k)
            x.keyEquivalentModifierMask = mods
            x.target = target
            return x
        }
        _ = sub("Dictator", [
            i("About Dictator", #selector(about), target: self),
            .separator(),
            i("Settings…", #selector(openSettings), ",", target: self),
            .separator(),
            i("Hide Dictator", #selector(NSApplication.hide(_:)), "h"),
            i("Hide Others", #selector(NSApplication.hideOtherApplications(_:)), "h",
              [.command, .option]),
            i("Show All", #selector(NSApplication.unhideAllApplications(_:))),
            .separator(),
            i("Quit Dictator", #selector(NSApplication.terminate(_:)), "q"),
        ])
        // Without an Edit menu, ⌘C and ⌘V do nothing in the windows' text
        // fields: the shortcuts live in the menu, not in the field.
        _ = sub("Edit", [
            i("Undo", Selector(("undo:")), "z"),
            i("Redo", Selector(("redo:")), "z", [.command, .shift]),
            .separator(),
            i("Cut", #selector(NSText.cut(_:)), "x"),
            i("Copy", #selector(NSText.copy(_:)), "c"),
            i("Paste", #selector(NSText.paste(_:)), "v"),
            i("Select All", #selector(NSText.selectAll(_:)), "a"),
        ])
        let win = sub("Window", [
            i("Minimize", #selector(NSWindow.performMiniaturize(_:)), "m"),
            i("Close", #selector(NSWindow.performClose(_:)), "w"),
            .separator(),
            i("Dictator", #selector(openHub), "0", target: self),
        ])
        NSApp.windowsMenu = win
        let help = sub("Help", [i("Dictator Help", #selector(openHelp), "?", target: self)])
        NSApp.helpMenu = help
        return bar
    }

    @objc func about() {
        NSApp.activate(ignoringOtherApps: true)
        NSApp.orderFrontStandardAboutPanel(options: [
            .credits: NSAttributedString(
                string: "Dictation that stays on this Mac.",
                attributes: [.font: NSFont.systemFont(ofSize: 11),
                             .foregroundColor: NSColor.secondaryLabelColor]),
        ])
    }

    // -----------------------------------------------------------------------
    // Running from the disk image.

    /// Where this copy runs from, if that is somewhere it will not survive:
    /// the mounted .dmg, or the random read-only path macOS translocates a
    /// quarantined app to when it was not moved by Finder.
    var unsafeLocation: Bool {
        let p = Bundle.main.bundlePath
        if fake { return env["DICTATOR_SHOW"] == "move" }
        return Mode.current.isBundle
            && (p.hasPrefix("/Volumes/") || p.contains("/AppTranslocation/"))
    }

    /// Offer to copy the app into /Applications and reopen it from there.
    /// True when this copy is on its way out.
    func offerMove() -> Bool {
        guard unsafeLocation else { return false }
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.icon = NSApp.applicationIconImage
        a.messageText = "Move Dictator to Applications?"
        a.informativeText = "It is running from the disk image, where macOS stops it after "
            + "a few seconds. Dictator will copy itself to Applications and open from there."
        a.addButton(withTitle: "Move to Applications")
        a.addButton(withTitle: "Not Now")
        if a.runModal() != .alertFirstButtonReturn { return false }
        if fake {
            NSLog("dictator (fake): would move \(Bundle.main.bundlePath) to /Applications")
            return false
        }
        let src = Bundle.main.bundlePath
        let dest = "/Applications/Dictator.app"
        // An older copy that is running would fight this one for the key.
        for other in NSRunningApplication.runningApplications(
                withBundleIdentifier: Bundle.main.bundleIdentifier ?? "")
            where other != NSRunningApplication.current {
            other.terminate()
        }
        let fm = FileManager.default
        if fm.fileExists(atPath: dest) {
            try? fm.trashItem(at: URL(fileURLWithPath: dest), resultingItemURL: nil)
        }
        // ditto keeps the signature, the resource forks and the extended
        // attributes exactly as they are; a plain copy can lose the latter.
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        p.arguments = [src, dest]
        let ok = (try? p.run()) != nil && { p.waitUntilExit(); return p.terminationStatus == 0 }()
        guard ok else {
            let e = NSAlert()
            e.messageText = "Could not copy Dictator"
            e.informativeText = "Drag Dictator onto the Applications folder in the disk "
                + "image window, then open it from Applications."
            e.runModal()
            NSApp.terminate(nil)
            return true
        }
        let cfg = NSWorkspace.OpenConfiguration()
        cfg.createsNewApplicationInstance = true
        NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: dest),
                                           configuration: cfg) { _, _ in
            DispatchQueue.main.async { NSApp.terminate(nil) }
        }
        return true
    }

    // -----------------------------------------------------------------------
    // The menu bar item.

    /// A monochrome mic with a coloured dot beside it. The mic is a template
    /// image so it follows the menu bar's light and dark; the dot is text so
    /// it can keep its colour.
    func drawIcon() {
        guard let b = item?.button else { return }
        let img = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Dictator")
        img?.isTemplate = true
        b.image = img
        b.imagePosition = .imageLeft
        b.attributedTitle = NSAttributedString(string: "●", attributes: [
            .foregroundColor: model.shown.color,
            .font: NSFont.systemFont(ofSize: 8),
            .baselineOffset: 1,
        ])
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        model.refresh()
        menu.removeAllItems()
        let s = model.shown

        let head = NSMenuItem(title: "", action: nil, keyEquivalent: "")
        let t = NSMutableAttributedString(string: "Dictator   ",
            attributes: [.font: NSFont.boldSystemFont(ofSize: 13)])
        t.append(NSAttributedString(string: "● ", attributes: [.foregroundColor: s.color]))
        t.append(NSAttributedString(string: s.label))
        head.attributedTitle = t
        // Needs permission and Error open the fix rather than just saying so.
        if s.state == "needs_permission" || s.state == "error" {
            head.action = #selector(openFix)
            head.target = self
        } else {
            head.isEnabled = false
        }
        menu.addItem(head)
        if s.state == "error", let e = s.error {
            let line = NSMenuItem(title: String(e.prefix(60)), action: #selector(openFix),
                                  keyEquivalent: "")
            line.target = self
            menu.addItem(line)
        }
        menu.addItem(.separator())

        add(menu, "Open Dictator…", #selector(openHub))
        let lang = NSMenuItem(title: "Language", action: nil, keyEquivalent: "")
        let sub = NSMenu()
        for (code, title) in [("english", "Auto (English first)"), ("hinglish", "Hinglish")] {
            let i = NSMenuItem(title: title, action: #selector(pickLanguage(_:)), keyEquivalent: "")
            i.target = self
            i.representedObject = code
            i.state = model.language == code ? .on : .off
            sub.addItem(i)
        }
        lang.submenu = sub
        menu.addItem(lang)

        // Only the models that are not there yet. A list of things that are
        // fine is noise in a menu.
        let missing = s.models.filter { !$0.have }
        if !missing.isEmpty {
            menu.addItem(.separator())
            for m in missing {
                let pct = Int((m.progress * 100).rounded())
                let i = NSMenuItem(title: "\(modelTitle(m.name))   "
                                   + (m.progress > 0 ? "downloading \(pct)%" : "waiting"),
                                   action: nil, keyEquivalent: "")
                i.isEnabled = false
                menu.addItem(i)
            }
        }
        menu.addItem(.separator())
        add(menu, model.paused ? "Resume dictation" : "Pause dictation", #selector(togglePause))
        // Dictation stopped by itself. Inside the app nothing restarts it, so
        // the way back is here rather than in quitting and reopening.
        if !fake && !model.paused && !model.running && model.trusted {
            add(menu, "Restart dictation", #selector(restartDictation))
        }
        add(menu, "Settings…", #selector(openSettings), key: ",")
        add(menu, "Quit Dictator", #selector(quit), key: "q")
    }

    private func add(_ menu: NSMenu, _ title: String, _ sel: Selector, key: String = "") {
        let i = NSMenuItem(title: title, action: sel, keyEquivalent: key)
        i.target = self
        menu.addItem(i)
    }

    @objc func openHub() { showHub(.home) }
    @objc func openSettings() { showHub(.settings) }
    @objc func openHelp() { showHub(.help) }

    @objc func openFix() {
        if model.state == "needs_permission" {
            NSWorkspace.shared.open(URL(string:
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
        } else {
            showHub(.settings)
        }
    }

    @objc func pickLanguage(_ sender: NSMenuItem) {
        if let l = sender.representedObject as? String { model.setLanguage(l) }
    }

    @objc func togglePause() {
        if Supervisor.shared.paused { Supervisor.shared.resume() } else { Supervisor.shared.pause() }
        model.refresh()
        drawIcon()
    }

    @objc func restartDictation() {
        Supervisor.shared.start()
        model.refresh()
        drawIcon()
    }

    @objc func quit() { NSApp.terminate(nil) }

    // -----------------------------------------------------------------------
    // Windows. One of each, brought to the front if it is already open.

    func show<V: View>(_ id: String, _ title: String, _ size: NSSize, min: NSSize? = nil,
                       _ view: () -> V) -> NSWindow {
        if let w = windows[id] {
            w.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
            if w.isMiniaturized { w.deminiaturize(nil) }
            w.makeKeyAndOrderFront(nil)
            w.orderFrontRegardless()
            NSApp.activate(ignoringOtherApps: true)
            return w
        }
        var style: NSWindow.StyleMask = [.titled, .closable, .miniaturizable, .fullSizeContentView]
        if min != nil { style.insert(.resizable) }
        let w = NSWindow(contentRect: NSRect(origin: .zero, size: size),
                         styleMask: style, backing: .buffered, defer: false)
        w.title = title
        // The content runs up under a clear title bar, the way modern Mac
        // apps look; the traffic lights sit over the sidebar.
        w.titlebarAppearsTransparent = true
        w.titleVisibility = .hidden
        w.isMovableByWindowBackground = true
        w.backgroundColor = NSColor(srgbRed: 0.980, green: 0.973, blue: 0.961, alpha: 1)
        w.appearance = NSAppearance(named: .aqua)
        w.isReleasedWhenClosed = false
        w.delegate = self
        w.contentViewController = NSHostingController(
            rootView: view().environmentObject(model))
        w.setContentSize(size)
        if let m = min { w.contentMinSize = m }
        w.center()
        // Open where the user is looking. Without this the window lands on
        // the desktop Space while they sit in a full-screen app, and the
        // first launch looks like nothing happened at all.
        w.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        windows[id] = w
        w.makeKeyAndOrderFront(nil)
        // In front even when activation is refused (macOS 14 lets the
        // frontmost app decline a steal); it becomes key on the first click.
        w.orderFrontRegardless()
        // With no Dock icon the app does not come to the front on its own.
        NSApp.activate(ignoringOtherApps: true)
        return w
    }

    func showHub(_ page: Page) {
        model.page = page
        _ = show("hub", "Dictator", Theme.hubSize, min: NSSize(width: 820, height: 560)) {
            HubView()
        }
    }

    func showOnboarding() {
        onboarding = true
        _ = show("onboarding", "Welcome to Dictator", Theme.onboardingSize) {
            OnboardingView(done: { [weak self] in self?.finishOnboarding() })
        }
    }

    /// Closed half way: notifications speak again, and the cards come back on
    /// the next launch because `onboarded` was never set.
    func windowWillClose(_ note: Notification) {
        guard let w = note.object as? NSWindow, windows["onboarding"] === w else { return }
        onboarding = false
        windows["onboarding"] = nil
    }

    func finishOnboarding() {
        Prefs.onboarded = true
        windows["onboarding"]?.close()
        // Then the Hub, once, on Home. After this the app is the menu bar
        // item and the key.
        showHub(.home)
    }
}
