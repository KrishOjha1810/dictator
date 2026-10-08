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
    case home = "Home", words = "Words", snippets = "Snippets", apps = "Apps"
    case review = "Review", meetings = "Meetings", settings = "Settings"
    var id: String { rawValue }

    var symbol: String {
        switch self {
        case .home: return "house"
        case .words: return "character.book.closed"
        case .snippets: return "text.quote"
        case .apps: return "square.grid.2x2"
        case .review: return "checklist"
        case .meetings: return "person.2"
        case .settings: return "gearshape"
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

    func setKey(_ k: String) {
        guard Prefs.keys.contains(k), k != Prefs.key else { return }
        Prefs.key = k
        key = k
        Supervisor.shared.restart()
    }
}

final class UI: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let model = AppModel.shared
    var item: NSStatusItem!
    var windows: [String: NSWindow] = [:]
    var timer: Timer?

    func applicationDidFinishLaunching(_ note: Notification) {
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
        if first { showOnboarding() }
    }

    func applicationWillTerminate(_ note: Notification) {
        Supervisor.shared.stopAndWait()
    }

    /// A monochrome mic with a coloured dot beside it. The mic is a template
    /// image so it follows the menu bar's light and dark; the dot is text so
    /// it can keep its colour.
    func drawIcon() {
        guard let b = item.button else { return }
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

    func show<V: View>(_ id: String, _ title: String, _ size: NSSize,
                       resizable: Bool, _ view: () -> V) -> NSWindow {
        if let w = windows[id] {
            w.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return w
        }
        var style: NSWindow.StyleMask = [.titled, .closable]
        if resizable { style.formUnion([.resizable, .miniaturizable, .fullSizeContentView]) }
        let w = NSWindow(contentRect: NSRect(origin: .zero, size: size),
                         styleMask: style, backing: .buffered, defer: false)
        w.title = title
        w.isReleasedWhenClosed = false
        w.contentViewController = NSHostingController(
            rootView: view().environmentObject(model))
        w.setContentSize(size)
        w.center()
        windows[id] = w
        w.makeKeyAndOrderFront(nil)
        // An accessory app does not come to the front on its own.
        NSApp.activate(ignoringOtherApps: true)
        return w
    }

    func showHub(_ page: Page) {
        model.page = page
        _ = show("hub", "Dictator", NSSize(width: 880, height: 580), resizable: true) {
            HubView()
        }
    }

    func showOnboarding() {
        onboarding = true
        let w = show("onboarding", "Welcome to Dictator", NSSize(width: 560, height: 440),
                     resizable: false) {
            OnboardingView(done: { [weak self] in self?.finishOnboarding() })
        }
        // Closed half way: notifications speak again, and the cards come
        // back on the next launch because `onboarded` was never set.
        NotificationCenter.default.addObserver(
            forName: NSWindow.willCloseNotification, object: w, queue: .main) { [weak self] _ in
            onboarding = false
            self?.windows["onboarding"] = nil
        }
    }

    func finishOnboarding() {
        Prefs.onboarded = true
        windows["onboarding"]?.close()
        // Then the Hub, once, on Home. After this the app is the menu bar
        // item and the key.
        showHub(.home)
    }
}
