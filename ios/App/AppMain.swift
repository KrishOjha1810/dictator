// The app around the keyboard.
//
// It exists for three things an extension cannot do for itself: ask for the
// microphone (the system prompt only appears for an app), download the speech
// model the first time, and tell the user where the two switches are. It also
// runs the same dictation the keyboard runs, which gives a baseline: if it
// works here and not in the keyboard, the difference is the extension sandbox
// and not this code.

import AVFoundation
import Speech
import SwiftUI

@main
struct DictatorApp: App {
    var body: some Scene {
        WindowGroup { Setup() }
    }
}

struct Setup: View {
    @State private var steps: [Step] = []
    @State private var running = false
    @State private var dictation: Dictation?
    @State private var heard = ""
    @State private var listening = false

    var body: some View {
        NavigationStack {
            List {
                Section("Checks") {
                    if steps.isEmpty && !running {
                        Text("Run the checks to see what is missing.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(steps) { s in
                        HStack(alignment: .firstTextBaseline) {
                            Image(systemName: s.ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .foregroundStyle(s.ok ? .green : .red)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(s.name)
                                Text(s.detail).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    Button(running ? "Checking" : "Run the checks") {
                        Task { await run() }
                    }
                    .disabled(running)
                }

                Section("Try it here") {
                    Text(heard.isEmpty ? "Nothing yet" : heard)
                        .foregroundStyle(heard.isEmpty ? .secondary : .primary)
                    Button(listening ? "Stop" : "Hold and talk, here") {
                        Task { listening ? await stop() : await start() }
                    }
                }

                Section("Turn the keyboard on") {
                    Label("Settings, General, Keyboard, Keyboards, Add New Keyboard, Dictator",
                          systemImage: "1.circle")
                    Label("Tap Dictator in that list and turn on Allow Full Access",
                          systemImage: "2.circle")
                    Text("Full Access is what lets a keyboard reach the microphone. "
                         + "Nothing you say leaves the phone: the speech model runs on it.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Dictator")
        }
    }

    private func run() async {
        running = true
        steps = []
        defer { running = false }

        let granted = await AVAudioApplication.requestRecordPermission()
        add("Microphone", granted, granted ? "allowed" : "denied in Settings, Privacy, Microphone")

        let supported = await SpeechTranscriber.supportedLocales.map(\.identifier)
        let have = supported.contains(preferredLocale.identifier)
        add("Indian English supported", have,
            have ? preferredLocale.identifier : "this iOS has \(supported.count) locales, none of them this one")
        guard have else { return }

        do {
            let what = try await Dictation.ensureModel()
            add("Speech model", true, what)
        } catch {
            add("Speech model", false, "\(error)")
            return
        }

        // The point of the whole target. Succeeding here in the app says
        // nothing about the keyboard, so the keyboard reports it separately.
        do {
            let d = Dictation()
            try await d.start()
            await d.stop()
            add("Microphone opens", true, "AVAudioEngine started and stopped cleanly")
        } catch {
            add("Microphone opens", false, "\(error)")
        }
    }

    private func start() async {
        let d = Dictation()
        d.onPartial = { t in heard = t }
        do {
            try await d.start()
            dictation = d
            listening = true
        } catch {
            heard = "could not start: \(error)"
        }
    }

    private func stop() async {
        guard let d = dictation else { return }
        heard = await d.stop()
        dictation = nil
        listening = false
    }

    private func add(_ name: String, _ ok: Bool, _ detail: String) {
        steps.append(Step(name: name, ok: ok, detail: detail))
    }
}
