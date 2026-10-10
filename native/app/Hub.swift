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
            Group {
                switch model.page {
                case .home: HomePage()
                case .words: WordsPage()
                case .snippets: SnippetsPage()
                case .scratchpad: ScratchpadPage()
                case .style: StylePage()
                case .review: Placeholder(page: .review,
                    blurb: "What it may have got wrong today, and whether it was right.",
                    title: "Review is coming to the app",
                    line: "Until then, a terminal shows the same list.",
                    command: "dictator review")
                case .meetings: Placeholder(page: .meetings,
                    blurb: "Record a meeting on this Mac and keep its notes.",
                    title: "Meetings are coming to the app",
                    line: "Start one with ⌥M or the record button on the pill. A stopped "
                        + "meeting's notes are in a terminal for now.",
                    command: "dictator meeting show")
                case .settings: SettingsPage()
                case .help: HelpPage()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(Theme.background)
        }
        .frame(minWidth: 820, minHeight: 560)
        .background(Theme.background)
        .overlay(Group { if model.paletteOpen { CommandPalette() } })
        .ignoresSafeArea()
    }
}

// ---------------------------------------------------------------------------
// Sidebar: an ink rail with the mark, the palette, and the pages in groups.

struct Sidebar: View {
    @EnvironmentObject var model: AppModel

    /// What each group is for, in the order a day goes: say things, teach
    /// it, keep things.
    static let groups: [(String, [Page])] = [
        ("", [.home]),
        ("Teach", [.words, .snippets, .style]),
        ("Keep", [.scratchpad, .meetings, .review]),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 10) {
                BrandMark(size: 26)
                Text("Dictator").font(.display(16, .bold))
                    .foregroundColor(Theme.railText)
            }
            .padding(.horizontal, 6)
            .padding(.bottom, Theme.s3)

            Button { model.paletteOpen = true } label: {
                HStack(spacing: Theme.s2) {
                    Image(systemName: "magnifyingglass").font(.system(size: 11, weight: .semibold))
                    Text("Search or jump").font(.system(size: 12.5))
                    Spacer()
                    Text("⌘K").font(.system(size: 11, weight: .semibold, design: .rounded))
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(RoundedRectangle(cornerRadius: 4).fill(Color.white.opacity(0.08)))
                }
                .foregroundColor(Theme.railSecondary)
                .padding(.horizontal, 10)
                .frame(height: 30)
                .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color.white.opacity(0.06)))
                .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .strokeBorder(Color.white.opacity(0.08), lineWidth: 1))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.bottom, Theme.s3)

            ForEach(Self.groups, id: \.0) { title, pages in
                if !title.isEmpty {
                    Text(title).font(.system(size: 11.5, weight: .semibold))
                        .foregroundColor(Theme.railSecondary.opacity(0.8))
                        .padding(.leading, 10)
                        .padding(.top, Theme.s3)
                        .padding(.bottom, 2)
                }
                ForEach(pages) { SidebarItem(page: $0) }
            }
            Spacer()
            ForEach([Page.settings, .help]) { SidebarItem(page: $0) }

            VStack(alignment: .leading, spacing: 6) {
                StatusLine()
                HStack(spacing: 5) {
                    Image(systemName: "lock.fill").font(.system(size: 9, weight: .bold))
                    Text("Local only, on this Mac")
                        .font(.system(size: 11, weight: .medium))
                }
                .foregroundColor(Color(nsColor: Palette.cursorGlow).opacity(0.85))
                .help("Speech is turned into text here. Nothing you say is uploaded.")
            }
            .padding(.horizontal, 10)
            .padding(.top, Theme.s3)
        }
        .padding(.horizontal, Theme.s3)
        .padding(.top, 50)   // under the traffic lights
        .padding(.bottom, Theme.s4)
        .frame(width: 216)
        .frame(maxHeight: .infinity)
        .background(Theme.rail)
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
                    .font(.system(size: 12.5, weight: .medium))
                    .foregroundColor(on ? Theme.railText : Theme.railSecondary)
                    .frame(width: 18)
                Text(page.rawValue)
                    .font(.system(size: 13, weight: on ? .semibold : .regular))
                    .foregroundColor(on ? Theme.railText : Theme.railText.opacity(0.82))
                Spacer()
            }
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(on ? Theme.railSelected : (hover.on ? Theme.railHover : .clear)))
            // The selected page carries the icon's cursor: a teal bar.
            .overlay(alignment: .leading) {
                if on {
                    Capsule().fill(Theme.cursorGlow).frame(width: 3, height: 16)
                        .shadow(color: Theme.cursorGlow.opacity(0.7), radius: 3)
                        .offset(x: -1)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover.on = $0 && !snapshotRun }
    }
}

/// The same dot as the menu bar item, in words.
struct StatusLine: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        let s = model.shown
        HStack(spacing: 6) {
            Circle().fill(Color(nsColor: s.color)).frame(width: 7, height: 7)
            Text(detail(s)).font(.system(size: 12)).foregroundColor(Theme.railSecondary)
                .lineLimit(1)
        }
    }

    private func detail(_ s: Status) -> String {
        if s.state == "downloading",
           let m = s.models.first(where: { $0.downloading }) ?? s.models.first(where: { !$0.have }) {
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
                EmptyState(art: page == .meetings ? .mic : .lines(2), title: title, line: line)
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
                .background(RoundedRectangle(cornerRadius: Theme.smallRadius).fill(Theme.sunken))
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
// Home: today. A hero with the brand gradient and the time saved, the
// numbers, the privacy promise, then history by day, with search.

struct Said: Identifiable {
    var id: String
    var at: Date
    var text: String
    var app: String
    var engine: String
    /// "en", "hi" or "" as history stores it.
    var lang: String
    /// Seconds of speech, 0 when not known.
    var secs: Double
}

final class HomeState: ObservableObject {
    @Published var words: Int?
    @Published var wpm: Double?
    @Published var streak: Int?
    @Published var saved: Int?
    @Published var todayWords: Int?
    @Published var todaySaved: Int?
    @Published var said: [Said] = []
    @Published var loaded = false
    @Published var query = ""
}

/// "3 h 12 min", "14 min", "45 s".
func duration(_ secs: Int) -> String {
    if secs >= 3600 { return "\(secs / 3600) h \((secs % 3600) / 60) min" }
    if secs >= 60 { return "\(secs / 60) min" }
    return "\(secs) s"
}

/// What a history row was said in, from its language and engine.
func spokenIn(lang: String, engine: String) -> String? {
    let l = lang.lowercased()
    if l.hasPrefix("hi") || l == "hinglish" { return "Hinglish" }
    if l.hasPrefix("en") { return "English" }
    let e = engineTitle(engine)
    if e == "Hinglish engine" { return "Hinglish" }
    if e == "English engine" { return "English" }
    return nil
}

struct HomePage: View {
    @EnvironmentObject var model: AppModel
    @StateObject private var st = HomeState()

    var body: some View {
        PageScroll {
            if let r = model.clash { RivalBanner(running: r) }
            hero
            HStack(spacing: Theme.s3) {
                stat("text.word.spacing", st.words.map { $0.formatted() } ?? "–", "words, all time")
                stat("hourglass", st.saved.map(duration) ?? "–", "saved against typing")
                stat("speedometer", st.wpm.map { "\(Int($0.rounded()))" } ?? "–", "words a minute")
                stat("flame", st.streak.map { "\($0)" } ?? "–", "day streak")
            }
            PrivacyPromise()

            VStack(alignment: .leading, spacing: Theme.s3) {
                HStack {
                    Text("History").font(.sectionTitle).foregroundColor(Theme.text)
                    Spacer()
                    SearchField(prompt: "Search what you said", text: $st.query)
                        .frame(width: 260)
                }
                if !st.loaded {
                    Loading()
                } else if st.said.isEmpty {
                    EmptyState(art: .mic, title: "Nothing yet",
                               line: "Hold \(Prefs.keyNames[model.key] ?? model.key) and talk in "
                                   + "any app. What you say shows up here.")
                        .card()
                } else if days.isEmpty {
                    EmptyState(art: .search, title: "No matches",
                               line: "Nothing you said recently contains “\(st.query)”.")
                        .card()
                } else {
                    ForEach(days, id: \.0) { day, rows in
                        VStack(alignment: .leading, spacing: Theme.s2) {
                            SectionLabel(day)
                            RowsCard(rows) { r in HistoryRow(said: r, ms: ms(for: r)) }
                        }
                    }
                }
            }
        }
        .onAppear {
            if let q = model.takeSeed(.home) { st.query = q }
            load()
            model.checkRivals()
        }
        // A hold writes its history row before last.json, and the app reads
        // last.json every second, so a new `at` means a new row to show.
        // Without this Home only caught up when the page was opened again.
        .onChange(of: model.last?.at) { load() }
    }

    /// The brand moment: the gradient, today's words, and the time they saved.
    private var hero: some View {
        let key = Prefs.keyNames[model.key] ?? model.key
        return HStack(alignment: .center, spacing: Theme.s5) {
            VStack(alignment: .leading, spacing: Theme.s2) {
                Text(greeting).font(.display(30, .bold)).foregroundColor(.white)
                HStack(spacing: 6) {
                    Text("Hold")
                    Text(key).font(.system(size: 12, weight: .bold, design: .rounded))
                        .padding(.horizontal, 7).frame(minHeight: 22)
                        .background(RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .fill(Color.white.opacity(0.18)))
                        .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.35), lineWidth: 1))
                    Text("and talk. Double-tap it to go hands free.")
                }
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.white.opacity(0.88))
                HStack(spacing: Theme.s2) {
                    heroChip("text.cursor", st.todayWords.map { "\($0.formatted()) words today" }
                             ?? "No words yet today")
                    if let ms = model.last?.ms {
                        heroChip("bolt.fill", "last pasted in \(waited(ms))")
                    }
                }
                .padding(.top, Theme.s2)
            }
            Spacer(minLength: 0)
            VStack(alignment: .trailing, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(st.todaySaved.map(duration) ?? "0 s")
                        .font(.display(40, .bold))
                        .foregroundColor(.white)
                        .lineLimit(1).minimumScaleFactor(0.6)
                    Capsule().fill(Theme.cursorGlow).frame(width: 4, height: 34)
                        .shadow(color: Theme.cursorGlow.opacity(0.9), radius: 6)
                }
                Text("saved today against typing")
                    .font(.system(size: 12.5, weight: .medium)).foregroundColor(.white.opacity(0.8))
                Text("at 40 words a minute")
                    .font(.system(size: 11)).foregroundColor(.white.opacity(0.6))
            }
        }
        .padding(.horizontal, Theme.s5 + 4)
        .padding(.vertical, Theme.s5)
        .background(RoundedRectangle(cornerRadius: Theme.heroRadius, style: .continuous)
            .fill(Theme.brand))
        .overlay(RoundedRectangle(cornerRadius: Theme.heroRadius, style: .continuous)
            .strokeBorder(Color.white.opacity(0.14), lineWidth: 1))
    }

    private func heroChip(_ symbol: String, _ s: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: symbol).font(.system(size: 10, weight: .bold))
            Text(s).font(.system(size: 12, weight: .semibold))
        }
        .foregroundColor(.white)
        .padding(.horizontal, 10).padding(.vertical, 5)
        .background(Capsule().fill(Color.black.opacity(0.18)))
    }

    private var greeting: String {
        let h = Calendar.current.component(.hour, from: Date())
        return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"
    }

    private func stat(_ symbol: String, _ big: String, _ small: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: symbol)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(Theme.accent)
            Text(big).font(.statNumber).foregroundColor(Theme.text)
                .lineLimit(1).minimumScaleFactor(0.6)
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
                let int: (String) -> Int? = { (s[$0] as? NSNumber)?.intValue }
                st.words = int("words")
                st.wpm = (s["wpm"] as? NSNumber)?.doubleValue
                st.streak = int("streak_days")
                st.saved = int("saved_secs")
                st.todayWords = int("today_words")
                st.todaySaved = int("today_saved_secs")
            }
            st.said = loadSaid(hist)
            st.loaded = true
        }
    }
}

/// History rows as `dictator history --json` prints them.
func loadSaid(_ hist: Any?) -> [Said] {
    var rows = records(hist, under: ["history", "items", "rows"], nameKey: "id")
        .enumerated().map { i, r in
            Said(id: "\(r["id"] ?? i)",
                 at: Date(timeIntervalSince1970: (r["at"] as? NSNumber)?.doubleValue ?? 0),
                 text: str(r, "kept", "text", "shown", "heard"),
                 app: str(r, "app"), engine: str(r, "engine"), lang: str(r, "lang"),
                 secs: (r["secs"] as? NSNumber)?.doubleValue ?? 0)
        }
    // The canned history is from one fixed week. Moved so its newest row is a
    // few minutes ago, so fake mode shows Today and Yesterday the way a real
    // day does.
    if fake, let newest = rows.map(\.at).max() {
        let shift = Date().addingTimeInterval(-300).timeIntervalSince(newest)
        rows = rows.map { var r = $0; r.at = r.at.addingTimeInterval(shift); return r }
    }
    return rows
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
                    if let l = spokenIn(lang: said.lang, engine: said.engine) {
                        Pill(text: l, tint: l == "Hinglish" ? Theme.live : Theme.accent)
                    }
                    if !said.app.isEmpty { meta("macwindow", said.app) }
                    if said.secs > 0 { meta("waveform", String(format: "%.1f s spoken", said.secs)) }
                    if let ms = ms { meta("bolt.fill", "pasted in \(waited(ms))", Theme.live) }
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
        .background(st.hover ? Theme.raised.opacity(0.6) : Color.clear)
        .contentShape(Rectangle())
        .onHover { st.hover = $0 && !snapshotRun }
    }

    private func meta(_ symbol: String, _ text: String, _ tint: Color = Theme.tertiary) -> some View {
        HStack(spacing: 4) {
            Image(systemName: symbol).font(.system(size: 10))
            Text(text).font(.caption12)
        }
        .foregroundColor(tint)
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
    @EnvironmentObject var model: AppModel
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
                EmptyState(art: .lines(1), title: "No words yet",
                           line: "Add a name it keeps getting wrong, and it will spell it "
                               + "your way from the next sentence on.")
                    .card()
            } else if shown.isEmpty {
                EmptyState(art: .search, title: "No matches",
                           line: "No word contains “\(st.query)”.").card()
            } else {
                RowsCard(shown) { w in WordRow(word: w) { remove(w) } }
            }
        }
        .onAppear {
            if let q = model.takeSeed(.words) { st.query = q }
            load()
        }
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
        .onHover { st.hover = $0 && !snapshotRun }
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
    @EnvironmentObject var model: AppModel
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
                EmptyState(art: .lines(3), title: "No snippets yet",
                           line: "Add one for anything you type often: an address, a "
                               + "sign-off, a standup template.")
                    .card()
            } else if shown.isEmpty {
                EmptyState(art: .search, title: "No matches",
                           line: "No snippet contains “\(st.query)”.").card()
            } else {
                RowsCard(shown) { s in SnipRow(snip: s) { remove(s) } }
            }
        }
        .onAppear {
            if let q = model.takeSeed(.snippets) { st.query = q }
            load()
        }
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
        .onHover { st.hover = $0 && !snapshotRun }
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
                                .toggleStyle(BrandSwitch()).labelsHidden().tint(Theme.accentFill)
                                .controlSize(.small)
                        }
                        .padding(.horizontal, Theme.s4)
                        .padding(.vertical, Theme.s3)
                    }
                }
                VStack(alignment: .leading, spacing: Theme.s2) {
                    section("Per app")
                    if st.apps.isEmpty {
                        EmptyState(art: .lines(2), title: "Same rules in every app",
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

    private func section(_ s: String) -> some View { SectionLabel(s) }

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
                tip("hands.and.sparkles", "Hands free",
                    "Double-tap \(Prefs.keyNames[model.key] ?? model.key) and talk as long as you "
                    + "like, up to two minutes. Press it once to finish and paste, or Escape to "
                    + "throw it away. The pill shows a cross and a check while it listens.")
                Rectangle().fill(Theme.hairline).frame(height: 1)
                tip("capsule", "The pill",
                    "It appears while the microphone is open. Move the pointer to its place to "
                    + "see its buttons: dictate, the Notetaker (⌥M) and the Scratchpad (⌥S). "
                    + "Drag it to any edge or corner.")
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
            if model.key == "fn" { GlobeKeyNote() }
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
            Text(Rivals.warning(running.rival, key: model.key))
                .font(.system(size: 13))
                .foregroundColor(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: Theme.s2)
            Button("Change key") { model.page = .settings }
                .buttonStyle(QuietButton())
            if running.rival.quittable {
                Button("Quit \(running.rival.name)") { model.quitRival() }
                    .buttonStyle(PrimaryButton())
            }
        }
        .padding(.horizontal, Theme.s4)
        .padding(.vertical, Theme.s3)
        .background(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
            .fill(Theme.warn.opacity(0.08)))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
            .strokeBorder(Theme.warn.opacity(0.35), lineWidth: 1))
    }
}
