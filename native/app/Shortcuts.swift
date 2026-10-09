// How the rest of the system reaches the app: the pill's buttons, through
// dictator:// URLs, and two global shortcuts, Option-M for the Notetaker and
// Option-S for the Scratchpad.
//
// The shortcuts are Carbon hot keys (RegisterEventHotKey), which need no
// permission at all: the system delivers exactly that key combination to us
// and nothing else, unlike an event tap that sees every keystroke. Which are
// on is in indicator.json ("shortcuts"), written by Settings through
// `dictator indicator shortcut`, and read here directly, like status.json. A
// shortcut that is off is unregistered, so the keys type what they always
// typed (ß and µ on a US layout).
//
// The pill finds the app by STATE/app.lock: the app holds an flock on it for
// its whole life and writes its own bundle path into it. The kernel drops the
// lock when the app dies, so a crashed app is never mistaken for a running one.

import AppKit
import Carbon.HIToolbox

enum Shortcut: UInt32 {
    case notetaker = 1, scratchpad = 2

    var keyCode: UInt32 {
        switch self {
        case .notetaker: return UInt32(kVK_ANSI_M)
        case .scratchpad: return UInt32(kVK_ANSI_S)
        }
    }
    var name: String { self == .notetaker ? "notetaker" : "scratchpad" }
}

final class Hotkeys {
    static let shared = Hotkeys()
    private var refs: [Shortcut: EventHotKeyRef] = [:]
    private var handler: EventHandlerRef?
    var actions: [Shortcut: () -> Void] = [:]
    private var settingsAt: Date?

    private func install() {
        guard handler == nil else { return }
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                                 eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, event, _ in
            var id = EventHotKeyID()
            let err = GetEventParameter(event, EventParamName(kEventParamDirectObject),
                                        EventParamType(typeEventHotKeyID), nil,
                                        MemoryLayout<EventHotKeyID>.size, nil, &id)
            guard err == noErr, let s = Shortcut(rawValue: id.id) else { return OSStatus(eventNotHandledErr) }
            DispatchQueue.main.async { Hotkeys.shared.fire(s) }
            return noErr
        }, 1, &spec, nil, &handler)
    }

    private func fire(_ s: Shortcut) {
        // Checked again at the moment of firing, so a shortcut switched off a
        // second ago cannot act even if its unregister were somehow missed.
        guard IndicatorFile.read().shortcuts[s.name] ?? true else { return }
        actions[s]?()
    }

    /// Register what indicator.json says is on, unregister the rest.
    func apply() {
        if fake { return }       // fake mode must never grab keys from the real app
        install()
        let want = IndicatorFile.read().shortcuts
        for s in [Shortcut.notetaker, .scratchpad] {
            let on = want[s.name] ?? true
            if on && refs[s] == nil {
                var ref: EventHotKeyRef?
                let id = EventHotKeyID(signature: OSType(0x4463_7472), id: s.rawValue)  // 'Dctr'
                let err = RegisterEventHotKey(s.keyCode, UInt32(optionKey), id,
                                              GetApplicationEventTarget(), 0, &ref)
                if err == noErr, let r = ref { refs[s] = r }
                else { NSLog("dictator: could not register the \(s.name) shortcut (\(err))") }
            } else if !on, let r = refs[s] {
                UnregisterEventHotKey(r)
                refs[s] = nil
            }
        }
    }

    /// Called every second with the rest of the refresh: re-apply only when
    /// indicator.json changed, which is cheap to ask.
    func refreshIfChanged() {
        let m = IndicatorFile.mtime()
        guard m != settingsAt else { return }
        settingsAt = m
        apply()
    }
}

/// indicator.json, the parts the app reads directly. Written only through
/// `dictator indicator`; see dictator/orbnative.py.
struct IndicatorFile {
    var position = "top"
    var idle = "hover"
    var controls = ["dictate", "notetaker", "scratchpad"]
    var shortcuts = ["notetaker": true, "scratchpad": true]

    static var url: URL {
        (fake ? fixturesDir : stateDir).appendingPathComponent("indicator.json")
    }

    static func read() -> IndicatorFile {
        var f = IndicatorFile()
        guard let d = try? Data(contentsOf: url),
              let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any] else { return f }
        f.apply(o)
        return f
    }

    /// The same rules as orbnative.settings(): anything unknown is the default.
    mutating func apply(_ o: [String: Any]) {
        if let p = o["position"] as? String, indicatorPositions.contains(where: { $0.0 == p }) {
            position = p
        }
        if let i = o["idle"] as? String, ["hover", "always", "hide"].contains(i) { idle = i }
        else if o["hide_idle"] as? Bool == true { idle = "hide" }
        if let c = o["controls"] as? [String] {
            controls = ["dictate", "notetaker", "scratchpad"].filter { c.contains($0) }
        }
        if let s = o["shortcuts"] as? [String: Any] {
            for k in ["notetaker", "scratchpad"] { if let v = s[k] as? Bool { shortcuts[k] = v } }
        }
    }

    static func mtime() -> Date? {
        (try? FileManager.default.attributesOfItem(atPath: url.path))?[.modificationDate] as? Date
    }
}

/// STATE/app.lock: held for the app's life, with its bundle path inside, so
/// the pill knows the app is there and which copy to open URLs in.
enum AppLock {
    private static var fd: Int32 = -1

    static func hold() {
        if fake || fd >= 0 { return }
        try? FileManager.default.createDirectory(at: stateDir, withIntermediateDirectories: true)
        let f = open(stateDir.appendingPathComponent("app.lock").path, O_RDWR | O_CREAT, 0o600)
        guard f >= 0 else { return }
        guard flock(f, LOCK_EX | LOCK_NB) == 0 else {
            // Another copy of the app is running on this state directory and
            // already answers the pill.
            close(f)
            return
        }
        fd = f
        let path = Array((Bundle.main.bundlePath + "\n").utf8)
        ftruncate(f, 0)
        _ = path.withUnsafeBytes { pwrite(f, $0.baseAddress, $0.count, 0) }
    }
}
