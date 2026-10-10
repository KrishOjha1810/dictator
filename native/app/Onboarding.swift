// Six cards, shown on the first launch only.
//
// Continue is enabled by what is actually true, never by a button having been
// clicked: the microphone status as AVFoundation reports it, AXIsProcessTrusted
// for this process, the key seen going down, the models on disk as the loop
// reports them in status.json, and a new result in last.json. The same rule
// `doctor` follows, for the same reason: a ticked checkbox that does not count
// is the failure this app was written to end.

import AVFoundation
import AppKit
import SwiftUI

final class OnboardingState: ObservableObject {
    @Published var card = 0
    @Published var keySeen = false
    @Published var asked = false
    /// The key picked on the "Your key" card. Applied (and the loop restarted
    /// for it) once, on Continue; trying keys out costs nothing.
    @Published var key = Prefs.key
    /// Whether the Hinglish question was answered on this run.
    @Published var answered = false
    /// When the "Try it" card appeared. A last.json older than this is from
    /// before, and does not count as trying it.
    @Published var tryFrom: Double = 0

    init() {
        // DICTATOR_CARD=n opens on card n, for screenshots in fake mode.
        if fake, let n = env["DICTATOR_CARD"].flatMap(Int.init) { card = max(0, min(5, n)) }
        if card == 5 { tryFrom = Date().timeIntervalSince1970 }
    }
}

struct OnboardingView: View {
    @EnvironmentObject var model: AppModel
    var done: () -> Void
    @StateObject private var st = OnboardingState()

    private let count = 6

    var body: some View {
        VStack(spacing: 0) {
            VStack(spacing: 0) {
            progress
                .padding(.top, 22)

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
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(.horizontal, 56)
            }
            // The first card is the brand moment: the icon's gradient, full
            // bleed, with the grille's lines drifting off the corner.
            .background(Group {
                if st.card == 0 {
                    ZStack {
                        Theme.brand
                        VStack(alignment: .leading, spacing: 18) {
                            ForEach([260.0, 340, 200, 300, 230], id: \.self) { w in
                                Capsule().fill(Color.white.opacity(0.06)).frame(width: w, height: 14)
                            }
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
                        .offset(x: -60, y: 30)
                    }
                    .clipped()
                }
            })

            footer
                .padding(.horizontal, Theme.s5)
                .padding(.vertical, Theme.s4)
                .background(Theme.card.opacity(0.6))
                .overlay(Rectangle().fill(Theme.hairline).frame(height: 1), alignment: .top)
        }
        .frame(minWidth: Theme.onboardingSize.width, maxWidth: .infinity,
               minHeight: Theme.onboardingSize.height, maxHeight: .infinity)
        .background(Theme.background)
        .ignoresSafeArea()
    }

    // -----------------------------------------------------------------------

    private var progress: some View {
        HStack(spacing: 6) {
            ForEach(0..<count, id: \.self) { i in
                Capsule()
                    .fill(st.card == 0 ? Color.white.opacity(i == 0 ? 0.95 : 0.3)
                          : i == st.card ? Theme.live : i < st.card ? Theme.accent : Theme.border)
                    .frame(width: i == st.card ? 22 : 14, height: 5)
            }
        }
        .animation(.easeOut(duration: 0.2), value: st.card)
    }

    private var footer: some View {
        HStack(spacing: Theme.s3) {
            if st.card > 0 {
                Button("Back") { st.card -= 1 }.buttonStyle(QuietButton())
            }
            Spacer()
            // The models card is the one step that can take minutes, and
            // what it waits for keeps arriving with the window closed.
            if st.card == 4 && !ready {
                Button("Continue, finish in background") { next() }
                    .buttonStyle(.plain)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(Theme.accent)
            }
            if st.card == count - 1 && !ready {
                Button("Skip") { done() }
                    .buttonStyle(.plain)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(Theme.secondary)
            }
            Button(primaryTitle) { next() }
                .buttonStyle(PrimaryButton())
                .keyboardShortcut(.defaultAction)
                .disabled(!ready)
        }
    }

    private var primaryTitle: String {
        switch st.card {
        case 0: return "Get started"
        case count - 1: return "Finish"
        default: return "Continue"
        }
    }

    private func next() {
        // The one place the key is applied. Each press on the card used to
        // restart the loop, and each restart killed the model download.
        if st.card == 3 { model.setKey(st.key) }
        if st.card == count - 1 { done(); return }
        st.card += 1
        if st.card == count - 1 { st.tryFrom = Date().timeIntervalSince1970 }
    }

    /// Whether the current card's step is really done.
    private var ready: Bool {
        switch st.card {
        case 1: return model.mic == .authorized
        case 2: return model.trusted
        case 3: return st.keySeen
        case 4: return model.status.modelsReady
        case 5: return tried != nil
        default: return true
        }
    }

    /// The hold made since the "Try it" card appeared, if there was one.
    private var tried: Last? {
        guard let l = model.last, l.at > st.tryFrom, st.tryFrom > 0,
              !l.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return l
    }

    private var keyName: String { Prefs.keyNames[st.key] ?? st.key }

    // -----------------------------------------------------------------------
    // Pieces every card uses.

    private func header(_ symbol: String, _ title: String, _ line: String) -> some View {
        VStack(spacing: Theme.s3) {
            Image(systemName: symbol)
                .font(.system(size: 24, weight: .semibold))
                .foregroundColor(.white)
                .frame(width: 56, height: 56)
                .background(RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Theme.brand))
                .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(Color.white.opacity(0.18), lineWidth: 1))
                .shadow(color: Color(nsColor: Palette.gradViolet).opacity(0.3), radius: 8, y: 3)
                .padding(.bottom, Theme.s1)
            Text(title).font(.display(26)).foregroundColor(Theme.text)
                .multilineTextAlignment(.center)
            Text(line).font(.system(size: 15)).foregroundColor(Theme.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 440)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func ok(_ label: String) -> some View {
        Label(label, systemImage: "checkmark.circle.fill")
            .font(.system(size: 14, weight: .medium))
            .foregroundColor(Theme.good)
            .frame(height: 32)
    }

    private func hint(_ s: String) -> some View {
        Text(s).font(.system(size: 12)).foregroundColor(Theme.secondary)
            .multilineTextAlignment(.center)
            .frame(maxWidth: 440)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func settingsLink(_ title: String, _ pane: String) -> some View {
        Button(title) {
            NSWorkspace.shared.open(URL(string:
                "x-apple.systempreferences:com.apple.preference.security?\(pane)")!)
        }
        .buttonStyle(.plain)
        .font(.system(size: 12, weight: .medium))
        .foregroundColor(Theme.accent)
    }

    // -----------------------------------------------------------------------

    private var welcome: some View {
        VStack(spacing: Theme.s4) {
            BrandMark(size: 96)
                .shadow(color: .black.opacity(0.3), radius: 16, y: 8)
                .padding(.bottom, Theme.s2)
            Text("Talk, and it types").font(.display(34))
                .foregroundColor(.white)
            Text("Hold a key, say what you mean, in English or Hinglish, and the words "
                 + "land at your cursor in any app.")
                .font(.system(size: 15, weight: .medium)).foregroundColor(.white.opacity(0.85))
                .multilineTextAlignment(.center).frame(maxWidth: 430)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 6) {
                Image(systemName: "lock.fill").font(.system(size: 10, weight: .bold))
                Text("Everything stays on this Mac").font(.system(size: 12, weight: .semibold))
            }
            .foregroundColor(.white)
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(Capsule().fill(Color.black.opacity(0.2)))
            .overlay(Capsule().strokeBorder(Theme.cursorGlow.opacity(0.6), lineWidth: 1))
            .padding(.top, Theme.s1)
        }
    }

    private var microphone: some View {
        VStack(spacing: Theme.s5) {
            header("mic.fill", "Let Dictator hear you",
                   "It listens only while you hold the key. Audio never leaves this Mac.")
            if model.mic == .authorized {
                ok("Microphone allowed")
            } else if model.mic == .denied || model.mic == .restricted {
                // Once refused, the prompt never shows again; only the
                // switch in System Settings can change it.
                VStack(spacing: Theme.s2) {
                    hint("It was turned off before. Switch Dictator on in System Settings, "
                         + "Privacy & Security, Microphone.")
                    Button("Open Microphone settings") {
                        NSWorkspace.shared.open(URL(string:
                            "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")!)
                    }
                    .buttonStyle(QuietButton())
                }
            } else {
                Button("Allow microphone") { askForMicrophone { _ in model.refresh() } }
                    .buttonStyle(QuietButton())
            }
        }
    }

    private var accessibility: some View {
        VStack(spacing: Theme.s5) {
            header("keyboard.badge.ellipsis", "Let Dictator type for you",
                   "This is how your words reach the app you are using, and how the key "
                   + "is noticed while another app is in front.")
            if model.trusted {
                ok("Accessibility allowed")
            } else {
                Button("Allow Accessibility") {
                    st.asked = true
                    _ = askForAccessibility()
                    NSWorkspace.shared.open(URL(string:
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
                }
                .buttonStyle(QuietButton())
                if st.asked {
                    // The stale-entry trap from the README: an old row for
                    // this app, its switch already on, and macOS not
                    // counting it.
                    hint("Already switched on and still waiting? That entry belongs to an "
                         + "older copy. Select it, remove it with the minus button, then "
                         + "click Allow Accessibility again.")
                }
            }
        }
    }

    private var yourKey: some View {
        VStack(spacing: Theme.s5) {
            header("command", "Choose your key",
                   "Hold it to talk, let go to stop; double-tap it to talk hands free. "
                   + "Pick one, then press it once to check.")
            HStack(spacing: Theme.s3) {
                ForEach(Prefs.keys, id: \.self) { k in keyTile(k) }
            }
            if st.keySeen {
                ok("Got it")
            } else {
                Text("Press \(keyName) now")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(Theme.secondary)
                    .frame(height: 32)
            }
            if st.key == "fn" { GlobeKeyNote(compact: true) }
        }
        .background(KeyWatcher(key: st.key) { st.keySeen = true }.id(st.key))
    }

    private func keyTile(_ k: String) -> some View {
        let on = st.key == k
        let name = Prefs.keyNames[k] ?? k
        let (glyph, side): (String, String) = {
            switch k {
            case "fn": return ("fn", "globe key")
            case "rightcmd": return ("⌘", "right")
            case "rightopt": return ("⌥", "right")
            default: return ("⌘", "left")
            }
        }()
        return Button {
            if st.key != k { st.key = k; st.keySeen = false }
        } label: {
            VStack(spacing: 4) {
                Text(glyph).font(.system(size: 22, weight: .medium, design: .rounded))
                    .foregroundColor(on ? Theme.accent : Theme.text)
                Text(side).font(.system(size: 11)).foregroundColor(Theme.secondary)
            }
            .frame(width: 104, height: 76)
            .background(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
                .fill(on ? Theme.accentSoft : Theme.card))
            .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
                .strokeBorder(on ? Theme.accent : Theme.border, lineWidth: on ? 2 : 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(name)
    }

    private var languages: some View {
        VStack(spacing: Theme.s5) {
            header("character.bubble", "Do you speak Hinglish?",
                   "Hindi and English mixed, like “yaar ye test kar ke dekho”. If you do, "
                   + "Dictator goes straight to the engine that understands it.")
            HStack(spacing: Theme.s3) {
                choice("Yes, Hinglish", "Hindi and English", "hinglish")
                choice("No, English", "Fastest for English", "english")
            }
            models
        }
    }

    private func choice(_ title: String, _ sub: String, _ code: String) -> some View {
        let on = st.answered && model.language == code
        return Button {
            st.answered = true
            model.setLanguage(code)
        } label: {
            HStack(spacing: Theme.s3) {
                Image(systemName: on ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 16))
                    .foregroundColor(on ? Theme.accent : Theme.tertiary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.system(size: 14, weight: .semibold))
                        .foregroundColor(Theme.text)
                    Text(sub).font(.system(size: 12)).foregroundColor(Theme.secondary)
                }
                Spacer()
            }
            .padding(.horizontal, Theme.s4)
            .frame(width: 210, height: 60)
            .background(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
                .fill(on ? Theme.accentSoft : Theme.card))
            .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
                .strokeBorder(on ? Theme.accent : Theme.border, lineWidth: on ? 2 : 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// Download progress, one line per model. English is needed to go on;
    /// Hinglish keeps arriving in the background.
    private var models: some View {
        VStack(alignment: .leading, spacing: 6) {
            if model.status.models.isEmpty {
                hint("Waiting for Dictator to report its speech models…")
            }
            ForEach(model.status.models, id: \.name) { m in
                HStack(spacing: Theme.s2) {
                    Image(systemName: m.have ? "checkmark.circle.fill" : "arrow.down.circle")
                        .foregroundColor(m.have ? Theme.good : Theme.accent)
                        .font(.system(size: 12))
                    Text(modelTitle(m.name)).font(.system(size: 12, weight: .medium))
                        .foregroundColor(Theme.text)
                        .frame(width: 104, alignment: .leading)
                    if m.have {
                        Text("ready").font(.system(size: 12)).foregroundColor(Theme.secondary)
                        Spacer()
                    } else if m.needsAction && (m.stuck || m.removed) {
                        // A download that failed or stopped does not come
                        // back by waiting on this card.
                        Text(m.removed ? "removed" : "stopped")
                            .font(.system(size: 12)).foregroundColor(Theme.secondary)
                        Button(m.removed ? "Download" : "Retry") { downloadModel(m.name) }
                            .buttonStyle(QuietButton())
                        Spacer()
                    } else {
                        BrandProgress(value: m.progress)
                            .frame(width: 180)
                        Text("\(Int((m.progress * 100).rounded()))%")
                            .font(.system(size: 12).monospacedDigit())
                            .foregroundColor(Theme.secondary)
                            .frame(width: 36, alignment: .trailing)
                        Spacer()
                    }
                }
                .frame(width: 380, alignment: .leading)
            }
        }
    }

    private var tryIt: some View {
        VStack(spacing: Theme.s5) {
            header("waveform", "Try it",
                   "Hold \(keyName) and say: “yaar ye test kar ke dekho”. Let go, and it "
                   + "shows up here.")
            Group {
                if let l = tried {
                    VStack(alignment: .leading, spacing: Theme.s2) {
                        Text(l.text).font(.system(size: 17, weight: .medium))
                            .foregroundColor(Theme.text)
                            .fixedSize(horizontal: false, vertical: true)
                        HStack(spacing: Theme.s3) {
                            Label("You did it", systemImage: "checkmark.circle.fill")
                                .foregroundColor(Theme.good)
                            if let ms = l.ms {
                                Label("\(l.pasted ? "pasted" : "ready") in \(waited(ms))",
                                      systemImage: "bolt.fill")
                                    .foregroundColor(Theme.secondary)
                            }
                            if !l.engine.isEmpty {
                                Text(engineTitle(l.engine)).foregroundColor(Theme.tertiary)
                            }
                        }
                        .font(.system(size: 12, weight: .medium))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Listening(key: keyName)
                }
            }
            .frame(width: 440)
            .frame(minHeight: 48)
            .card(padding: Theme.s5)
        }
    }
}

/// The waiting state of the "Try it" card: a softly pulsing dot. Driven by
/// the clock rather than by view state, so it needs no @State.
struct Listening: View {
    var key: String

    var body: some View {
        TimelineView(.animation) { t in
            let phase = (sin(t.date.timeIntervalSinceReferenceDate * 3) + 1) / 2
            HStack(spacing: Theme.s3) {
                ZStack {
                    Circle().fill(Theme.live.opacity(0.22))
                        .frame(width: 14 + 10 * phase, height: 14 + 10 * phase)
                    Circle().fill(Theme.live).frame(width: 10, height: 10)
                }
                .frame(width: 26, height: 26)
                Text("Listening… hold \(key) and speak")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(Theme.secondary)
                Spacer()
            }
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
