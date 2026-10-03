// Paste text, and put the clipboard back only once it has actually been read.
//
// The obvious version (copy, send Cmd+V, sleep, restore) is wrong, and it is
// wrong in a way that is invisible until the machine is busy: under load the
// target app has not read the pasteboard when the timer fires, so the restore
// lands first and the user gets their OLD clipboard pasted instead of what
// they said. A fixed delay is a guess about someone else's scheduling.
//
// So the text is published as a PROMISE rather than as data. The pasteboard
// calls back when something actually asks for the string, and that callback is
// a read receipt: proof the paste happened rather than a hope that it did.
// Only then is the previous clipboard restored.
//
// Also declares org.nspasteboard.ConcealedType, the convention clipboard
// managers watch for, so a dictated sentence does not end up in the user's
// clipboard history.

import AppKit

final class Provider: NSObject, NSPasteboardWriting {
    let text: String
    var read = false
    init(_ t: String) { text = t }

    func writableTypes(for pb: NSPasteboard) -> [NSPasteboard.PasteboardType] {
        [.string]
    }
    func writingOptions(forType type: NSPasteboard.PasteboardType,
                        pasteboard: NSPasteboard) -> NSPasteboard.WritingOptions {
        .promised          // hand it over only when asked
    }
    func pasteboardPropertyList(forType type: NSPasteboard.PasteboardType) -> Any? {
        read = true        // the receipt
        return text
    }
}

let args = CommandLine.arguments
guard args.count > 1 else {
    FileHandle.standardError.write("usage: dictator-paste <text> [--send]\n".data(using: .utf8)!)
    exit(2)
}
let text = args[1]
let send = args.contains("--send")
let typeIt = args.contains("--type")
let src0 = CGEventSource(stateID: .combinedSessionState)

let pb = NSPasteboard.general
// Snapshot every type, not just the string: restoring with setString alone
// destroys RTF, images and multi-item clipboards.
let saved: [[NSPasteboard.PasteboardType: Data]] = (pb.pasteboardItems ?? []).map { item in
    var d: [NSPasteboard.PasteboardType: Data] = [:]
    for t in item.types { if let v = item.data(forType: t) { d[t] = v } }
    return d
}
let savedCount = pb.changeCount

// PLAIN DATA, not a promise. The promise was the clever version: it could
// report when something had actually collected the text, so the clipboard was
// only restored once the paste had provably happened.
//
// It does not work reliably here. On real holds the receipt came back "unread"
// every time while the same helper run from a shell reported "read", and the
// cost was not one slow paste. A long transcript is delivered in several
// pieces, so it was four seconds of waiting PER PIECE, and each piece left its
// own text on the clipboard as the fallback, so the safety net held only the
// last piece and the rest of the sentence was gone. That is how a whole
// dictation was lost.
//
// Plain data with a short settle is what every other tool does, and it is
// right for the same reason: the paste either lands or it does not, and a
// receipt that lies about which is worse than no receipt at all.
pb.clearContents()
pb.setString(text, forType: .string)
let afterWrite = pb.changeCount

// Posting a keystroke needs Accessibility, and without it CGEventPost does
// nothing AND reports nothing: it is not an error, the event simply never
// reaches anybody. So this helper happily wrote the clipboard, posted a
// Command-V into the void, and printed "pasted".
//
// Seen on a real machine the day the bundle identifier changed: three holds
// in a row transcribed correctly, logged "pasting into Terminal", and the
// words never appeared. Nothing anywhere said why, because from the inside
// everything had worked.
//
// The text is already on the clipboard by the time this is called, so the
// honest answer is to say so and let the caller tell the user to press
// Command-V, rather than to claim a paste that did not happen.
func canPost() -> Bool {
    return AXIsProcessTrusted()
}

func tap(_ key: CGKeyCode, flags: CGEventFlags) {
    let src = CGEventSource(stateID: .combinedSessionState)
    let down = CGEvent(keyboardEventSource: src, virtualKey: key, keyDown: true)
    let up = CGEvent(keyboardEventSource: src, virtualKey: key, keyDown: false)
    down?.flags = flags
    up?.flags = flags
    down?.post(tap: .cghidEventTap)
    up?.post(tap: .cghidEventTap)
}

// Two ways to get the words in. Typing is the honest one: it touches nobody's
// clipboard, it produces no paste event, so an application that treats a paste
// differently from typing (Claude Code turns a long one into an attachment)
// sees exactly what a person at the keyboard would produce.
//
// It is not free. Every character is two events the target has to process, so
// it needs a gap between them or they arrive out of order or not at all, and
// that gap is the whole cost: a 300 character transcript is about half a
// second of visible typing. Pasting is one event whatever the length.
//
// Unicode is NOT a reason to avoid it. keyboardSetUnicodeString carries any
// character, Devanagari and emoji included, because the string travels with
// the event instead of being looked up from a key code.
if typeIt {
    for ch in Array(text.utf16) {
        var c = ch
        let d = CGEvent(keyboardEventSource: src0, virtualKey: 0, keyDown: true)
        let u = CGEvent(keyboardEventSource: src0, virtualKey: 0, keyDown: false)
        d?.keyboardSetUnicodeString(stringLength: 1, unicodeString: &c)
        u?.keyboardSetUnicodeString(stringLength: 1, unicodeString: &c)
        d?.post(tap: .cghidEventTap)
        u?.post(tap: .cghidEventTap)
        usleep(1500)
    }
    if send { usleep(120_000); tap(36, flags: []) }
    print("typed")
    exit(0)
}

tap(9, flags: .maskCommand)                     // Cmd+V
if send { usleep(120_000); tap(36, flags: []) } // Return

// Long enough for the target to read the pasteboard, short enough that a
// three piece delivery is not a wait. Nothing is being detected here: this is
// simply time for the paste to happen before the clipboard changes under it.
usleep(250_000)

// A short quiet period so the reader is finished with it, then restore, but
// only if nobody else has changed the clipboard in the meantime.
//
// AND only if the text was actually read. Without a receipt we do not know
// that Cmd-V reached anything, and restoring the old clipboard on top of a
// paste that never happened destroys the only remaining copy of what the
// person just said. Leaving it on the clipboard costs them one stale
// clipboard entry; restoring costs them the sentence. Print which happened,
// so the caller can tell them the words are on the clipboard rather than
// leaving them to wonder where the words went.
// Restore only if nobody else has touched the clipboard since. `--keep` says
// this is not the last piece of a longer delivery, so the text stays put and
// the caller restores once at the end; restoring between pieces is what left
// only the final chunk behind when a delivery went wrong.
// ...and only if we were able to post the keystroke at all. Without
// Accessibility the paste never happened, so `changeCount` is unchanged for
// the wrong reason, and restoring here wipes the text out of the one place
// the user could still have reached it from. Measured on a real machine: the
// hold transcribed correctly, the log said "pasting into Terminal", nothing
// appeared, and the clipboard still held what it held an hour earlier. The
// words existed for 250 milliseconds and then this line deleted them.
if canPost() && !args.contains("--keep") && pb.changeCount == afterWrite {
    pb.clearContents()
    for d in saved {
        let item = NSPasteboardItem()
        for (t, v) in d { item.setData(v, forType: t) }
        pb.writeObjects([item])
    }
}
if canPost() {
    print("pasted")
} else {
    // Not "pasted". The words are on the clipboard and nowhere else.
    print("no-accessibility")
}
