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

/// How wide the window is, for the two places that have to adapt to it.
///
/// Read from one GeometryReader at the root rather than measured again in
/// each view: a sidebar cannot see the window from inside its own fixed
/// width, which is how this came to be laid out for 1020 points and then
/// clipped on both sides at anything narrower.
private struct WindowWidthKey: EnvironmentKey { static let defaultValue: CGFloat = 1180 }

extension EnvironmentValues {
    var windowWidth: CGFloat {
        get { self[WindowWidthKey.self] }
        set { self[WindowWidthKey.self] = newValue }
    }
}

/// Below this the right hand column folds into the page instead of sitting
/// beside it. Nothing is lost, it just stacks.
let roomForRecent: CGFloat = 1000
/// Below this the sidebar keeps its icons and drops its words.
let roomForRailLabels: CGFloat = 840

struct HubView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        GeometryReader { geo in
            shell.environment(\.windowWidth, geo.size.width)
        }
        .ignoresSafeArea()
    }

    private var shell: some View {
        HStack(spacing: 0) {
            Sidebar()
            Group {
                switch model.page {
                case .home: HomePage()
                case .history: HistoryPage()
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
        // No minimum width here. It used to be 1020, which did not stop the
        // window being resized smaller: it made the content stay 1020 wide
        // and sit centred, so the sidebar was cut off on the left and the
        // recent column on the right. The window has a minimum; the layout
        // adapts instead of insisting.
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        // A soft shadow under everything, so white type stays readable where
        // the sky is pale near the horizon. The alternative was darkening the
        // sky until it was black, which was tried and is how this ended up
        // looking like a plain dark window.
        .shadow(color: .black.opacity(Glass.on ? 0.42 : 0), radius: 2.5, y: 1)
        .background(Group {
            // The app's own sky, not the user's desktop. Why, in Backdrop.
            if Glass.on { Backdrop() } else { Theme.background }
        })
        .overlay(Group { if model.paletteOpen { CommandPalette() } })
        .ignoresSafeArea()
    }
}

// ---------------------------------------------------------------------------
// Sidebar.
//
// It used to be an ink band with the pages under group headings. On glass it
// is the same sheet as the rest of the window, told apart by one hairline
// down its right edge, which is all a sidebar on glass should be.
//
// Six pages, flat, no headings: a list long enough to need headings is a list
// nobody reads. Under them are the words the user has taught it, which is the
// one thing in this app that is theirs, and at the bottom the key, which is
// what a new user forgets and what a returning user opens the window for.

final class RailState: ObservableObject {
    @Published var counts: [Page: Int] = [:]
    @Published var taught: [Word] = []
}

struct Sidebar: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.windowWidth) private var windowWidth
    @StateObject private var st = RailState()

    var body: some View {
        let wide = windowWidth >= roomForRailLabels
        return content(wide)
    }

    private func content(_ wide: Bool) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                BrandMark(size: 25)
                if wide {
                    Text("Dictator").font(.display(15, .semibold)).foregroundColor(Theme.text)
                }
            }
            .padding(.horizontal, 8)
            .padding(.bottom, 20)

            VStack(spacing: 2) {
                ForEach(Page.main) {
                    SidebarItem(page: $0, count: wide ? st.counts[$0] : nil, labelled: wide)
                }
            }

            if wide, !st.taught.isEmpty {
                Text("Words you taught it")
                    .font(.system(size: 11)).foregroundColor(Theme.tertiary)
                    .padding(.horizontal, 12).padding(.top, 24).padding(.bottom, 8)
                VStack(spacing: 2) {
                    ForEach(st.taught.prefix(5)) { w in
                        Button { model.page = .words } label: {
                            HStack(spacing: 11) {
                                Initial(name: w.term)
                                Text(w.term).font(.system(size: 13))
                                    .foregroundColor(Theme.secondary).lineLimit(1)
                                Spacer(minLength: 0)
                            }
                            .padding(.horizontal, 12).frame(height: 32)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            Spacer(minLength: 24)

            VStack(alignment: .leading, spacing: 6) {
                Rectangle().fill(Theme.hairline).frame(height: 1).padding(.bottom, 5)
                HStack(spacing: 9) {
                    Text(Prefs.keyNames[model.key] ?? model.key)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(Theme.text)
                        .padding(.horizontal, 7).frame(height: 22)
                        .background(RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .fill(Color.white.opacity(0.12)))
                        .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.22), lineWidth: 1))
                    if wide {
                        Text("hold to talk").font(.system(size: 12))
                            .foregroundColor(Theme.secondary)
                    }
                }
                if wide {
                    Text("double tap for hands free")
                        .font(.system(size: 11)).foregroundColor(Theme.tertiary)
                    StatusLine().padding(.top, 2)
                }
            }
            .padding(.horizontal, 12)
        }
        .padding(.top, 50)   // under the traffic lights
        .padding(.bottom, 18)
        // Width first, then the inset. The other way round, a child a few
        // points wider than the rail made the padded view wider than the
        // frame, and the whole column slid left until the inset looked like
        // it had been forgotten.
        .frame(width: wide ? 192 : 42, alignment: .leading)
        .padding(.horizontal, 11)
        .frame(maxHeight: .infinity, alignment: .top)
        .clipped()
        .background(Theme.rail)
        .overlay(alignment: .trailing) { Rectangle().fill(Theme.hairline).frame(width: 1) }
        .onAppear(perform: load)
    }

    /// The three numbers beside the pages. One call, on open, because a
    /// sidebar that reloads while you look at it is a sidebar that flickers.
    private func load() {
        CLI.load({ (CLI.json(["stats"]), CLI.json(["words"]), CLI.json(["snippets"])) }) { s, w, sn in
            if let d = s as? [String: Any] {
                st.counts[.history] = (d["words"] as? NSNumber)?.intValue
            }
            st.taught = records(w, under: ["words", "terms"], nameKey: "term")
                .map { Word(term: str($0, "term", "word"),
                            heard: $0["heard"] as? [String] ?? [], pending: false,
                            count: ($0["count"] as? NSNumber)?.intValue ?? 0) }
                .filter { !$0.term.isEmpty }
                .sorted { $0.count > $1.count }
            st.counts[.words] = st.taught.count
            let snips = records(sn, under: ["snippets", "items"], nameKey: "name")
            st.counts[.snippets] = snips.isEmpty ? nil : snips.count
        }
    }
}

struct SidebarItem: View {
    @EnvironmentObject var model: AppModel
    var page: Page
    /// How many of the thing the page holds, shown small and right aligned.
    /// Nil for a page where a number means nothing.
    var count: Int? = nil
    /// False in a narrow window: the icon alone, with the name as its help.
    var labelled = true
    @StateObject private var hover = Hover()

    var body: some View {
        let on = model.page == page
        Button { model.page = page } label: {
            HStack(spacing: 12) {
                Image(systemName: page.symbol)
                    .font(.system(size: 13, weight: .regular))
                    .foregroundColor(on ? Theme.text : Theme.secondary)
                    .frame(width: 16)
                if labelled {
                    Text(page.rawValue)
                        .font(.system(size: 13.5, weight: on ? .medium : .regular))
                        .foregroundColor(on ? Theme.text : Theme.secondary)
                }
                Spacer(minLength: 0)
                if let c = count {
                    Text(c.formatted())
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(Theme.tertiary)
                }
            }
            .padding(.horizontal, labelled ? 12 : 7)
            .frame(height: 36)
            // Selection is a lighter sheet of the same glass with a hairline
            // round it, not a coloured pill: one accent in the app, and it
            // belongs to the microphone.
            .background(RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(on ? Theme.railSelected : (hover.on ? Theme.railHover : .clear)))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous)
                .strokeBorder(on ? Theme.hairline : .clear, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(labelled ? "" : page.rawValue)
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
        let page = VStack(alignment: .leading, spacing: Theme.s5) { content }
            .frame(maxWidth: 720, alignment: .leading)
            .padding(.horizontal, 30)
            .padding(.top, 44)
            .padding(.bottom, Theme.s6)
            .frame(maxWidth: .infinity, alignment: .topLeading)

        // A snapshot run draws the page without the scroll view.
        //
        // `bitmapImageRepForCachingDisplay` does not capture what is inside
        // an NSScrollView, so every page built on this came out blank and
        // the screenshots have quietly been of the sidebar for as long as
        // the tool has existed. The page itself is identical either way;
        // only the clipping is gone, which is what a screenshot wants
        // anyway (DICTATOR_HUB_SIZE exists to draw a long page whole).
        return Group {
            if snapshotRun {
                page
            } else {
                ScrollView { page }
                    .scrollContentBackground(.hidden)
            }
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
    @Published var taught: [Word] = []
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

    // Home answers three questions and stops: what did I just say, is it
    // working, and what has it learned. Everything that is a list to go
    // through lives in History, because a page that is both a dashboard and
    // an archive is neither.
    @Environment(\.windowWidth) private var windowWidth

    var body: some View {
        let beside = windowWidth >= roomForRecent
        return HStack(spacing: 0) {
            PageScroll {
                if let r = model.clash { RivalBanner(running: r) }
                greetingRow
                lastSaid
                cards
                learned
                // Narrow window: the same column, stacked under the page
                // rather than clipped off the side of it.
                if !beside { recent.padding(.top, Theme.s3) }
            }
            if beside {
                Rectangle().fill(Theme.hairline).frame(width: 1)
                // layoutPriority so the scroll view beside it cannot take
                // this column's width. A ScrollView asks for everything,
                // and without this the column was squeezed to about 225
                // points and clipped its own text off the window.
                recent.frame(width: 274).layoutPriority(1)
            }
        }
        .onAppear {
            if let q = model.takeSeed(.home) { st.query = q }
            load()
            model.checkRivals()
        }
    }

    private var recent: some View {
        RecentColumn(said: Array(st.said.prefix(5)),
                     listening: model.status.state == "ready" && !model.paused)
    }

    // -----------------------------------------------------------------------

    private var greetingRow: some View {
        HStack(alignment: .center, spacing: Theme.s5) {
            VStack(alignment: .leading, spacing: 7) {
                Text("\(greeting), \(firstName)")
                    .font(.display(24, .semibold)).foregroundColor(Theme.text)
                    .lineLimit(1).minimumScaleFactor(0.75).fixedSize(horizontal: false, vertical: true)
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 9) {
                        Chip(text: "nothing left this Mac", symbol: "lock.fill")
                        Text(st.words.map { "\($0.formatted()) dictations, all of them here" }
                             ?? "everything stays here")
                            .font(.system(size: 13)).foregroundColor(Theme.tertiary)
                            .lineLimit(1)
                    }
                    Chip(text: "nothing left this Mac", symbol: "lock.fill")
                }
            }
            Spacer(minLength: 0)
            SearchField(prompt: "Search what you said", text: $st.query)
                .frame(minWidth: 150, idealWidth: 244, maxWidth: 244)
                .onSubmit { model.seed[.history] = st.query; model.page = .history }
        }
    }

    /// The hero, and the one thing a reading app would put a book cover in:
    /// what this app makes is a sentence, so the sentence goes here, large
    /// enough to read from across the desk.
    private var lastSaid: some View {
        let l = model.last
        return VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                Circle().fill(Theme.live).frame(width: 7, height: 7)
                    .shadow(color: Theme.live.opacity(0.9), radius: 5)
                Text(l.map { "Last thing you said, \(ago($0.at))" } ?? "Nothing said yet")
                    .font(.system(size: 11.5)).foregroundColor(Theme.live)
                Spacer(minLength: 0)
                if let e = l.flatMap({ spokenIn(lang: "", engine: $0.engine) }) {
                    Chip(text: e, tone: e == "Hinglish" ? .moss : .sky)
                }
            }
            .padding(.bottom, 15)

            Text(highlighted(l?.text ?? "Hold the key and talk. What you say lands here."))
                .font(.system(size: 26, weight: .light))
                .foregroundColor(Theme.text)
                .lineSpacing(7)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 520, alignment: .leading)

            Rectangle().fill(Theme.hairline).frame(height: 1).padding(.top, 20)

            // One row if it fits, two if it does not. ViewThatFits rather
            // than a width to compare against: the number that matters is
            // how much room is left after the sidebar and the recent
            // column, not how wide the window is, and a guess at it is what
            // pushed this row to 780 points and shoved the recent column
            // off the right of a 1170 point window.
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 16) { facts(l); Spacer(minLength: 12); actions(l) }
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 16) { facts(l); Spacer(minLength: 0) }
                    HStack(spacing: 8) { actions(l); Spacer(minLength: 0) }
                }
            }
            .padding(.top, 14)
        }
        .padding(.horizontal, 26).padding(.vertical, 22)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous)
            .strokeBorder(Theme.hairline, lineWidth: 1))
    }

    @ViewBuilder
    private func facts(_ l: Last?) -> some View {
        if let a = l?.app, !a.isEmpty { fact("went to", a) }
        if let s = st.said.first?.secs, s > 0 { fact("held", String(format: "%.1fs", s)) }
        if let ms = l?.ms { fact("pasted", "\(waited(ms)) later") }
    }

    @ViewBuilder
    private func actions(_ l: Last?) -> some View {
        quiet("Undo the paste") { _ = CLI.act(["undo"]) }
        quiet("Copy") {
            if let s = l?.text {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(s, forType: .string)
            }
        }
        quiet("Fix a word") { model.page = .words }
    }

    private func fact(_ label: String, _ value: String) -> some View {
        HStack(spacing: 4) {
            Text(label).foregroundColor(Theme.tertiary)
            Text(value).foregroundColor(Theme.secondary).fontWeight(.medium)
        }
        .font(.system(size: 12))
        .fixedSize()
    }

    private func quiet(_ title: String, _ act: @escaping () -> Void) -> some View {
        Button(action: act) {
            Text(title).font(.system(size: 12, weight: .medium))
                .foregroundColor(Theme.secondary).fixedSize()
                .padding(.horizontal, 14).frame(height: 32)
                .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .strokeBorder(Theme.hairline, lineWidth: 1))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// Any word the user has taught it, shown teal where it appears. Not a
    /// decoration: it is the only place you see the teaching having worked.
    private func highlighted(_ s: String) -> AttributedString {
        var out = AttributedString(s)
        for w in st.taught where w.term.count > 2 {
            var from = out.startIndex
            while let r = out[from...].range(of: w.term, options: .caseInsensitive) {
                out[r].foregroundColor = Theme.live
                out[r].underlineStyle = .single
                from = r.upperBound
                if from >= out.endIndex { break }
            }
        }
        return out
    }

    // -----------------------------------------------------------------------

    /// One wide card and two square ones, 1.6 : 1 : 1.
    ///
    /// Measured and divided rather than left to the stack. `layoutPriority`
    /// is not a ratio: it gives that view everything it asks for and lets
    /// the others collapse, which is exactly what happened the first time.
    private var cards: some View {
        GeometryReader { geo in
            let gap: CGFloat = 12
            let unit = max(0, geo.size.width - gap * 2) / 3.6
            HStack(spacing: gap) {
                StatCard(label: "SAVED TODAY", symbol: "clock", tone: .sand,
                         value: st.todaySaved.map(duration) ?? "0 s",
                         caption: "against typing it at 40 a minute",
                         spark: spark)
                    .frame(width: unit * 1.6)
                StatCard(label: "SPOKEN", symbol: "waveform", tone: .moss,
                         value: st.todayWords.map { $0.formatted() } ?? "0",
                         caption: "words today, none of them typed", spark: nil)
                    .frame(width: unit)
                StatCard(label: "STREAK", symbol: "flame", tone: .sky,
                         value: st.streak.map { "\($0)" } ?? "0",
                         caption: "days in a row", spark: nil)
                    .frame(width: unit)
            }
        }
        .frame(height: 132)
    }

    /// Words per day over the last week, as a share of the busiest day.
    /// Drawn from the history already loaded rather than asked for again.
    private var spark: [Double] {
        let cal = Calendar.current
        var byDay: [Date: Int] = [:]
        for r in st.said {
            let d = cal.startOfDay(for: r.at)
            byDay[d, default: 0] += r.text.split(separator: " ").count
        }
        let days = (0..<7).reversed().map {
            cal.date(byAdding: .day, value: -$0, to: cal.startOfDay(for: Date()))!
        }
        let counts = days.map { Double(byDay[$0] ?? 0) }
        let top = counts.max() ?? 0
        return top > 0 ? counts.map { 0.18 + 0.82 * ($0 / top) } : counts.map { _ in 0.18 }
    }

    // -----------------------------------------------------------------------

    private var learned: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("It learned these from you")
                    .font(.display(14.5, .semibold)).foregroundColor(Theme.text)
                Spacer()
                Button { model.page = .words } label: {
                    Text(st.taught.isEmpty ? "Teach it one" : "All \(st.taught.count)")
                        .font(.system(size: 12)).foregroundColor(Theme.tertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.bottom, 2)

            ForEach(st.taught.filter { !$0.heard.isEmpty }.prefix(3)) { w in
                HStack(spacing: 14) {
                    Text(w.heard[0])
                        .foregroundColor(Theme.tertiary).strikethrough(true, color: Theme.hairline)
                    Text("\u{25B8}").font(.system(size: 9)).foregroundColor(Theme.tertiary)
                    Text(w.term).foregroundColor(Theme.text)
                    Spacer()
                    Text("\(w.count)\u{00D7}")
                        .font(.system(size: 11.5, design: .monospaced))
                        .foregroundColor(Theme.tertiary)
                }
                .font(.system(size: 13.5))
                .padding(.vertical, 9)
                .overlay(alignment: .top) { Rectangle().fill(Theme.hairline).frame(height: 1) }
            }
        }
    }

    private var greeting: String {
        let h = Calendar.current.component(.hour, from: Date())
        return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"
    }

    /// The Mac's own full name, first word only. No setting to get wrong and
    /// nothing asked for at first launch.
    private var firstName: String {
        NSFullUserName().split(separator: " ").first.map(String.init) ?? "there"
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
        CLI.load({ CLI.json(["words"]) }) { any in
            st.taught = records(any, under: ["words", "terms"], nameKey: "term")
                .map { Word(term: str($0, "term", "word"),
                            heard: $0["heard"] as? [String] ?? [], pending: false,
                            count: ($0["count"] as? NSNumber)?.intValue ?? 0) }
                .filter { !$0.term.isEmpty }
                .sorted { $0.count > $1.count }
        }
    }
}

/// Everything said, searchable.
///
/// This used to be the bottom half of Home. It is its own page because Home
/// answers "is it working" and this answers "where is that thing I said", and
/// a page that does both does neither well.
struct HistoryPage: View {
    @EnvironmentObject var model: AppModel
    @StateObject private var st = HomeState()

    var body: some View {
        PageScroll {
            HStack(alignment: .center, spacing: Theme.s5) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("What you said")
                        .font(.display(24, .semibold)).foregroundColor(Theme.text)
                    Text(st.words.map { "\($0.formatted()) dictations, searchable by the words in them" }
                         ?? "searchable by the words in them")
                        .font(.system(size: 13)).foregroundColor(Theme.tertiary)
                }
                Spacer(minLength: 0)
                SearchField(prompt: "Search what you said", text: $st.query).frame(width: 258)
            }

            if !st.loaded {
                Loading()
            } else if days.isEmpty {
                EmptyState(art: .search, title: st.query.isEmpty ? "Nothing yet" : "No matches",
                           line: st.query.isEmpty
                               ? "Hold \(Prefs.keyNames[model.key] ?? model.key) and talk in any app."
                               : "Nothing you said recently contains \u{201C}\(st.query)\u{201D}.")
            } else {
                ForEach(days, id: \.0) { day, rows in
                    VStack(alignment: .leading, spacing: Theme.s2) {
                        SectionLabel(day)
                        VStack(spacing: 0) {
                            ForEach(rows) { r in
                                HistoryRow(said: r, ms: nil)
                                    .overlay(alignment: .top) {
                                        if r.id != rows.first?.id {
                                            Rectangle().fill(Theme.hairline).frame(height: 1)
                                        }
                                    }
                            }
                        }
                        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .strokeBorder(Theme.hairline, lineWidth: 1))
                    }
                }
            }
        }
        .onAppear {
            if let q = model.takeSeed(.history) { st.query = q }
            load()
        }
    }

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
        CLI.load({ (CLI.json(["stats"]), CLI.json(["history", "400"])) }) { stats, hist in
            if let s = stats as? [String: Any] {
                st.words = (s["words"] as? NSNumber)?.intValue
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
