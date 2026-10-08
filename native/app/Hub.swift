// The Hub: the window for looking back at what you said and for teaching it.
//
// Every page is a thin view over one CLI command run with --json. Nothing is
// counted, searched or stored here; if a number on this page is wrong, the
// command that printed it is where to fix it.
//
// Page state lives in small ObservableObject classes held with @StateObject,
// not in @State. In the macOS 27 SDK @State is a macro, and the Command Line
// Tools ship no SwiftUIMacros plugin, so @State only compiles inside Xcode and
// this app is built with plain swiftc.

import AppKit
import SwiftUI

struct HubView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        NavigationSplitView {
            List(selection: Binding(get: { Optional(model.page) },
                                    set: { if let p = $0 { model.page = p } })) {
                Section {
                    ForEach(Page.allCases.filter { $0 != .settings }) { p in
                        Label(p.rawValue, systemImage: p.symbol).tag(p)
                    }
                }
                Section {
                    Label(Page.settings.rawValue, systemImage: Page.settings.symbol)
                        .tag(Page.settings)
                }
            }
            .navigationSplitViewColumnWidth(min: 170, ideal: 190, max: 240)
        } detail: {
            Group {
                switch model.page {
                case .home: HomePage()
                case .words: WordsPage()
                case .snippets: SnippetsPage()
                case .apps: TextPage(title: "Apps",
                    blurb: "Formatting rules per application. They run on this Mac; no "
                         + "cloud model sees what you said.",
                    command: ["format"],
                    hint: "Change one with: dictator format in Slack lists on")
                case .review: Placeholder(title: "Review",
                    blurb: "What it may have got wrong today, and whether it was right.",
                    hint: "For now, in a terminal: dictator review")
                case .meetings: Placeholder(title: "Meetings",
                    blurb: "Meeting capture and its notes.",
                    hint: "For now, in a terminal: dictator capture")
                case .settings: SettingsPage()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }
}

// ---------------------------------------------------------------------------
// Reading what the CLI printed. The --json shapes are new, so this accepts a
// bare list, a list under a named key, or a map of name to record, rather
// than failing the page over a wrapper.

func records(_ any: Any?, under keys: [String], nameKey: String) -> [[String: Any]] {
    if let a = any as? [[String: Any]] { return a }
    guard let d = any as? [String: Any] else { return [] }
    for k in keys {
        if let a = d[k] as? [[String: Any]] { return a }
        if let m = d[k] as? [String: [String: Any]] {
            return m.keys.sorted().map { var r = m[$0]!; r[nameKey] = $0; return r }
        }
    }
    if let m = d as? [String: [String: Any]] {
        return m.keys.sorted().map { var r = m[$0]!; r[nameKey] = $0; return r }
    }
    return []
}

func str(_ r: [String: Any], _ keys: String...) -> String {
    for k in keys { if let s = r[k] as? String, !s.isEmpty { return s } }
    return ""
}

struct PageTitle: View {
    var text: String
    var body: some View {
        Text(text).font(.system(size: 24, weight: .semibold)).padding(.bottom, 4)
    }
}

struct Placeholder: View {
    var title: String
    var blurb: String
    var hint: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            PageTitle(text: title)
            Text(blurb).foregroundColor(.secondary)
            Text(hint).font(.system(.body, design: .monospaced)).textSelection(.enabled)
                .padding(.top, 8)
        }
        .padding(28)
    }
}

/// A page that is, for now, what a command prints. Better than a blank page,
/// and it says exactly what the real one will show.
final class TextState: ObservableObject {
    @Published var out = ""
}

struct TextPage: View {
    var title: String
    var blurb: String
    var command: [String]
    var hint: String
    @StateObject private var st = TextState()

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            PageTitle(text: title)
            Text(blurb).foregroundColor(.secondary)
            ScrollView {
                Text(st.out.isEmpty ? "Loading…" : st.out)
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Text(hint).font(.caption).foregroundColor(.secondary)
        }
        .padding(28)
        .onAppear { CLI.load({ CLI.text(command) }) { st.out = $0 } }
    }
}

// ---------------------------------------------------------------------------
// Home: stats, then history by day, with search.

struct Said: Identifiable {
    var id: String
    var at: Date
    var text: String
    var app: String
    var kept: String
}

final class HomeState: ObservableObject {
    @Published var words: Int?
    @Published var wpm: Double?
    @Published var streak: Int?
    @Published var said: [Said] = []
    @Published var loaded = false
    @Published var query = ""
}

struct HomePage: View {
    @StateObject private var st = HomeState()

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            PageTitle(text: "Home")
            HStack(spacing: 0) {
                stat(st.words.map { $0.formatted() } ?? "–", "words")
                Divider().frame(height: 40)
                stat(st.wpm.map { "\(Int($0.rounded())) wpm" } ?? "–", "average")
                Divider().frame(height: 40)
                stat(st.streak.map { $0 == 1 ? "1 day" : "\($0) days" } ?? "–", "streak")
            }
            .padding(.vertical, 12)
            .background(RoundedRectangle(cornerRadius: 10)
                .fill(Color(nsColor: .controlBackgroundColor)))
            .overlay(RoundedRectangle(cornerRadius: 10)
                .stroke(Color.secondary.opacity(0.2)))

            TextField("Search what you said", text: $st.query)
                .textFieldStyle(.roundedBorder)

            if !st.loaded {
                Text("Loading…").foregroundColor(.secondary)
            } else if st.said.isEmpty {
                Text("Nothing yet. Hold your key and talk; it shows up here.")
                    .foregroundColor(.secondary)
            } else {
                List {
                    ForEach(days, id: \.0) { day, rows in
                        Section(day) {
                            ForEach(rows) { r in
                                HStack(alignment: .firstTextBaseline, spacing: 12) {
                                    Text(r.at.formatted(date: .omitted, time: .shortened))
                                        .font(.system(.caption, design: .monospaced))
                                        .foregroundColor(.secondary)
                                        .frame(width: 60, alignment: .leading)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(r.text).textSelection(.enabled)
                                        if !r.app.isEmpty {
                                            Text(r.app).font(.caption)
                                                .foregroundColor(.secondary)
                                        }
                                    }
                                }
                                .padding(.vertical, 2)
                            }
                        }
                    }
                }
                .listStyle(.inset)
            }
        }
        .padding(28)
        .onAppear(perform: load)
    }

    private func stat(_ big: String, _ small: String) -> some View {
        VStack(spacing: 2) {
            Text(big).font(.system(size: 20, weight: .semibold))
            Text(small).font(.caption).foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    /// Filtered by the search box, then grouped under Today, Yesterday and
    /// dates. Searching the rows already loaded is enough for a first
    /// version; `dictator find --json` is the place for searching all of it.
    private var days: [(String, [Said])] {
        let q = st.query.lowercased()
        let hit = q.isEmpty ? st.said : st.said.filter {
            $0.text.lowercased().contains(q) || $0.app.lowercased().contains(q)
        }
        let cal = Calendar.current
        var out: [(String, [Said])] = []
        for r in hit.sorted(by: { $0.at > $1.at }) {
            let name = cal.isDateInToday(r.at) ? "Today"
                : cal.isDateInYesterday(r.at) ? "Yesterday"
                : r.at.formatted(date: .abbreviated, time: .omitted)
            if out.last?.0 == name { out[out.count - 1].1.append(r) }
            else { out.append((name, [r])) }
        }
        return out
    }

    private func load() {
        CLI.load({ (CLI.json(["stats"]), CLI.json(["history"])) }) { stats, hist in
            if let s = stats as? [String: Any] {
                st.words = (s["words"] as? NSNumber)?.intValue
                st.wpm = (s["wpm"] as? NSNumber)?.doubleValue
                st.streak = (s["streak_days"] as? NSNumber)?.intValue
            }
            st.said = records(hist, under: ["history", "items", "rows"], nameKey: "id")
                .enumerated().map { i, r in
                    Said(id: "\(r["id"] ?? i)",
                         at: Date(timeIntervalSince1970: (r["at"] as? NSNumber)?.doubleValue ?? 0),
                         text: str(r, "kept", "shown", "text", "heard"),
                         app: str(r, "app"), kept: str(r, "kept"))
                }
            st.loaded = true
        }
    }
}

// ---------------------------------------------------------------------------
// Words and Snippets: a list, a way to add, a way to remove.

struct Word: Identifiable {
    var id: String { term }
    var term: String
    var heard: [String]
    var pending: Bool
}

final class WordsState: ObservableObject {
    @Published var words: [Word] = []
    @Published var loaded = false
    @Published var adding = ""
}

struct WordsPage: View {
    @StateObject private var st = WordsState()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            PageTitle(text: "Words")
            Text("Names and terms it should spell your way. Learned from your "
                 + "corrections, or added here.").foregroundColor(.secondary)
            HStack {
                TextField("Add a word, e.g. Kubernetes", text: $st.adding)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(add)
                Button("Add", action: add)
                    .disabled(st.adding.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if !st.loaded {
                Text("Loading…").foregroundColor(.secondary)
            } else if st.words.isEmpty {
                Text("Nothing learned yet.").foregroundColor(.secondary)
            } else {
                List {
                    ForEach(st.words) { w in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(w.term).font(.system(size: 14, weight: .medium))
                                if !w.heard.isEmpty {
                                    Text("heard as " + w.heard.prefix(3).joined(separator: ", "))
                                        .font(.caption).foregroundColor(.secondary)
                                }
                            }
                            if w.pending {
                                Text("noticed once").font(.caption)
                                    .padding(.horizontal, 6).padding(.vertical, 2)
                                    .background(Capsule().fill(Color.orange.opacity(0.2)))
                            }
                            Spacer()
                            Button(role: .destructive) { remove(w) } label: {
                                Image(systemName: "minus.circle")
                            }
                            .buttonStyle(.borderless)
                            .help("Stop fixing this word")
                        }
                    }
                }
                .listStyle(.inset)
            }
        }
        .padding(28)
        .onAppear(perform: load)
    }

    private func load() {
        CLI.load({ CLI.json(["words"]) }) { any in
            let parse: ([[String: Any]], Bool) -> [Word] = { rows, pending in
                rows.map { Word(term: str($0, "term", "word"),
                                heard: $0["heard"] as? [String] ?? [], pending: pending) }
            }
            st.words = parse(records(any, under: ["words", "terms"], nameKey: "term"), false)
                + parse(records((any as? [String: Any])?["pending"], under: [],
                                nameKey: "term"), true)
            st.words.removeAll { $0.term.isEmpty }
            st.loaded = true
        }
    }

    private func add() {
        let t = st.adding.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty else { return }
        st.adding = ""
        if fake { st.words.append(Word(term: t, heard: [], pending: false)); return }
        CLI.load({ CLI.act(["learn", t]) }) { _ in load() }
    }

    private func remove(_ w: Word) {
        if fake { st.words.removeAll { $0.term == w.term }; return }
        CLI.load({ CLI.act(["unlearn", w.term]) }) { _ in load() }
    }
}

struct Snip: Identifiable {
    var id: String { trigger }
    var trigger: String
    var text: String
    var count: Int
}

final class SnippetsState: ObservableObject {
    @Published var snips: [Snip] = []
    @Published var loaded = false
    @Published var trigger = ""
    @Published var text = ""
}

struct SnippetsPage: View {
    @StateObject private var st = SnippetsState()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            PageTitle(text: "Snippets")
            Text("Say a short phrase, get a longer text.").foregroundColor(.secondary)
            HStack {
                TextField("When I say…", text: $st.trigger).textFieldStyle(.roundedBorder)
                TextField("…type this", text: $st.text).textFieldStyle(.roundedBorder)
                    .onSubmit(add)
                Button("Add", action: add)
                    .disabled(st.trigger.trimmingCharacters(in: .whitespaces).isEmpty
                              || st.text.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if !st.loaded {
                Text("Loading…").foregroundColor(.secondary)
            } else if st.snips.isEmpty {
                Text("No snippets yet.").foregroundColor(.secondary)
            } else {
                List {
                    ForEach(st.snips) { s in
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("“\(s.trigger)”").font(.system(size: 14, weight: .medium))
                                Text(s.text).foregroundColor(.secondary).lineLimit(2)
                                if s.count > 0 {
                                    Text("used \(s.count) time\(s.count == 1 ? "" : "s")")
                                        .font(.caption).foregroundColor(.secondary)
                                }
                            }
                            Spacer()
                            Button(role: .destructive) { remove(s) } label: {
                                Image(systemName: "minus.circle")
                            }
                            .buttonStyle(.borderless)
                        }
                    }
                }
                .listStyle(.inset)
            }
        }
        .padding(28)
        .onAppear(perform: load)
    }

    private func load() {
        CLI.load({ CLI.json(["snippet"]) }) { any in
            st.snips = records(any, under: ["snippets", "items"], nameKey: "trigger").map {
                Snip(trigger: str($0, "trigger", "say"), text: str($0, "text", "get"),
                     count: ($0["count"] as? NSNumber)?.intValue ?? 0)
            }
            st.snips.removeAll { $0.trigger.isEmpty }
            st.loaded = true
        }
    }

    private func add() {
        let t = st.trigger.trimmingCharacters(in: .whitespaces)
        let x = st.text.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty, !x.isEmpty else { return }
        st.trigger = ""; st.text = ""
        if fake { st.snips.append(Snip(trigger: t, text: x, count: 0)); return }
        CLI.load({ CLI.act(["snippet", t, x]) }) { _ in load() }
    }

    private func remove(_ s: Snip) {
        if fake { st.snips.removeAll { $0.trigger == s.trigger }; return }
        CLI.load({ CLI.act(["unsnippet", s.trigger]) }) { _ in load() }
    }
}
