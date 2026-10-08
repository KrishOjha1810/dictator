// Everything the windows know about Dictator comes through this file, and it
// comes from exactly two places: ~/.dictator/status.json, which the dictation
// loop writes, and the bundled CLI run with --json. The app never reads the
// history database or the vocabulary store itself. A second copy of that logic
// in Swift would be a second thing to keep right, and the Python one is the
// one with tests.
//
// DICTATOR_FAKE=1 swaps both for canned files in native/app/Fixtures, so the
// windows can be worked on without a model, a hotkey or a permission.

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

/// Where the canned files are. An explicit DICTATOR_FIXTURES, then a copy in
/// the bundle, then the source tree this binary was compiled from, which is
/// the usual case: build with tools/build_app.sh and run the result.
let fixturesDir: URL = {
    if let f = env["DICTATOR_FIXTURES"], !f.isEmpty { return URL(fileURLWithPath: f) }
    if let r = Bundle.main.resourceURL?.appendingPathComponent("Fixtures"),
       FileManager.default.fileExists(atPath: r.path) { return r }
    return URL(fileURLWithPath: #filePath).deletingLastPathComponent()
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
        if fake { return "(fake mode) dictator " + args.joined(separator: " ") }
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
                return Model(name: k, have: r["have"] as? Bool ?? false,
                             progress: (r["progress"] as? NSNumber)?.doubleValue ?? 0)
            }
        }
        return s
    }

    /// Every model the loop knows about is on disk. Card 5 of onboarding
    /// waits for this, and an empty list means the loop has not said yet,
    /// which is not the same as done.
    var modelsReady: Bool { !models.isEmpty && models.allSatisfy { $0.have } }

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
/// purpose; anything else that stops it takes the app down with it, so
/// launchd restarts the pair together, which is the rule the headless app
/// has always had.
final class Supervisor {
    static let shared = Supervisor()
    private var child: Process?
    private var stopping = false
    private(set) var paused = false
    var onChange: (() -> Void)?

    var running: Bool { child?.isRunning ?? false }

    func start() {
        guard !fake, child == nil else { return }
        guard let (exe, argv, e) = cliCommand(["dictate", Prefs.key]) else {
            NSLog("dictator: cannot find the dictator command")
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
                exit(p.terminationStatus)
            }
        }
        do { try p.run() } catch {
            NSLog("dictator: could not start dictation: \(error)")
            return
        }
        child = p
        paused = false
        onChange?()
    }

    func stop() {
        guard let p = child, p.isRunning else { return }
        stopping = true
        p.terminate()
    }

    func pause() { paused = true; stop(); onChange?() }
    func resume() { paused = false; start() }

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
    static let keys = ["fn", "rightcmd", "rightopt", "leftcmd"]
    static let keyNames = ["fn": "fn", "rightcmd": "Right ⌘",
                           "rightopt": "Right ⌥", "leftcmd": "Left ⌘"]

    /// The hold key the child is started with. Same names as KEYS in
    /// bin/dictator, because it is passed straight to `dictate`.
    static var key: String {
        get {
            let k = UserDefaults.standard.string(forKey: "key") ?? "fn"
            return keys.contains(k) ? k : "fn"
        }
        set { UserDefaults.standard.set(newValue, forKey: "key") }
    }

    static var onboarded: Bool {
        get { UserDefaults.standard.bool(forKey: "onboarded") }
        set { UserDefaults.standard.set(newValue, forKey: "onboarded") }
    }
}
