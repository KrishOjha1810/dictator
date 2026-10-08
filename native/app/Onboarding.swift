// Six cards, shown on the first launch only.
//
// Continue is enabled by what is actually true, never by a button having been
// clicked: the microphone status as AVFoundation reports it, AXIsProcessTrusted
// for this process, the key seen going down, the models on disk as the loop
// reports them in status.json, and words arriving in the box. The same rule
// `doctor` follows, for the same reason: a ticked checkbox that does not count
// is the failure this app was written to end.

import AVFoundation
import AppKit
import SwiftUI

final class OnboardingState: ObservableObject {
    @Published var card = 0
    @Published var keySeen = false
    @Published var tried = ""
    @Published var asked = false
}

struct OnboardingView: View {
    @EnvironmentObject var model: AppModel
    var done: () -> Void
    @StateObject private var st = OnboardingState()

    private let count = 6

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                ForEach(0..<count, id: \.self) { i in
                    Circle()
                        .fill(i <= st.card ? Color.accentColor : Color.secondary.opacity(0.3))
                        .frame(width: 7, height: 7)
                }
            }
            .padding(.bottom, 28)

            Group {
                switch st.card {
                case 0: welcome
                case 1: microphone
                case 2: accessibility
                case 3: yourKey
                case 4: languages
                default: tryIt
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

            HStack {
                if st.card > 0 {
                    Button("Back") { st.card -= 1 }
                }
                Spacer()
                // The models card is the one step that can take minutes, and
                // what it waits for keeps arriving with the window closed.
                if st.card == 4 && !ready {
                    Button("Continue, finish in background") { st.card += 1 }
                }
                Button(st.card == count - 1 ? "Done" : "Continue →") {
                    if st.card == count - 1 { done() } else { st.card += 1 }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(!ready)
            }
        }
        .padding(32)
        .frame(width: 560, height: 440)
    }

    /// Whether the current card's step is really done.
    private var ready: Bool {
        switch st.card {
        case 1: return model.mic == .authorized
        case 2: return model.trusted
        case 3: return st.keySeen
        case 4: return model.status.modelsReady
        case 5: return !st.tried.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        default: return true
        }
    }

    private func title(_ s: String) -> some View {
        Text(s).font(.system(size: 22, weight: .semibold)).padding(.bottom, 12)
    }

    private func line(_ s: String) -> some View {
        Text(s).font(.system(size: 14)).foregroundColor(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func check(_ ok: Bool, _ label: String) -> some View {
        Label(label, systemImage: ok ? "checkmark.circle.fill" : "circle")
            .foregroundColor(ok ? .green : .secondary)
            .font(.system(size: 13))
    }

    // ---------------------------------------------------------------------

    private var welcome: some View {
        VStack(alignment: .leading) {
            title("Hold a key, talk, and the words land at your cursor")
            line("It works in any app that takes text: the terminal, a browser, "
                 + "a chat window. Speech is turned into text on this Mac and "
                 + "nothing you say leaves it.")
            Spacer().frame(height: 16)
            line("Five short steps: two permissions, your key, the speech models, "
                 + "and a first sentence.")
        }
    }

    private var microphone: some View {
        VStack(alignment: .leading, spacing: 10) {
            title("Dictator needs your microphone")
            line("It listens only while you hold the key. Audio never leaves this Mac.")
            Spacer().frame(height: 12)
            HStack(spacing: 16) {
                Button("Allow microphone") { askForMicrophone { _ in model.refresh() } }
                    .disabled(model.mic == .authorized)
                check(model.mic == .authorized,
                      model.mic == .authorized ? "Allowed" : "Not yet")
            }
            if model.mic == .denied || model.mic == .restricted {
                // Once refused, the prompt never shows again; only the
                // switch in System Settings can change it.
                line("It was turned off before. Switch Dictator on in System "
                     + "Settings, Privacy & Security, Microphone.")
                Button("Open Microphone settings") {
                    NSWorkspace.shared.open(URL(string:
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")!)
                }
            }
        }
    }

    private var accessibility: some View {
        VStack(alignment: .leading, spacing: 10) {
            title("And Accessibility, to type for you")
            line("This is how the words get into the app you are using, and how "
                 + "the key is noticed while another app is in front.")
            Spacer().frame(height: 12)
            HStack(spacing: 16) {
                Button("Allow Accessibility") {
                    st.asked = true
                    _ = askForAccessibility()
                    NSWorkspace.shared.open(URL(string:
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
                }
                .disabled(model.trusted)
                check(model.trusted, model.trusted ? "Allowed" : "Not yet")
            }
            if st.asked && !model.trusted {
                // The stale-entry trap from the README: an old row for this
                // app, its switch already on, and macOS not counting it.
                line("If Dictator is already switched on in the list and this "
                     + "still says Not yet, the entry belongs to an older copy. "
                     + "Select it, remove it with the minus button, then click "
                     + "Allow Accessibility again.")
            }
        }
    }

    private var yourKey: some View {
        VStack(alignment: .leading, spacing: 10) {
            title("Your key")
            line("Hold it to talk, let go to stop. Pick one, then press it now.")
            Spacer().frame(height: 8)
            Picker("", selection: Binding(get: { model.key },
                                          set: { model.setKey($0); st.keySeen = false })) {
                ForEach(Prefs.keys, id: \.self) { Text(Prefs.keyNames[$0] ?? $0).tag($0) }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 360)
            check(st.keySeen, st.keySeen ? "Seen" : "Press \(Prefs.keyNames[model.key] ?? model.key) now")
                .padding(.top, 8)
        }
        .background(KeyWatcher(key: model.key) { st.keySeen = true }.id(model.key))
    }

    private var languages: some View {
        VStack(alignment: .leading, spacing: 10) {
            title("Languages")
            line("English is ready first. Hinglish needs a larger model, which keeps "
                 + "downloading in the background if you move on later.")
            Spacer().frame(height: 8)
            if model.status.models.isEmpty {
                line("Waiting for Dictator to report its models…")
            }
            ForEach(model.status.models, id: \.name) { m in
                VStack(alignment: .leading, spacing: 4) {
                    check(m.have, modelTitle(m.name) + (m.have ? ", ready" : ""))
                    if !m.have {
                        ProgressView(value: m.progress).frame(width: 360)
                    }
                }
            }
        }
    }

    private var tryIt: some View {
        VStack(alignment: .leading, spacing: 10) {
            title("Try it")
            line("Click in the box, hold \(Prefs.keyNames[model.key] ?? model.key) and say: "
                 + "\"yaar ye test kar ke dekho\". Let go and it appears here.")
            TextEditor(text: $st.tried)
                .font(.system(size: 14))
                .frame(height: 110)
                .overlay(RoundedRectangle(cornerRadius: 6)
                    .stroke(Color.secondary.opacity(0.3)))
        }
    }
}

/// Notices the chosen modifier key going down. A global monitor sees it while
/// another app is in front, a local one while this window is; neither alone is
/// enough, because the card is in front while the user presses it.
struct KeyWatcher: NSViewRepresentable {
    var key: String
    var seen: () -> Void

    // Virtual key codes from Carbon's Events.h.
    static let codes: [String: UInt16] = ["fn": 63, "rightcmd": 54,
                                          "rightopt": 61, "leftcmd": 55]

    final class Coordinator {
        var monitors: [Any] = []
        deinit { monitors.forEach { NSEvent.removeMonitor($0) } }
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> NSView {
        let code = KeyWatcher.codes[key] ?? 63
        let hit: (NSEvent) -> Void = { e in
            // flagsChanged fires on release too; only the press counts.
            let down: Bool
            switch code {
            case 63: down = e.modifierFlags.contains(.function)
            case 61: down = e.modifierFlags.contains(.option)
            default: down = e.modifierFlags.contains(.command)
            }
            if e.keyCode == code && down { DispatchQueue.main.async { seen() } }
        }
        if let g = NSEvent.addGlobalMonitorForEvents(matching: .flagsChanged, handler: hit) {
            context.coordinator.monitors.append(g)
        }
        if let l = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged,
                                                    handler: { hit($0); return $0 }) {
            context.coordinator.monitors.append(l)
        }
        return NSView()
    }

    func updateNSView(_ v: NSView, context: Context) {}
}
