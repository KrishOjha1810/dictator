// The Notetaker: start and stop recording a meeting from the pill, the menu
// or Option-M. All of the recording is `dictator meeting start|stop`
// (dictator_core/meeting.py); this only decides when to run it, and asks first.
//
// Recording other people has consent implications, and in some places legal
// ones. So the first time, the app (never the pill, which is too small and too
// easy to click past) says so in a window and waits for a yes. After that the
// shortcut and the button act straight away; macOS shows its own recording
// indicator for as long as a meeting records, and the pill's button is red.

import AppKit
import Foundation

final class Notetaker {
    static let shared = Notetaker()

    /// A start or stop is running. Clicks meanwhile are ignored, so a
    /// double click cannot start two recorders or stop one twice.
    private(set) var busy = false
    /// Fake mode never records; it remembers a pretend state instead.
    private var fakeRecording = false

    /// Is a meeting recording, asked of the CLI (which asks the recorder's
    /// pid, not a flag file).
    func recording(_ done: @escaping (Bool) -> Void) {
        if fake { done(fakeRecording); return }
        CLI.load({ CLI.json(["meeting", "status"]) }) { any in
            done((any as? [String: Any])?["recording"] as? Bool ?? false)
        }
    }

    func toggle() {
        guard !busy else { return }
        if !Prefs.meetingConsent {
            guard askConsent() else { return }
            Prefs.meetingConsent = true
        }
        busy = true
        recording { on in on ? self.stop() : self.start() }
    }

    private func start() {
        if fake {
            NSLog("dictator (fake): would run dictator meeting start")
            fakeRecording = true
            busy = false
            return
        }
        CLI.load({ runCLI(["meeting", "start"]) }) { r in
            self.busy = false
            guard r.status != 0 else { return }
            // Usually the Screen Recording permission the recorder needs for
            // the other side of the call. The CLI says which, in words.
            let a = NSAlert()
            a.messageText = "The Notetaker did not start"
            a.informativeText = String(data: r.out, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            a.addButton(withTitle: "OK")
            NSApp.activate(ignoringOtherApps: true)
            a.runModal()
        }
    }

    /// Stopping also transcribes and writes the notes, which takes minutes,
    /// so it runs in the background. The recorder itself stops at once; the
    /// pill's button stops being red as soon as it has.
    private func stop() {
        if fake {
            NSLog("dictator (fake): would run dictator meeting stop")
            fakeRecording = false
            busy = false
            return
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { self.busy = false }
        CLI.load({ runCLI(["meeting", "stop"]) }) { r in
            NSLog("dictator: meeting stop exited \(r.status)")
        }
    }

    /// The one-time question. True when the person agreed.
    func askConsent() -> Bool {
        let a = NSAlert()
        a.icon = NSImage(systemSymbolName: "record.circle", accessibilityDescription: nil)
        a.messageText = "The Notetaker records other people"
        a.informativeText = """
            It records two tracks on this Mac: your microphone, and the system audio, \
            which is everybody else on the call. Nothing is uploaded; the transcript and \
            the notes are made here.

            Recording a conversation has consent implications, and in some places legal \
            ones: several US states, and much of Europe, require everyone to agree. The \
            Notetaker never starts on its own, and macOS shows its recording indicator for \
            as long as it runs. Tell the room. It costs one sentence.

            Start and stop it with the record button on the pill, or Option-M.
            """
        a.addButton(withTitle: "Start Recording")
        a.addButton(withTitle: "Cancel")
        NSApp.activate(ignoringOtherApps: true)
        a.window.level = .floating
        return a.runModal() == .alertFirstButtonReturn
    }
}
