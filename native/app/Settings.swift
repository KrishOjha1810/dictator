// Settings: the last page of the Hub. Each row is a CLI command or one of the
// two things the app keeps itself (the hold key and whether onboarding ran).

import AVFoundation
import AppKit
import ServiceManagement
import SwiftUI

final class SettingsState: ObservableObject {
    @Published var atLogin = SMAppService.mainApp.status == .enabled
    @Published var doctor = ""
    @Published var running = false
    @Published var installed = ""
    @Published var confirmErase = false
    @Published var erased = ""
}

struct SettingsPage: View {
    @EnvironmentObject var model: AppModel
    @StateObject private var st = SettingsState()

    var body: some View {
        Form {
            general
            language
            microphone
            privacy
            advanced
            about
        }
        .formStyle(.grouped)
        .onAppear { model.loadLanguage() }
    }

    // -----------------------------------------------------------------------

    private var general: some View {
        Section("General") {
            Picker("Hold to talk", selection: Binding(get: { model.key },
                                                      set: { model.setKey($0) })) {
                ForEach(Prefs.keys, id: \.self) { Text(Prefs.keyNames[$0] ?? $0).tag($0) }
            }
            // Only the bundle registers itself as a login item. A repo install
            // already has one, the launchd plist `dictator on` writes, and two
            // of them would start two listeners on the same key.
            if Mode.current.isBundle {
                Toggle("Start at login", isOn: Binding(get: { st.atLogin }, set: { on in
                    do {
                        if on { try SMAppService.mainApp.register() }
                        else { try SMAppService.mainApp.unregister() }
                    } catch {
                        NSLog("dictator: login item: \(error)")
                    }
                    st.atLogin = SMAppService.mainApp.status == .enabled
                }))
            } else {
                LabeledContent("Start at login", value: "dictator on / dictator off")
            }
        }
    }

    private var language: some View {
        Section("Language") {
            Picker("Expect", selection: Binding(get: { model.language },
                                                set: { model.setLanguage($0) })) {
                Text("Auto (English first, Hinglish when it hears it)").tag("english")
                Text("Hinglish").tag("hinglish")
            }
            if model.status.models.isEmpty {
                Text("Models: not reported yet").foregroundColor(.secondary)
            }
            ForEach(model.status.models, id: \.name) { m in
                LabeledContent(modelTitle(m.name)) {
                    if m.have {
                        Text("Ready").foregroundColor(.secondary)
                    } else {
                        ProgressView(value: m.progress).frame(width: 160)
                    }
                }
            }
        }
    }

    private var microphone: some View {
        Section("Microphone") {
            LabeledContent("Input",
                value: AVCaptureDevice.default(for: .audio)?.localizedName ?? "None found")
            LabeledContent("Permission", value: model.mic == .authorized ? "Allowed" : "Not allowed")
            Text("Dictator records from the system's default input. Change it in "
                 + "System Settings, Sound.").font(.caption).foregroundColor(.secondary)
        }
    }

    private var privacy: some View {
        Section("Privacy") {
            LabeledContent("History is kept in") {
                Button(stateDir.path) {
                    NSWorkspace.shared.activateFileViewerSelecting([stateDir])
                }
                .buttonStyle(.link)
            }
            Text("On this Mac only. Nothing is uploaded.")
                .font(.caption).foregroundColor(.secondary)
            HStack {
                Button("Delete all history…", role: .destructive) { st.confirmErase = true }
                if !st.erased.isEmpty { Text(st.erased).foregroundColor(.secondary) }
            }
            .alert("Delete everything you have dictated?", isPresented: $st.confirmErase) {
                Button("Delete", role: .destructive) {
                    // `forget all` asks for the word ERASE on stdin; this
                    // alert is where the user said it.
                    CLI.load({ CLI.act(["forget", "all"], input: "ERASE\n") }) { ok in
                        st.erased = ok ? "Deleted." : "Could not delete."
                    }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("This cannot be undone.")
            }
        }
    }

    private var advanced: some View {
        Section("Advanced") {
            HStack {
                Button("Install command line tool") { st.installed = installCLI() }
                if !st.installed.isEmpty {
                    Text(st.installed).font(.caption).foregroundColor(.secondary)
                }
            }
            Text("Puts `dictator` in ~/.local/bin. No administrator password.")
                .font(.caption).foregroundColor(.secondary)
            HStack {
                Button(st.running ? "Running…" : "Run diagnostics") {
                    st.running = true
                    CLI.load({ CLI.text(["doctor"]) }) { out in
                        st.doctor = out
                        st.running = false
                    }
                }
                .disabled(st.running)
                Button("Show log") {
                    NSWorkspace.shared.activateFileViewerSelecting(
                        [stateDir.appendingPathComponent("dictate.log")])
                }
            }
            if !st.doctor.isEmpty {
                ScrollView {
                    Text(st.doctor).font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(height: 200)
            }
        }
    }

    private var about: some View {
        Section("About") {
            let info = Bundle.main.infoDictionary ?? [:]
            LabeledContent("Version", value: (info["CFBundleShortVersionString"] as? String ?? "dev")
                + " (" + (info["CFBundleVersion"] as? String ?? "0") + ")")
            LabeledContent("Running from", value: Mode.current.isBundle ? "app bundle" : "repo install")
            VStack(alignment: .leading, spacing: 4) {
                Text("Speech recognition by whisper.cpp (MIT) with OpenAI Whisper "
                     + "models (MIT).")
                Text("English model: NVIDIA parakeet-tdt-0.6b-v3, licensed under "
                     + "CC-BY-4.0, converted to GGUF by ggml-org.")
                Text("Python runtime from python-build-standalone. jellyfish (MIT).")
            }
            .font(.caption).foregroundColor(.secondary)
        }
    }
}

/// Make `dictator` work in a terminal. A small script rather than a symlink to
/// the bundled CLI, because the CLI on its own would start with the system
/// Python and without DICTATOR_BUNDLE, which is a different install. Written
/// into ~/.local/bin so it needs no administrator password.
func installCLI() -> String {
    if fake { return "(fake mode) not installed" }
    let bin = home.appendingPathComponent(".local/bin")
    let dest = bin.appendingPathComponent("dictator")
    let fm = FileManager.default
    do {
        try fm.createDirectory(at: bin, withIntermediateDirectories: true)
        if fm.fileExists(atPath: dest.path) || (try? fm.destinationOfSymbolicLink(atPath: dest.path)) != nil {
            try fm.removeItem(at: dest)
        }
        switch Mode.current {
        case .bundle(let app):
            let q = app.path.replacingOccurrences(of: "'", with: "'\\''")
            let script = """
                #!/bin/sh
                # Written by Dictator.app. Runs the CLI inside the app, with its own Python.
                APP='\(q)'
                export DICTATOR_BUNDLE="$APP"
                export PYTHONPATH="$APP/Contents/Resources:$APP/Contents/Resources/site-packages"
                exec "$APP/Contents/Resources/python/bin/python3" "$APP/Contents/Resources/bin/dictator" "$@"

                """
            try script.write(to: dest, atomically: true, encoding: .utf8)
            try fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: dest.path)
        case .repo:
            guard let cli = Bundle.main.infoDictionary?["DictatorCLI"] as? String else {
                return "cannot find the dictator command"
            }
            try fm.createSymbolicLink(atPath: dest.path, withDestinationPath: cli)
        }
    } catch {
        return "could not install: \(error.localizedDescription)"
    }
    let path = env["PATH"] ?? ""
    return path.split(separator: ":").contains(Substring(bin.path))
        ? "Installed. Open a new terminal and run: dictator"
        : "Installed. Add ~/.local/bin to your PATH to use it."
}
