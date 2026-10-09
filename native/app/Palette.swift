// ⌘K: one field to jump to any page, find anything you said, wrote or taught
// it, and run the few actions worth a shortcut.
//
// Like the pages, it only reads what the CLI prints (`history`, `words`,
// `format`) and runs CLI commands; the notes come from the shared NotesStore.
// The field is an NSTextField rather than a SwiftUI TextField so it can take
// the cursor when the palette opens and hand the arrow keys, Return and
// Escape to the list, without @FocusState (see the top of Hub.swift for why
// macros are out).

import AppKit
import SwiftUI

struct PaletteItem: Identifiable {
    var id: String
    var group: String
    var symbol: String
    var title: String
    var detail: String = ""
    var run: () -> Void
}

final class PaletteState: ObservableObject {
    @Published var selected = 0
    @Published var said: [Said] = []
    @Published var words: [String] = []
    @Published var rules: [Rule] = []
    var loaded = false
}

struct CommandPalette: View {
    @EnvironmentObject var model: AppModel
    @StateObject private var st = PaletteState()
    @ObservedObject private var notes = NotesStore.shared

    var body: some View {
        let items = results
        ZStack(alignment: .top) {
            Color.black.opacity(0.28)
                .contentShape(Rectangle())
                .onTapGesture { close() }
            VStack(spacing: 0) {
                HStack(spacing: Theme.s3) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(Theme.accent)
                    PaletteField(text: $model.paletteQuery,
                                 placeholder: "Jump to a page, search, or run a command",
                                 onMove: { move($0, items.count) },
                                 onSubmit: { runSelected(items) },
                                 onCancel: close)
                        .frame(height: 24)
                    Text("esc").font(.system(size: 11, weight: .semibold, design: .rounded))
                        .foregroundColor(Theme.tertiary)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(RoundedRectangle(cornerRadius: 5).fill(Theme.raised))
                }
                .padding(.horizontal, Theme.s4)
                .frame(height: 54)
                Rectangle().fill(Theme.hairline).frame(height: 1)
                if items.isEmpty {
                    EmptyState(art: .search, title: "Nothing matches",
                               line: "Try a page name, a word you said, or “note”.")
                        .padding(.vertical, -Theme.s3)
                } else {
                    ScrollViewReader { proxy in
                        ScrollView {
                            VStack(alignment: .leading, spacing: 1) {
                                ForEach(Array(items.enumerated()), id: \.element.id) { i, item in
                                    if i == 0 || items[i - 1].group != item.group {
                                        Text(item.group).font(.system(size: 11.5, weight: .semibold))
                                            .foregroundColor(Theme.tertiary)
                                            .padding(.horizontal, Theme.s3)
                                            .padding(.top, i == 0 ? 6 : Theme.s3)
                                            .padding(.bottom, 3)
                                    }
                                    row(item, on: i == clamp(items.count))
                                        .id(item.id)
                                        .onTapGesture { st.selected = i; runSelected(items) }
                                }
                            }
                            .padding(Theme.s2)
                        }
                        .frame(maxHeight: 380)
                        .onChange(of: st.selected) {
                            let i = clamp(items.count)
                            if items.indices.contains(i) { proxy.scrollTo(items[i].id) }
                        }
                    }
                }
                Rectangle().fill(Theme.hairline).frame(height: 1)
                HStack(spacing: Theme.s4) {
                    hint("↑↓", "move")
                    hint("↩", "run")
                    hint("esc", "close")
                    Spacer()
                    HStack(spacing: 5) {
                        BrandMark(size: 14)
                        Text("Searches this Mac only").font(.system(size: 11))
                            .foregroundColor(Theme.tertiary)
                    }
                }
                .padding(.horizontal, Theme.s4)
                .frame(height: 34)
            }
            .frame(width: 600)
            .fixedSize(horizontal: false, vertical: true)
            .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Theme.card)
                .shadow(color: .black.opacity(0.28), radius: 30, x: 0, y: 14))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Theme.border, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .padding(.top, 84)
        }
        .onAppear(perform: load)
        .onChange(of: model.paletteQuery) { st.selected = 0 }
    }

    // -----------------------------------------------------------------------

    private func row(_ item: PaletteItem, on: Bool) -> some View {
        HStack(spacing: Theme.s3) {
            Image(systemName: item.symbol)
                .font(.system(size: 12.5, weight: .medium))
                .foregroundColor(on ? Theme.accent : Theme.secondary)
                .frame(width: 26, height: 26)
                .background(RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(on ? Theme.accentSoft : Theme.raised))
            Text(item.title).font(.system(size: 13.5, weight: on ? .semibold : .regular))
                .foregroundColor(Theme.text).lineLimit(1)
            Spacer(minLength: Theme.s2)
            if !item.detail.isEmpty {
                Text(item.detail).font(.system(size: 12)).foregroundColor(Theme.tertiary)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, Theme.s2)
        .frame(height: 38)
        .background(RoundedRectangle(cornerRadius: 9, style: .continuous)
            .fill(on ? Theme.accentSoft.opacity(0.7) : .clear))
        .overlay(alignment: .leading) {
            if on {
                Capsule().fill(Theme.live).frame(width: 3, height: 18).offset(x: -1)
            }
        }
        .contentShape(Rectangle())
    }

    private func hint(_ key: String, _ what: String) -> some View {
        HStack(spacing: 4) {
            Text(key).font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundColor(Theme.secondary)
            Text(what).font(.system(size: 11)).foregroundColor(Theme.tertiary)
        }
    }

    private func clamp(_ n: Int) -> Int { n == 0 ? 0 : min(max(st.selected, 0), n - 1) }

    private func move(_ by: Int, _ n: Int) {
        guard n > 0 else { return }
        st.selected = (clamp(n) + by + n) % n
    }

    private func close() {
        model.paletteOpen = false
        model.paletteQuery = ""
    }

    private func runSelected(_ items: [PaletteItem]) {
        guard !items.isEmpty else { return }
        let item = items[clamp(items.count)]
        close()
        DispatchQueue.main.async { item.run() }
    }

    // -----------------------------------------------------------------------
    // What there is to find.

    private var ui: UI? { NSApp.delegate as? UI }

    private var commands: [PaletteItem] {
        var out: [PaletteItem] = []
        let go: (Page, String) -> PaletteItem = { p, detail in
            PaletteItem(id: "go-\(p.rawValue)", group: "Go to", symbol: p.symbol,
                        title: p.rawValue, detail: detail) { model.page = p }
        }
        out += [go(.home, "Today and history"), go(.words, "Names it spells your way"),
                go(.snippets, "Short phrases, long text"), go(.style, "How text is tidied"),
                go(.scratchpad, "Your notes"), go(.meetings, "Notetaker"),
                go(.review, "What it may have got wrong"), go(.settings, "Key, language, look"),
                go(.help, "How it works")]
        out += [
            PaletteItem(id: "act-note", group: "Actions", symbol: "square.and.pencil",
                        title: "New note", detail: "⌥S") { ui?.showScratchpad(nil) },
            PaletteItem(id: "act-handsfree", group: "Actions", symbol: "waveform",
                        title: "Dictate hands free into a new note",
                        detail: "Press your key to finish") {
                ui?.showScratchpad(nil)
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                    CLI.load({ CLI.act(["hands-free", "toggle"]) }) { _ in }
                }
            },
            PaletteItem(id: "act-notetaker", group: "Actions", symbol: "record.circle",
                        title: "Start or stop the Notetaker", detail: "⌥M") {
                Notetaker.shared.toggle()
            },
            PaletteItem(id: "act-pause", group: "Actions",
                        symbol: model.paused ? "play.circle" : "pause.circle",
                        title: model.paused ? "Resume dictation" : "Pause dictation") {
                ui?.togglePause()
            },
            PaletteItem(id: "act-copylast", group: "Actions", symbol: "doc.on.doc",
                        title: "Copy the last thing you said",
                        detail: model.last.map { String($0.text.prefix(40)) } ?? "") {
                if let t = model.last?.text { copyToPasteboard(t) }
            },
            PaletteItem(id: "act-updates", group: "Actions", symbol: "arrow.down.circle",
                        title: "Check for updates", detail: "Version \(Updater.shared.version)") {
                Updater.shared.checkForUpdates()
            },
        ]
        for a in Appearance.allCases where a != model.appearance {
            out.append(PaletteItem(id: "look-\(a.rawValue)", group: "Actions",
                                   symbol: a == .dark ? "moon" : a == .light ? "sun.max" : "circle.lefthalf.filled",
                                   title: "Appearance: \(a.title)") { model.setAppearance(a) })
        }
        for r in st.rules {
            let name = StylePage.titles[r.name]?.0 ?? r.name
            out.append(PaletteItem(id: "rule-\(r.name)", group: "Style",
                                   symbol: r.on ? "switch.2" : "switch.2",
                                   title: "Turn \(r.on ? "off" : "on"): \(name)",
                                   detail: StylePage.titles[r.name]?.1 ?? "") {
                let arg = r.name == "enabled" ? [r.on ? "off" : "on"] : [r.name, r.on ? "off" : "on"]
                if let i = st.rules.firstIndex(where: { $0.name == r.name }) { st.rules[i].on.toggle() }
                CLI.load({ CLI.act(["format"] + arg) }) { _ in }
            })
        }
        return out
    }

    /// Commands that match, then what you said, wrote and taught it.
    private var results: [PaletteItem] {
        let q = model.paletteQuery.lowercased().trimmingCharacters(in: .whitespaces)
        if q.isEmpty {
            return commands.filter { $0.group != "Style" }
        }
        let terms = q.split(separator: " ").map(String.init)
        let hit: (String) -> Bool = { s in
            let l = s.lowercased()
            return terms.allSatisfy { l.contains($0) }
        }
        var out = commands.filter { hit($0.title) || hit($0.group + " " + $0.title) }
        // Titles that start with the query first.
        out.sort { a, b in
            a.title.lowercased().hasPrefix(q) && !b.title.lowercased().hasPrefix(q)
        }
        guard q.count >= 2 else { return out }
        let said = st.said.filter { hit($0.text) }.prefix(5).map { s in
            PaletteItem(id: "said-\(s.id)", group: "You said", symbol: "text.quote",
                        title: s.text, detail: "Copy") {
                copyToPasteboard(s.text)
            }
        }
        let wrote = notes.notes.filter { hit($0.text) }.prefix(4).map { n in
            PaletteItem(id: "note-\(n.id)", group: "Notes", symbol: "note.text",
                        title: n.title, detail: noteDate(n.updated)) {
                ui?.showScratchpad(n.id)
            }
        }
        let taught = st.words.filter { hit($0) }.prefix(3).map { w in
            PaletteItem(id: "word-\(w)", group: "Words", symbol: "character.book.closed",
                        title: w, detail: "Show in Words") {
                model.seed[.words] = w
                model.page = .words
            }
        }
        return out + said + wrote + taught
    }

    private func load() {
        guard !st.loaded else { return }
        st.loaded = true
        if !notes.loaded { notes.load() }
        CLI.load({ (CLI.json(["history", "200"]), CLI.json(["words"]), CLI.text(["format"])) }) { h, w, f in
            st.said = loadSaid(h)
            st.words = records(w, under: ["words", "terms"], nameKey: "term")
                .map { str($0, "term", "word") }.filter { !$0.isEmpty }
            st.rules = f.split(separator: "\n").compactMap { line in
                let p = line.split(separator: " ")
                guard p.count == 2, StylePage.titles[String(p[0])] != nil,
                      p[1] == "on" || p[1] == "off" else { return nil }
                return Rule(name: String(p[0]), on: p[1] == "on")
            }
        }
    }
}

/// The palette's text field: takes the cursor when it appears, and passes
/// the arrow keys, Return and Escape up instead of acting on them.
struct PaletteField: NSViewRepresentable {
    @Binding var text: String
    var placeholder: String
    var onMove: (Int) -> Void
    var onSubmit: () -> Void
    var onCancel: () -> Void

    final class Coordinator: NSObject, NSTextFieldDelegate {
        var parent: PaletteField
        init(_ p: PaletteField) { parent = p }

        func controlTextDidChange(_ n: Notification) {
            if let f = n.object as? NSTextField { parent.text = f.stringValue }
        }

        func control(_ control: NSControl, textView: NSTextView,
                     doCommandBy sel: Selector) -> Bool {
            switch sel {
            case #selector(NSResponder.moveUp(_:)): parent.onMove(-1); return true
            case #selector(NSResponder.moveDown(_:)): parent.onMove(1); return true
            case #selector(NSResponder.insertNewline(_:)): parent.onSubmit(); return true
            case #selector(NSResponder.cancelOperation(_:)): parent.onCancel(); return true
            default: return false
            }
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSTextField {
        let f = NSTextField()
        f.isBordered = false
        f.drawsBackground = false
        f.focusRingType = .none
        f.font = .systemFont(ofSize: 17)
        f.textColor = Palette.text
        f.placeholderAttributedString = NSAttributedString(string: placeholder, attributes: [
            .font: NSFont.systemFont(ofSize: 17), .foregroundColor: Palette.tertiary])
        f.delegate = context.coordinator
        f.stringValue = text
        f.cell?.lineBreakMode = .byTruncatingTail
        DispatchQueue.main.async {
            f.window?.makeFirstResponder(f)
            f.currentEditor()?.selectedRange = NSRange(location: (f.stringValue as NSString).length,
                                                       length: 0)
        }
        return f
    }

    func updateNSView(_ f: NSTextField, context: Context) {
        context.coordinator.parent = self
        if f.stringValue != text { f.stringValue = text }
    }
}
