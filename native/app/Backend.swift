// Everything the windows know about Dictator comes through this file, and it
// comes from exactly two places: ~/.dictator/status.json, which the dictation
// loop writes, and the bundled CLI run with --json. The app never reads the
// history database or the vocabulary store itself. A second copy of that logic
// in Swift would be a second thing to keep right, and the Python one is the
// one with tests.
//
// DICTATOR_FAKE=1 swaps both for canned files (native/app/Fixtures, shipped in
// the bundle's Resources), so the windows can be worked on without a model, a
// hotkey or a permission.

import AppKit
import Foundation

let env = ProcessInfo.processInfo.environment

/// How this copy of the app was put together, decided once at launch.
enum Mode {
    /// Inside Dictator.app from the .dmg: its own Python, its own CLI.
    case bundle(URL)
    /// Built by `dictator build` from a checkout: the system python3 and the
    /// CLI path written into Info.plist. Exactly what it was before the UI.
    case repo

    static let current: Mode = {
        let app = URL(fileURLWithPath: Bundle.main.bundlePath)
        let python = app.appendingPathComponent("Contents/Resources/python")
        if app.pathExtension == "app",
           FileManager.default.fileExists(atPath: python.path) {
            return .bundle(app)
        }
        return .repo
    }()

    var isBundle: Bool {
        if case .bundle = self { return true }
        return false
    }
}

/// Canned data instead of the backend. Nothing is started and nothing is
/// written, so it is safe to run while a real install is dictating.
let fake = env["DICTATOR_FAKE"] == "1"

/// Whether to show anything at all. A repo install had no menu bar item and
/// no windows before this, and someone who installed from source and rebuilt
/// should not find a menu bar item they never asked for. DICTATOR_UI=1 turns it
/// on there too, for the maintainer.
let showsUI = Mode.current.isBundle || fake || env["DICTATOR_UI"] == "1"

/// Same rule as core.state_dir(): DICTATOR_STATE wins, then the directory the
/// build wrote the log into, then ~/.dictator.
let stateDir: URL = {
    if let s = env["DICTATOR_STATE"], !s.isEmpty {
        return URL(fileURLWithPath: (s as NSString).expandingTildeInPath)
    }
    if let log = Bundle.main.infoDictionary?["DictatorLog"] as? String {
        return URL(fileURLWithPath: (log as NSString).deletingLastPathComponent)
    }
    return home.appendingPathComponent(".dictator")
}()

/// Where the canned files are: an explicit DICTATOR_FIXTURES, else the copy
/// tools/build_dmg.sh puts in the bundle (Contents/Resources/Fixtures).
///
/// There used to be a third fallback, the source tree this binary was
/// compiled from (#filePath). In a release that path is the maintainer's
/// Desktop, so fake mode on anybody's Mac made macOS ask for Desktop access
/// on behalf of a folder that is not theirs. A bare binary from
/// tools/build_app.sh now needs DICTATOR_FIXTURES=native/app/Fixtures.
let fixturesDir: URL = {
    if let f = env["DICTATOR_FIXTURES"], !f.isEmpty {
        return URL(fileURLWithPath: (f as NSString).expandingTildeInPath)
    }
    return (Bundle.main.resourceURL ?? URL(fileURLWithPath: Bundle.main.bundlePath))
        .appendingPathComponent("Fixtures")
}()

// ---------------------------------------------------------------------------
// Starting Python.

/// The command line and environment for one run of the CLI. In bundle mode
/// that is the bundled interpreter on the bundled CLI, with DICTATOR_BUNDLE so
/// the Python side looks for its helpers inside the app. In repo mode it is
/// the system python3 on the CLI the build pointed us at.
func cliCommand(_ args: [String]) -> (URL, [String], [String: String])? {
    var e = env
    // launchd hands a process almost no PATH, and in a repo install both sox
    // and whisper live in Homebrew. The bundle carries its own, but keeping
    // Homebrew on the path costs nothing and is what `doctor` falls back to.
    e["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    switch Mode.current {
    case .bundle(let app):
        let res = app.appendingPathComponent("Contents/Resources")
        e["DICTATOR_BUNDLE"] = app.path
        e["PYTHONPATH"] = res.path + ":" + res.appendingPathComponent("site-packages").path
        // The bundled runtime must not pick up the user's own Python setup.
        e.removeValue(forKey: "PYTHONHOME")
        return (res.appendingPathComponent("python/bin/python3"),
                [res.appendingPathComponent("bin/dictator").path] + args, e)
    case .repo:
        let info = Bundle.main.infoDictionary ?? [:]
        guard let cli = info["DictatorCLI"] as? String,
              FileManager.default.isExecutableFile(atPath: cli) else { return nil }
        return (URL(fileURLWithPath: "/usr/bin/env"), ["python3", cli] + args, e)
    }
}

/// Run the CLI once and hand back what it printed. Called off the main
/// thread; every page wraps it in `CLI.load`.
func runCLI(_ args: [String], input: String? = nil) -> (status: Int32, out: Data) {
    guard let (exe, argv, e) = cliCommand(args) else {
        return (127, Data("cannot find the dictator command".utf8))
    }
    let p = Process()
    p.executableURL = exe
    p.arguments = argv
    p.environment = e
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = pipe
    // Commands that ask before they destroy something (`forget all` wants the
    // word ERASE) get their answer here, after the window has asked the same
    // question. Without stdin they read EOF and leave everything alone.
    let stdin = Pipe()
    p.standardInput = stdin
    do { try p.run() } catch { return (127, Data("\(error)".utf8)) }
    if let input = input { stdin.fileHandleForWriting.write(Data(input.utf8)) }
    try? stdin.fileHandleForWriting.close()
    // Read before waiting, or a full pipe deadlocks the wait.
    let out = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus, out)
}

/// The thin layer every page talks to. Each call is one CLI command; in fake
/// mode the read commands come from Fixtures and the write commands change
/// nothing, so a page can be clicked through without consequences.
enum CLI {
    /// `dictator <args> --json`, parsed. nil when it failed or printed
    /// something that is not JSON, which the page shows as "could not load".
    static func json(_ args: [String]) -> Any? {
        if fake {
            let name = args.first { !$0.hasPrefix("-") } ?? "status"
            guard let d = try? Data(contentsOf: fixturesDir
                    .appendingPathComponent(name + ".json")) else { return nil }
            return try? JSONSerialization.jsonObject(with: d)
        }
        let r = runCLI(args + ["--json"])
        guard r.status == 0 else { return nil }
        return try? JSONSerialization.jsonObject(with: r.out)
    }

    /// A command whose output is for a person: `doctor`, `format`. Returned
    /// as text, shown as text.
    static func text(_ args: [String]) -> String {
        if fake {
            // `format in` reads Fixtures/format-in.txt, and so on.
            let f = fixturesDir.appendingPathComponent(args.joined(separator: "-") + ".txt")
            return (try? String(contentsOf: f, encoding: .utf8))
                ?? "(fake mode) dictator " + args.joined(separator: " ")
        }
        let r = runCLI(args)
        return String(data: r.out, encoding: .utf8) ?? ""
    }

    /// A command that changes something: learn, unlearn, snippet, language.
    /// True when it exited cleanly.
    @discardableResult
    static func act(_ args: [String], input: String? = nil) -> Bool {
        if fake { NSLog("dictator (fake): would run \(args)"); return true }
        return runCLI(args, input: input).status == 0
    }

    /// Run off the main thread, deliver on it.
    static func load<T>(_ work: @escaping () -> T, then: @escaping (T) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            let v = work()
            DispatchQueue.main.async { then(v) }
        }
    }
}

// ---------------------------------------------------------------------------
// status.json

/// What the dictation loop says it is doing. Read every second by the menu
/// bar; a missing or stale file is not an error, it is "not running yet".
struct Status: Equatable {
    struct Model: Equatable {
        var name: String
        var have: Bool
        var progress: Double
        /// Needed before dictation works. The loop says so per model; a file
        /// written before it did falls back to the one rule the loop uses
        /// today, that the large multilingual model is the optional one.
        var essential: Bool
    }

    var state = "starting"
    var models: [Model] = []
    var error: String? = nil
    var updated: Double = 0

    static func read() -> Status {
        let url = fake ? fixturesDir.appendingPathComponent("status.json")
                       : stateDir.appendingPathComponent("status.json")
        guard let d = try? Data(contentsOf: url),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any]
        else { return Status() }
        var s = Status()
        s.state = o["state"] as? String ?? "starting"
        s.error = o["error"] as? String
        s.updated = (o["updated"] as? NSNumber)?.doubleValue ?? 0
        if let m = o["models"] as? [String: Any] {
            s.models = m.keys.sorted().map { k in
                let r = m[k] as? [String: Any] ?? [:]
                let lower = k.lowercased()
                return Model(name: k, have: r["have"] as? Bool ?? false,
                             progress: (r["progress"] as? NSNumber)?.doubleValue ?? 0,
                             essential: r["essential"] as? Bool
                                 ?? !(lower.contains("large") || lower.contains("turbo")))
            }
        }
        return s
    }

    /// Every model English needs is on disk. The models card of onboarding
    /// waits for this, and an empty list means the loop has not said yet,
    /// which is not the same as done. The Hinglish model is not waited for:
    /// it is 1.5 GB, it is optional, and the card says it keeps arriving in
    /// the background.
    var modelsReady: Bool {
        !models.isEmpty && models.filter { $0.essential }.allSatisfy { $0.have }
    }

    var label: String {
        switch state {
        case "ready": return "Ready"
        case "listening": return "Listening"
        case "transcribing": return "Transcribing"
        case "downloading": return "Downloading model"
        case "paused": return "Paused"
        case "needs_permission": return "Needs permission"
        case "error": return "Error"
        default: return "Starting"
        }
    }

    var color: NSColor {
        switch state {
        case "ready", "listening", "transcribing": return .systemGreen
        case "downloading", "paused": return .systemOrange
        case "needs_permission", "error": return .systemRed
        default: return .systemGray
        }
    }
}

// ---------------------------------------------------------------------------
// last.json

/// The last thing said, as the loop wrote it after the hold (core.write_last):
/// the text, how long from letting go of the key to the text being delivered,
/// which engine answered, the app, whether it was pasted, and when. The "Try
/// it" card shows this instead of waiting for a paste into its own box, and
/// Home shows the time-to-paste.
struct Last: Equatable {
    var text = ""
    var ms: Int? = nil
    var engine = ""
    var app = ""
    var pasted = false
    var at: Double = 0

    static func read() -> Last? {
        let url = (fake ? fixturesDir : stateDir).appendingPathComponent("last.json")
        guard let d = try? Data(contentsOf: url),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any]
        else { return nil }
        return Last(text: o["text"] as? String ?? "",
                    ms: (o["ms"] as? NSNumber)?.intValue,
                    engine: o["engine"] as? String ?? "",
                    app: o["app"] as? String ?? "",
                    pasted: o["pasted"] as? Bool ?? false,
                    at: (o["at"] as? NSNumber)?.doubleValue ?? 0)
    }
}

/// "1.2 s" or "640 ms": how long a person waited.
func waited(_ ms: Int) -> String {
    ms >= 1000 ? String(format: "%.1f s", Double(ms) / 1000) : "\(ms) ms"
}

/// "whisper" and "parakeet" are engine names, not something to show.
func engineTitle(_ e: String) -> String {
    let l = e.lowercased()
    if l.contains("parakeet") { return "English engine" }
    if l.contains("whisper") || l.contains("turbo") || l.contains("large") { return "Hinglish engine" }
    return e
}

/// "ggml-large-v3-turbo.bin" is a file name, not something to put in a menu.
func modelTitle(_ file: String) -> String {
    let f = file.lowercased()
    if f.contains("parakeet") { return "English model" }
    if f.contains("large") || f.contains("turbo") { return "Hinglish model" }
    if f.contains("tiny") { return "Quick model" }
    return file
}

// ---------------------------------------------------------------------------
// The dictation child, when there is a UI around it.

/// Starts `dictator dictate <key>` and keeps it running. Pause stops it on
/// purpose. Anything else that stops it is a failure, and what happens next
/// depends on who started the app. A repo install runs under its LaunchAgent,
/// so the app exits with the child and launchd restarts the pair together,
/// which is the rule the headless app has always had. The app from the .dmg
/// is opened from Finder or as a login item, and nothing would restart it,
/// so it stays, says what went wrong, and offers to restart dictation.
final class Supervisor {
    static let shared = Supervisor()
    private var child: Process?
    private var stopping = false
    private(set) var paused = false
    /// Why dictation is not running when it should be, for the menu. nil
    /// while it runs, while paused, and before the first start.
    private(set) var failure: String?
    /// When the current child was started. A status.json written before
    /// this is an earlier run's, and is not shown as the present.
    private(set) var startedAt: Double = 0
    var onChange: (() -> Void)?

    var running: Bool { child?.isRunning ?? false }

    /// Start dictation, unless the user paused it. Resume clears the pause
    /// first; the Accessibility wait calling this after a pause does not
    /// undo it.
    func start() {
        guard !fake, !paused, child == nil else { return }
        guard let (exe, argv, e) = cliCommand(["dictate", Prefs.key]) else {
            NSLog("dictator: cannot find the dictator command")
            failure = "Cannot find Dictator's own files. Reinstall the app."
            onChange?()
            return
        }
        let p = Process()
        p.executableURL = exe
        p.arguments = argv
        p.environment = e
        if let h = logHandle() {
            p.standardOutput = h
            p.standardError = h
        }
        p.terminationHandler = { [weak self] p in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.child = nil
                if self.stopping {
                    self.stopping = false
                    self.onChange?()
                    return
                }
                guard Mode.current.isBundle else { exit(p.terminationStatus) }
                // The loop writes its own last word into status.json (a
                // missing permission, or the listener dying), and that is
                // more specific than anything said here, so it is only
                // covered when it is not one of those.
                let s = Status.read()
                if !((s.state == "error" || s.state == "needs_permission")
                        && s.updated >= self.startedAt.rounded(.down)) {
                    self.failure = "Dictation stopped (exit \(p.terminationStatus))."
                }
                NSLog("dictator: dictation exited with \(p.terminationStatus)")
                self.onChange?()
            }
        }
        do { try p.run() } catch {
            NSLog("dictator: could not start dictation: \(error)")
            failure = "Dictation could not start: \(error.localizedDescription)"
            onChange?()
            return
        }
        child = p
        failure = nil
        startedAt = Date().timeIntervalSince1970
        onChange?()
    }

    func stop() {
        guard let p = child, p.isRunning else { return }
        stopping = true
        p.terminate()
    }

    func pause() { paused = true; failure = nil; stop(); onChange?() }
    func resume() { paused = false; start() }

    /// Quit: stop the child and give it a moment to close the microphone
    /// and write "paused". It treats SIGTERM as a clean stop; killed with
    /// the app instead, its recorder would keep the microphone open.
    func stopAndWait(_ seconds: Double = 2.0) {
        guard let p = child, p.isRunning else { return }
        stop()
        let until = Date().addingTimeInterval(seconds)
        while p.isRunning && Date() < until { usleep(50_000) }
    }

    /// A new hold key means a new child; the old one is listening for the
    /// old key.
    func restart() {
        guard let p = child, p.isRunning else { return }
        let old = p.terminationHandler
        p.terminationHandler = { [weak self] q in
            old?(q)
            DispatchQueue.main.async { self?.start() }
        }
        stop()
    }
}

func logHandle() -> FileHandle? {
    let info = Bundle.main.infoDictionary ?? [:]
    let log = URL(fileURLWithPath: (info["DictatorLog"] as? String)
        ?? stateDir.appendingPathComponent("dictate.log").path)
    try? FileManager.default.createDirectory(
        at: log.deletingLastPathComponent(), withIntermediateDirectories: true)
    if !FileManager.default.fileExists(atPath: log.path) {
        FileManager.default.createFile(atPath: log.path, contents: nil)
    }
    guard let h = try? FileHandle(forWritingTo: log) else { return nil }
    h.seekToEndOfFile()
    return h
}

// ---------------------------------------------------------------------------
// The few things the app remembers itself. Everything else is the CLI's.

enum Prefs {
    /// Fake mode keeps its own preferences, so clicking through the cards
    /// with canned data never changes the real app's key or onboarding.
    static let store: UserDefaults = fake
        ? (UserDefaults(suiteName: "com.dictator.dictation.fake") ?? .standard) : .standard

    static let keys = ["fn", "rightcmd", "rightopt", "leftcmd"]
    static let keyNames = ["fn": "fn", "rightcmd": "Right ⌘",
                           "rightopt": "Right ⌥", "leftcmd": "Left ⌘"]

    /// The hold key the child is started with. Same names as KEYS in
    /// bin/dictator, because it is passed straight to `dictate`.
    static var key: String {
        get {
            let k = store.string(forKey: "key") ?? "fn"
            return keys.contains(k) ? k : "fn"
        }
        set { store.set(newValue, forKey: "key") }
    }

    /// A Dock icon and an app menu, so the app can be quit and force quit
    /// like any other. On by default; off makes it a menu bar item only.
    static var showInDock: Bool {
        get { store.object(forKey: "showInDock") as? Bool ?? true }
        set { store.set(newValue, forKey: "showInDock") }
    }

    static var onboarded: Bool {
        get { store.bool(forKey: "onboarded") }
        set { store.set(newValue, forKey: "onboarded") }
    }
}
