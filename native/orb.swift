// dictator-orb: a small pill that tells the truth about your microphone, and
// the few buttons that go with it.
//
// THE PROMISE. Only one look says "the microphone is open":
//
//   listening   a dark pill with moving bars        our microphone IS open
//   hands free  the same, with a cross at one end   our microphone IS open, and
//               and a check at the other            stays open until you finish
//   thinking    a dark pill with three dots         closed; words being worked out
//   nothing     no pill at all                      closed (the default)
//
// Listening (and hands free, which is listening drawn with two buttons) is
// drawn if and only if our microphone is truly open. Thinking and nothing can
// never be shown while it is: when the mic is ours and hot, the look is
// listening whatever hud.json says, and listening is always on screen, in
// every setting. hud.json only decides HOW listening is drawn (how loud, and
// whether it is a hands free session), never WHETHER.
//
// WHILE NOBODY IS DICTATING, indicator.json's "idle" decides:
//
//   hover   (default) nothing is drawn. Move the pointer to the pill's place
//           (a zone a little larger than it) and it fades in with its buttons;
//           move away and it fades out about a second later.
//   always  the small faint grey pill stays on screen, as before; hovering it
//           shows the buttons.
//   hide    nothing, and no buttons; it appears only while dictating.
//
// So no pill means our microphone is closed, or this helper is not running. It
// says nothing about OTHER apps: another program may have the microphone while
// we draw nothing; macOS's own orange dot is the indicator for that.
//
// THREE LAYERS decide "is our mic open", because the daemon must not be able
// to lie about itself:
//
//   presence   is a mic actually capturing?   CoreAudio
//              kAudioDevicePropertyDeviceIsRunningSomewhere. Needs no
//              permission, is event driven, and is the same signal behind the
//              orange dot macOS shows you. The daemon cannot fake it.
//   ownership  is it OURS?                    an flock on mic.lock. The kernel
//              drops it on process death including SIGKILL, so there is no
//              staleness window to be wrong in.
//   detail     which state, and how loud?     hud.json, trusted for appearance
//              only, never for whether to draw listening.
//
// Listening if and only if presence AND ownership. If the mic is hot but the
// detail is stale we still draw listening: we know the mic is open, we just do
// not know how loud, and over-reporting is the only safe direction to err.
//
// WHERE. One of eight places on the screen you are working on: top centre
// (the default, under the notch or the menu bar, never in the notch: that is
// the camera housing and has no pixels), bottom centre above the Dock, the
// middle of the left and right edges, and the four corners. Always inside the
// screen's visible frame. At top and bottom centre the pill and its buttons
// lie HORIZONTALLY; everywhere else, the two edge centres and all four
// corners, they stand VERTICALLY along the side of the screen, and the
// waveform's bars turn with them.
//
// THE BUTTONS, shown on hover in the order of indicator.json's "controls":
//
//   the pill itself (dictate)   click: start hands free dictation; click again,
//                               or press the key once, to finish and paste
//   notetaker                   start or stop recording a meeting, through the
//                               app (which asks for consent the first time);
//                               red while a meeting records
//   scratchpad                  open the Scratchpad window in the app
//
// They stack from the pill toward the middle of the screen. Hovering one slides
// out a label with its name and shortcut, on the inside: left of the stack at
// the right edge, right of it at the left edge, below it at the top, above it
// at the bottom. During a hands free session the pill carries its own cross
// (stop and throw away, as Escape) and check (stop, transcribe and paste).
//
// HOW A CLICK GETS ANYWHERE. Dictation commands go to the loop as one datagram
// on STATE/dictate.sock (dictator_core/control.py), which hands them to the key
// listener, so a session started by a click and one started by a double tap
// are the same session. Notetaker and Scratchpad open dictator://notetaker and
// dictator://scratchpad in the app whose path is in STATE/app.lock, and only
// while the app holds that lock; without the app they are not shown.
//
// MOVING IT. Drag the pill or any button: a press that moves more than three
// points is a drag, anything less is a click. While it moves, the eight places
// are drawn as slots in their own orientation and the nearest is highlighted;
// the pill turns to match the place it is over. Let go and it snaps there. The
// choice is written to STATE/indicator.json, which the app's Settings and
// `dictator indicator` also write; this process watches the file.
//
// FOCUS. The window is a non-activating panel that never becomes key, so a
// click on any button leaves the cursor in the app you were typing into, which
// is where the words are pasted. The label and the drop slots ignore the mouse.
//
// LOOKING AT IT WITHOUT A SCREEN. DICTATOR_ORB_SNAPSHOT=DIR draws every look,
// both orientations, the buttons, a label, the recording and hands free states
// and the drop slots on a made-up screen into PNGs in DIR, then exits,
// touching no microphone and no state. Needs no Screen Recording permission.

import Cocoa
import CoreAudio
import QuartzCore

// ---------------------------------------------------------------- geometry

let PAD: CGFloat = 2            // between the pill and its window's edge
let TOP_GAP: CGFloat = 4        // under the notch or the menu bar, as before
let MARGIN: CGFloat = 12        // from the Dock and the side edges
let BTN: CGFloat = 28           // a round button
let GAP: CGFloat = 6            // between the pill and a button, and buttons
let HOVER_SLACK: CGFloat = 14   // the hover zone reaches this far past the stack

enum Look { case idle, listening, thinking }

enum Orientation { case horizontal, vertical }

/// What the pill itself is drawn as. Decided from the look, the setting and
/// whether the pointer is near; see App.mode().
enum PillMode: Equatable {
    case faint          // idle, "always": the small grey pill
    case mic            // idle and revealed, dictate on: a dark pill with a mic
    case plain          // idle and revealed, dictate off: a dark empty pill
    case listening, handsFree, thinking
}

/// The pill's size for a mode, lying along the orientation. The dictating
/// looks and the revealed one share one size so nothing jumps between them;
/// hands free is longer, to carry its two buttons.
func pillSize(_ m: PillMode, _ o: Orientation) -> NSSize {
    let s: NSSize
    switch m {
    case .faint: s = NSSize(width: 44, height: 10)
    case .mic, .plain, .listening, .thinking: s = NSSize(width: 84, height: 28)
    case .handsFree: s = NSSize(width: 136, height: 32)
    }
    return o == .horizontal ? s : NSSize(width: s.height, height: s.width)
}

/// The eight places. Raw values are what indicator.json, `dictator indicator`
/// and the app's picker use (orbnative.POSITIONS, same order).
enum Spot: String, CaseIterable {
    case top, bottom, left, right
    case topLeft = "top-left", topRight = "top-right"
    case bottomLeft = "bottom-left", bottomRight = "bottom-right"
}

enum Side { case left, right, above, below }
enum Dir { case right, up, down }

extension Spot {
    /// Only the two centres of the top and bottom lie flat. The corners sit
    /// on the side edges, so they stand up like the edge centres.
    var orientation: Orientation { (self == .top || self == .bottom) ? .horizontal : .vertical }

    /// Which way the buttons stack from the pill: toward the middle of the
    /// screen.
    var stack: Dir {
        switch self {
        case .top, .bottom: return .right
        case .bottomLeft, .bottomRight: return .up
        default: return .down
        }
    }

    /// Where a label slides out: the inside of the screen.
    var labelSide: Side {
        switch self {
        case .top: return .below
        case .bottom: return .above
        case .left, .topLeft, .bottomLeft: return .right
        case .right, .topRight, .bottomRight: return .left
        }
    }
}

/// The controls indicator.json can list. The dictate control is the pill
/// itself, so only the other two are separate buttons.
enum Control: String, CaseIterable { case dictate, notetaker, scratchpad }

extension NSScreen {
    /// The dead camera-housing rect, or nil on a screen without a notch.
    /// The auxiliary areas are the usable "ears"; the gap between them is the
    /// housing itself.
    var notchRect: NSRect? {
        guard let l = auxiliaryTopLeftArea, let r = auxiliaryTopRightArea,
              r.minX > l.maxX else { return nil }
        return NSRect(x: l.maxX, y: frame.maxY - safeAreaInsets.top,
                      width: r.minX - l.maxX, height: safeAreaInsets.top)
    }

    var displayID: CGDirectDisplayID? {
        (deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)
            .map { CGDirectDisplayID($0.uint32Value) }
    }
}

/// Where everything goes, in the window's own coordinates, and the window.
struct Frames: Equatable {
    var window: NSRect
    var pill: NSRect
    var buttons: [Control: NSRect]
}

/// A screen reduced to the three rects placement needs. A value rather than
/// an NSScreen so the snapshot can place things on a screen that does not
/// exist.
struct ScreenGeom {
    var frame: NSRect
    var visible: NSRect
    var notch: NSRect?

    init(frame: NSRect, visible: NSRect, notch: NSRect?) {
        self.frame = frame
        self.visible = visible
        self.notch = notch
    }
    init(_ s: NSScreen) { self.init(frame: s.frame, visible: s.visibleFrame, notch: s.notchRect) }

    /// The window frame for a pill of `pill` size alone at `spot`. Integral,
    /// because a half-point origin makes AppKit round the frame outward and
    /// the pill renders as a smudge.
    func windowFrame(_ spot: Spot, pill: NSSize) -> NSRect {
        let w = pill.width + PAD * 2, h = pill.height + PAD * 2
        let v = visible
        // With the menu bar set to hide, the visible frame reaches the top of
        // the screen, and on a notched screen that is inside the housing.
        let top = min(v.maxY, notch?.minY ?? .greatestFiniteMagnitude)
        let x: CGFloat, y: CGFloat
        switch spot {
        case .top:         x = (notch?.midX ?? v.midX) - w / 2; y = top - TOP_GAP - h
        case .bottom:      x = v.midX - w / 2;                  y = v.minY + MARGIN
        case .left:        x = v.minX + MARGIN;                 y = v.midY - h / 2
        case .right:       x = v.maxX - MARGIN - w;             y = v.midY - h / 2
        case .topLeft:     x = v.minX + MARGIN;                 y = top - TOP_GAP - h
        case .topRight:    x = v.maxX - MARGIN - w;             y = top - TOP_GAP - h
        case .bottomLeft:  x = v.minX + MARGIN;                 y = v.minY + MARGIN
        case .bottomRight: x = v.maxX - MARGIN - w;             y = v.minY + MARGIN
        }
        return NSRect(x: x.rounded(), y: y.rounded(), width: w, height: h)
    }

    /// The pill where it always was, and the buttons stacked from it toward
    /// the middle of the screen. Returned in the window's coordinates, with
    /// the window in global ones.
    func frames(_ spot: Spot, pill: NSSize, buttons: [Control]) -> Frames {
        let pr = windowFrame(spot, pill: pill).insetBy(dx: PAD, dy: PAD)
        var placed: [(Control, NSRect)] = []
        var edge = pr
        for c in buttons {
            let r: NSRect
            switch spot.stack {
            case .right: r = NSRect(x: edge.maxX + GAP, y: (pr.midY - BTN / 2).rounded(),
                                    width: BTN, height: BTN)
            case .down:  r = NSRect(x: (pr.midX - BTN / 2).rounded(), y: edge.minY - GAP - BTN,
                                    width: BTN, height: BTN)
            case .up:    r = NSRect(x: (pr.midX - BTN / 2).rounded(), y: edge.maxY + GAP,
                                    width: BTN, height: BTN)
            }
            placed.append((c, r))
            edge = r
        }
        var u = pr
        for (_, r) in placed { u = u.union(r) }
        let win = u.insetBy(dx: -PAD, dy: -PAD)
        var out: [Control: NSRect] = [:]
        for (c, r) in placed { out[c] = r.offsetBy(dx: -win.minX, dy: -win.minY) }
        return Frames(window: win, pill: pr.offsetBy(dx: -win.minX, dy: -win.minY), buttons: out)
    }

    /// The place whose centre is closest to `p`. Measured against slots of
    /// each place's own orientation, whatever the pill looks like now, so the
    /// answer does not change because the pill happened to be idle.
    func nearest(to p: NSPoint) -> Spot {
        func d(_ s: Spot) -> CGFloat {
            let f = windowFrame(s, pill: pillSize(.listening, s.orientation))
            return hypot(f.midX - p.x, f.midY - p.y)
        }
        return Spot.allCases.min { d($0) < d($1) }!
    }
}

/// The screen the person is actually working on.
///
/// `NSScreen.main` is AppKit's name for the screen with the KEYBOARD FOCUS,
/// not the built-in one, so on a desk with an external display the pill
/// follows the window you are typing into rather than sitting on a laptop
/// that may be closed. An indicator you have to go and look for is not an
/// indicator. Never falls back to the global origin: a transparent window at
/// (0,0) sits behind the Dock and is indistinguishable from one that never
/// appeared.
func pickScreen() -> NSScreen? {
    if let focused = NSScreen.main { return focused }
    // No focused window, which happens between apps. The pointer is the next
    // best guess at where somebody is looking.
    if let under = screenUnderMouse() { return under }
    if let notched = NSScreen.screens.first(where: { $0.notchRect != nil }) {
        return notched
    }
    return NSScreen.screens.first
}

func screenUnderMouse() -> NSScreen? {
    let mouse = NSEvent.mouseLocation
    return NSScreen.screens.first { NSMouseInRect(mouse, $0.frame, false) }
}

// ---------------------------------------------------------------- settings

/// Same rule as core.state_dir(): DICTATOR_STATE, which orbnative passes
/// down, else ~/.dictator. This was hardcoded once, so a loop started with
/// DICTATOR_STATE elsewhere had an orb watching some other mic.lock.
let STATE: URL = {
    if let s = ProcessInfo.processInfo.environment["DICTATOR_STATE"],
       !s.trimmingCharacters(in: .whitespaces).isEmpty {
        return URL(fileURLWithPath: (s as NSString).expandingTildeInPath)
    }
    return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".dictator")
}()

enum IdleMode: String { case hover, always, hide }

/// indicator.json, as orbnative.settings() reads it.
struct IndicatorSettings: Equatable {
    var spot: Spot = .top
    var idle: IdleMode = .hover
    var controls: [Control] = Control.allCases
    var shortcutNotetaker = true
    var shortcutScratchpad = true

    static var url: URL { STATE.appendingPathComponent("indicator.json") }

    static func raw() -> [String: Any] {
        guard let d = try? Data(contentsOf: url),
              let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any]
        else { return [:] }
        return o
    }

    /// Anything missing or unknown is the default, as in orbnative.settings().
    static func read() -> IndicatorSettings {
        let o = raw()
        var s = IndicatorSettings()
        if let p = o["position"] as? String, let spot = Spot(rawValue: p) { s.spot = spot }
        if let i = o["idle"] as? String, let m = IdleMode(rawValue: i) {
            s.idle = m
        } else if o["hide_idle"] as? Bool == true {
            s.idle = .hide
        }
        if let c = o["controls"] as? [String] {
            s.controls = Control.allCases.filter { c.contains($0.rawValue) }
        }
        if let sc = o["shortcuts"] as? [String: Any] {
            if let v = sc["notetaker"] as? Bool { s.shortcutNotetaker = v }
            if let v = sc["scratchpad"] as? Bool { s.shortcutScratchpad = v }
        }
        return s
    }

    /// Write the position back, keeping every other key, atomically: the
    /// app may be reading the same file.
    static func save(spot: Spot) {
        var o = raw()
        o["position"] = spot.rawValue
        guard let d = try? JSONSerialization.data(withJSONObject: o, options: [.prettyPrinted])
        else { return }
        try? FileManager.default.createDirectory(at: STATE, withIntermediateDirectories: true)
        let tmp = STATE.appendingPathComponent("indicator.json.tmp")
        do {
            try d.write(to: tmp)
            _ = rename(tmp.path, url.path)
        } catch {
            FileHandle.standardError.write("orb: could not save the position: \(error)\n"
                .data(using: .utf8)!)
        }
    }

    static func mtime() -> Date? {
        (try? FileManager.default.attributesOfItem(atPath: url.path))?[.modificationDate] as? Date
    }
}

/// The hold key, for the labels. orbnative passes it as DICTATOR_KEY.
let KEY_NAME: String = {
    switch ProcessInfo.processInfo.environment["DICTATOR_KEY"] ?? "fn" {
    case "rightcmd": return "right ⌘"
    case "rightopt": return "right ⌥"
    case "leftcmd": return "left ⌘"
    default: return "fn"
    }
}()

// ---------------------------------------------------------------- truth

/// Layer 1. Is any input device actually running? Event driven, no polling,
/// no permission prompt: reading device STATE is not reading audio DATA.
final class MicPresence {
    private var device = AudioDeviceID(0)
    private var addr = AudioObjectPropertyAddress(
        mSelector: kAudioDevicePropertyDeviceIsRunningSomewhere,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain)
    private var block: AudioObjectPropertyListenerBlock?
    private let onChange: () -> Void

    init(onChange: @escaping () -> Void) {
        self.onChange = onChange
        attach()
        // The default input can change under us when a headset connects, which
        // leaves a listener bound to a device nobody is using. That is the
        // easiest way to end up with a silently wrong orb, so watch for it.
        var d = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        AudioObjectAddPropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject), &d, DispatchQueue.main) { [weak self] _, _ in
                self?.reattach()
            }
    }

    private func defaultInput() -> AudioDeviceID {
        var id = AudioDeviceID(0)
        var sz = UInt32(MemoryLayout<AudioDeviceID>.size)
        var a = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject),
                                   &a, 0, nil, &sz, &id)
        return id
    }

    private func attach() {
        device = defaultInput()
        guard device != 0 else { return }
        let b: AudioObjectPropertyListenerBlock = { [weak self] _, _ in self?.onChange() }
        block = b
        AudioObjectAddPropertyListenerBlock(device, &addr, DispatchQueue.main, b)
    }

    private func reattach() {
        if device != 0, let b = block {
            AudioObjectRemovePropertyListenerBlock(device, &addr, DispatchQueue.main, b)
        }
        attach()
        onChange()
    }

    /// True while something, anyone, is capturing from the default input.
    var isHot: Bool {
        guard device != 0 else { return false }
        var v = UInt32(0)
        var sz = UInt32(MemoryLayout<UInt32>.size)
        let err = AudioObjectGetPropertyData(device, &addr, 0, nil, &sz, &v)
        return err == noErr && v != 0
    }
}

/// Layer 2. Is the open mic ours? Acquiring the lock proves nobody holds it.
func weOwnTheMic() -> Bool {
    let path = STATE.appendingPathComponent("mic.lock").path
    let fd = open(path, O_RDONLY | O_CREAT, 0o644)
    guard fd >= 0 else { return false }
    defer { close(fd) }
    if flock(fd, LOCK_EX | LOCK_NB) == 0 {
        flock(fd, LOCK_UN)
        return false            // we took it, so the daemon does not hold it
    }
    return errno == EWOULDBLOCK  // still held: the daemon is alive and capturing
}

/// Layer 3. Appearance only. Never consulted about whether to draw listening.
struct Detail { var phase = "capturing"; var level: CGFloat = 0; var fresh = false }

func readDetail() -> Detail {
    var d = Detail()
    guard let raw = try? Data(contentsOf: STATE.appendingPathComponent("hud.json")),
          let j = (try? JSONSerialization.jsonObject(with: raw)) as? [String: Any]
    else { return d }
    let ts = (j["ts"] as? Double) ?? 0
    d.fresh = Date().timeIntervalSince1970 - ts < 1.0
    d.level = CGFloat((j["level"] as? Double) ?? 0)
    if let p = j["phase"] as? String { d.phase = p }
    return d
}

/// The whole decision, in one pure function so it can be read in one place.
/// Listening exactly when our mic is open; thinking only when it is not.
func decide(hot: Bool, ours: Bool, detail d: Detail) -> Look {
    if hot && ours { return .listening }
    // Transcribing happens AFTER the key is released, so the microphone is
    // already closed while the user waits for their words. A fresh
    // "thinking" shows the dots so the key does not appear to have done
    // nothing. The dots do not look like listening, and listening is not
    // reachable down here.
    if d.fresh && (d.phase == "thinking" || d.phase == "working") { return .thinking }
    return .idle
}

// ---------------------------------------------------------------- the others

/// Is somebody holding this flock? Asked by trying to take it, which the
/// kernel answers truthfully even for a holder killed with SIGKILL.
func lockHeld(_ name: String) -> Bool {
    let fd = open(STATE.appendingPathComponent(name).path, O_RDONLY)
    guard fd >= 0 else { return false }
    defer { close(fd) }
    if flock(fd, LOCK_EX | LOCK_NB) == 0 {
        flock(fd, LOCK_UN)
        return false
    }
    return errno == EWOULDBLOCK
}

/// One command to the dictation loop (dictator_core/control.py): toggle, finish or
/// cancel. A datagram: nobody bound means it fails at once, never reaches a
/// stranger.
@discardableResult
func tellLoop(_ word: String) -> Bool {
    let path = STATE.appendingPathComponent("dictate.sock").path
    var addr = sockaddr_un()
    addr.sun_family = sa_family_t(AF_UNIX)
    let bytes = Array(path.utf8)
    guard bytes.count < MemoryLayout.size(ofValue: addr.sun_path) else { return false }
    withUnsafeMutableBytes(of: &addr.sun_path) { p in
        p.copyBytes(from: bytes)
        p[bytes.count] = 0
    }
    let fd = socket(AF_UNIX, SOCK_DGRAM, 0)
    guard fd >= 0 else { return false }
    defer { close(fd) }
    let msg = Array(word.utf8)
    let n = withUnsafePointer(to: &addr) { a in
        a.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
            sendto(fd, msg, msg.count, 0, sa, socklen_t(MemoryLayout<sockaddr_un>.size))
        }
    }
    return n == msg.count
}

/// The app, if it is running: it holds STATE/app.lock and writes its own
/// bundle path into it. The Notetaker and Scratchpad buttons need it.
func runningApp() -> URL? {
    guard lockHeld("app.lock"),
          let s = try? String(contentsOf: STATE.appendingPathComponent("app.lock"), encoding: .utf8)
    else { return nil }
    let p = s.trimmingCharacters(in: .whitespacesAndNewlines)
    return p.hasSuffix(".app") ? URL(fileURLWithPath: p) : nil
}

/// Is a meeting being recorded: meetings/current names it, its status.json
/// says recording, and the recorder's pid is alive. The same three questions
/// meeting.running() asks.
func meetingRecording() -> Bool {
    let m = STATE.appendingPathComponent("meetings")
    guard let id = try? String(contentsOf: m.appendingPathComponent("current"), encoding: .utf8)
    else { return false }
    let st = m.appendingPathComponent(id.trimmingCharacters(in: .whitespacesAndNewlines))
        .appendingPathComponent("status.json")
    guard let d = try? Data(contentsOf: st),
          let j = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any],
          j["state"] as? String == "recording",
          let pid = (j["pid"] as? NSNumber)?.int32Value, pid > 0 else { return false }
    return kill(pid, 0) == 0 || errno == EPERM
}

/// Open dictator://what in the running app. `activate` brings it forward,
/// which the Scratchpad wants and the Notetaker does not.
func openInApp(_ what: String, activate: Bool) {
    guard let app = runningApp(), let url = URL(string: "dictator://" + what) else { return }
    let cfg = NSWorkspace.OpenConfiguration()
    cfg.activates = activate
    NSWorkspace.shared.open([url], withApplicationAt: app, configuration: cfg) { _, err in
        if let e = err {
            FileHandle.standardError.write("orb: could not open \(url): \(e)\n".data(using: .utf8)!)
        }
    }
}

// ---------------------------------------------------------------- drawing

func symbol(_ name: String, _ size: CGFloat, _ color: NSColor = .white,
            weight: NSFont.Weight = .semibold) -> NSImage? {
    let cfg = NSImage.SymbolConfiguration(pointSize: size, weight: weight)
        .applying(NSImage.SymbolConfiguration(paletteColors: [color]))
    return NSImage(systemSymbolName: name, accessibilityDescription: nil)?
        .withSymbolConfiguration(cfg)
}

func drawSymbol(_ img: NSImage?, in r: NSRect) {
    guard let i = img else { return }
    let s = i.size
    i.draw(in: NSRect(x: (r.midX - s.width / 2).rounded(), y: (r.midY - s.height / 2).rounded(),
                      width: s.width, height: s.height))
}

let RED = NSColor(srgbRed: 0.90, green: 0.22, blue: 0.20, alpha: 1)
let TEAL = NSColor(srgbRed: 0.063, green: 0.490, blue: 0.431, alpha: 1)

/// What is under the pointer, or was pressed.
enum Hit: Equatable { case pill, cancel, finish, button(Control) }

protocol OrbDelegate: AnyObject {
    func pressed(_ h: Hit)
    func dragMoved(mouse: NSPoint)
    func dragEnded(mouse: NSPoint)
    func hovering(_ h: Hit?)
}

/// The pill and its buttons, drawn in one view. Drawn rather than built from
/// layers so the live window and the snapshot are the same code.
final class OrbView: NSView {
    var mode: PillMode = .faint { didSet { if mode != oldValue { modeChanged() } } }
    var orientation: Orientation = .horizontal { didSet { needsDisplay = true } }
    var frames = Frames(window: .zero, pill: .zero, buttons: [:]) { didSet { needsDisplay = true } }
    var recording = false { didSet { if recording != oldValue { needsDisplay = true } } }
    private(set) var hovered: Hit?
    weak var delegate: OrbDelegate?

    private var link: CADisplayLink?
    private var level: CGFloat = 0          // smoothed
    private var target: CGFloat = 0
    private var phase: CGFloat = 0          // wobble, and the dots' pulse

    private var downAt: NSPoint?
    private var downHit: Hit?
    private(set) var dragging = false

    private var reduceMotion: Bool { NSWorkspace.shared.accessibilityDisplayShouldReduceMotion }
    private var opaqueBG: Bool { NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency }
    private var contrast: Bool { NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast }

    override init(frame: NSRect) {
        super.init(frame: frame)
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification,
            object: nil, queue: .main) { [weak self] _ in self?.needsDisplay = true }
    }
    required init?(coder: NSCoder) { nil }

    private func modeChanged() {
        stopLink()
        if mode == .listening || mode == .handsFree || (mode == .thinking && !reduceMotion) {
            startLink()
        }
        needsDisplay = true
    }

    // ------------------------------------------------------------ geometry

    /// The cross and the check of a hands free pill, at its two ends: left
    /// and right lying down, top and bottom standing up.
    func endButtons() -> (cancel: NSRect, finish: NSRect)? {
        guard mode == .handsFree else { return nil }
        let r = frames.pill
        let d = min(r.width, r.height) - 8
        if orientation == .horizontal {
            let y = (r.midY - d / 2).rounded()
            return (NSRect(x: r.minX + 4, y: y, width: d, height: d),
                    NSRect(x: r.maxX - 4 - d, y: y, width: d, height: d))
        }
        let x = (r.midX - d / 2).rounded()
        return (NSRect(x: x, y: r.maxY - 4 - d, width: d, height: d),
                NSRect(x: x, y: r.minY + 4, width: d, height: d))
    }

    func hit(_ p: NSPoint) -> Hit? {
        if let e = endButtons() {
            if e.cancel.insetBy(dx: -3, dy: -3).contains(p) { return .cancel }
            if e.finish.insetBy(dx: -3, dy: -3).contains(p) { return .finish }
        }
        if frames.pill.insetBy(dx: -2, dy: -2).contains(p) { return .pill }
        for (c, r) in frames.buttons where r.insetBy(dx: -2, dy: -2).contains(p) {
            return .button(c)
        }
        return nil
    }

    /// The rect of a hit, for placing its label.
    func rect(of h: Hit) -> NSRect {
        switch h {
        case .pill: return frames.pill
        case .cancel: return endButtons()?.cancel ?? frames.pill
        case .finish: return endButtons()?.finish ?? frames.pill
        case .button(let c): return frames.buttons[c] ?? frames.pill
        }
    }

    // ------------------------------------------------------------ drawing

    override func draw(_ dirty: NSRect) {
        drawPill()
        for c in Control.allCases {
            if let r = frames.buttons[c] { drawButton(c, r) }
        }
    }

    private func capsule(_ r: NSRect) -> NSBezierPath {
        let rad = min(r.width, r.height) / 2
        return NSBezierPath(roundedRect: r, xRadius: rad, yRadius: rad)
    }

    private var darkFill: NSColor { NSColor.black.withAlphaComponent(opaqueBG ? 1 : 0.86) }
    private var rim: NSColor { NSColor.white.withAlphaComponent(contrast ? 0.45 : 0.16) }

    private func drawPill() {
        let r = frames.pill
        guard r.width > 0 else { return }
        let path = capsule(r.insetBy(dx: 0.5, dy: 0.5))
        path.lineWidth = 0.75
        switch mode {
        case .faint:
            // Neutral grey and faint: findable, not noticed. A light rim
            // keeps it visible on a dark wallpaper, the grey on a light one.
            NSColor(white: 0.40, alpha: opaqueBG ? 1 : (contrast ? 0.75 : 0.45)).setFill()
            path.fill()
            NSColor.white.withAlphaComponent(0.45).setStroke()
            path.stroke()
            return
        case .mic, .plain:
            (hovered == .pill && mode == .mic ? NSColor(white: 0.17, alpha: opaqueBG ? 1 : 0.94)
                                              : darkFill).setFill()
        default:
            darkFill.setFill()
        }
        path.fill()
        rim.setStroke()
        path.stroke()

        switch mode {
        case .mic:
            drawSymbol(symbol("mic.fill", 13), in: r)
        case .listening:
            drawBars(in: r, count: 11)
        case .handsFree:
            guard let e = endButtons() else { return }
            // The cross: grey, the quiet way out. The check: white, the
            // one you came to press.
            let c = NSBezierPath(ovalIn: e.cancel)
            NSColor(white: hovered == .cancel ? 0.42 : 0.30, alpha: 1).setFill()
            c.fill()
            drawSymbol(symbol("xmark", 10, .white, weight: .bold), in: e.cancel)
            let f = NSBezierPath(ovalIn: e.finish)
            NSColor(white: hovered == .finish ? 0.86 : 1.0, alpha: 1).setFill()
            f.fill()
            drawSymbol(symbol("checkmark", 10, .black, weight: .bold), in: e.finish)
            // The waveform between them.
            let inner: NSRect
            if orientation == .horizontal {
                inner = NSRect(x: e.cancel.maxX + 6, y: r.minY, width: e.finish.minX - e.cancel.maxX - 12,
                               height: r.height)
            } else {
                inner = NSRect(x: r.minX, y: e.finish.maxY + 6, width: r.width,
                               height: e.cancel.minY - e.finish.maxY - 12)
            }
            drawBars(in: inner, count: 9, ends: false)
        case .thinking:
            let ds: CGFloat = 5
            let still: [CGFloat] = [1.0, 0.65, 0.35]
            for i in 0..<3 {
                let off = CGFloat(i - 1) * 10
                let c = orientation == .horizontal ? NSPoint(x: r.midX + off, y: r.midY)
                                                   : NSPoint(x: r.midX, y: r.midY - off)
                let a = reduceMotion || link == nil ? still[i]
                    : 0.3 + 0.7 * max(0, sin(phase * 0.45 - CGFloat(i) * 0.9))
                NSColor.white.withAlphaComponent(a).setFill()
                NSBezierPath(ovalIn: NSRect(x: c.x - ds / 2, y: c.y - ds / 2, width: ds, height: ds)).fill()
            }
        default:
            break
        }
    }

    /// Bars along the pill, not a dot: a row of them shows the SHAPE of what
    /// you are saying. Lying down they are upright strokes in a row; standing
    /// up they turn into flat strokes stacked top to bottom, like the pill.
    /// The middle ones react most, which is what a voice looks like and what
    /// stops it reading as a progress bar.
    private func drawBars(in r: NSRect, count n: Int, ends: Bool = true) {
        let thick: CGFloat = 2.5
        let along = orientation == .horizontal ? r.width : r.height
        let across = orientation == .horizontal ? r.height : r.width
        let span = along - (ends ? across : 0)          // clear of the round ends
        let gap = (span - CGFloat(n) * thick) / CGFloat(n - 1)
        let full = across - 10
        let mid = CGFloat(n - 1) / 2
        let lvl = level
        NSColor.white.withAlphaComponent(0.95).setFill()
        for i in 0..<n {
            let d = abs(CGFloat(i) - mid) / max(mid, 1)
            let shape = 1.0 - d * 0.6
            let wobble = reduceMotion ? 1 : 0.78 + 0.22 * sin(phase + CGFloat(i) * 1.7)
            let k = max(0.18, 0.18 + 0.82 * min(1, lvl * 1.4) * shape * wobble)
            let len = (full * k).rounded()
            let start = (ends ? across / 2 : 0) + CGFloat(i) * (thick + gap)
            let b: NSRect
            if orientation == .horizontal {
                b = NSRect(x: r.minX + start, y: r.midY - len / 2, width: thick, height: len)
            } else {
                b = NSRect(x: r.midX - len / 2, y: r.maxY - start - thick, width: len, height: thick)
            }
            NSBezierPath(roundedRect: b, xRadius: thick / 2, yRadius: thick / 2).fill()
        }
    }

    private func drawButton(_ c: Control, _ r: NSRect) {
        let on = hovered == .button(c)
        let p = NSBezierPath(ovalIn: r.insetBy(dx: 0.5, dy: 0.5))
        p.lineWidth = 0.75
        if c == .notetaker && recording {
            RED.setFill()
            p.fill()
            NSColor.white.withAlphaComponent(0.35).setStroke()
            p.stroke()
            drawSymbol(symbol("stop.fill", 10), in: r)
            return
        }
        (on ? NSColor(white: 0.20, alpha: opaqueBG ? 1 : 0.95) : darkFill).setFill()
        p.fill()
        rim.setStroke()
        p.stroke()
        switch c {
        case .notetaker:
            // A record button: a ring with a red dot, like a camera's.
            let dot = r.insetBy(dx: r.width * 0.34, dy: r.height * 0.34)
            RED.setFill()
            NSBezierPath(ovalIn: dot).fill()
            let ring = NSBezierPath(ovalIn: r.insetBy(dx: r.width * 0.24, dy: r.height * 0.24))
            ring.lineWidth = 1.5
            NSColor.white.withAlphaComponent(0.9).setStroke()
            ring.stroke()
        case .scratchpad:
            drawSymbol(symbol("square.and.pencil", 12), in: r.offsetBy(dx: 0.5, dy: 0.5))
        case .dictate:
            drawSymbol(symbol("mic.fill", 12), in: r)
        }
    }

    // ------------------------------------------------------------ animation

    func feed(_ v: CGFloat) { target = max(0, min(1, v)) }

    /// For the snapshot: a level and a phase, drawn now, no display link.
    func freeze(level v: CGFloat, phase p: CGFloat) {
        level = v; target = v; phase = p
        stopLink()
        needsDisplay = true
    }

    private func startLink() {
        guard link == nil, window != nil else { return }
        let l = displayLink(target: self, selector: #selector(step))
        // A range, not a fixed rate: the system picks the efficient one, and
        // 30fps is ample for a level meter whose release envelope is 180ms.
        l.preferredFrameRateRange = CAFrameRateRange(minimum: 20, maximum: 30, preferred: 30)
        l.add(to: .main, forMode: .common)
        link = l
    }
    private func stopLink() { link?.invalidate(); link = nil }

    @objc private func step() {
        // Fast attack so it feels instant, slow release so it does not strobe.
        let coeff: CGFloat = target > level ? 0.55 : 0.12
        level += (target - level) * coeff
        phase += 0.35
        needsDisplay = true
    }

    func pause() { stopLink() }
    func resume() { modeChanged() }

    // ------------------------------------------------------------ the mouse

    /// The first click lands even though this panel never becomes key.
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach { removeTrackingArea($0) }
        addTrackingArea(NSTrackingArea(rect: bounds,
                                       options: [.mouseEnteredAndExited, .mouseMoved,
                                                 .activeAlways, .inVisibleRect],
                                       owner: self, userInfo: nil))
    }

    func setHovered(_ h: Hit?) {
        guard h != hovered else { return }
        hovered = h
        needsDisplay = true
        delegate?.hovering(h)
    }

    override func mouseMoved(with e: NSEvent) {
        if !dragging { setHovered(hit(convert(e.locationInWindow, from: nil))) }
    }
    override func mouseEntered(with e: NSEvent) { mouseMoved(with: e) }
    override func mouseExited(with e: NSEvent) { if !dragging { setHovered(nil) } }

    override func mouseDown(with e: NSEvent) {
        downAt = NSEvent.mouseLocation
        downHit = hit(convert(e.locationInWindow, from: nil))
        dragging = false
    }

    override func mouseDragged(with e: NSEvent) {
        guard let start = downAt else { return }
        let p = NSEvent.mouseLocation
        // A few points of slack, so a click with a shaky hand is not a move.
        if !dragging && hypot(p.x - start.x, p.y - start.y) < 3 { return }
        if !dragging { setHovered(nil) }
        dragging = true
        delegate?.dragMoved(mouse: p)
    }

    override func mouseUp(with e: NSEvent) {
        defer { downAt = nil; downHit = nil; dragging = false }
        if dragging {
            delegate?.dragEnded(mouse: NSEvent.mouseLocation)
        } else if let h = downHit, h == hit(convert(e.locationInWindow, from: nil)) {
            delegate?.pressed(h)
        }
    }
}

// ---------------------------------------------------------------- the label

/// A dark rounded label: the feature's name, then its shortcut in bold.
final class LabelView: NSView {
    var text = NSAttributedString()

    static func make(_ name: String, _ shortcut: String?) -> NSAttributedString {
        let s = NSMutableAttributedString(string: name, attributes: [
            .font: NSFont.systemFont(ofSize: 12, weight: .medium),
            .foregroundColor: NSColor.white.withAlphaComponent(0.92)])
        if let k = shortcut, !k.isEmpty {
            s.append(NSAttributedString(string: "   " + k, attributes: [
                .font: NSFont.systemFont(ofSize: 12, weight: .bold),
                .foregroundColor: NSColor.white]))
        }
        return s
    }

    var fit: NSSize {
        let t = text.size()
        return NSSize(width: ceil(t.width) + 22, height: ceil(t.height) + 12)
    }

    override func draw(_ dirty: NSRect) {
        let r = bounds.insetBy(dx: 0.5, dy: 0.5)
        let p = NSBezierPath(roundedRect: r, xRadius: 8, yRadius: 8)
        NSColor(white: 0.08, alpha: NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency
                ? 1 : 0.92).setFill()
        p.fill()
        NSColor.white.withAlphaComponent(0.14).setStroke()
        p.lineWidth = 0.75
        p.stroke()
        let t = text.size()
        text.draw(at: NSPoint(x: 11, y: ((bounds.height - t.height) / 2).rounded()))
    }
}

/// Where a label of `size` goes beside `r` (global), on `side`.
func labelFrame(beside r: NSRect, side: Side, size: NSSize) -> NSRect {
    let g: CGFloat = 8
    let o: NSPoint
    switch side {
    case .left:  o = NSPoint(x: r.minX - g - size.width, y: r.midY - size.height / 2)
    case .right: o = NSPoint(x: r.maxX + g, y: r.midY - size.height / 2)
    case .below: o = NSPoint(x: r.midX - size.width / 2, y: r.minY - g - size.height)
    case .above: o = NSPoint(x: r.midX - size.width / 2, y: r.maxY + g)
    }
    return NSRect(origin: NSPoint(x: o.x.rounded(), y: o.y.rounded()), size: size)
}

// ---------------------------------------------------------------- drop targets

/// Draw the eight slots for one screen into the current graphics context,
/// each in its own orientation, so the drag shows which way the pill will
/// stand. `origin` is the screen's frame origin. Shared by the live overlay
/// and the snapshot.
func drawTargets(_ g: ScreenGeom, highlight: Spot?, origin: NSPoint) {
    for s in Spot.allCases {
        let f = g.windowFrame(s, pill: pillSize(.listening, s.orientation)).insetBy(dx: PAD, dy: PAD)
            .offsetBy(dx: -origin.x, dy: -origin.y)
        let on = s == highlight
        let r = on ? f.insetBy(dx: -3, dy: -3) : f
        let rad = min(r.width, r.height) / 2
        let p = NSBezierPath(roundedRect: r, xRadius: rad, yRadius: rad)
        // Dark enough to read on a light wallpaper, rimmed in white to read
        // on a dark one. The highlighted slot takes the app's teal.
        (on ? TEAL.withAlphaComponent(0.55) : NSColor.black.withAlphaComponent(0.16)).setFill()
        p.fill()
        NSColor.white.withAlphaComponent(on ? 0.95 : 0.6).setStroke()
        p.lineWidth = on ? 2 : 1
        if !on { p.setLineDash([4, 3], count: 2, phase: 0) }
        p.stroke()
    }
}

final class TargetsView: NSView {
    var geom: ScreenGeom
    var highlight: Spot? { didSet { if highlight != oldValue { needsDisplay = true } } }

    init(geom: ScreenGeom) {
        self.geom = geom
        super.init(frame: NSRect(origin: .zero, size: geom.frame.size))
    }
    required init?(coder: NSCoder) { nil }

    override func draw(_ dirty: NSRect) {
        drawTargets(geom, highlight: highlight, origin: geom.frame.origin)
    }
}

/// A panel that never becomes key or main, so a click on it does not take
/// the cursor out of the field you are typing in.
final class OrbPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

func floatingPanel(_ rect: NSRect, level: Int) -> OrbPanel {
    let w = OrbPanel(contentRect: rect, styleMask: [.borderless, .nonactivatingPanel],
                     backing: .buffered, defer: false)
    w.isOpaque = false
    w.backgroundColor = .clear
    w.hasShadow = false
    w.level = NSWindow.Level(rawValue: NSWindow.Level.statusBar.rawValue + level)
    w.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
    w.isReleasedWhenClosed = false
    w.animationBehavior = .none
    w.hidesOnDeactivate = false
    w.becomesKeyOnlyIfNeeded = true
    w.isMovable = false            // moved by hand, so it can snap
    // Opt-in: keep the pill off a shared or recorded stream while leaving it
    // fully visible to the person at the machine.
    if ProcessInfo.processInfo.environment["VB_ORB_PRIVATE"] != nil {
        w.sharingType = .none
    }
    return w
}

// ---------------------------------------------------------------- what to show

/// Everything the window depends on, in one value, so a change is one
/// comparison and the decision is in one function.
struct Scene: Equatable {
    var mode: PillMode
    var orientation: Orientation
    var buttons: [Control]
}

/// The pill's mode and the buttons beside it, from the facts. Pure, so it
/// can be read in one place: listening is never hidden and never replaced.
func scene(look: Look, handsFree: Bool, revealed: Bool, idle: IdleMode,
           controls: [Control], loop: Bool, app: Bool, spot: Spot) -> Scene? {
    let o = spot.orientation
    let extra = controls.filter {
        $0 != .dictate && app && (idle != .hide)
    }
    switch look {
    case .listening:
        // Always shown, whatever the setting. Hands free carries its own
        // cross and check and nothing else.
        if handsFree { return Scene(mode: .handsFree, orientation: o, buttons: []) }
        return Scene(mode: .listening, orientation: o, buttons: revealed ? extra : [])
    case .thinking:
        return Scene(mode: .thinking, orientation: o, buttons: revealed ? extra : [])
    case .idle:
        if revealed && idle != .hide {
            let mic = controls.contains(.dictate) && loop
            return Scene(mode: mic ? .mic : .plain, orientation: o, buttons: extra)
        }
        if idle == .always { return Scene(mode: .faint, orientation: o, buttons: []) }
        return nil
    }
}

// ---------------------------------------------------------------- the app

final class App: NSObject, NSApplicationDelegate, OrbDelegate {
    private var win: OrbPanel!
    private var view: OrbView!
    private var label: OrbPanel?
    private var labelFor: Hit?
    private var overlay: OrbPanel?
    private var overlayID: CGDirectDisplayID?
    private var presence: MicPresence!
    private var poll: Timer?
    private var lock: Int32 = -1
    private var settings = IndicatorSettings.read()
    private var settingsAt = IndicatorSettings.mtime()
    private var ticks = 0
    /// The screen the pill lives on until something says otherwise: a drop
    /// on another screen, or dictation starting on whichever has the focus.
    private var screenID: CGDirectDisplayID?
    private var snapping = false
    private let debug = ProcessInfo.processInfo.environment["VB_ORB_DEBUG"] != nil
    private var lastDebug = ""

    private var look: Look = .idle
    private var handsFree = false
    private var level: CGFloat = 0
    private var revealed = false
    private var lastNear = Date.distantPast
    private var recording = false
    private var appURL: URL?
    private var loopUp = false
    private var shown: Scene?
    /// The orientation the pill takes while it is being dragged: that of
    /// the place under it, so it turns as it crosses from an edge to the top.
    private var dragOrientation: Orientation?
    private var fadeGen = 0

    /// Called directly, not from applicationDidFinishLaunching.
    ///
    /// A binary that is not inside a .app bundle does not reliably get that
    /// callback: NSApplication delivers it as part of a launch sequence a
    /// bare executable never completes. So the orb ran, stayed alive, and did
    /// nothing at all, with no error anywhere, because its entire setup lived
    /// in a method that was never called.
    func start() {
        holdOurOwnLock()
        view = OrbView(frame: NSRect(x: 0, y: 0, width: 10, height: 10))
        view.delegate = self
        makeWindow()
        wire()
        checkOthers()
        evaluate()
    }

    /// Once, for the life of the process.
    private func wire() {
        presence = MicPresence { [weak self] in self?.evaluate() }

        let nc = NSWorkspace.shared.notificationCenter
        // Rebuild rather than resume across sleep: the default input can
        // change while we are out, and a window kept across a sleep can
        // silently stop drawing (see show()).
        nc.addObserver(forName: NSWorkspace.didWakeNotification, object: nil,
                       queue: .main) { [weak self] _ in self?.rebuild() }
        nc.addObserver(forName: NSWorkspace.sessionDidResignActiveNotification, object: nil,
                       queue: .main) { [weak self] _ in self?.hide(now: true) }
        nc.addObserver(forName: NSWorkspace.sessionDidBecomeActiveNotification, object: nil,
                       queue: .main) { [weak self] _ in self?.evaluate() }
        NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification, object: nil,
            queue: .main) { [weak self] _ in self?.shown = nil; self?.evaluate() }

        // The level, the phase and the pointer still need reading; the
        // expensive question (is a mic open at all) is answered by the
        // event-driven listener above.
        poll = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let s = self else { return }
            s.ticks += 1
            if s.ticks % 5 == 0 { s.reloadSettings() }
            if s.ticks % 10 == 0 { s.checkOthers() }
            s.evaluate()
        }
    }

    /// Held for our whole life, so that whoever opens the microphone can
    /// check an indicator exists before doing so.
    private func holdOurOwnLock() {
        try? FileManager.default.createDirectory(at: STATE, withIntermediateDirectories: true)
        lock = open(STATE.appendingPathComponent("orb.lock").path, O_RDONLY | O_CREAT, 0o644)
        if lock >= 0 { flock(lock, LOCK_EX | LOCK_NB) }
    }

    /// The app, the loop's control channel, and a meeting: once a second,
    /// cheap file and lock checks.
    private func checkOthers() {
        appURL = runningApp()
        loopUp = lockHeld("dictate.sock.lock")
        let r = meetingRecording()
        if r != recording { recording = r; view.recording = r; refreshLabel() }
    }

    /// Builds the window and nothing else. This runs again on every rebuild,
    /// so anything else put here runs again on every rebuild: the observers
    /// and the poll timer used to live here, and one of them called
    /// evaluate(), which called show(), which came straight back.
    private func makeWindow() {
        win = floatingPanel(NSRect(origin: .zero, size: view.frame.size), level: 3)
        win.contentView = view
        NotificationCenter.default.addObserver(
            forName: NSWindow.didChangeOcclusionStateNotification, object: win,
            queue: .main) { [weak self] n in
                guard let s = self, (n.object as? NSWindow) === s.win else { return }
                // Pause the drawing, never the state machine: it must be right
                // the instant it becomes visible again.
                s.win.occlusionState.contains(.visible) ? s.view.resume() : s.view.pause()
            }
    }

    private func currentScreen() -> NSScreen? {
        if let id = screenID, let s = NSScreen.screens.first(where: { $0.displayID == id }) {
            return s
        }
        let s = pickScreen()
        screenID = s?.displayID
        return s
    }

    /// Where the stack would be if it were revealed now, grown by a margin:
    /// the pointer entering this shows it. Computed whether or not anything
    /// is on screen, which is the point: there is nothing to hover over.
    private func hoverZone() -> NSRect? {
        guard let s = currentScreen() else { return nil }
        let sc = scene(look: look, handsFree: handsFree, revealed: true, idle: settings.idle,
                       controls: settings.controls, loop: loopUp, app: appURL != nil,
                       spot: settings.spot)
        guard let sc = sc else { return nil }
        let f = ScreenGeom(s).frames(settings.spot, pill: pillSize(sc.mode, sc.orientation),
                                     buttons: sc.buttons)
        var z = f.window
        if win.isVisible { z = z.union(win.frame) }
        return z.insetBy(dx: -HOVER_SLACK, dy: -HOVER_SLACK)
    }

    private func move(to f: NSRect, animated: Bool, done: (() -> Void)? = nil) {
        if f == win.frame { done?(); return }
        if !animated || !win.isVisible || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            win.setFrame(f, display: true)
            done?()
            return
        }
        NSAnimationContext.runAnimationGroup({ c in
            c.duration = 0.18
            c.timingFunction = CAMediaTimingFunction(name: .easeOut)
            win.animator().setFrame(f, display: true)
        }, completionHandler: { done?() })
    }

    /// Rebuild rather than reuse. A window kept across a sleep/wake cycle can
    /// silently stop rendering, and from then on orderFrontRegardless() is a
    /// no-op that still reports success: the object exists, every API you
    /// would query looks healthy, and nothing is drawn. Construction is
    /// sub-millisecond, so rebuilding is cheap insurance against the one
    /// failure we cannot see.
    private func show(_ f: NSRect, fast: Bool) {
        fadeGen += 1
        if win.isVisible && win.alphaValue > 0.99 && !win.ignoresMouseEvents { return }
        if !win.isVisible {
            makeWindow()
            win.setFrame(f, display: false)
            win.alphaValue = 0
            win.orderFrontRegardless()
        }
        win.ignoresMouseEvents = false
        view.resume()
        if NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            win.alphaValue = 1
            return
        }
        NSAnimationContext.runAnimationGroup { c in
            c.duration = fast ? 0.08 : 0.16
            win.animator().alphaValue = 1
        }
    }

    /// A short fade, then out of the way entirely. Clicks pass through from
    /// the moment it starts fading.
    private func hide(now: Bool = false) {
        hideTargets()
        hideLabel()
        guard win.isVisible else { return }
        // Already fading: this runs every tick, and restarting the fade each
        // time would mean it never finished and never left the screen.
        if win.ignoresMouseEvents && !now { return }
        fadeGen += 1
        let gen = fadeGen
        win.ignoresMouseEvents = true
        view.setHovered(nil)
        if now || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            win.orderOut(nil)
            view.pause()
            return
        }
        NSAnimationContext.runAnimationGroup({ c in
            c.duration = 0.2
            win.animator().alphaValue = 0
        }, completionHandler: { [weak self] in
            guard let s = self, s.fadeGen == gen else { return }
            s.win.orderOut(nil)
            s.view.pause()
        })
    }

    private func rebuild() {
        hide(now: true)
        shown = nil
        evaluate()
    }

    private func reloadSettings() {
        let m = IndicatorSettings.mtime()
        guard m != settingsAt else { return }
        settingsAt = m
        let s = IndicatorSettings.read()
        guard s != settings else { return }
        settings = s
        evaluate()
    }

    /// Show it regardless of the microphone, so "does it draw" can be tested
    /// apart from "does it decide correctly". Those failed together and looked
    /// identical: nothing on screen.
    private let forced = ProcessInfo.processInfo.environment["VB_ORB_TEST"] != nil

    private func evaluate() {
        var newLook: Look
        let d = readDetail()
        if forced {
            newLook = .listening
            handsFree = ProcessInfo.processInfo.environment["VB_ORB_TEST"] == "handsfree"
            level = 0.7
        } else {
            let hot = presence.isHot
            let ours = weOwnTheMic()
            newLook = decide(hot: hot, ours: ours, detail: d)
            // Appearance only: the cross and check are drawn on a pill that
            // is already listening because the microphone is open.
            handsFree = newLook == .listening && d.fresh && d.phase == "handsfree"
            level = d.fresh ? d.level : 0.3
            if debug {
                let now = "\(hot)/\(ours)/\(newLook)/\(handsFree)"
                if now != lastDebug {
                    lastDebug = now
                    FileHandle.standardError.write(
                        "orb: mic hot=\(hot) ours=\(ours) -> \(newLook) hf=\(handsFree)\n"
                            .data(using: .utf8)!)
                }
            }
        }
        // Dictation starting is the moment to come to the screen being worked
        // on; anything after that stays put, so the pill does not jump
        // between screens in the middle of a sentence.
        if look == .idle && newLook == .listening && !view.dragging {
            screenID = pickScreen()?.displayID
        }
        look = newLook
        view.feed(level)
        if view.dragging || snapping { return }

        // The pointer, read every tick: there may be no window to hover.
        if let z = hoverZone(), NSMouseInRect(NSEvent.mouseLocation, z, false) {
            lastNear = Date()
            revealed = true
        } else if revealed && Date().timeIntervalSince(lastNear) > 1.0 {
            revealed = false
        }
        if settings.idle == .hide { revealed = false }

        let sc = scene(look: look, handsFree: handsFree, revealed: revealed, idle: settings.idle,
                       controls: settings.controls, loop: loopUp, app: appURL != nil,
                       spot: settings.spot)
        apply(sc)
    }

    private func apply(_ sc: Scene?) {
        guard let sc = sc, let s = currentScreen() else {
            shown = nil
            hide()
            return
        }
        let f = ScreenGeom(s).frames(settings.spot, pill: pillSize(sc.mode, sc.orientation),
                                     buttons: sc.buttons)
        if sc != shown || f.window != win.frame {
            let wasVisible = win.isVisible && !win.ignoresMouseEvents
            shown = sc
            view.mode = sc.mode
            view.orientation = sc.orientation
            view.frames = f
            if wasVisible {
                win.setFrame(f.window, display: true)
            }
            if let h = view.hovered, view.hit(view.convert(
                win.convertPoint(fromScreen: NSEvent.mouseLocation), from: nil)) != h {
                view.setHovered(nil)
            }
        }
        // Listening shows at once; the rest fades in.
        show(f.window, fast: sc.mode == .listening || sc.mode == .handsFree)
        if !win.isVisible || win.frame != f.window { win.setFrame(f.window, display: true) }
        refreshLabel()
    }

    // ------------------------------------------------------------ clicks

    func pressed(_ h: Hit) {
        switch h {
        case .pill:
            // Start a hands free session, or finish the one that is open.
            // While a key is held the listener leaves the hold alone.
            if shown?.mode == .mic || shown?.mode == .listening || shown?.mode == .handsFree {
                tellLoop("toggle")
            }
        case .cancel: tellLoop("cancel")
        case .finish: tellLoop("finish")
        case .button(.notetaker): openInApp("notetaker", activate: false)
        case .button(.scratchpad): openInApp("scratchpad", activate: true)
        case .button(.dictate): tellLoop("toggle")
        }
        if debug {
            FileHandle.standardError.write("orb: pressed \(h)\n".data(using: .utf8)!)
        }
    }

    // ------------------------------------------------------------ labels

    func hovering(_ h: Hit?) { refreshLabel() }

    private func labelText(_ h: Hit) -> NSAttributedString? {
        let s = settings
        switch h {
        case .pill:
            switch shown?.mode {
            case .mic?: return LabelView.make("Dictate hands free", "double-tap \(KEY_NAME)")
            case .listening?: return LabelView.make("Listening", "release \(KEY_NAME)")
            default: return nil
            }
        case .cancel: return LabelView.make("Cancel, paste nothing", "esc")
        case .finish: return LabelView.make("Finish and paste", KEY_NAME)
        case .button(.notetaker):
            return LabelView.make(recording ? "Stop Notetaker" : "Start Notetaker",
                                  s.shortcutNotetaker ? "⌥ M" : nil)
        case .button(.scratchpad):
            return LabelView.make("Scratchpad", s.shortcutScratchpad ? "⌥ S" : nil)
        case .button(.dictate): return nil
        }
    }

    private func refreshLabel() {
        guard win.isVisible, !win.ignoresMouseEvents, !view.dragging,
              let h = view.hovered, let t = labelText(h) else { hideLabel(); return }
        let lv: LabelView
        let isNew: Bool
        if let l = label, let v = l.contentView as? LabelView {
            lv = v
            isNew = labelFor != h
        } else {
            lv = LabelView(frame: .zero)
            let l = floatingPanel(.zero, level: 4)
            l.ignoresMouseEvents = true
            l.contentView = lv
            label = l
            isNew = true
        }
        lv.text = t
        lv.needsDisplay = true
        let r = view.rect(of: h).offsetBy(dx: win.frame.minX, dy: win.frame.minY)
        let f = labelFrame(beside: r, side: settings.spot.labelSide, size: lv.fit)
        labelFor = h
        guard let l = label else { return }
        if !isNew && l.isVisible { l.setFrame(f, display: true); return }
        // Slide out from the button: start a few points toward it, faded.
        let off: (CGFloat, CGFloat)
        switch settings.spot.labelSide {
        case .left: off = (6, 0)
        case .right: off = (-6, 0)
        case .below: off = (0, 6)
        case .above: off = (0, -6)
        }
        l.setFrame(f.offsetBy(dx: off.0, dy: off.1), display: true)
        l.alphaValue = 0
        l.orderFrontRegardless()
        if NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            l.setFrame(f, display: true)
            l.alphaValue = 1
            return
        }
        NSAnimationContext.runAnimationGroup { c in
            c.duration = 0.14
            c.timingFunction = CAMediaTimingFunction(name: .easeOut)
            l.animator().setFrame(f, display: true)
            l.animator().alphaValue = 1
        }
    }

    private func hideLabel() {
        label?.orderOut(nil)
        labelFor = nil
    }

    // ------------------------------------------------------------ dragging

    /// The pill alone follows the pointer, turned to the orientation of the
    /// place under it; the buttons come back once it lands.
    func dragMoved(mouse: NSPoint) {
        hideLabel()
        guard let s = NSScreen.screens.first(where: { NSMouseInRect(mouse, $0.frame, false) })
                ?? pickScreen() else { return }
        let g = ScreenGeom(s)
        let near = g.nearest(to: mouse)
        let o = near.orientation
        let mode = shown?.mode ?? .plain
        let dm: PillMode = (mode == .faint) ? .plain : mode
        let size = pillSize(dm, o)
        let wf = NSRect(x: (mouse.x - size.width / 2 - PAD).rounded(),
                        y: (mouse.y - size.height / 2 - PAD).rounded(),
                        width: size.width + PAD * 2, height: size.height + PAD * 2)
        if dragOrientation != o || view.mode != dm {
            dragOrientation = o
            view.mode = dm
            view.orientation = o
        }
        view.frames = Frames(window: wf, pill: NSRect(x: PAD, y: PAD, width: size.width,
                                                      height: size.height), buttons: [:])
        win.setFrame(wf, display: true)
        showTargets(on: s).highlight = near
    }

    func dragEnded(mouse: NSPoint) {
        hideTargets()
        dragOrientation = nil
        guard let s = NSScreen.screens.first(where: { NSMouseInRect(mouse, $0.frame, false) })
                ?? pickScreen() else { return }
        let g = ScreenGeom(s)
        let spot = g.nearest(to: mouse)
        settings.spot = spot
        screenID = s.displayID
        IndicatorSettings.save(spot: spot)
        settingsAt = IndicatorSettings.mtime()
        let size = pillSize(view.mode, spot.orientation)
        snapping = true
        move(to: g.windowFrame(spot, pill: size), animated: true) { [weak self] in
            guard let self = self else { return }
            self.snapping = false
            self.shown = nil
            self.lastNear = Date()          // the pointer is right here
            self.evaluate()
        }
        if debug {
            FileHandle.standardError.write("orb: dropped at \(spot.rawValue) on \(s.localizedName)\n"
                .data(using: .utf8)!)
        }
    }

    @discardableResult
    private func showTargets(on s: NSScreen) -> TargetsView {
        if let o = overlay, overlayID == s.displayID, let v = o.contentView as? TargetsView {
            return v
        }
        hideTargets()
        // Below the pill, above everything else, and blind to the mouse: the
        // drag belongs to the pill.
        let o = floatingPanel(s.frame, level: 2)
        o.ignoresMouseEvents = true
        let v = TargetsView(geom: ScreenGeom(s))
        o.contentView = v
        o.orderFrontRegardless()
        overlay = o
        overlayID = s.displayID
        return v
    }

    private func hideTargets() {
        overlay?.orderOut(nil)
        overlay = nil
        overlayID = nil
    }
}

// ---------------------------------------------------------------- snapshot

/// Draw what the pill looks like into PNGs, without a window, a microphone
/// or a state directory. For checking the design from a shell that has no
/// Screen Recording permission.
enum Snapshot {
    static func run(into dir: URL) -> Int32 {
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        var ok = true
        func out(_ name: String, _ rep: NSBitmapImageRep?) {
            ok = write(rep, to: dir.appendingPathComponent(name)) && ok
        }
        let all: [Control] = [.notetaker, .scratchpad]
        out("round4-hidden.png", scene(.top, nil, zone: true,
                                       caption: "Idle: nothing drawn. The dashed zone (not drawn for real) reveals it."))
        out("round4-hover-top.png", scene(.top, Scene(mode: .mic, orientation: .horizontal, buttons: all),
                                          caption: "Hover at top centre: mic pill, Notetaker, Scratchpad"))
        out("round4-hover-right.png", scene(.right, Scene(mode: .mic, orientation: .vertical, buttons: all),
                                            caption: "Hover at the right edge: the stack stands up"))
        out("round4-label.png", scene(.right, Scene(mode: .mic, orientation: .vertical, buttons: all),
                                      hover: .button(.notetaker),
                                      caption: "A label slides out to the inside"))
        out("round4-label-top.png", scene(.top, Scene(mode: .mic, orientation: .horizontal, buttons: all),
                                          hover: .button(.scratchpad),
                                          caption: "At the top, labels drop below"))
        out("round4-recording.png", scene(.topRight, Scene(mode: .mic, orientation: .vertical, buttons: all),
                                          hover: .button(.notetaker), recording: true,
                                          caption: "A corner stands up too; Notetaker red while recording"))
        out("round4-listening-vertical.png", scene(.left, Scene(mode: .listening, orientation: .vertical,
                                                                buttons: []),
                                                   caption: "Listening at the left edge: bars lie flat, stacked"))
        out("round4-listening-horizontal.png", scene(.top, Scene(mode: .listening, orientation: .horizontal,
                                                                 buttons: []),
                                                     caption: "Listening at the top"))
        out("round4-handsfree-horizontal.png", scene(.bottom, Scene(mode: .handsFree, orientation: .horizontal,
                                                                    buttons: []),
                                                     hover: .finish,
                                                     caption: "Hands free at the bottom: cancel, waveform, finish"))
        out("round4-handsfree-vertical.png", scene(.right, Scene(mode: .handsFree, orientation: .vertical,
                                                                 buttons: []),
                                                   hover: .cancel,
                                                   caption: "Hands free at the right edge: cancel on top"))
        out("round4-thinking.png", scene(.bottomLeft, Scene(mode: .thinking, orientation: .vertical, buttons: []),
                                         caption: "Thinking, bottom left"))
        out("round4-drag-targets.png", screen(targets: true))
        out("round4-eight-places.png", screen(targets: false))
        return ok ? 0 : 1
    }

    /// A MacBook-like 1512x982 screen: a 37pt menu bar with a notch, a Dock.
    static let geom: ScreenGeom = {
        let frame = NSRect(x: 0, y: 0, width: 1512, height: 982)
        let menu: CGFloat = 37, dock: CGFloat = 72
        return ScreenGeom(frame: frame,
                          visible: NSRect(x: 0, y: dock, width: 1512, height: 982 - menu - dock),
                          notch: NSRect(x: 756 - 92, y: 982 - menu, width: 184, height: menu))
    }()

    static func canvas(_ size: NSSize, scale: CGFloat = 2,
                       _ draw: (CGContext) -> Void) -> NSBitmapImageRep? {
        guard let rep = NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: Int(size.width * scale),
            pixelsHigh: Int(size.height * scale), bitsPerSample: 8, samplesPerPixel: 4,
            hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
            bytesPerRow: 0, bitsPerPixel: 0),
              let g = NSGraphicsContext(bitmapImageRep: rep) else { return nil }
        rep.size = size
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = g
        g.cgContext.scaleBy(x: scale, y: scale)
        draw(g.cgContext)
        NSGraphicsContext.restoreGraphicsState()
        return rep
    }

    static func wallpaper(_ g: ScreenGeom) {
        NSGradient(colors: [NSColor(srgbRed: 0.55, green: 0.66, blue: 0.80, alpha: 1),
                            NSColor(srgbRed: 0.86, green: 0.80, blue: 0.74, alpha: 1)])?
            .draw(in: g.frame, angle: 90)
        let w = NSRect(x: 260, y: 230, width: 900, height: 560)
        NSColor.white.setFill()
        NSBezierPath(roundedRect: w, xRadius: 12, yRadius: 12).fill()
        NSColor(white: 0.95, alpha: 1).setFill()
        NSBezierPath(rect: NSRect(x: w.minX, y: w.maxY - 40, width: w.width, height: 28)).fill()
        NSColor.white.withAlphaComponent(0.55).setFill()
        NSRect(x: 0, y: g.visible.maxY, width: g.frame.width,
               height: g.frame.maxY - g.visible.maxY).fill()
        NSColor.black.setFill()
        if let n = g.notch {
            NSBezierPath(roundedRect: NSRect(x: n.minX, y: n.minY, width: n.width, height: n.height + 12),
                         xRadius: 10, yRadius: 10).fill()
        }
        NSColor.white.withAlphaComponent(0.45).setFill()
        NSBezierPath(roundedRect: NSRect(x: 456, y: 4, width: 600, height: 64),
                     xRadius: 18, yRadius: 18).fill()
    }

    static func orb(_ sc: Scene, at spot: Spot, hover: Hit?, recording: Bool) -> (OrbView, Frames) {
        let f = geom.frames(spot, pill: pillSize(sc.mode, sc.orientation), buttons: sc.buttons)
        let v = OrbView(frame: NSRect(origin: .zero, size: f.window.size))
        v.mode = sc.mode
        v.orientation = sc.orientation
        v.frames = f
        v.recording = recording
        v.freeze(level: 0.65, phase: 1.3)
        if let h = hover { v.setHovered(h) }
        return (v, f)
    }

    /// A crop of the made-up screen around one spot, at twice the size, with
    /// the orb (and its label) drawn where it really goes.
    static func scene(_ spot: Spot, _ sc: Scene?, hover: Hit? = nil, recording: Bool = false,
                      zone: Bool = false, caption: String) -> NSBitmapImageRep? {
        let g = geom
        let probe = sc ?? Scene(mode: .mic, orientation: spot.orientation, buttons: [.notetaker, .scratchpad])
        let (v, f) = orb(probe, at: spot, hover: hover, recording: recording)
        var labelRect: NSRect?
        var lv: LabelView?
        if sc != nil, let h = hover {
            let t: NSAttributedString?
            switch h {
            case .button(.notetaker): t = LabelView.make(recording ? "Stop Notetaker" : "Start Notetaker", "⌥ M")
            case .button(.scratchpad): t = LabelView.make("Scratchpad", "⌥ S")
            case .cancel: t = LabelView.make("Cancel, paste nothing", "esc")
            case .finish: t = LabelView.make("Finish and paste", KEY_NAME)
            case .pill: t = LabelView.make("Dictate hands free", "double-tap \(KEY_NAME)")
            default: t = nil
            }
            if let t = t {
                let l = LabelView(frame: .zero)
                l.text = t
                let r = v.rect(of: h).offsetBy(dx: f.window.minX, dy: f.window.minY)
                let lf = labelFrame(beside: r, side: spot.labelSide, size: l.fit)
                l.frame = NSRect(origin: .zero, size: lf.size)
                labelRect = lf
                lv = l
            }
        }
        // The crop: the orb, its label, and room around them, inside the screen.
        var focus = f.window
        if let lr = labelRect { focus = focus.union(lr) }
        let crop = NSRect(x: focus.midX - 230, y: focus.midY - 110, width: 460, height: 220)
            .offsetBy(dx: 0, dy: 0)
        let c = NSRect(x: max(g.frame.minX, min(crop.minX, g.frame.maxX - crop.width)),
                       y: max(g.frame.minY, min(crop.minY, g.frame.maxY - crop.height)),
                       width: crop.width, height: crop.height)
        let capH: CGFloat = 26
        return canvas(NSSize(width: c.width, height: c.height + capH)) { ctx in
            NSColor.white.setFill()
            NSRect(x: 0, y: c.height, width: c.width, height: capH).fill()
            NSAttributedString(string: caption, attributes: [
                .font: NSFont.systemFont(ofSize: 11, weight: .medium),
                .foregroundColor: NSColor(white: 0.25, alpha: 1)])
                .draw(at: NSPoint(x: 10, y: c.height + 7))
            ctx.saveGState()
            ctx.clip(to: NSRect(x: 0, y: 0, width: c.width, height: c.height))
            ctx.translateBy(x: -c.minX, y: -c.minY)
            wallpaper(g)
            if zone {
                let z = f.window.insetBy(dx: -HOVER_SLACK, dy: -HOVER_SLACK)
                let p = NSBezierPath(roundedRect: z, xRadius: 8, yRadius: 8)
                p.setLineDash([4, 3], count: 2, phase: 0)
                p.lineWidth = 1
                NSColor.black.withAlphaComponent(0.35).setStroke()
                p.stroke()
            }
            if sc != nil {
                ctx.saveGState()
                ctx.translateBy(x: f.window.minX, y: f.window.minY)
                v.draw(v.bounds)
                ctx.restoreGState()
            }
            if let l = lv, let lr = labelRect {
                ctx.saveGState()
                ctx.translateBy(x: lr.minX, y: lr.minY)
                l.draw(l.bounds)
                ctx.restoreGState()
            }
            ctx.restoreGState()
        }
    }

    /// The whole made-up screen: the drop slots mid-drag, or the listening
    /// pill at each of the eight places (one pill only ever exists).
    static func screen(targets: Bool) -> NSBitmapImageRep? {
        let g = geom
        return canvas(g.frame.size, scale: 1) { ctx in
            wallpaper(g)
            if targets {
                drawTargets(g, highlight: .right, origin: .zero)
                // The pill under the pointer, already standing up as it nears
                // the right edge.
                let size = pillSize(.plain, .vertical)
                let t = g.windowFrame(.right, pill: size)
                let f = Frames(window: NSRect(x: t.minX - 90, y: t.minY + 40, width: t.width, height: t.height),
                               pill: NSRect(x: PAD, y: PAD, width: size.width, height: size.height),
                               buttons: [:])
                let v = OrbView(frame: NSRect(origin: .zero, size: f.window.size))
                v.mode = .plain
                v.orientation = .vertical
                v.frames = f
                ctx.saveGState()
                ctx.translateBy(x: f.window.minX, y: f.window.minY)
                v.draw(v.bounds)
                ctx.restoreGState()
            } else {
                for s in Spot.allCases {
                    let (v, f) = orb(Scene(mode: .listening, orientation: s.orientation, buttons: []),
                                     at: s, hover: nil, recording: false)
                    ctx.saveGState()
                    ctx.translateBy(x: f.window.minX, y: f.window.minY)
                    v.draw(v.bounds)
                    ctx.restoreGState()
                }
            }
        }
    }

    static func write(_ rep: NSBitmapImageRep?, to url: URL) -> Bool {
        guard let data = rep?.representation(using: .png, properties: [:]) else { return false }
        do { try data.write(to: url); print(url.path); return true } catch {
            FileHandle.standardError.write("orb: \(error)\n".data(using: .utf8)!)
            return false
        }
    }
}

// ---------------------------------------------------------------- main

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
if let dir = ProcessInfo.processInfo.environment["DICTATOR_ORB_SNAPSHOT"], !dir.isEmpty {
    exit(Snapshot.run(into: URL(fileURLWithPath: (dir as NSString).expandingTildeInPath)))
}
let delegate = App()
app.delegate = delegate
delegate.start()        // before run(), because the callback may never come
app.run()
