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
    @Published var dock = Prefs.showInDock
}

struct SettingsPage: View {
    @EnvironmentObject var model: AppModel
    @StateObject private var st = SettingsState()

    var body: some View {
        PageScroll {
            PageHeader("Settings", "Your key, language, and where your words are kept.")
            general
            language
            microphone
            privacy
            advanced
            about
        }
        .tint(Theme.accent)
        .onAppear { model.loadLanguage() }
    }

    // -----------------------------------------------------------------------

    private var general: some View {
        SettingsGroup("General") {
            SettingRow("Hold to talk", "The key you hold while you speak.") {
                Picker("", selection: Binding(get: { model.key },
                                              set: { model.setKey($0) })) {
                    ForEach(Prefs.keys, id: \.self) { Text(Prefs.keyNames[$0] ?? $0).tag($0) }
                }
                .labelsHidden().fixedSize()
            }
            Hairline()
            // Only the bundle registers itself as a login item. A repo install
            // already has one, the launchd plist `dictator on` writes, and two
            // of them would start two listeners on the same key.
            if Mode.current.isBundle {
                SettingRow("Start at login", "Ready to dictate after a restart.") {
                    Toggle("", isOn: Binding(get: { st.atLogin }, set: { on in
                        do {
                            if on { try SMAppService.mainApp.register() }
                            else { try SMAppService.mainApp.unregister() }
                        } catch {
                            NSLog("dictator: login item: \(error)")
                        }
                        st.atLogin = SMAppService.mainApp.status == .enabled
                    }))
                    .toggleStyle(.switch).labelsHidden()
                }
            } else {
                SettingRow("Start at login", "Set from a terminal in a repo install.") {
                    Text("dictator on / off").font(.system(size: 12, design: .monospaced))
                        .foregroundColor(Theme.secondary)
                }
            }
            Hairline()
            SettingRow("Show in Dock", "Off: only the menu bar item, and quit from there.") {
                Toggle("", isOn: Binding(get: { st.dock }, set: { on in
                    Prefs.showInDock = on
                    st.dock = on
                    (NSApp.delegate as? UI)?.applyDockPolicy()
                }))
                .toggleStyle(.switch).labelsHidden()
            }
        }
    }

    private var language: some View {
        SettingsGroup("Language") {
            SettingRow("Expect", "Hinglish skips the English-only engine.") {
                Picker("", selection: Binding(get: { model.language },
                                              set: { model.setLanguage($0) })) {
                    Text("Auto, English first").tag("english")
                    Text("Hinglish").tag("hinglish")
                }
                .labelsHidden().fixedSize()
            }
            if model.status.models.isEmpty {
                Hairline()
                SettingRow("Speech models", "Not reported yet.") { EmptyView() }
            }
            ForEach(model.status.models, id: \.name) { m in
                Hairline()
                SettingRow(modelTitle(m.name), m.essential ? "Needed to dictate."
                                                           : "Optional, for Hinglish.") {
                    if m.have {
                        Label("Ready", systemImage: "checkmark.circle.fill")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(Theme.good)
                    } else {
                        HStack(spacing: Theme.s2) {
                            ProgressView(value: m.progress).frame(width: 140)
                            Text("\(Int((m.progress * 100).rounded()))%")
                                .font(.system(size: 12).monospacedDigit())
                                .foregroundColor(Theme.secondary)
                        }
                    }
                }
            }
        }
    }

    private var microphone: some View {
        SettingsGroup("Microphone") {
            SettingRow("Input", "The system default. Change it in System Settings, Sound.") {
                Text(AVCaptureDevice.default(for: .audio)?.localizedName ?? "None found")
                    .font(.system(size: 13)).foregroundColor(Theme.secondary)
            }
            Hairline()
            SettingRow("Permission", nil) {
                if model.mic == .authorized {
                    Label("Allowed", systemImage: "checkmark.circle.fill")
                        .font(.system(size: 12, weight: .medium)).foregroundColor(Theme.good)
                } else {
                    Button("Open settings") {
                        NSWorkspace.shared.open(URL(string:
                            "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")!)
                    }
                    .buttonStyle(QuietButton())
                }
            }
        }
    }

    private var privacy: some View {
        SettingsGroup("Privacy") {
            SettingRow("History is kept in", "On this Mac only. Nothing you say is uploaded.") {
                Button(stateDir.path.replacingOccurrences(of: home.path, with: "~")) {
                    NSWorkspace.shared.activateFileViewerSelecting([stateDir])
                }
                .buttonStyle(.link)
            }
            Hairline()
            SettingRow("Delete all history", st.erased.isEmpty ? "This cannot be undone." : st.erased) {
                Button("Delete…") { st.confirmErase = true }
                    .buttonStyle(QuietButton())
                    .foregroundColor(Theme.bad)
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
        SettingsGroup("Advanced") {
            SettingRow("Command line tool",
                       st.installed.isEmpty ? "Puts `dictator` in ~/.local/bin. No password."
                                            : st.installed) {
                Button("Install") { st.installed = installCLI() }.buttonStyle(QuietButton())
            }
            Hairline()
            SettingRow("Diagnostics", "Checks permissions, models and the key.") {
                HStack(spacing: Theme.s2) {
                    Button("Show log") {
                        NSWorkspace.shared.activateFileViewerSelecting(
                            [stateDir.appendingPathComponent("dictate.log")])
                    }
                    .buttonStyle(QuietButton())
                    Button(st.running ? "Running…" : "Run") {
                        st.running = true
                        CLI.load({ CLI.text(["doctor"]) }) { out in
                            st.doctor = out
                            st.running = false
                        }
                    }
                    .buttonStyle(QuietButton())
                    .disabled(st.running)
                }
            }
            if !st.doctor.isEmpty {
                Hairline()
                ScrollView {
                    Text(st.doctor).font(.system(size: 11, design: .monospaced))
                        .foregroundColor(Theme.text)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(height: 200)
                .padding(Theme.s4)
            }
        }
    }

    private var about: some View {
        SettingsGroup("About") {
            let info = Bundle.main.infoDictionary ?? [:]
            SettingRow("Version", Mode.current.isBundle ? "App bundle" : "Repo install") {
                Text((info["CFBundleShortVersionString"] as? String ?? "dev")
                     + " (" + (info["CFBundleVersion"] as? String ?? "0") + ")")
                    .font(.system(size: 13).monospacedDigit()).foregroundColor(Theme.secondary)
            }
            Hairline()
            VStack(alignment: .leading, spacing: 4) {
                Text("Speech recognition by whisper.cpp (MIT) with OpenAI Whisper "
                     + "models (MIT).")
                Text("English model: NVIDIA parakeet-tdt-0.6b-v3, licensed under "
                     + "CC-BY-4.0, converted to GGUF by ggml-org.")
                Text("Python runtime from python-build-standalone. jellyfish (MIT).")
            }
            .font(.caption12).foregroundColor(Theme.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, Theme.s4)
            .padding(.vertical, Theme.s3)
        }
    }
}

/// A titled white card of rows.
struct SettingsGroup<Content: View>: View {
    var title: String
    var content: Content
    init(_ title: String, @ViewBuilder _ c: () -> Content) {
        self.title = title
        content = c()
    }
    var body: some View {
        VStack(alignment: .leading, spacing: Theme.s2) {
            Text(title.uppercased()).font(.system(size: 11, weight: .semibold)).kerning(0.6)
                .foregroundColor(Theme.tertiary).padding(.leading, Theme.s1)
            VStack(spacing: 0) { content }.card(padding: 0)
        }
    }
}

/// One setting: a name, a line under it, and the control on the right.
struct SettingRow<Trailing: View>: View {
    var title: String
    var detail: String?
    var trailing: Trailing
    init(_ title: String, _ detail: String?, @ViewBuilder trailing: () -> Trailing) {
        self.title = title
        self.detail = detail
        self.trailing = trailing()
    }
    var body: some View {
        HStack(spacing: Theme.s4) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 13, weight: .medium)).foregroundColor(Theme.text)
                if let d = detail, !d.isEmpty {
                    Text(d).font(.caption12).foregroundColor(Theme.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: Theme.s4)
            trailing
        }
        .padding(.horizontal, Theme.s4)
        .padding(.vertical, 11)
        .frame(minHeight: 52)
    }
}

struct Hairline: View {
    var body: some View {
        Rectangle().fill(Theme.hairline).frame(height: 1).padding(.leading, Theme.s4)
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
