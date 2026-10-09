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
        HStack(spacing: 0) {
            Sidebar()
            Rectangle().fill(Theme.border).frame(width: 1)
            Group {
                switch model.page {
                case .home: HomePage()
                case .words: WordsPage()
                case .snippets: SnippetsPage()
                case .style: StylePage()
                case .review: Placeholder(page: .review,
                    blurb: "What it may have got wrong today, and whether it was right.",
                    title: "Review is coming to the app",
                    line: "Until then, a terminal shows the same list.",
                    command: "dictator review")
                case .meetings: Placeholder(page: .meetings,
                    blurb: "Record a meeting on this Mac and keep its notes.",
                    title: "Meetings are coming to the app",
                    line: "Until then, start a capture from a terminal.",
                    command: "dictator capture")
                case .settings: SettingsPage()
                case .help: HelpPage()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(Theme.background)
        }
        .frame(minWidth: 820, minHeight: 560)
        .background(Theme.background)
        .ignoresSafeArea()
    }
}

// ---------------------------------------------------------------------------
// Sidebar

struct Sidebar: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: Theme.s2) {
                Image(nsImage: NSApp.applicationIconImage)
                    .resizable().frame(width: 24, height: 24)
                Text("Dictator").font(.system(size: 15, weight: .semibold))
                    .foregroundColor(Theme.text)
            }
            .padding(.horizontal, Theme.s2)
            .padding(.bottom, Theme.s4)

            ForEach(Page.main) { SidebarItem(page: $0) }
            Spacer()
            ForEach([Page.settings, .help]) { SidebarItem(page: $0) }

            VStack(alignment: .leading, spacing: Theme.s2) {
                StatusLine()
                Pill(text: "On this Mac only", symbol: "lock.fill")
                    .help("Speech is turned into text here. Nothing you say is uploaded.")
            }
            .padding(.horizontal, Theme.s2)
            .padding(.top, Theme.s4)
        }
        .padding(.horizontal, Theme.s3)
        .padding(.top, 52)   // under the traffic lights
        .padding(.bottom, Theme.s4)
        .frame(width: 212)
        .frame(maxHeight: .infinity)
        .background(Theme.sidebar)
    }
}

struct SidebarItem: View {
    @EnvironmentObject var model: AppModel
    var page: Page
    @StateObject private var hover = Hover()

    var body: some View {
        let on = model.page == page
        Button { model.page = page } label: {
            HStack(spacing: 10) {
                Image(systemName: page.symbol)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(on ? Theme.accent : Theme.secondary)
                    .frame(width: 18)
                Text(page.rawValue)
                    .font(.system(size: 13, weight: on ? .semibold : .regular))
                    .foregroundColor(on ? Theme.text : Theme.text.opacity(0.85))
                Spacer()
            }
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(on ? Theme.card : (hover.on ? Theme.border.opacity(0.5) : .clear))
                .shadow(color: .black.opacity(on ? 0.05 : 0), radius: 2, x: 0, y: 1))
            .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous)
                .strokeBorder(on ? Theme.border : .clear, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover.on = $0 }
    }
}

/// The same dot as the menu bar item, in words.
struct StatusLine: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        let s = model.shown
        HStack(spacing: 6) {
            Circle().fill(Color(nsColor: s.color)).frame(width: 7, height: 7)
            Text(detail(s)).font(.system(size: 12)).foregroundColor(Theme.secondary)
                .lineLimit(1)
        }
    }

    private func detail(_ s: Status) -> String {
        if s.state == "downloading",
           let m = s.models.first(where: { !$0.have }) {
            return "\(modelTitle(m.name)) \(Int((m.progress * 100).rounded()))%"
        }
        return s.label
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

/// The padding every page uses, and a scroll view with it.
struct PageScroll<Content: View>: View {
    var content: Content
    init(@ViewBuilder _ c: () -> Content) { content = c() }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.s5) { content }
                .frame(maxWidth: 760, alignment: .leading)
                .padding(.horizontal, Theme.s7)
                .padding(.top, 48)
                .padding(.bottom, Theme.s6)
                .frame(maxWidth: .infinity)
        }
    }
}

/// A list inside one card, rows split by hairlines.
struct RowsCard<Item: Identifiable, Row: View>: View {
    var items: [Item]
    var row: (Item) -> Row

    init(_ items: [Item], @ViewBuilder row: @escaping (Item) -> Row) {
        self.items = items
        self.row = row
    }

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(items.enumerated()), id: \.element.id) { i, item in
                if i > 0 { Rectangle().fill(Theme.hairline).frame(height: 1) }
                row(item)
            }
        }
        .card(padding: 0)
    }
}

struct Loading: View {
    var body: some View {
        HStack(spacing: Theme.s2) {
            ProgressView().controlSize(.small)
            Text("Loading…").font(.system(size: 13)).foregroundColor(Theme.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Theme.s7)
    }
}

struct Placeholder: View {
    var page: Page
    var blurb: String
    var title: String
    var line: String
    var command: String

    var body: some View {
        PageScroll {
            PageHeader(page.rawValue, blurb)
            VStack(spacing: Theme.s4) {
                EmptyState(symbol: page.symbol, title: title, line: line)
                    .padding(.bottom, -Theme.s5)
                HStack(spacing: Theme.s2) {
                    Text(command).font(.system(size: 13, design: .monospaced))
                        .foregroundColor(Theme.text).textSelection(.enabled)
                    Button { copyToPasteboard(command) } label: {
                        Image(systemName: "doc.on.doc")
                    }
                    .buttonStyle(IconButton())
                    .help("Copy")
                }
                .padding(.leading, Theme.s3)
                .padding(.trailing, Theme.s1)
                .padding(.vertical, Theme.s1)
                .background(RoundedRectangle(cornerRadius: Theme.smallRadius).fill(Theme.background))
                .overlay(RoundedRectangle(cornerRadius: Theme.smallRadius)
                    .strokeBorder(Theme.border))
                .padding(.bottom, Theme.s6)
            }
            .frame(maxWidth: .infinity)
            .card()
        }
    }
}

// ---------------------------------------------------------------------------
// Home: greeting, stats, then history by day, with search.

struct Said: Identifiable {
    var id: String
    var at: Date
    var text: String
    var app: String
    var engine: String
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
    @EnvironmentObject var model: AppModel
    @StateObject private var st = HomeState()

    var body: some View {
        PageScroll {
            if let r = model.clash { RivalBanner(running: r) }
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: Theme.s2) {
                    Text(greeting).font(.pageTitle).foregroundColor(Theme.text)
                    HStack(spacing: 6) {
                        Text("Hold").foregroundColor(Theme.secondary)
                        KeyCap(label: Prefs.keyNames[model.key] ?? model.key)
                        Text("and talk in any app. Let go, and the words land at your cursor.")
                            .foregroundColor(Theme.secondary)
                    }
                    .font(.body14)
                }
                Spacer()
            }

            HStack(spacing: Theme.s3) {
                stat("text.word.spacing", st.words.map { $0.formatted() } ?? "–", "words dictated")
                stat("speedometer", st.wpm.map { "\(Int($0.rounded()))" } ?? "–", "words per minute")
                stat("flame", st.streak.map { "\($0)" } ?? "–",
                     "day streak")
                stat("bolt", model.last?.ms.map(waited) ?? "–", "last time to paste")
            }

            VStack(alignment: .leading, spacing: Theme.s3) {
                HStack {
                    Text("History").font(.system(size: 17, weight: .semibold))
                        .foregroundColor(Theme.text)
                    Spacer()
                    SearchField(prompt: "Search what you said", text: $st.query)
                        .frame(width: 260)
                }
                if !st.loaded {
                    Loading()
                } else if st.said.isEmpty {
                    EmptyState(symbol: "waveform", title: "Nothing yet",
                               line: "Hold \(Prefs.keyNames[model.key] ?? model.key) and talk in "
                                   + "any app. What you say shows up here.")
                        .card()
                } else if days.isEmpty {
                    EmptyState(symbol: "magnifyingglass", title: "No matches",
                               line: "Nothing you said recently contains “\(st.query)”.")
                        .card()
                } else {
                    ForEach(days, id: \.0) { day, rows in
                        VStack(alignment: .leading, spacing: Theme.s2) {
                            Text(day.uppercased())
                                .font(.system(size: 11, weight: .semibold))
                                .kerning(0.6)
                                .foregroundColor(Theme.tertiary)
                                .padding(.leading, Theme.s1)
                            RowsCard(rows) { r in HistoryRow(said: r, ms: ms(for: r)) }
                        }
                    }
                }
            }
        }
        .onAppear {
            load()
            model.checkRivals()
        }
    }

    private var greeting: String {
        let h = Calendar.current.component(.hour, from: Date())
        return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"
    }

    private func stat(_ symbol: String, _ big: String, _ small: String) -> some View {
        VStack(alignment: .leading, spacing: Theme.s2) {
            Image(systemName: symbol)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Theme.accent)
                .frame(width: 26, height: 26)
                .background(Circle().fill(Theme.accentSoft))
            Text(big).font(.statNumber).foregroundColor(Theme.text)
                .lineLimit(1).minimumScaleFactor(0.7)
            Text(small).font(.caption12).foregroundColor(Theme.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .card()
    }

    /// The time-to-paste is only known for the last hold (last.json); history
    /// does not store it. Shown on the row it belongs to.
    private func ms(for r: Said) -> Int? {
        guard let l = model.last, let ms = l.ms, !l.text.isEmpty,
              l.text == r.text,
              fake || abs(l.at - r.at.timeIntervalSince1970) < 120 else { return nil }
        return ms
    }

    /// Filtered by the search box, then grouped under Today, Yesterday and
    /// dates. Searching the rows already loaded is enough for a first
    /// version; `dictator find --json` is the place for searching all of it.
    private var days: [(String, [Said])] {
        let q = st.query.lowercased().trimmingCharacters(in: .whitespaces)
        let hit = q.isEmpty ? st.said : st.said.filter {
            $0.text.lowercased().contains(q) || $0.app.lowercased().contains(q)
        }
        let cal = Calendar.current
        var out: [(String, [Said])] = []
        for r in hit.sorted(by: { $0.at > $1.at }) {
            let name = cal.isDateInToday(r.at) ? "Today"
                : cal.isDateInYesterday(r.at) ? "Yesterday"
                : r.at.formatted(.dateTime.weekday(.wide).day().month(.wide))
            if out.last?.0 == name { out[out.count - 1].1.append(r) }
            else { out.append((name, [r])) }
        }
        return out
    }

    private func load() {
        CLI.load({ (CLI.json(["stats"]), CLI.json(["history", "200"])) }) { stats, hist in
            if let s = stats as? [String: Any] {
                st.words = (s["words"] as? NSNumber)?.intValue
                st.wpm = (s["wpm"] as? NSNumber)?.doubleValue
                st.streak = (s["streak_days"] as? NSNumber)?.intValue
            }
            var rows = records(hist, under: ["history", "items", "rows"], nameKey: "id")
                .enumerated().map { i, r in
                    Said(id: "\(r["id"] ?? i)",
                         at: Date(timeIntervalSince1970: (r["at"] as? NSNumber)?.doubleValue ?? 0),
                         text: str(r, "kept", "text", "shown", "heard"),
                         app: str(r, "app"), engine: str(r, "engine"))
                }
            // The canned history is from one fixed week. Moved so its newest
            // row is a few minutes ago, so fake mode shows Today and Yesterday
            // the way a real day does.
            if fake, let newest = rows.map(\.at).max() {
                let shift = Date().addingTimeInterval(-300).timeIntervalSince(newest)
                rows = rows.map { var r = $0; r.at = r.at.addingTimeInterval(shift); return r }
            }
            st.said = rows
            st.loaded = true
        }
    }
}

final class RowState: ObservableObject {
    @Published var hover = false
    @Published var copied = false
}

struct HistoryRow: View {
    var said: Said
    var ms: Int?
    @StateObject private var st = RowState()

    var body: some View {
        HStack(alignment: .top, spacing: Theme.s4) {
            Text(said.at.formatted(date: .omitted, time: .shortened))
                .font(.system(size: 12).monospacedDigit())
                .foregroundColor(Theme.tertiary)
                .frame(width: 64, alignment: .leading)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 6) {
                Text(said.text).font(.body14).foregroundColor(Theme.text)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: Theme.s3) {
                    if !said.app.isEmpty { meta("macwindow", said.app) }
                    if !said.engine.isEmpty { meta("waveform", engineTitle(said.engine)) }
                    if let ms = ms { meta("bolt", "pasted in \(waited(ms))") }
                }
            }
            Spacer(minLength: Theme.s2)
            Button {
                copyToPasteboard(said.text)
                st.copied = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) { st.copied = false }
            } label: {
                Image(systemName: st.copied ? "checkmark" : "doc.on.doc")
                    .foregroundColor(st.copied ? Theme.good : Theme.secondary)
            }
            .buttonStyle(IconButton())
            .opacity(st.hover || st.copied ? 1 : 0.35)
            .help("Copy")
        }
        .padding(.horizontal, Theme.s4)
        .padding(.vertical, Theme.s3)
        .background(st.hover ? Theme.background.opacity(0.7) : Color.clear)
        .contentShape(Rectangle())
        .onHover { st.hover = $0 }
    }

    private func meta(_ symbol: String, _ text: String) -> some View {
        HStack(spacing: 4) {
            Image(systemName: symbol).font(.system(size: 10))
            Text(text).font(.caption12)
        }
        .foregroundColor(Theme.tertiary)
    }
}

// ---------------------------------------------------------------------------
// Words and Snippets: a list, a way to add, a way to remove.

struct Word: Identifiable {
    var id: String { term }
    var term: String
    var heard: [String]
    var pending: Bool
    var count: Int
}

final class WordsState: ObservableObject {
    @Published var words: [Word] = []
    @Published var loaded = false
    @Published var adding = ""
    @Published var query = ""
}

struct WordsPage: View {
    @StateObject private var st = WordsState()

    var body: some View {
        PageScroll {
            PageHeader("Words", "Names and terms it should spell your way. Learned from your "
                       + "corrections, or added here.") {
                SearchField(prompt: "Search", text: $st.query).frame(width: 200)
            }
            HStack(spacing: Theme.s2) {
                InputField(prompt: "Add a word or name, e.g. Kubernetes", text: $st.adding,
                           onSubmit: add)
                Button("Add", action: add)
                    .buttonStyle(PrimaryButton())
                    .disabled(st.adding.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if !st.loaded {
                Loading()
            } else if st.words.isEmpty {
                EmptyState(symbol: "character.book.closed", title: "No words yet",
                           line: "Add a name it keeps getting wrong, and it will spell it "
                               + "your way from the next sentence on.")
                    .card()
            } else if shown.isEmpty {
                EmptyState(symbol: "magnifyingglass", title: "No matches",
                           line: "No word contains “\(st.query)”.").card()
            } else {
                RowsCard(shown) { w in WordRow(word: w) { remove(w) } }
            }
        }
        .onAppear(perform: load)
    }

    private var shown: [Word] {
        let q = st.query.lowercased().trimmingCharacters(in: .whitespaces)
        return q.isEmpty ? st.words : st.words.filter {
            $0.term.lowercased().contains(q) || $0.heard.contains { $0.lowercased().contains(q) }
        }
    }

    private func load() {
        CLI.load({ CLI.json(["words"]) }) { any in
            let parse: ([[String: Any]], Bool) -> [Word] = { rows, pending in
                rows.map { Word(term: str($0, "term", "word"),
                                heard: $0["heard"] as? [String] ?? [], pending: pending,
                                count: ($0["count"] as? NSNumber)?.intValue ?? 0) }
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
        if fake { st.words.insert(Word(term: t, heard: [], pending: false, count: 0), at: 0); return }
        CLI.load({ CLI.act(["learn", t]) }) { _ in load() }
    }

    private func remove(_ w: Word) {
        if fake { st.words.removeAll { $0.term == w.term }; return }
        CLI.load({ CLI.act(["unlearn", w.term]) }) { _ in load() }
    }
}

struct WordRow: View {
    var word: Word
    var remove: () -> Void
    @StateObject private var st = RowState()

    var body: some View {
        HStack(spacing: Theme.s3) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: Theme.s2) {
                    Text(word.term).font(.system(size: 14, weight: .medium))
                        .foregroundColor(Theme.text)
                    if word.pending {
                        Pill(text: "noticed once", tint: Theme.warn)
                            .help("Seen corrected once. A second time and it is learned.")
                    }
                }
                if !word.heard.isEmpty {
                    Text("heard as " + word.heard.prefix(3).map { "“\($0)”" }.joined(separator: ", "))
                        .font(.caption12).foregroundColor(Theme.secondary)
                }
            }
            Spacer()
            if word.count > 0 {
                Text("fixed \(word.count)×").font(.caption12.monospacedDigit())
                    .foregroundColor(Theme.tertiary)
            }
            Button(action: remove) { Image(systemName: "trash") }
                .buttonStyle(IconButton())
                .opacity(st.hover ? 1 : 0)
                .help("Stop fixing this word")
        }
        .padding(.horizontal, Theme.s4)
        .padding(.vertical, Theme.s3)
        .contentShape(Rectangle())
        .onHover { st.hover = $0 }
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
    @Published var query = ""
}

struct SnippetsPage: View {
    @StateObject private var st = SnippetsState()

    var body: some View {
        PageScroll {
            PageHeader("Snippets", "Say a short phrase, and a longer text is typed instead.") {
                SearchField(prompt: "Search", text: $st.query).frame(width: 200)
            }
            HStack(spacing: Theme.s2) {
                InputField(prompt: "When I say…", text: $st.trigger).frame(width: 200)
                Image(systemName: "arrow.right").foregroundColor(Theme.tertiary)
                InputField(prompt: "…type this", text: $st.text, onSubmit: add)
                Button("Add", action: add)
                    .buttonStyle(PrimaryButton())
                    .disabled(st.trigger.trimmingCharacters(in: .whitespaces).isEmpty
                              || st.text.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if !st.loaded {
                Loading()
            } else if st.snips.isEmpty {
                EmptyState(symbol: "text.badge.plus", title: "No snippets yet",
                           line: "Add one for anything you type often: an address, a "
                               + "sign-off, a standup template.")
                    .card()
            } else if shown.isEmpty {
                EmptyState(symbol: "magnifyingglass", title: "No matches",
                           line: "No snippet contains “\(st.query)”.").card()
            } else {
                RowsCard(shown) { s in SnipRow(snip: s) { remove(s) } }
            }
        }
        .onAppear(perform: load)
    }

    private var shown: [Snip] {
        let q = st.query.lowercased().trimmingCharacters(in: .whitespaces)
        return q.isEmpty ? st.snips : st.snips.filter {
            $0.trigger.lowercased().contains(q) || $0.text.lowercased().contains(q)
        }
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
        if fake { st.snips.insert(Snip(trigger: t, text: x, count: 0), at: 0); return }
        CLI.load({ CLI.act(["snippet", t, x]) }) { _ in load() }
    }

    private func remove(_ s: Snip) {
        if fake { st.snips.removeAll { $0.trigger == s.trigger }; return }
        CLI.load({ CLI.act(["unsnippet", s.trigger]) }) { _ in load() }
    }
}

struct SnipRow: View {
    var snip: Snip
    var remove: () -> Void
    @StateObject private var st = RowState()

    var body: some View {
        HStack(alignment: .top, spacing: Theme.s4) {
            Text("“\(snip.trigger)”").font(.system(size: 14, weight: .medium))
                .foregroundColor(Theme.text)
                .frame(width: 180, alignment: .leading)
            Image(systemName: "arrow.right").font(.system(size: 11))
                .foregroundColor(Theme.tertiary).padding(.top, 3)
            VStack(alignment: .leading, spacing: 3) {
                Text(snip.text).font(.body14).foregroundColor(Theme.secondary)
                    .lineLimit(3)
                if snip.count > 0 {
                    Text("used \(snip.count) time\(snip.count == 1 ? "" : "s")")
                        .font(.caption12).foregroundColor(Theme.tertiary)
                }
            }
            Spacer()
            Button(action: remove) { Image(systemName: "trash") }
                .buttonStyle(IconButton())
                .opacity(st.hover ? 1 : 0)
                .help("Remove this snippet")
        }
        .padding(.horizontal, Theme.s4)
        .padding(.vertical, Theme.s3)
        .contentShape(Rectangle())
        .onHover { st.hover = $0 }
    }
}

// ---------------------------------------------------------------------------
// Style: how text is shaped, everywhere and per app. `dictator format` and
// `dictator format in` print a line per rule; this lays those lines out. The
// global rules can be switched here (`dictator format <rule> on|off`); the
// per-app ones are shown, and changed in a terminal for now.

struct Rule: Identifiable {
    var id: String { name }
    var name: String
    var on: Bool
}

struct AppRules: Identifiable {
    var id: String { app }
    var app: String
    var rules: [Rule]
}

final class StyleState: ObservableObject {
    @Published var global: [Rule] = []
    @Published var apps: [AppRules] = []
    @Published var loaded = false
}

struct StylePage: View {
    @StateObject private var st = StyleState()

    static let titles: [String: (String, String)] = [
        "enabled": ("Shape the text", "Tidy what you said before it is typed."),
        "punctuation": ("Punctuation", "Commas and full stops where you paused."),
        "sentences": ("Sentences", "A capital letter at the start of each one."),
        "lists": ("Lists", "“One… two… three…” becomes a numbered list."),
        "fillers": ("Remove fillers", "Leave out um, uh and the like."),
        "stutters": ("Remove stutters", "“is is” becomes “is”, and “g giving” becomes “giving”."),
    ]

    var body: some View {
        PageScroll {
            PageHeader("Style", "How your words are tidied before they land. Applied on "
                       + "this Mac, never by a cloud model.")
            if !st.loaded {
                Loading()
            } else {
                VStack(alignment: .leading, spacing: Theme.s2) {
                    section("Everywhere")
                    RowsCard(st.global) { r in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(Self.titles[r.name]?.0 ?? r.name)
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundColor(Theme.text)
                                Text(Self.titles[r.name]?.1 ?? "")
                                    .font(.caption12).foregroundColor(Theme.secondary)
                            }
                            Spacer()
                            Toggle("", isOn: Binding(get: { r.on }, set: { set(r.name, $0) }))
                                .toggleStyle(.switch).labelsHidden().tint(Theme.accent)
                                .controlSize(.small)
                        }
                        .padding(.horizontal, Theme.s4)
                        .padding(.vertical, Theme.s3)
                    }
                }
                VStack(alignment: .leading, spacing: Theme.s2) {
                    section("Per app")
                    if st.apps.isEmpty {
                        EmptyState(symbol: "square.grid.2x2", title: "Same rules in every app",
                                   line: "To change one app only, run in a terminal: "
                                       + "dictator format in Slack lists on")
                            .card()
                    } else {
                        RowsCard(st.apps) { a in
                            HStack(alignment: .firstTextBaseline) {
                                Text(a.app == "terminal" ? "Terminals" : a.app)
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundColor(Theme.text)
                                    .frame(width: 160, alignment: .leading)
                                HStack(spacing: 6) {
                                    ForEach(a.rules) { r in
                                        Pill(text: (Self.titles[r.name]?.0 ?? r.name)
                                                 + (r.on ? " on" : " off"),
                                             tint: r.on ? Theme.accent : Theme.secondary)
                                    }
                                }
                                Spacer()
                            }
                            .padding(.horizontal, Theme.s4)
                            .padding(.vertical, Theme.s3)
                        }
                        Text("Change one in a terminal: dictator format in Slack lists on")
                            .font(.caption12).foregroundColor(Theme.tertiary)
                            .textSelection(.enabled)
                            .padding(.leading, Theme.s1)
                    }
                }
            }
        }
        .onAppear(perform: load)
    }

    private func section(_ s: String) -> some View {
        Text(s.uppercased()).font(.system(size: 11, weight: .semibold)).kerning(0.6)
            .foregroundColor(Theme.tertiary).padding(.leading, Theme.s1)
    }

    private func load() {
        CLI.load({ (CLI.text(["format"]), CLI.text(["format", "in"])) }) { g, a in
            // "  lists        off": a rule name, then on or off.
            st.global = g.split(separator: "\n").compactMap { line in
                let w = line.split(separator: " ")
                guard w.count == 2, Self.titles[String(w[0])] != nil,
                      w[1] == "on" || w[1] == "off" else { return nil }
                return Rule(name: String(w[0]), on: w[1] == "on")
            }
            // "  Slack          lists on, punctuation off"
            st.apps = a.split(separator: "\n").compactMap { line in
                let t = line.trimmingCharacters(in: .whitespaces)
                guard let gap = t.range(of: "  ") else { return nil }
                let app = String(t[..<gap.lowerBound])
                let rules = t[gap.upperBound...].split(separator: ",").compactMap { p -> Rule? in
                    let w = p.split(separator: " ")
                    guard w.count == 2, w[1] == "on" || w[1] == "off" else { return nil }
                    return Rule(name: String(w[0]), on: w[1] == "on")
                }
                return rules.isEmpty ? nil : AppRules(app: app, rules: rules)
            }
            st.loaded = true
        }
    }

    private func set(_ name: String, _ on: Bool) {
        if let i = st.global.firstIndex(where: { $0.name == name }) { st.global[i].on = on }
        let arg = name == "enabled" ? [on ? "on" : "off"] : [name, on ? "on" : "off"]
        if fake { return }
        CLI.load({ CLI.act(["format"] + arg) }) { _ in load() }
    }
}

// ---------------------------------------------------------------------------
// Help

struct HelpPage: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        PageScroll {
            PageHeader("Help", "How it works, and what to do when it does not.")
            VStack(spacing: 0) {
                tip("hand.tap", "Hold, talk, let go",
                    "Hold \(Prefs.keyNames[model.key] ?? model.key), say what you mean, and "
                    + "let go. The words are typed where your cursor is.")
                Rectangle().fill(Theme.hairline).frame(height: 1)
                tip("character.bubble", "Hindi and English together",
                    "Set the language to Hinglish in Settings if you mix the two. English "
                    + "first is quicker if you mostly speak English.")
                Rectangle().fill(Theme.hairline).frame(height: 1)
                tip("character.book.closed", "It keeps getting a name wrong",
                    "Add it on the Words page, or correct it once where it was typed. "
                    + "It learns from the second correction.")
                Rectangle().fill(Theme.hairline).frame(height: 1)
                tip("exclamationmark.triangle", "Nothing is typed",
                    "Check that Accessibility is on for Dictator in System Settings, then "
                    + "run the diagnostics in Settings, Advanced.")
            }
            .card(padding: 0)
            HStack(spacing: Theme.s2) {
                Button("Open Accessibility settings") {
                    NSWorkspace.shared.open(URL(string:
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
                }
                .buttonStyle(QuietButton())
                Button("Run diagnostics") { model.page = .settings }
                    .buttonStyle(QuietButton())
                Button("Show log") {
                    NSWorkspace.shared.activateFileViewerSelecting(
                        [stateDir.appendingPathComponent("dictate.log")])
                }
                .buttonStyle(QuietButton())
            }
        }
    }

    private func tip(_ symbol: String, _ title: String, _ line: String) -> some View {
        HStack(alignment: .top, spacing: Theme.s3) {
            Image(systemName: symbol).font(.system(size: 13, weight: .medium))
                .foregroundColor(Theme.accent)
                .frame(width: 28, height: 28)
                .background(Circle().fill(Theme.accentSoft))
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.system(size: 14, weight: .medium)).foregroundColor(Theme.text)
                Text(line).font(.system(size: 13)).foregroundColor(Theme.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
        }
        .padding(Theme.s4)
    }
}

/// Another dictation app on the same key. Says so, and offers the two ways
/// out; it never quits anything without the click.
struct RivalBanner: View {
    @EnvironmentObject var model: AppModel
    var running: Rivals.Running

    var body: some View {
        HStack(alignment: .center, spacing: Theme.s3) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(Theme.warn)
            Text(Rivals.warning(running.rival))
                .font(.system(size: 13))
                .foregroundColor(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: Theme.s2)
            Button("Change key") { model.page = .settings }
                .buttonStyle(QuietButton())
            Button("Quit \(running.rival.name)") { model.quitRival() }
                .buttonStyle(PrimaryButton())
        }
        .padding(.horizontal, Theme.s4)
        .padding(.vertical, Theme.s3)
        .background(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
            .fill(Theme.warn.opacity(0.08)))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
            .strokeBorder(Theme.warn.opacity(0.35), lineWidth: 1))
    }
}
