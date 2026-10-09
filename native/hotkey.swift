// dictator-hotkey: a hold-to-talk (and hands free) listener for macOS.
//
// Prints one line per gesture on stdout, so any language can consume it:
//
//   READY <key> toggle=<latch|off> cap=<ms> doubletap=<on|off>
//   The latch gesture is TWO clean taps of the latch key inside a hold.
//                        the listener is armed, and says how it is configured
//   DOWN                 the talk key went down; start capturing now
//   UP <held_ms>         the talk key came up; stop and transcribe
//   CANCEL <held_ms>     another key joined, so this was a chord, not talking
//   LOCKED <held_ms>     the screen locked while held; treat as CANCEL
//   LATCH <ms>           the hold just became a HANDS FREE session. The mic
//                        that DOWN opened stays open, and the talk key release
//                        that follows deliberately emits NOTHING. Reached by
//                        a DOUBLE TAP of the talk key, by two clean taps of
//                        the latch key inside a hold, or by TOGGLE on stdin.
//   LISTENING <ms>       heartbeat, every 5s, only while a session is open
//   UP <ms> toggle       the user ended the session (one press of the talk
//                        key, FINISH or TOGGLE on stdin); stop and transcribe
//   CANCEL <ms> esc      Escape was pressed mid session; stop and DISCARD
//   CANCEL <ms> button   CANCEL arrived on stdin (the pill's x); DISCARD
//   CANCEL <ms> cap      the session hit its hard cap; stop and DISCARD
//   CANCEL <ms> tap      we lost the ability to see the stop gesture; DISCARD
//   CANCEL <ms> exit     we are exiting mid session; DISCARD
//   LOCKED <ms> lock     the screen locked mid session; DISCARD
//   BYE                  exiting; any open hold or session has been closed
//
// Commands, one per line on stdin, from the dictation loop (the pill's buttons
// reach us this way, so a session has one owner whichever way it started):
//
//   TOGGLE   no session: open one (DOWN, LATCH 0). In one: end it, UP toggle.
//   FINISH   in a session: end it and transcribe (UP <ms> toggle)
//   CANCEL   in a session: end it and discard (CANCEL <ms> button)
//
// The trailing word on the session lines is a reason, always last, always
// optional to read. Every consumer that already splits on whitespace and reads
// token 0 as the verb and token 1 as milliseconds keeps working untouched.
//
// Design notes, each of which is load-bearing:
//
//  * HOLD, and a chord to LATCH. macOS fires the Globe key's own action (emoji
//    picker, input switch) only on the release of a CLEAN TAP, and ignores a
//    hold. So a hold collides with nothing and needs no change to System
//    Settings. A tap gesture would fight the OS.
//
//  * The DOUBLE TAP is the one tap gesture, and it is decided late on
//    purpose. Each tap is still emitted as DOWN and a short UP, so a single
//    tap does exactly what it always did (the loop discards anything under a
//    quarter second). Only when a second clean tap starts within 350 ms of the
//    first one ending, and ends within 300 ms of starting, is its release
//    turned into LATCH instead of UP. The mic the second DOWN opened is the
//    session's mic. macOS still runs the Globe key's own action on each clean
//    tap; this process is listen only and cannot swallow it, so the setup
//    tells the user to set "Press Globe key to" to Do Nothing.
//
//  * The latch key is a MODIFIER by default (shift), not the space bar. fn is
//    not a translation modifier: fn+space produces U+0020 exactly as space
//    alone does, and this process is listen only and CANNOT swallow it. So
//    fn+space would type a space into whatever is in front, scroll a browser,
//    open Quick Look in the Finder, play or pause a video, and press whichever
//    button has focus in a dialog. A modifier tap produces no character and
//    triggers nothing on its own, which is the same reason a hold is safe.
//    --toggle-key space is still offered, for anyone who wants it knowing all
//    of that, and it warns on stderr when selected.
//
//  * LISTEN ONLY, never a suppressing tap. We never need to swallow the key,
//    and a slow suppressing callback stalls keyboard input for the whole
//    machine until it returns. Not a risk worth taking for no benefit. This is
//    also why we do not "fix" fn+space by eating the space: the fix costs more
//    than the collision.
//
//  * We match on KEYCODE, never on the fn flag alone. Arrow keys, Home, End,
//    PageUp/PageDown and the F-keys all set the fn flag, so flag-only matching
//    starts a recording every time you press an arrow. Measured, not theoretical.
//    The latch is the one place we read the flag: on the latch key's OWN event
//    the flag answers exactly the question we are asking, "was the talk key
//    physically down at the instant this key moved", and it answers it even if
//    we missed the talk key's own event.
//
//  * The gesture is decided on key-UP, but DOWN is emitted immediately so the
//    caller can warm the microphone. That is what reconciles "decide late for
//    correctness" with "never lose the first syllable". The latch is decided
//    the same way, on the RELEASE of a clean latch tap: fn+shift+left is a real
//    text selection chord, and deciding on the shift press would latch before
//    the arrow key that proves the user was editing, not talking.
//
//  * A SESSION HAS NO KEY TO POLL. The hold is guarded by a deadman that asks
//    the hardware whether the key is still down, because a missed key-up would
//    otherwise leave the microphone open forever. A hands free session has no
//    such witness: the user's hands are off the keyboard, that is the point, so
//    no event is coming and nothing will fall out of the hardware to correct us.
//    What replaces the deadman is the timer actively verifying the world every
//    second instead of waiting to be told: a hard cap, a login session check,
//    and the rule that the moment we can no longer SEE the stop gesture, we
//    stop. A microphone the user believes is closed but which is open is the
//    worst bug this product can have, so every ambiguity ends the session.

import Cocoa
import CoreGraphics

// ---------------------------------------------------------------- options

struct Options {
    var keyCode: Int64 = 63          // kVK_Function (Fn / Globe)
    var keyName  = "fn"
    var minHoldMs: Double = 120      // shorter than this is a mis-press

    // The latch key, tapped cleanly inside a hold, starts and stops a hands
    // free session. Empty means the gesture is off and this binary behaves
    // exactly as the hold-only one did.
    var latchCodes: Set<Int64> = [56, 60]   // left and right shift
    var latchName = "shift"
    var latchMask: CGEventFlags? = .maskShift   // nil for a non-modifier latch

    // Generous but bounded. Five minutes of hands free dictation is a long
    // utterance; a microphone open for five minutes that nobody remembers
    // opening is a different kind of event entirely.
    var maxSessionMs: Double = 300_000
    var selfTest = false
    /// Read scripted events from stdin and print what they produce, with no
    /// event tap and no permission. For the Python tests.
    var script = false
    /// A double tap of the talk key starts a hands free session.
    var doubleTap = true
}

/// Keycodes and modifier mask for each latch key we accept. Both sides of a
/// modifier count: which shift you tap is not a gesture the user is making.
func latchSpec(_ name: String) -> (Set<Int64>, CGEventFlags?)? {
    switch name {
    case "shift":    return ([56, 60], .maskShift)
    case "control":  return ([59, 62], .maskControl)
    case "option":   return ([58, 61], .maskAlternate)
    case "command":  return ([54, 55], .maskCommand)
    case "rightcmd": return ([54],     .maskCommand)
    case "space":    return ([49],     nil)     // not a modifier: types a space
    case "off":      return ([],       nil)
    default:         return nil
    }
}

func parseArgs() -> Options {
    var o = Options()
    var it = CommandLine.arguments.dropFirst().makeIterator()
    while let a = it.next() {
        switch a {
        case "--key":
            let v = it.next() ?? "fn"
            switch v {
            case "fn", "globe":       o.keyCode = 63; o.keyName = "fn"
            case "rightcmd":          o.keyCode = 54; o.keyName = "rightcmd"
            case "rightopt":          o.keyCode = 61; o.keyName = "rightopt"
            case "leftcmd":           o.keyCode = 55; o.keyName = "leftcmd"
            default:
                FileHandle.standardError.write("unknown --key \(v)\n".data(using: .utf8)!)
                exit(2)
            }
        case "--min-hold":
            o.minHoldMs = Double(it.next() ?? "120") ?? 120
        case "--toggle-key":
            let v = it.next() ?? "shift"
            guard let (codes, mask) = latchSpec(v) else {
                FileHandle.standardError.write(
                    "unknown --toggle-key \(v) (shift, control, option, command, rightcmd, space, off)\n"
                        .data(using: .utf8)!)
                exit(2)
            }
            o.latchCodes = codes; o.latchName = codes.isEmpty ? "off" : v; o.latchMask = mask
        case "--max-session":
            o.maxSessionMs = Double(it.next() ?? "300000") ?? 300_000
        case "--self-test":
            o.selfTest = true
        case "--script":
            o.script = true
        case "--double-tap":
            o.doubleTap = (it.next() ?? "on") != "off"
        case "--help", "-h":
            print("""
            dictator-hotkey [--key fn|rightcmd|rightopt|leftcmd] [--min-hold MS]
                            [--toggle-key shift|control|option|command|rightcmd|space|off]
                            [--max-session MS] [--double-tap on|off]
                            [--self-test] [--script]

            Emits DOWN / UP <ms> / CANCEL <ms> on stdout for a hold-to-talk key,
            and LATCH / LISTENING <ms> / UP <ms> toggle for a hands free session
            started by tapping the toggle key inside a hold, or by a double tap
            of the talk key. A press of the talk key ends a session, Escape
            discards it.

            --script reads events from stdin (down, up, key, esc, sleep MS,
            TOGGLE, FINISH, CANCEL) and prints the lines they produce, with no
            event tap and no permission.

            --toggle-key space is a collision and is not the default: fn+space
            still types a space into whatever is in front of you, because this
            process only listens and cannot swallow it.

            --self-test drives the gesture state machine with scripted events
            and needs no permissions. Everything else requires Accessibility
            (or Input Monitoring) for the running process.
            """)
            exit(0)
        default: break
        }
    }
    // The talk key cannot also be the latch key: the chord would be one key
    // pressed against itself and every hold would latch.
    if o.latchCodes.contains(o.keyCode) {
        FileHandle.standardError.write(
            "dictator-hotkey: --toggle-key \(o.latchName) is the same key as --key \(o.keyName)\n"
                .data(using: .utf8)!)
        exit(2)
    }
    return o
}

var opts = parseArgs()

// ---------------------------------------------------------------- output

// Line-buffered and flushed, because the consumer reads us as a pipe. The
// self test redirects this rather than reading back our own stdout.
var sink: ((String) -> Void)? = nil

func emit(_ s: String) {
    if let sink = sink { sink(s); return }
    print(s)
    fflush(stdout)
}

// ---------------------------------------------------------------- state

final class Gesture {
    private var downAt: Date? = nil          // an open HOLD
    private var interrupted = false
    private var sessionAt: Date? = nil       // an open hands free SESSION
    private var latchAt: Date? = nil         // latch key down inside a hold
    private var latchDirty = false           // something else arrived since
    private var lastToggleAt: Date? = nil
    private var firstTapAt: Date? = nil      // first of the two taps
    /// How long the second tap has to arrive within. Long enough to be
    /// comfortable, short enough that two unrelated shift presses seconds
    /// apart are never read as one gesture.
    private let doubleTapWindow = 0.6
    private var lastBeat: Int = -1

    var isHeld: Bool { downAt != nil }
    var inSession: Bool { sessionAt != nil }

    // ---- the hold, unchanged ---------------------------------------------

    // The double tap of the talk key. A tap is a press shorter than this
    // with nothing else pressed during it; the second one has to START this
    // soon after the first one ENDED.
    static let tapMaxMs: Double = 300
    static let tapGap: TimeInterval = 0.35
    private var lastTapUpAt: Date? = nil     // a clean tap of the talk key just ended
    private var followsTap = false           // this press began inside the gap
    private var latchedAt: Date? = nil       // when the open session began
    private var pressInSession = false       // the talk key is down inside a session

    func down() {
        // During a session the talk key is the stop. One press ends it and
        // transcribes, on the press rather than the release, so it feels
        // immediate; the release that follows says nothing. A press within a
        // third of a second of the session starting is the same burst of
        // tapping that started it (a triple tap), not a decision to stop.
        if sessionAt != nil {
            guard !pressInSession else { return }
            pressInSession = true
            if let l = latchedAt, Date().timeIntervalSince(l) < 0.3 { return }
            endSession(reason: "UP", why: "toggle")
            return
        }
        if pressInSession { return }          // still the press that ended one
        guard downAt == nil else { return }   // ignore auto-repeat
        let now = Date()
        followsTap = opts.doubleTap
            && (lastTapUpAt.map { now.timeIntervalSince($0) <= Gesture.tapGap } ?? false)
        lastTapUpAt = nil
        downAt = now
        interrupted = false
        emit("DOWN")
    }

    /// Any key other than the talk key, held or not. Between two taps it
    /// means they were not one gesture; during a hold it makes it a chord.
    func otherKey() {
        lastTapUpAt = nil
        interrupt()
    }

    /// Another key arrived while we were held, so the user was typing a chord
    /// (fn+left is Home, fn+F1 is brightness). Not talking.
    func interrupt() {
        if latchAt != nil { latchDirty = true }   // ...and not latching either
        guard downAt != nil, !interrupted else { return }
        interrupted = true
    }

    func up(reason: String = "UP") {
        // A latch tap must begin and end inside the same hold. Once the talk
        // key is up there is nothing left to tap it against.
        latchAt = nil
        pressInSession = false
        guard let d = downAt else { return }
        let ms = Date().timeIntervalSince(d) * 1000
        let cleanTap = opts.doubleTap && reason == "UP" && !interrupted && ms < Gesture.tapMaxMs
        if cleanTap && followsTap {
            // The second of two clean taps. Its DOWN already opened the mic;
            // instead of closing it, this release makes it a session.
            followsTap = false
            lastTapUpAt = nil
            startSession()
            return
        }
        downAt = nil
        followsTap = false
        lastTapUpAt = cleanTap ? Date() : nil
        if interrupted {
            emit(String(format: "CANCEL %.0f", ms))
        } else if ms < opts.minHoldMs && reason == "UP" {
            // Too short to be speech. Emitted so the caller can discard the
            // warmed buffer rather than transcribe a click.
            emit(String(format: "CANCEL %.0f", ms))
        } else {
            emit("\(reason) \(Int(ms.rounded()))")
        }
    }

    /// Close any open hold. Used on exit and on screen lock, so the caller can
    /// never be left believing the mic is still held.
    func closeIfHeld(reason: String) {
        if isHeld { up(reason: reason) }
    }

    /// The hold we believe is open, in milliseconds, or nil if none.
    var heldForMs: Double? {
        guard let d = downAt else { return nil }
        return Date().timeIntervalSince(d) * 1000
    }

    // ---- the latch --------------------------------------------------------

    /// The latch key went down while the talk key was held. Deliberately does
    /// NOT latch yet: fn+shift+arrow is a text selection chord, and we only
    /// learn that the arrow is coming after the shift. Marking the hold
    /// interrupted here keeps the old behaviour exactly for every press that
    /// does not become a clean tap: it still CANCELs.
    func latchDown() {
        guard latchAt == nil else { return }      // auto-repeat, or the other shift
        latchAt = Date()
        latchDirty = false
        if downAt != nil { interrupted = true }
    }

    /// The latch key came up. This is the gesture, but only if nothing else
    /// happened between the press and the release.
    /// The whole gesture: two clean taps. Tests and nothing else.
    func latchGesture() {
        latchDown(); latchUp()
        latchDown(); latchUp()
    }

    func latchUp() {
        let started = latchAt
        latchAt = nil
        guard started != nil, !latchDirty else { return }

        // A clean tap is not the gesture on its own, so it must not destroy
        // the recording either. Pressing shift once while dictating is an
        // ordinary thing to do, and it used to cancel the hold outright.
        interrupted = false

        // TWO taps, not one. A single tap of a modifier inside a hold cannot
        // be told apart from somebody simply pressing shift while they talk,
        // and it is not a theoretical confusion: with one tap the gesture
        // latched during ordinary dictation, ended immediately, and threw the
        // sentence away. It ate several in a row. Two taps in half a second
        // is a thing a person does on purpose.
        let now = Date()
        if let first = firstTapAt, now.timeIntervalSince(first) <= doubleTapWindow {
            firstTapAt = nil
        } else {
            firstTapAt = now
            return
        }

        // Key chatter, or a finger that bounced, should not stop a session the
        // same gesture just started. A user cannot mean two things in a third
        // of a second.
        if let t = lastToggleAt, now.timeIntervalSince(t) < 0.35 { return }
        lastToggleAt = now
        if sessionAt != nil {
            endSession(reason: "UP", why: "toggle")
        } else {
            startSession()
        }
    }

    /// Turn the hold that is already recording into a hands free session.
    /// No stop, no restart, no gap: the microphone opened by DOWN keeps
    /// running, which is why the latch can be tapped mid-sentence.
    func startSession() {
        if let d = downAt {
            downAt = nil
            interrupted = false
            sessionAt = d                       // so the final ms is the whole take
            emit("LATCH \(Int((Date().timeIntervalSince(d) * 1000).rounded()))")
        } else {
            // The hold was already closed under us (a tap that died and was
            // re-armed, a cap), so nothing is recording. Open the mic first or
            // the session would be silent and the user would never know.
            emit("DOWN")
            sessionAt = Date()
            emit("LATCH 0")
        }
        lastBeat = -1
        latchedAt = Date()
    }

    /// End a session. `reason` is the verb the consumer already understands:
    /// UP means transcribe, CANCEL and LOCKED mean discard. Everything except
    /// the user's own stop gesture discards, because a session that ended for
    /// any other reason ended without the user deciding it should, and pasting
    /// several minutes of whatever the room was saying into the frontmost app
    /// is not a recoverable mistake.
    func endSession(reason: String, why: String) {
        guard let s = sessionAt else { return }
        sessionAt = nil
        latchAt = nil
        latchedAt = nil
        lastTapUpAt = nil
        let ms = Date().timeIntervalSince(s) * 1000
        emit("\(reason) \(Int(ms.rounded())) \(why)")
    }

    /// One command from stdin. See the header.
    func command(_ c: String) {
        switch c.uppercased() {
        case "TOGGLE":
            if sessionAt != nil { endSession(reason: "UP", why: "toggle") }
            else if downAt == nil { startSession() }
            // A hold in progress: the person is already talking. Leave it.
        case "FINISH":
            endSession(reason: "UP", why: "toggle")
        case "CANCEL":
            endSession(reason: "CANCEL", why: "button")
        default:
            break
        }
    }

    /// Escape, while a session is open: throw it away.
    func escape() {
        if sessionAt != nil { endSession(reason: "CANCEL", why: "esc") }
    }

    /// How long the open session has been running, or nil if none.
    var sessionMs: Double? {
        guard let s = sessionAt else { return nil }
        return Date().timeIntervalSince(s) * 1000
    }

    /// A liveness line every 5s. It costs nothing and it buys the consumer its
    /// own deadman: no heartbeat means this process is wedged or gone, and the
    /// consumer should close the microphone without waiting to be told. It is
    /// also what makes the indicator's "listening" state provably live for the
    /// whole session rather than merely never switched off.
    func beat() {
        guard let ms = sessionMs else { return }
        let n = Int(ms / 5000)
        if n != lastBeat {
            lastBeat = n
            if n > 0 { emit("LISTENING \(Int(ms.rounded()))") }
        }
    }
}

let gesture = Gesture()

// ---------------------------------------------------------------- self test

// Drives the state machine with scripted events. No tap, no permissions, no
// keyboard: this is the part that has to be right, and it is the part nobody
// can test by hand without a hot microphone.
func runSelfTest() -> Never {
    var failures: [String] = []
    var passed = 0

    func scenario(_ name: String,
                  minHold: Double = 0,
                  latch: Set<Int64> = [56, 60],
                  doubleTap: Bool = true,
                  _ body: (Gesture) -> Void,
                  expect: [String]) {
        opts.minHoldMs = minHold
        opts.latchCodes = latch
        opts.doubleTap = doubleTap
        var out: [String] = []
        sink = { out.append($0) }
        body(Gesture())
        sink = nil
        let verbs = out.map { $0.split(separator: " ").first.map(String.init) ?? "" }
        let expectVerbs = expect.map { $0.split(separator: " ").first.map(String.init) ?? "" }
        var ok = verbs == expectVerbs
        // Where the expectation names a reason word, check it too.
        if ok {
            for (line, want) in zip(out, expect) where want.split(separator: " ").count > 2 {
                if !line.hasSuffix(want.split(separator: " ").last.map(String.init)!) { ok = false }
            }
        }
        if ok { passed += 1 } else {
            failures.append("\(name): expected \(expectVerbs), got \(out)")
        }
    }

    // --- the hold path, which must be untouched ---------------------------

    scenario("hold: press, speak, release", minHold: 120, { g in
        g.down()
        usleep(150_000)
        g.up()
    }, expect: ["DOWN", "UP 150"])

    scenario("hold: too short to be speech", minHold: 120, { g in
        g.down()
        g.up()
    }, expect: ["DOWN", "CANCEL 0"])

    scenario("hold: no floor means every press counts", minHold: 0, { g in
        g.down()
        g.up()
    }, expect: ["DOWN", "UP 0"])

    scenario("hold: another key makes it a chord", { g in
        g.down()
        g.interrupt()
        g.up()
    }, expect: ["DOWN", "CANCEL 0"])

    scenario("hold: auto-repeat does not re-open", { g in
        g.down(); g.down(); g.down()
        g.up()
    }, expect: ["DOWN", "UP 0"])

    scenario("hold: screen lock closes it", { g in
        g.down()
        g.closeIfHeld(reason: "LOCKED")
    }, expect: ["DOWN", "LOCKED 0"])

    scenario("hold: closing a hold that is not open says nothing", { g in
        g.closeIfHeld(reason: "UP")
        g.up()
    }, expect: [])

    // --- the latch --------------------------------------------------------

    scenario("latch: clean tap inside a hold starts a session", { g in
        g.down()
        g.latchGesture()
        g.up()                      // the release that follows must say nothing
    }, expect: ["DOWN", "LATCH 0"])

    scenario("latch: a press of the talk key stops and transcribes", { g in
        g.down(); g.latchGesture(); g.up()
        usleep(400_000)             // past the chatter debounce
        g.down()                    // no second DOWN: the mic is already open
        g.up()
    }, expect: ["DOWN", "LATCH 0", "UP 400 toggle"])

    scenario("latch: the second double tap of the latch key still stops it", { g in
        g.down(); g.latchGesture(); g.up()
        usleep(400_000)
        g.latchGesture()
    }, expect: ["DOWN", "LATCH 0", "UP 400 toggle"])

    scenario("latch: fn+shift+arrow is editing, not a latch", { g in
        g.down()
        g.latchDown()
        g.interrupt()               // the arrow key
        g.latchUp()
        g.up()
    }, expect: ["DOWN", "CANCEL 0"])

    scenario("latch: shift held past the talk key release does not latch", { g in
        g.down()
        g.latchDown()
        g.up()                      // fn released first
        g.latchUp()
    }, expect: ["DOWN", "CANCEL 0"])

    scenario("latch: chatter cannot stop what it just started", { g in
        g.down(); g.latchDown(); g.latchUp()
        g.latchDown(); g.latchUp()  // same tap, bounced
        g.up()
    }, expect: ["DOWN", "LATCH 0"])

    scenario("session: the hard cap discards", { g in
        g.down(); g.latchGesture(); g.up()
        g.endSession(reason: "CANCEL", why: "cap")
    }, expect: ["DOWN", "LATCH 0", "CANCEL 0 cap"])

    scenario("session: a lost tap discards", { g in
        g.down(); g.latchGesture(); g.up()
        g.endSession(reason: "CANCEL", why: "tap")
    }, expect: ["DOWN", "LATCH 0", "CANCEL 0 tap"])

    scenario("session: screen lock discards", { g in
        g.down(); g.latchGesture(); g.up()
        g.endSession(reason: "LOCKED", why: "lock")
    }, expect: ["DOWN", "LATCH 0", "LOCKED 0 lock"])

    scenario("session: exiting discards", { g in
        g.down(); g.latchGesture(); g.up()
        g.endSession(reason: "CANCEL", why: "exit")
    }, expect: ["DOWN", "LATCH 0", "CANCEL 0 exit"])

    scenario("session: ending twice says it once", { g in
        g.down(); g.latchGesture(); g.up()
        g.endSession(reason: "CANCEL", why: "cap")
        g.endSession(reason: "CANCEL", why: "exit")
    }, expect: ["DOWN", "LATCH 0", "CANCEL 0 cap"])

    scenario("session: a press straight after the latch is not a stop", { g in
        g.down(); g.latchGesture(); g.up()
        g.down(); g.up()            // inside the 0.3 s after it began
    }, expect: ["DOWN", "LATCH 0"])

    scenario("session: one press stops it, and the next press is a hold again", { g in
        g.down(); g.latchGesture(); g.up()
        usleep(350_000)
        g.down(); g.up()            // the stop; its release says nothing
        g.down(); g.up()            // an ordinary hold
    }, expect: ["DOWN", "LATCH 0", "UP 350 toggle", "DOWN", "UP 0"])

    scenario("session: heartbeats only while one is open", { g in
        let g2 = g
        g2.beat()                   // nothing open
        g2.down(); g2.latchGesture(); g2.up()
        g2.beat()                   // 0ms in, too early to beat
    }, expect: ["DOWN", "LATCH 0"])

    scenario("session: a latch with nothing recording opens the mic first", { g in
        g.latchGesture()            // no hold: the tap died and was re-armed
    }, expect: ["DOWN", "LATCH 0"])

    scenario("latch: ONE tap does nothing at all", { g in
        // The whole reason the gesture needs two. A single tap of a modifier
        // inside a hold cannot be told apart from somebody pressing shift
        // while they talk, and when one tap was enough it latched during
        // ordinary dictation, ended immediately, and threw the sentence away.
        g.down()
        g.latchDown(); g.latchUp()
        g.up()
    }, expect: ["DOWN", "UP 0"])

    scenario("latch: one tap does not cancel the recording either", { g in
        // It used to. Pressing shift once mid sentence is an ordinary thing
        // to do, and it killed the hold outright.
        g.down()
        g.latchDown(); g.latchUp()
        g.up()
    }, expect: ["DOWN", "UP 0"])

    scenario("latch: two taps far apart are two accidents, not a gesture", { g in
        g.down()
        g.latchDown(); g.latchUp()
        usleep(800_000)             // past the window
        g.latchDown(); g.latchUp()
        g.up()
    }, expect: ["DOWN", "UP 800"])

    // --- the double tap of the talk key -----------------------------------

    scenario("double tap: two clean taps start a session", { g in
        g.down(); g.up()
        g.down(); g.up()
    }, expect: ["DOWN", "UP 0", "DOWN", "LATCH 0"])

    scenario("double tap: one tap is still nothing but a short UP", { g in
        g.down(); g.up()
    }, expect: ["DOWN", "UP 0"])

    scenario("double tap: too slow is two separate taps", { g in
        g.down(); g.up()
        usleep(450_000)
        g.down(); g.up()
    }, expect: ["DOWN", "UP 0", "DOWN", "UP 0"])

    scenario("double tap: a held second press is push to talk", { g in
        g.down(); g.up()
        g.down(); usleep(350_000); g.up()
    }, expect: ["DOWN", "UP 0", "DOWN", "UP 350"])

    scenario("double tap: a key between the taps breaks it", { g in
        g.down(); g.up()
        g.otherKey()
        g.down(); g.up()
    }, expect: ["DOWN", "UP 0", "DOWN", "UP 0"])

    scenario("double tap: a chord is not a tap", { g in
        g.down(); g.otherKey(); g.up()
        g.down(); g.up()
    }, expect: ["DOWN", "CANCEL 0", "DOWN", "UP 0"])

    scenario("double tap: then one press stops and transcribes", { g in
        g.down(); g.up(); g.down(); g.up()
        usleep(350_000)
        g.down(); g.up()
    }, expect: ["DOWN", "UP 0", "DOWN", "LATCH 0", "UP 350 toggle"])

    scenario("double tap: a triple tap does not stop what it started", { g in
        g.down(); g.up(); g.down(); g.up(); g.down(); g.up()
    }, expect: ["DOWN", "UP 0", "DOWN", "LATCH 0"])

    scenario("double tap: escape discards", { g in
        g.down(); g.up(); g.down(); g.up()
        g.escape()
    }, expect: ["DOWN", "UP 0", "DOWN", "LATCH 0", "CANCEL 0 esc"])

    scenario("double tap: escape outside a session does nothing", { g in
        g.escape()
    }, expect: [])

    scenario("double tap: off gives two taps", doubleTap: false, { g in
        g.down(); g.up(); g.down(); g.up()
    }, expect: ["DOWN", "UP 0", "DOWN", "UP 0"])

    // --- commands from the loop (the pill's buttons) ----------------------

    scenario("commands: TOGGLE opens a session, TOGGLE again finishes it", { g in
        g.command("TOGGLE"); usleep(50_000); g.command("TOGGLE")
    }, expect: ["DOWN", "LATCH 0", "UP 50 toggle"])

    scenario("commands: CANCEL discards", { g in
        g.command("TOGGLE"); g.command("CANCEL")
    }, expect: ["DOWN", "LATCH 0", "CANCEL 0 button"])

    scenario("commands: FINISH and CANCEL with nothing open say nothing", { g in
        g.command("FINISH"); g.command("CANCEL")
    }, expect: [])

    scenario("commands: TOGGLE during a hold leaves the hold alone", { g in
        g.down(); g.command("TOGGLE"); g.up()
    }, expect: ["DOWN", "UP 0"])

    scenario("commands: a press of the talk key ends a session TOGGLE opened", { g in
        g.command("TOGGLE"); usleep(350_000)
        g.down(); g.up()
    }, expect: ["DOWN", "LATCH 0", "UP 350 toggle"])

    // --- the gesture turned off -------------------------------------------

    scenario("off: the old behaviour, byte for byte", latch: [], { g in
        g.down()
        g.interrupt()               // with no latch key, shift is just a chord
        g.up()
    }, expect: ["DOWN", "CANCEL 0"])

    let total = passed + failures.count
    for f in failures { print("FAIL  \(f)") }
    print("self-test: \(passed)/\(total) passed")
    exit(failures.isEmpty ? 0 : 1)
}

if opts.selfTest { runSelfTest() }

// Scripted events on stdin, the lines they produce on stdout. No tap, no
// permission: the Python tests drive the real state machine through this.
if opts.script {
    while let line = readLine() {
        let w = line.split(separator: " ").map(String.init)
        guard let v = w.first else { continue }
        switch v {
        case "down": gesture.down()
        case "up": gesture.up()
        case "key": gesture.otherKey()
        case "esc": gesture.escape(); gesture.otherKey()
        case "sleep": usleep(UInt32((Double(w.count > 1 ? w[1] : "0") ?? 0) * 1000))
        case "beat": gesture.beat()
        default: gesture.command(v)
        }
    }
    exit(0)
}

// ---------------------------------------------------------------- guards

/// Refuse to act at the login window, on a locked screen, or in a switched-out
/// user session. Otherwise a held key at lock time leaves a hot microphone.
func sessionUsable() -> Bool {
    guard let d = CGSessionCopyCurrentDictionary() as? [String: Any] else { return false }
    let onConsole = d["kCGSSessionOnConsoleKey"] as? Bool ?? false
    let loginDone = d["kCGSessionLoginDoneKey"] as? Bool ?? true
    let locked    = d["CGSSessionScreenIsLocked"] as? Bool ?? false
    return onConsole && loginDone && !locked
}

// ---------------------------------------------------------------- the tap

let FN_MASK = CGEventFlags.maskSecondaryFn.rawValue

/// Is our talk key currently down, according to this event's flags?
func keyIsDown(_ event: CGEvent) -> Bool {
    let f = event.flags
    switch opts.keyCode {
    case 63: return f.contains(.maskSecondaryFn)
    case 54, 55: return f.contains(.maskCommand)
    case 61: return f.contains(.maskAlternate)
    default: return false
    }
}

var tapRef: CFMachPort? = nil
var signalSources: [DispatchSourceSignal] = []

/// Everything that means "we can no longer observe the stop gesture". A hold
/// survives this because the hardware can still be asked whether the key is
/// down. A session cannot: the stop gesture is the only way out of it, so
/// losing sight of the keyboard has to end it.
func endSessionBlind(_ why: String) {
    if gesture.inSession { gesture.endSession(reason: "CANCEL", why: why) }
}

let callback: CGEventTapCallBack = { _, type, event, _ in
    // The system disables a tap that is slow or that sees certain input. It
    // stays dead until explicitly re-enabled, which is a stuck-hot-mic bug if
    // you miss it.
    if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
        gesture.closeIfHeld(reason: "UP")
        endSessionBlind("tap")
        if let t = tapRef { CGEvent.tapEnable(tap: t, enable: true) }
        return Unmanaged.passUnretained(event)
    }

    if !sessionUsable() {
        gesture.closeIfHeld(reason: "LOCKED")
        if gesture.inSession { gesture.endSession(reason: "LOCKED", why: "lock") }
        return Unmanaged.passUnretained(event)
    }

    let kc = event.getIntegerValueField(.keyboardEventKeycode)
    let latched = opts.latchCodes.contains(kc)
    // Read the talk key off THIS event's own flags rather than off what we
    // believe. It is the same question asked of a better witness: if we missed
    // the talk key's own event, this one still carries the flag.
    let talkHeld = keyIsDown(event)

    if type == .flagsChanged {
        if kc == opts.keyCode {
            talkHeld ? gesture.down() : gesture.up()
        } else if latched, let mask = opts.latchMask {
            // A modifier latch: its own flag tells us which edge this is.
            if !talkHeld {
                gesture.otherKey()              // outside a hold it is just a chord
            } else if event.flags.contains(mask) {
                gesture.latchDown()
            } else {
                gesture.latchUp()
            }
        } else {
            // A different modifier: inside a hold it is a chord, and between
            // two taps it means they were not a double tap.
            gesture.otherKey()
        }
        return Unmanaged.passUnretained(event)
    }

    if latched && opts.latchMask == nil {
        // A non-modifier latch (space). The character has already gone to the
        // frontmost app by the time we see this; see the header.
        if talkHeld {
            if type == .keyDown { gesture.latchDown() } else { gesture.latchUp() }
            return Unmanaged.passUnretained(event)
        }
    }

    // Escape throws a hands free session away. It still reaches the app in
    // front: this tap only listens.
    if type == .keyDown && kc == 53 { gesture.escape() }
    // Any ordinary key pressed while held means the user is typing, not
    // talking, and between two taps it means they were not a double tap.
    if type == .keyDown { gesture.otherKey() }
    return Unmanaged.passUnretained(event)
}

// A modifier latch arrives as flagsChanged, so in the default configuration we
// still never ask for keyUp. Every event type in the mask is a callback on the
// path of every keystroke on the machine, and the one thing this tap must
// never be is slow.
let needsKeyUp = opts.latchMask == nil && !opts.latchCodes.isEmpty

var mask = (1 << CGEventType.flagsChanged.rawValue)
         | (1 << CGEventType.keyDown.rawValue)
         | (1 << CGEventType.tapDisabledByTimeout.rawValue)
         | (1 << CGEventType.tapDisabledByUserInput.rawValue)
if needsKeyUp { mask |= (1 << CGEventType.keyUp.rawValue) }

guard let tap = CGEvent.tapCreate(tap: .cgSessionEventTap,
                                  place: .headInsertEventTap,
                                  options: .listenOnly,
                                  eventsOfInterest: CGEventMask(mask),
                                  callback: callback,
                                  userInfo: nil) else {
    FileHandle.standardError.write("""
    dictator-hotkey: could not create an event tap.

    Grant the app running this process Accessibility permission:
      System Settings > Privacy & Security > Accessibility

    Note macOS only honours a fresh grant for taps created by a NEW process,
    so restart this after granting.

    """.data(using: .utf8)!)
    exit(1)
}
tapRef = tap

CFRunLoopAddSource(CFRunLoopGetCurrent(),
                   CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0),
                   .commonModes)
CGEvent.tapEnable(tap: tap, enable: true)

// The disable callback is not reliable; Ghostty shipped without a watchdog and
// its hotkey died after every sleep/wake cycle.
Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { _ in
    guard let t = tapRef else { return }
    if !CGEvent.tapIsEnabled(tap: t) {
        gesture.closeIfHeld(reason: "UP")
        endSessionBlind("tap")
        CGEvent.tapEnable(tap: t, enable: true)
    }
}

// A tap that is disabled mid-hold never delivers the key-up, so the utterance
// would run forever with the microphone open. Re-arming the tap does not
// synthesise the release we missed, so nothing above catches this.
//
// `CGEventSource.keyState` is the reliable reading here. Its sibling
// `flagsState` is a snapshot of the last event's flags and goes stale, which
// is why we ask about the key rather than the modifier.
let HARD_CAP_MS: Double = 120_000

Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
    // A session first, and it never coexists with a hold. This branch is the
    // session's entire safety net, because it is the only thing that runs
    // while the user's hands are nowhere near the keyboard.
    if let open = gesture.sessionMs {
        if open > opts.maxSessionMs {
            // Nobody dictates for this long on purpose. Discarding rather than
            // transcribing is deliberate: a session that reached the cap is far
            // more likely to be a microphone somebody forgot than a monologue.
            gesture.endSession(reason: "CANCEL", why: "cap")
            return
        }
        // Asked every second, not only when an event arrives. The hold learns
        // about a locked screen from the next keystroke; a hands free session
        // has no next keystroke, so it has to look.
        if !sessionUsable() {
            gesture.endSession(reason: "LOCKED", why: "lock")
            return
        }
        if let t = tapRef, !CGEvent.tapIsEnabled(tap: t) {
            gesture.endSession(reason: "CANCEL", why: "tap")
            CGEvent.tapEnable(tap: t, enable: true)
            return
        }
        gesture.beat()
        return
    }

    guard let held = gesture.heldForMs else { return }

    if held > HARD_CAP_MS {
        gesture.closeIfHeld(reason: "UP")     // nobody speaks for two minutes
        return
    }
    let stillDown = CGEventSource.keyState(.combinedSessionState,
                                           key: CGKeyCode(opts.keyCode))
    if !stillDown {
        // We believe it is held and the hardware disagrees. Trust the hardware.
        gesture.closeIfHeld(reason: "UP")
    }
}

// Never exit leaving the caller believing the key is still held, or that a
// session it can no longer be told about is still running.
for sig in [SIGINT, SIGTERM, SIGHUP] {
    signal(sig, SIG_IGN)
    let src = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    src.setEventHandler {
        gesture.closeIfHeld(reason: "UP")
        if gesture.inSession { gesture.endSession(reason: "CANCEL", why: "exit") }
        emit("BYE")
        exit(0)
    }
    src.resume()
    signalSources.append(src)
}

// Prove the tap can actually RECEIVE, not merely that it was created. The two
// are different and the difference is invisible: without Accessibility for THIS
// process, tapCreate succeeds and then nothing ever arrives. That is the whole
// failure mode of running from launchd, where the process is no longer the
// terminal the permission was granted to.
//
// A synthetic F16 (unmapped on a stock Mac, so harmless) posted to ourselves
// settles it in a few milliseconds.
var sawSelfTest = false
let probeTap = CGEvent.tapCreate(tap: .cghidEventTap, place: .headInsertEventTap,
                                 options: .listenOnly,
                                 eventsOfInterest: CGEventMask(1 << CGEventType.keyDown.rawValue),
                                 callback: { _, _, ev, _ in
    if ev.getIntegerValueField(.keyboardEventKeycode) == 106 { sawSelfTest = true }
    return Unmanaged.passUnretained(ev)
}, userInfo: nil)
if let pt = probeTap {
    CFRunLoopAddSource(CFRunLoopGetCurrent(),
                       CFMachPortCreateRunLoopSource(kCFAllocatorDefault, pt, 0),
                       .commonModes)
    CGEvent.tapEnable(tap: pt, enable: true)
    let src = CGEventSource(stateID: .hidSystemState)
    CGEvent(keyboardEventSource: src, virtualKey: 106, keyDown: true)?.post(tap: .cghidEventTap)
    CGEvent(keyboardEventSource: src, virtualKey: 106, keyDown: false)?.post(tap: .cghidEventTap)
    CFRunLoopRunInMode(.defaultMode, 0.4, false)
    CGEvent.tapEnable(tap: pt, enable: false)
}
// AXIsProcessTrusted is the one that decides whether HARDWARE events arrive.
// The synthetic probe above cannot tell you: a process can always see events
// it posted itself, so it proves the tap is alive and nothing more.
let trusted = AXIsProcessTrusted()
FileHandle.standardError.write(
    "dictator-hotkey: accessibility trusted = \(trusted)\n".data(using: .utf8)!)
if !trusted {
    FileHandle.standardError.write("""

    Hardware key presses will NOT reach this process.

    macOS grants Accessibility per application, and when this runs at login it
    is not the terminal you granted. Add the thing that starts it:
      System Settings > Privacy & Security > Accessibility
      +  and add:  /usr/bin/env     (or your python3)

    A grant is only honoured by a NEW process, so restart it afterwards:
      dictator off && dictator on

    """.data(using: .utf8)!)
}
if !sawSelfTest {
    FileHandle.standardError.write("""
    dictator-hotkey: the event tap was created but receives NOTHING.

    macOS grants Accessibility per application, and this process is not the
    terminal you granted it to. Add the program that STARTS it:
      System Settings > Privacy & Security > Accessibility

    A fresh grant is only honoured for a NEW process, so restart after adding.

    """.data(using: .utf8)!)
}
if opts.latchMask == nil && !opts.latchCodes.isEmpty {
    FileHandle.standardError.write("""
    dictator-hotkey: --toggle-key \(opts.latchName) types into the app in front.

    fn is not a translation modifier, so \(opts.keyName)+\(opts.latchName) reaches the
    frontmost app exactly as \(opts.latchName) alone does, and this process listens
    without suppressing. Expect a stray character in your text, a scrolled
    page, a Quick Look window in the Finder, or a pressed button in a dialog.
    A modifier (--toggle-key shift) produces nothing at all.

    """.data(using: .utf8)!)
}

// Commands from the loop on stdin (the pill's buttons). An EOF, as when the
// caller gave us no pipe, just stops reading.
FileHandle.standardInput.readabilityHandler = { h in
    let d = h.availableData
    if d.isEmpty { h.readabilityHandler = nil; return }
    let text = String(decoding: d, as: UTF8.self)
    DispatchQueue.main.async {
        for line in text.split(whereSeparator: \.isNewline) {
            gesture.command(line.trimmingCharacters(in: .whitespaces))
        }
    }
}

emit("READY \(opts.keyName) toggle=\(opts.latchCodes.isEmpty ? "off" : opts.latchName) "
     + "cap=\(Int(opts.maxSessionMs)) doubletap=\(opts.doubleTap ? "on" : "off")")
CFRunLoopRun()
