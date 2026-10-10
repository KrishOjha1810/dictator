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
    @Published var position = "top"
    @Published var idle = "hover"
    @Published var controls: [String] = ["dictate", "notetaker", "scratchpad"]
    @Published var shortcuts: [String: Bool] = ["notetaker": true, "scratchpad": true]
    @Published var autoUpdate = Updater.shared.automaticallyChecks
    /// The model the Delete alert is asking about.
    @Published var removing: Status.Model? = nil
    /// What the last Delete said, under the models.
    @Published var modelNote = ""
    /// Pause or mute other audio while the microphone is open.
    @Published var quietMedia = true
}

/// The eight places the pill can sit, as `dictator indicator` names them
/// (orbnative.POSITIONS, and `Spot` in native/orb.swift).
let indicatorPositions: [(String, String)] = [
    ("top", "Top centre"), ("bottom", "Bottom centre"),
    ("left", "Left edge"), ("right", "Right edge"),
    ("top-left", "Top left"), ("top-right", "Top right"),
    ("bottom-left", "Bottom left"), ("bottom-right", "Bottom right"),
]

struct SettingsPage: View {
    @EnvironmentObject var model: AppModel
    @StateObject private var st = SettingsState()

    var body: some View {
        PageScroll {
            PageHeader("Settings", "Your key, language, look, and where your words are kept.")
            general
            appearance
            language
            microphone
            privacy
            advanced
            updates
            about
        }
        .tint(Theme.accentFill)
        .onAppear {
            model.loadLanguage()
            loadIndicator()
        }
    }

    /// Read back what indicator.json says, which a drag of the pill may have
    /// changed since the page was last open.
    private func loadIndicator() {
        CLI.load({ CLI.json(["indicator"]) }) { o in
            guard let d = o as? [String: Any] else { return }
            var f = IndicatorFile()
            f.apply(d)
            st.position = f.position
            st.idle = f.idle
            st.controls = f.controls
            st.shortcuts = f.shortcuts
        }
    }

    /// The running pill watches the file `dictator indicator` writes, so it
    /// moves as soon as this returns; nothing is restarted.
    private func setIndicator(_ args: [String]) {
        CLI.load({ CLI.act(["indicator"] + args) }) { ok in
            if ok && !fake { loadIndicator() }
            Hotkeys.shared.refreshIfChanged()
        }
    }

    private func setControl(_ c: String, _ on: Bool) {
        var now = st.controls.filter { $0 != c }
        if on { now.append(c) }
        st.controls = ["dictate", "notetaker", "scratchpad"].filter { now.contains($0) }
        setIndicator(["controls", st.controls.isEmpty ? "none" : st.controls.joined(separator: ",")])
    }

    private func controlToggle(_ c: String) -> some View {
        Toggle("", isOn: Binding(get: { st.controls.contains(c) }, set: { setControl(c, $0) }))
            .toggleStyle(BrandSwitch()).labelsHidden().controlSize(.small)
    }

    private func shortcutToggle(_ k: String) -> some View {
        Toggle("", isOn: Binding(get: { st.shortcuts[k] ?? true }, set: { on in
            st.shortcuts[k] = on
            setIndicator(["shortcut", k, on ? "on" : "off"])
        }))
        .toggleStyle(BrandSwitch()).labelsHidden()
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
                    .toggleStyle(BrandSwitch()).labelsHidden()
                }
            } else {
                SettingRow("Start at login", "Set from a terminal in a repo install.") {
                    Text("dictator on / off").font(.system(size: 12, design: .monospaced))
                        .foregroundColor(Theme.secondary)
                }
            }
            Hairline()
            SettingRow("Indicator position",
                       "Where the pill sits. You can also drag it; it snaps to the nearest place.") {
                Picker("", selection: Binding(get: { st.position }, set: { p in
                    st.position = p
                    setIndicator(["position", p])
                })) {
                    ForEach(indicatorPositions, id: \.0) { Text($0.1).tag($0.0) }
                }
                .labelsHidden().fixedSize()
            }
            Hairline()
            SettingRow("When not dictating",
                       "While the microphone is open the pill always shows, dark with moving "
                       + "bars. Show on hover: nothing until the pointer comes to its place, "
                       + "then the pill and its buttons.") {
                Picker("", selection: Binding(get: { st.idle }, set: { v in
                    st.idle = v
                    setIndicator(["idle", v])
                })) {
                    Text("Show on hover").tag("hover")
                    Text("Always show").tag("always")
                    Text("Hide").tag("hide")
                }
                .labelsHidden().fixedSize()
            }
            Hairline()
            SettingRow("Buttons on hover",
                       "Click the pill to dictate hands free; the record button starts the "
                       + "Notetaker; the pencil opens the Scratchpad.") {
                VStack(alignment: .trailing, spacing: 6) {
                    ForEach([("dictate", "Dictate"), ("notetaker", "Notetaker"),
                             ("scratchpad", "Scratchpad")], id: \.0) { c in
                        HStack(spacing: Theme.s2) {
                            Text(c.1).font(.system(size: 12)).fixedSize()
                            controlToggle(c.0)
                        }
                    }
                }
                .foregroundColor(Theme.secondary)
                .disabled(st.idle == "hide")
            }
            Hairline()
            SettingRow("Notetaker shortcut",
                       "⌥M starts or stops recording a meeting, from any app.") {
                shortcutToggle("notetaker")
            }
            Hairline()
            SettingRow("Scratchpad shortcut",
                       "⌥S opens the Scratchpad, ready to dictate into.") {
                shortcutToggle("scratchpad")
            }
            Hairline()
            SettingRow("Show in Dock", "Off: only the menu bar item, and quit from there.") {
                Toggle("", isOn: Binding(get: { st.dock }, set: { on in
                    Prefs.showInDock = on
                    st.dock = on
                    (NSApp.delegate as? UI)?.applyDockPolicy()
                }))
                .toggleStyle(BrandSwitch()).labelsHidden()
            }
        }
    }

    private var appearance: some View {
        SettingsGroup("Appearance") {
            SettingRow("Look", "System follows your Mac, light by day and dark at night if "
                       + "you have it set that way.") {
                HStack(spacing: Theme.s2) {
                    ForEach(Appearance.allCases, id: \.self) { a in
                        AppearanceChoice(look: a, on: model.appearance == a) {
                            model.setAppearance(a)
                        }
                    }
                }
            }
        }
    }

    private var updates: some View {
        SettingsGroup("Updates") {
            SettingRow("Version \(Updater.shared.version)",
                       "Dictator looks for a newer version and asks before installing it.") {
                Button("Check now") { Updater.shared.checkForUpdates() }
                    .buttonStyle(QuietButton())
                    .disabled(!Updater.shared.canCheck)
            }
            Hairline()
            SettingRow("Automatically check for updates", "Look for a new version in the background.") {
                Toggle("", isOn: Binding(get: { st.autoUpdate }, set: { on in
                    Updater.shared.automaticallyChecks = on
                    st.autoUpdate = Updater.shared.automaticallyChecks
                }))
                .toggleStyle(BrandSwitch()).labelsHidden()
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
                SettingRow(modelTitle(m.name), modelDetail(m)) { modelControls(m) }
            }
            if !st.modelNote.isEmpty {
                Hairline()
                SettingRow("", st.modelNote) { EmptyView() }
            }
        }
        .alert(st.removing.map { "Delete the \(modelTitle($0.name))?" } ?? "",
               isPresented: Binding(get: { st.removing != nil },
                                    set: { if !$0 { st.removing = nil } })) {
            Button("Delete", role: .destructive) {
                if let m = st.removing { removeModel(m) }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            if let m = st.removing {
                Text(m.essential
                     ? "Dictation stops working until you download it again. "
                       + "Frees \(modelSize(m.mb))."
                     : "Hinglish falls back to English until you download it again. "
                       + "Frees \(modelSize(m.mb)).")
            }
        }
    }

    private func modelDetail(_ m: Status.Model) -> String {
        let what = m.essential ? "Needed to dictate." : "Optional, for Hinglish."
        if m.have || m.downloading { return "\(what) \(modelSize(m.mb))." }
        return "\(what) \(modelProblem(m))"
    }

    /// Ready: a Delete button. Arriving: its progress. Anything else: the one
    /// button that gets it back.
    @ViewBuilder
    private func modelControls(_ m: Status.Model) -> some View {
        if m.have {
            HStack(spacing: Theme.s3) {
                Label("Ready", systemImage: "checkmark.circle.fill")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Theme.good)
                Button("Delete…") { st.removing = m }
                    .buttonStyle(QuietButton())
                    .foregroundColor(Theme.bad)
            }
        } else if m.downloading {
            HStack(spacing: Theme.s2) {
                BrandProgress(value: m.progress).frame(width: 140)
                Text("\(Int((m.progress * 100).rounded()))%")
                    .font(.system(size: 12).monospacedDigit())
                    .foregroundColor(Theme.secondary)
            }
        } else {
            Button(m.stuck ? "Retry" : "Download") {
                st.modelNote = ""
                downloadModel(m.name)
            }
            .buttonStyle(QuietButton())
        }
    }

    /// `models remove` says what it freed, or why it would not; either way
    /// the sentence goes under the list.
    private func removeModel(_ m: Status.Model) {
        CLI.load({ CLI.text(["models", "remove", m.name, "--yes"]) }) { out in
            let line = out.split(separator: "\n")
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .first { $0.hasPrefix("removed") || $0.hasPrefix("not removed") } ?? ""
            st.modelNote = line.hasPrefix("removed")
                ? "Deleted the \(modelTitle(m.name)). \(modelSize(m.mb)) freed."
                : (line.isEmpty ? "Could not delete the \(modelTitle(m.name))." : line)
            model.refresh()
            model.loadLanguage()
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
            Hairline()
            SettingRow("Pause music while dictating",
                       "Music from your speakers ends up in what you say. It is paused while "
                       + "the microphone is open, or muted when the player cannot be paused, "
                       + "and comes back when you let go.") {
                Toggle("", isOn: Binding(get: { st.quietMedia }, set: { on in
                    st.quietMedia = on
                    CLI.load({ CLI.act(["quiet-media", on ? "on" : "off"]) }) { _ in }
                }))
                .toggleStyle(BrandSwitch()).labelsHidden()
            }
        }
        .onAppear {
            CLI.load({ CLI.json(["quiet-media"]) }) { o in
                if let on = (o as? [String: Any])?["on"] as? Bool { st.quietMedia = on }
            }
        }
    }

    private var privacy: some View {
        SettingsGroup("Privacy") {
            PrivacyPromise(compact: true)
                .padding(Theme.s3)
            Hairline()
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
            SectionLabel(title)
            VStack(spacing: 0) { content }.card(padding: 0)
        }
    }
}

/// A small drawing of the window in each look, to pick from.
struct AppearanceChoice: View {
    var look: Appearance
    var on: Bool
    var pick: () -> Void

    var body: some View {
        Button(action: pick) {
            VStack(spacing: 5) {
                ZStack {
                    switch look {
                    case .light: thumb(dark: false)
                    case .dark: thumb(dark: true)
                    case .system:
                        HStack(spacing: 0) {
                            thumb(dark: false).frame(width: 30, alignment: .leading).clipped()
                            thumb(dark: true).frame(width: 30, alignment: .trailing).clipped()
                        }
                    }
                }
                .frame(width: 60, height: 40)
                .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .strokeBorder(on ? Theme.accent : Theme.border, lineWidth: on ? 2 : 1))
                Text(look.title).font(.system(size: 11.5, weight: on ? .semibold : .regular))
                    .foregroundColor(on ? Theme.text : Theme.secondary)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// The sidebar, a page, and two lines of text.
    private func thumb(dark: Bool) -> some View {
        HStack(spacing: 0) {
            Color(nsColor: dark ? hex(0x0C1016) : hex(0xF0F0EA)).frame(width: 14)
            ZStack(alignment: .topLeading) {
                Color(nsColor: dark ? hex(0x10141B) : hex(0xF7F7F2))
                VStack(alignment: .leading, spacing: 4) {
                    RoundedRectangle(cornerRadius: 2).fill(Theme.brand).frame(width: 34, height: 9)
                    Capsule().fill(dark ? Color.white.opacity(0.5) : Color.black.opacity(0.35))
                        .frame(width: 26, height: 3)
                    Capsule().fill(dark ? Color.white.opacity(0.3) : Color.black.opacity(0.2))
                        .frame(width: 18, height: 3)
                }
                .padding(5)
            }
        }
        .frame(width: 60, height: 40)
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
