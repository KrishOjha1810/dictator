// dictator-orb: a small pill that tells the truth about your microphone.
//
// THE PROMISE. The pill has three looks, and only one of them says "the
// microphone is open":
//
//   listening  a dark pill with moving bars    our microphone IS open
//   thinking   a dark pill with three dots     our microphone is closed, and
//                                              the words are being worked out
//   idle       a small, faint grey pill        our microphone is closed
//
// Listening is drawn if and only if our microphone is truly open. Idle and
// thinking can never be drawn while it is: when the mic is ours and hot, the
// look is listening whatever hud.json says. So the idle pill is not a weaker
// "maybe listening"; it is a positive "Dictator is running and not hearing
// you".
//
// What the idle pill does NOT say: anything about OTHER apps. Another program
// may have the microphone while our pill sits idle; macOS's own orange dot is
// the indicator for that. And no pill at all means either that "Hide when not
// dictating" is on and our mic is closed, or that this helper is not running.
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
// screen's visible frame, so never under the menu bar or the Dock.
//
// MOVING IT. Drag the pill. While it moves, the eight places on the screen
// under the pointer are drawn as translucent slots and the nearest one is
// highlighted; let go and it snaps there with a short animation. The choice
// is written to STATE/indicator.json ({"position": ..., "hide_idle": ...}),
// which is also what the app's Settings and `dictator indicator` write. This
// process watches the file, so a change from either moves the pill at once.
//
// CLICKS. The window is a non-activating panel exactly the size of the pill:
// it never takes focus from the app you are typing into, and it only catches
// the mouse on the pill itself. The drop-target overlay ignores the mouse.
//
// LOOKING AT IT WITHOUT A SCREEN. DICTATOR_ORB_SNAPSHOT=DIR draws the pill in
// every look and the drop targets on a made-up screen into PNGs in DIR, then
// exits, touching no microphone and no state. Needs no Screen Recording
// permission.

import Cocoa
import CoreAudio
import QuartzCore

// ---------------------------------------------------------------- geometry

let PAD: CGFloat = 2            // between the pill and its window's edge
let TOP_GAP: CGFloat = 4        // under the notch or the menu bar, as before
let MARGIN: CGFloat = 12        // from the Dock and the side edges

enum Look { case idle, listening, thinking }

/// Sized to be noticed when it matters and ignored when it does not. Idle is
/// small and faint; hovering it grows it a little so it is easy to grab; the
/// two dictating looks share one size so going from listening to thinking
/// does not jump.
func pillSize(_ look: Look, hover: Bool) -> NSSize {
    switch look {
    case .idle: return hover ? NSSize(width: 56, height: 14) : NSSize(width: 44, height: 10)
    case .listening, .thinking: return NSSize(width: 84, height: 26)
    }
}

/// The eight places. Raw values are what indicator.json, `dictator indicator`
/// and the app's picker use (orbnative.POSITIONS, same order).
enum Spot: String, CaseIterable {
    case top, bottom, left, right
    case topLeft = "top-left", topRight = "top-right"
    case bottomLeft = "bottom-left", bottomRight = "bottom-right"
}

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

    /// The window frame for a pill of `pill` size at `spot`. Integral,
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

    /// The place whose centre is closest to `p`. Measured against slots of
    /// the same size whatever the pill's current size, so the answer does not
    /// change because the pill happened to be idle.
    func nearest(to p: NSPoint) -> Spot {
        let slot = pillSize(.listening, hover: false)
        func d(_ s: Spot) -> CGFloat {
            let f = windowFrame(s, pill: slot)
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
    return screenUnderMouse()
}

func screenUnderMouse() -> NSScreen? {
    let mouse = NSEvent.mouseLocation
    if let under = NSScreen.screens.first(where: { NSMouseInRect(mouse, $0.frame, false) }) {
        return under
    }
    if let notched = NSScreen.screens.first(where: { $0.notchRect != nil }) {
        return notched
    }
    return NSScreen.screens.first
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

struct IndicatorSettings: Equatable {
    var spot: Spot = .top
    var hideIdle = false

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
        if let h = o["hide_idle"] as? Bool { s.hideIdle = h }
        return s
    }

    /// Write the position back, keeping every other key, atomically: the
    /// app may be reading the same file.
    static func save(spot: Spot) {
        var o = raw()
        o["position"] = spot.rawValue
        if o["hide_idle"] == nil { o["hide_idle"] = false }
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

// ---------------------------------------------------------------- the pill

protocol PillDragDelegate: AnyObject {
    func dragMoved(origin: NSPoint, mouse: NSPoint)
    func dragEnded(mouse: NSPoint)
    func hoverChanged(_ on: Bool)
}

final class PillView: NSView {
    private let body = CAShapeLayer()
    private var bars: [CAShapeLayer] = []
    private var dots: [CAShapeLayer] = []
    private var link: CADisplayLink?
    private var level: CGFloat = 0          // smoothed
    private var target: CGFloat = 0
    private var phase: CGFloat = 0          // drives the waveform's wobble
    private(set) var look: Look = .idle
    private(set) var hover = false
    weak var drag: PillDragDelegate?

    private var downAt: NSPoint?
    private var winAt: NSPoint = .zero
    private(set) var dragging = false

    private let nBars = 11

    private var reduceMotion: Bool {
        NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    }
    private var opaqueBG: Bool {
        NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency
    }
    private var contrast: Bool {
        NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast
    }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.addSublayer(body)
        for _ in 0..<nBars {
            let b = CAShapeLayer()
            b.fillColor = NSColor.white.withAlphaComponent(0.95).cgColor
            layer?.addSublayer(b)
            bars.append(b)
        }
        for _ in 0..<3 {
            let d = CAShapeLayer()
            d.fillColor = NSColor.white.cgColor
            layer?.addSublayer(d)
            dots.append(d)
        }
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification,
            object: nil, queue: .main) { [weak self] _ in
                guard let s = self else { return }
                s.apply(s.look, force: true)
            }
    }
    required init?(coder: NSCoder) { nil }

    var size: NSSize { pillSize(look, hover: hover) }

    // ------------------------------------------------------------ drawing

    /// Paths follow the view's bounds, so the window can grow and shrink
    /// around the pill and everything inside stays centred.
    override func layout() {
        super.layout()
        relayout()
    }

    func relayout() {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        let r = bounds.insetBy(dx: PAD, dy: PAD)
        body.path = CGPath(roundedRect: r, cornerWidth: r.height / 2,
                           cornerHeight: r.height / 2, transform: nil)
        paint()

        // Bars, not a dot. A row of them shows the SHAPE of what you are
        // saying, not just that something is happening.
        let bw: CGFloat = 2.5
        let span = r.width - r.height                // keep clear of the round ends
        let gap = (span - CGFloat(nBars) * bw) / CGFloat(nBars - 1)
        let bh = r.height - 10
        for (i, b) in bars.enumerated() {
            let x = r.minX + r.height / 2 + CGFloat(i) * (bw + gap)
            b.bounds = NSRect(x: 0, y: 0, width: bw, height: bh)
            b.path = CGPath(roundedRect: b.bounds, cornerWidth: bw / 2,
                            cornerHeight: bw / 2, transform: nil)
            // Scale about the middle so a bar grows both ways, like a meter.
            b.anchorPoint = CGPoint(x: 0.5, y: 0.5)
            b.position = CGPoint(x: x + bw / 2, y: r.midY)
        }
        let ds: CGFloat = 5
        for (i, d) in dots.enumerated() {
            d.bounds = NSRect(x: 0, y: 0, width: ds, height: ds)
            d.path = CGPath(ellipseIn: d.bounds, transform: nil)
            d.position = CGPoint(x: r.midX + CGFloat(i - 1) * 10, y: r.midY)
        }
        setBars(level)
        CATransaction.commit()
    }

    private func paint() {
        switch look {
        case .idle:
            // Neutral grey and faint: it should be findable, not noticed. A
            // light rim keeps it visible on a dark wallpaper, the grey on a
            // light one.
            let a: CGFloat = hover ? 0.88 : (contrast ? 0.75 : 0.45)
            body.fillColor = NSColor(white: hover ? 0.22 : 0.40, alpha: opaqueBG ? 1 : a).cgColor
            body.strokeColor = NSColor.white.withAlphaComponent(hover ? 0.55 : 0.45).cgColor
            body.lineWidth = 0.75
        case .listening, .thinking:
            body.fillColor = NSColor.black.withAlphaComponent(opaqueBG ? 1.0 : 0.86).cgColor
            body.strokeColor = NSColor.white.withAlphaComponent(contrast ? 0.4 : 0.16).cgColor
            body.lineWidth = 0.75
        }
    }

    /// Bars at a given level. The middle ones react most, which is what a
    /// voice actually looks like and what stops it reading as a progress
    /// bar; a small wobble per bar keeps it from looking like one shape
    /// breathing.
    private func setBars(_ lvl: CGFloat) {
        let n = bars.count
        guard n > 0 else { return }
        let mid = CGFloat(n - 1) / 2
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        for (i, b) in bars.enumerated() {
            let d = abs(CGFloat(i) - mid) / max(mid, 1)          // 0 centre, 1 edge
            let shape = 1.0 - d * 0.6
            let wobble = reduceMotion ? 1 : 0.78 + 0.22 * sin(phase + CGFloat(i) * 1.7)
            let h = 0.18 + 0.82 * min(1, lvl * 1.4) * shape * wobble
            b.transform = CATransform3DMakeScale(1, max(0.18, h), 1)
        }
        CATransaction.commit()
    }

    func setHover(_ on: Bool) {
        guard on != hover else { return }
        hover = on
        paint()
    }

    func apply(_ new: Look, force: Bool = false) {
        guard new != look || force else { return }
        look = new
        bars.forEach { $0.removeAllAnimations() }
        dots.forEach { $0.removeAllAnimations() }
        stopLink()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        paint()
        switch new {
        case .idle:
            // The dominant state, so it must be free: no animation at all.
            bars.forEach { $0.opacity = 0 }
            dots.forEach { $0.opacity = 0 }

        case .listening:
            bars.forEach { $0.opacity = 1 }
            dots.forEach { $0.opacity = 0 }
            startLink()          // real audio each frame, so this one earns its cost

        case .thinking:
            bars.forEach { $0.opacity = 0 }
            // A still frame of the animation, which is also what reduced
            // motion and the snapshot show: three dots fading left to right.
            for (i, d) in dots.enumerated() { d.opacity = [1.0, 0.65, 0.35][i] }
            if !reduceMotion {
                let now = CACurrentMediaTime()
                for (i, d) in dots.enumerated() {
                    let a = CAKeyframeAnimation(keyPath: "opacity")
                    a.values = [0.3, 1.0, 0.3]
                    a.keyTimes = [0, 0.4, 1]
                    a.duration = 0.9
                    a.repeatCount = .infinity
                    a.beginTime = now + Double(i) * 0.15
                    a.fillMode = .backwards
                    d.add(a, forKey: "pulse")
                }
            }
        }
        CATransaction.commit()
    }

    func feed(_ v: CGFloat) { target = max(0, min(1, v)) }

    /// For the snapshot: a level, drawn now, with no display link.
    func freeze(level v: CGFloat, phase p: CGFloat) {
        level = v
        target = v
        phase = p
        stopLink()
        setBars(v)
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
        setBars(level)
    }

    func pause() { stopLink() }
    func resume() { if look == .listening { startLink() } }

    // ------------------------------------------------------------ the mouse

    /// The first click lands even though this panel never becomes key.
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach { removeTrackingArea($0) }
        addTrackingArea(NSTrackingArea(rect: bounds,
                                       options: [.mouseEnteredAndExited, .activeAlways,
                                                 .inVisibleRect],
                                       owner: self, userInfo: nil))
    }
    override func mouseEntered(with event: NSEvent) { drag?.hoverChanged(true) }
    override func mouseExited(with event: NSEvent) { if !dragging { drag?.hoverChanged(false) } }

    override func mouseDown(with event: NSEvent) {
        downAt = NSEvent.mouseLocation
        winAt = window?.frame.origin ?? .zero
        dragging = false
    }

    override func mouseDragged(with event: NSEvent) {
        guard let start = downAt else { return }
        let p = NSEvent.mouseLocation
        let dx = p.x - start.x, dy = p.y - start.y
        // A few points of slack, so a click with a shaky hand is not a move.
        if !dragging && hypot(dx, dy) < 3 { return }
        dragging = true
        drag?.dragMoved(origin: NSPoint(x: winAt.x + dx, y: winAt.y + dy), mouse: p)
    }

    override func mouseUp(with event: NSEvent) {
        defer { downAt = nil; dragging = false }
        guard dragging else { return }
        drag?.dragEnded(mouse: NSEvent.mouseLocation)
    }
}

// ---------------------------------------------------------------- drop targets

/// Draw the eight slots for one screen into the current graphics context.
/// `origin` is the screen's frame origin, so rects in global coordinates land
/// in the view's own. Shared by the live overlay and the snapshot.
func drawTargets(_ g: ScreenGeom, highlight: Spot?, origin: NSPoint) {
    let slot = pillSize(.listening, hover: false)
    for s in Spot.allCases {
        let f = g.windowFrame(s, pill: slot).insetBy(dx: PAD, dy: PAD)
            .offsetBy(dx: -origin.x, dy: -origin.y)
        let on = s == highlight
        let r = on ? f.insetBy(dx: -3, dy: -3) : f
        let p = NSBezierPath(roundedRect: r, xRadius: r.height / 2, yRadius: r.height / 2)
        // Dark enough to read on a light wallpaper, rimmed in white to read
        // on a dark one. The highlighted slot takes the app's teal.
        (on ? NSColor(srgbRed: 0.063, green: 0.490, blue: 0.431, alpha: 0.55)
            : NSColor.black.withAlphaComponent(0.16)).setFill()
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

/// The pill's own window. A panel that never becomes key or main, so a click
/// on the pill does not take the cursor out of the field you are typing in.
final class PillPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

func floatingPanel(_ rect: NSRect, level: Int) -> PillPanel {
    let w = PillPanel(contentRect: rect, styleMask: [.borderless, .nonactivatingPanel],
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

// ---------------------------------------------------------------- the app

final class App: NSObject, NSApplicationDelegate, PillDragDelegate {
    private var win: PillPanel!
    private var view: PillView!
    private var overlay: PillPanel?
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

    /// Called directly, not from applicationDidFinishLaunching.
    ///
    /// A binary that is not inside a .app bundle does not reliably get that
    /// callback: NSApplication delivers it as part of a launch sequence a
    /// bare executable never completes. So the orb ran, stayed alive, and did
    /// nothing at all, with no error anywhere, because its entire setup lived
    /// in a method that was never called.
    func start() {
        holdOurOwnLock()
        view = PillView(frame: NSRect(origin: .zero, size: pillSize(.idle, hover: false)))
        view.drag = self
        makeWindow()
        wire()
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
                       queue: .main) { [weak self] _ in self?.hide() }
        nc.addObserver(forName: NSWorkspace.sessionDidBecomeActiveNotification, object: nil,
                       queue: .main) { [weak self] _ in self?.evaluate() }
        NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification, object: nil,
            queue: .main) { [weak self] _ in self?.place(animated: false) }

        // The level and phase still need reading; the expensive question (is a
        // mic open at all) is answered by the event-driven listener above.
        poll = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let s = self else { return }
            s.ticks += 1
            if s.ticks % 5 == 0 { s.reloadSettings() }
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

    /// Put the window where the settings say, at the pill's current size.
    private func place(animated: Bool) {
        guard !view.dragging, !snapping, let s = currentScreen() else { return }
        let f = ScreenGeom(s).windowFrame(settings.spot, pill: view.size)
        move(to: f, animated: animated)
    }

    private func move(to f: NSRect, animated: Bool, done: (() -> Void)? = nil) {
        if f == win.frame { done?(); return }
        if debug {
            FileHandle.standardError.write("orb: \(view.look) at \(settings.spot.rawValue) -> \(f)\n"
                .data(using: .utf8)!)
        }
        if !animated || !win.isVisible || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            win.setFrame(f, display: true)
            view.relayout()
            done?()
            return
        }
        NSAnimationContext.runAnimationGroup({ c in
            c.duration = 0.18
            c.timingFunction = CAMediaTimingFunction(name: .easeOut)
            win.animator().setFrame(f, display: true)
        }, completionHandler: { [weak self] in
            self?.view.relayout()
            done?()
        })
    }

    /// Rebuild rather than reuse. A window kept across a sleep/wake cycle can
    /// silently stop rendering, and from then on orderFrontRegardless() is a
    /// no-op that still reports success: the object exists, every API you
    /// would query looks healthy, and nothing is drawn. Construction is
    /// sub-millisecond, so rebuilding is cheap insurance against the one
    /// failure we cannot see.
    private func show() {
        if win.isVisible { return }
        let look = view.look
        makeWindow()
        place(animated: false)
        view.apply(look, force: true)
        win.orderFrontRegardless()
    }
    private func hide() {
        hideTargets()
        if win.isVisible { win.orderOut(nil) }
    }
    private func rebuild() {
        hide()
        evaluate()
    }

    private func reloadSettings() {
        let m = IndicatorSettings.mtime()
        guard m != settingsAt else { return }
        settingsAt = m
        let s = IndicatorSettings.read()
        guard s != settings else { return }
        settings = s
        place(animated: true)
        evaluate()
    }

    /// Show it regardless of the microphone, so "does it draw" can be tested
    /// apart from "does it decide correctly". Those failed together and looked
    /// identical: nothing on screen.
    private let forced = ProcessInfo.processInfo.environment["VB_ORB_TEST"] != nil

    private func evaluate() {
        if forced {
            set(.listening)
            view.feed(0.7)
            show()
            return
        }
        let hot = presence.isHot
        let ours = weOwnTheMic()
        let d = readDetail()
        let look = decide(hot: hot, ours: ours, detail: d)
        if debug {
            let now = "\(hot)/\(ours)/\(look)"
            if now != lastDebug {
                lastDebug = now
                FileHandle.standardError.write(
                    "orb: mic hot=\(hot) ours=\(ours) -> \(look)\n".data(using: .utf8)!)
            }
        }
        if look == .idle && settings.hideIdle && !view.dragging {
            return hide()
        }
        set(look)
        // Hot but stale: we know the mic is open, not how loud. Some movement
        // rather than flat bars, because flat bars read as "not hearing".
        if look == .listening { view.feed(d.fresh ? d.level : 0.3) }
        show()
    }

    private func set(_ look: Look) {
        guard look != view.look else { return }
        // Dictation starting is the moment to come to the screen being worked
        // on; anything after that stays put, so the pill does not jump
        // between screens in the middle of a sentence.
        if view.look == .idle && look == .listening && !view.dragging {
            screenID = pickScreen()?.displayID
        }
        view.apply(look)
        place(animated: true)
    }

    // ------------------------------------------------------------ dragging

    func hoverChanged(_ on: Bool) {
        guard on != view.hover else { return }
        view.setHover(on)
        if view.look == .idle { place(animated: true) }
    }

    func dragMoved(origin: NSPoint, mouse: NSPoint) {
        win.setFrameOrigin(origin)
        guard let s = NSScreen.screens.first(where: { NSMouseInRect(mouse, $0.frame, false) })
                ?? screenUnderMouse() else { return }
        let g = ScreenGeom(s)
        showTargets(on: s).highlight = g.nearest(to: NSPoint(x: win.frame.midX, y: win.frame.midY))
    }

    func dragEnded(mouse: NSPoint) {
        hideTargets()
        guard let s = NSScreen.screens.first(where: { NSMouseInRect(mouse, $0.frame, false) })
                ?? screenUnderMouse() else { return }
        let g = ScreenGeom(s)
        let spot = g.nearest(to: NSPoint(x: win.frame.midX, y: win.frame.midY))
        settings.spot = spot
        screenID = s.displayID
        IndicatorSettings.save(spot: spot)
        settingsAt = IndicatorSettings.mtime()
        snapping = true
        move(to: g.windowFrame(spot, pill: view.size), animated: true) { [weak self] in
            self?.snapping = false
            self?.place(animated: true)    // in case the look changed meanwhile
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
        ok = write(states(), to: dir.appendingPathComponent("orb-states.png")) && ok
        ok = write(screen(dragging: true), to: dir.appendingPathComponent("orb-drag-targets.png")) && ok
        ok = write(screen(dragging: false), to: dir.appendingPathComponent("orb-placed.png")) && ok
        ok = write(screen(dragging: false, allSpots: true),
                   to: dir.appendingPathComponent("orb-eight-places.png")) && ok
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

    static func pill(_ look: Look, hover: Bool = false, level: CGFloat = 0.65) -> PillView {
        let size = pillSize(look, hover: hover)
        let v = PillView(frame: NSRect(x: 0, y: 0, width: size.width + PAD * 2,
                                       height: size.height + PAD * 2))
        v.apply(look, force: true)
        v.setHover(hover)
        v.relayout()
        if look == .listening { v.freeze(level: level, phase: 1.3) }
        return v
    }

    static func render(_ v: PillView, at origin: NSPoint, in ctx: CGContext) {
        ctx.saveGState()
        ctx.translateBy(x: origin.x, y: origin.y)
        v.layer?.render(in: ctx)
        ctx.restoreGState()
    }

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

    /// Every look, on a light and on a dark background.
    static func states() -> NSBitmapImageRep? {
        let looks: [(String, Look, Bool)] = [("idle", .idle, false), ("idle, hovered", .idle, true),
                                             ("listening", .listening, false),
                                             ("thinking", .thinking, false)]
        let colW: CGFloat = 150, rowH: CGFloat = 70
        let size = NSSize(width: colW * CGFloat(looks.count), height: rowH * 2 + 24)
        return canvas(size) { ctx in
            for (row, bg) in [NSColor(white: 0.96, alpha: 1), NSColor(white: 0.13, alpha: 1)].enumerated() {
                bg.setFill()
                NSRect(x: 0, y: CGFloat(row) * rowH, width: size.width, height: rowH).fill()
            }
            NSColor.white.setFill()
            NSRect(x: 0, y: rowH * 2, width: size.width, height: 24).fill()
            for (i, (name, look, hover)) in looks.enumerated() {
                let p = pill(look, hover: hover)
                for row in 0..<2 {
                    let o = NSPoint(x: CGFloat(i) * colW + (colW - p.frame.width) / 2,
                                    y: CGFloat(row) * rowH + (rowH - p.frame.height) / 2)
                    render(p, at: o, in: ctx)
                }
                let s = NSAttributedString(string: name, attributes: [
                    .font: NSFont.systemFont(ofSize: 11, weight: .medium),
                    .foregroundColor: NSColor(white: 0.25, alpha: 1)])
                s.draw(at: NSPoint(x: CGFloat(i) * colW + (colW - s.size().width) / 2,
                                   y: rowH * 2 + 5))
            }
        }
    }

    /// The made-up screen, with either the drop targets mid-drag or the
    /// pill settled at the top, listening.
    static func screen(dragging: Bool, allSpots: Bool = false) -> NSBitmapImageRep? {
        let g = geom
        return canvas(g.frame.size, scale: 1) { ctx in
            // Wallpaper: a soft gradient, light at the top like most.
            NSGradient(colors: [NSColor(srgbRed: 0.55, green: 0.66, blue: 0.80, alpha: 1),
                                NSColor(srgbRed: 0.86, green: 0.80, blue: 0.74, alpha: 1)])?
                .draw(in: g.frame, angle: 90)
            // A window, so there is something light under the targets too.
            let w = NSRect(x: 260, y: 230, width: 900, height: 560)
            NSColor.white.setFill()
            NSBezierPath(roundedRect: w, xRadius: 12, yRadius: 12).fill()
            NSColor(white: 0.95, alpha: 1).setFill()
            NSBezierPath(rect: NSRect(x: w.minX, y: w.maxY - 40, width: w.width, height: 28)).fill()
            // Menu bar, notch, Dock.
            NSColor.white.withAlphaComponent(0.55).setFill()
            NSRect(x: 0, y: g.visible.maxY, width: g.frame.width,
                   height: g.frame.maxY - g.visible.maxY).fill()
            NSColor.black.setFill()
            if let n = g.notch {
                // Rounded at the bottom only: the top corners run off the screen.
                NSBezierPath(roundedRect: NSRect(x: n.minX, y: n.minY, width: n.width,
                                                 height: n.height + 12),
                             xRadius: 10, yRadius: 10).fill()
            }
            NSColor.white.withAlphaComponent(0.45).setFill()
            NSBezierPath(roundedRect: NSRect(x: 456, y: 4, width: 600, height: 64),
                         xRadius: 18, yRadius: 18).fill()

            if dragging {
                drawTargets(g, highlight: .topRight, origin: .zero)
                // The pill under the pointer, on its way to the top right.
                let p = pill(.idle, hover: true)
                let t = g.windowFrame(.topRight, pill: pillSize(.idle, hover: true))
                render(p, at: NSPoint(x: t.minX - 70, y: t.minY - 46), in: ctx)
            } else if allSpots {
                // Not a real state, one pill only ever exists: where the idle
                // pill sits at each of the eight places.
                for s in Spot.allCases {
                    render(pill(.idle), at: g.windowFrame(s, pill: pillSize(.idle, hover: false)).origin,
                           in: ctx)
                }
            } else {
                let p = pill(.listening)
                render(p, at: g.windowFrame(.top, pill: pillSize(.listening, hover: false)).origin,
                       in: ctx)
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
