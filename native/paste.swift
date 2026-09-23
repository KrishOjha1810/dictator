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

let pb = NSPasteboard.general
// Snapshot every type, not just the string: restoring with setString alone
// destroys RTF, images and multi-item clipboards.
let saved: [[NSPasteboard.PasteboardType: Data]] = (pb.pasteboardItems ?? []).map { item in
    var d: [NSPasteboard.PasteboardType: Data] = [:]
    for t in item.types { if let v = item.data(forType: t) { d[t] = v } }
    return d
}
let savedCount = pb.changeCount

let provider = Provider(text)
pb.clearContents()
pb.writeObjects([provider])
pb.setString("", forType: NSPasteboard.PasteboardType("org.nspasteboard.ConcealedType"))
let afterWrite = pb.changeCount

func tap(_ key: CGKeyCode, flags: CGEventFlags) {
    let src = CGEventSource(stateID: .combinedSessionState)
    let down = CGEvent(keyboardEventSource: src, virtualKey: key, keyDown: true)
    let up = CGEvent(keyboardEventSource: src, virtualKey: key, keyDown: false)
    down?.flags = flags
    up?.flags = flags
    down?.post(tap: .cghidEventTap)
    up?.post(tap: .cghidEventTap)
}

tap(9, flags: .maskCommand)                     // Cmd+V
if send { usleep(120_000); tap(36, flags: []) } // Return

// Wait for the receipt. 1.5s was NOT generous: a busy terminal can take
// longer than that to read the pasteboard, so the receipt came back "unread"
// for pastes that had in fact landed, and the caller then tried a second
// delivery that overwrote the clipboard. Four seconds, and the caller treats
// a missing receipt as unknown rather than as failure.
let deadline = Date().addingTimeInterval(4.0)
while !provider.read && Date() < deadline {
    RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.01))
}

// A short quiet period so the reader is finished with it, then restore, but
// only if nobody else has changed the clipboard in the meantime.
usleep(200_000)
if pb.changeCount == afterWrite {
    pb.clearContents()
    for d in saved {
        let item = NSPasteboardItem()
        for (t, v) in d { item.setData(v, forType: t) }
        pb.writeObjects([item])
    }
}
print(provider.read ? "read" : "unread")
