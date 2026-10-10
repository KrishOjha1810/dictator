// The Scratchpad: a window with a big text area for notes you dictate into,
// and a Hub page listing them.
//
// The notes are Markdown files in STATE/notes, one per note; dictator_core/notes.py
// decides the format and `dictator notes` is the only thing that reads or
// writes them, as everywhere else in the app (see Backend.swift). Typing is
// saved a moment after it stops, when another note is picked, and when the
// window closes. Nothing leaves the Mac.

import AppKit
import SwiftUI

struct Note: Identifiable, Equatable {
    var id: String
    var title: String
    var text: String
    var updated: Double
}

/// Every note, and the one open in the window. One instance, shared by the
/// window and the Hub page, so an edit in one shows in the other.
final class NotesStore: ObservableObject {
    static let shared = NotesStore()

    @Published var notes: [Note] = []
    @Published var loaded = false
    /// The note in the window, and its text as typed (ahead of the file).
    @Published var current: String = ""
    @Published var text: String = "" { didSet { if text != oldValue { edited() } } }
    @Published var query = ""
    /// Bumped to put the cursor in the text area.
    @Published var focus = 0
    private var dirty = false
    private var timer: Timer?

    func load(then: (() -> Void)? = nil) {
        CLI.load({ CLI.json(["notes"]) }) { any in
            let rows = records(any, under: ["notes"], nameKey: "id")
            let fresh = rows.map {
                Note(id: str($0, "id"), title: str($0, "title"), text: str($0, "text"),
                     updated: ($0["updated"] as? NSNumber)?.doubleValue ?? 0)
            }.filter { !$0.id.isEmpty }
            // Fake mode keeps what was typed this session in memory.
            if !(fake && self.loaded) { self.notes = fresh }
            self.loaded = true
            then?()
        }
    }

    var shown: [Note] {
        let q = query.lowercased().trimmingCharacters(in: .whitespaces)
        return q.isEmpty ? notes : notes.filter { $0.text.lowercased().contains(q) }
    }

    /// A fresh id in the format notes.py uses, made here so a new note costs
    /// no round trip: the first save creates the file.
    func newID() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd-HHmmss"
        f.locale = Locale(identifier: "en_US_POSIX")
        let base = f.string(from: Date())
        var id = base, n = 1
        while notes.contains(where: { $0.id == id }) || id == current { n += 1; id = "\(base)-\(n)" }
        return id
    }

    /// Open a note in the window, or a new empty one. An empty note that is
    /// already open is reused rather than stacked up.
    func open(_ id: String?) {
        flush()
        if let id = id, let n = notes.first(where: { $0.id == id }) {
            current = n.id
            setText(n.text)
        } else if current.isEmpty || !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            current = newID()
            setText("")
        }
        focus += 1
    }

    private func setText(_ t: String) {
        text = t
        dirty = false
        timer?.invalidate()
    }

    private func edited() {
        dirty = true
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.8, repeats: false) { [weak self] _ in
            self?.flush()
        }
    }

    /// Save what is typed, if anything changed. Empty text deletes the file.
    func flush() {
        timer?.invalidate()
        guard dirty, !current.isEmpty else { return }
        dirty = false
        let id = current, t = text
        upsert(id, t)
        if fake { return }
        CLI.load({ CLI.act(["notes", "save", id], input: t) }) { _ in }
    }

    private func upsert(_ id: String, _ t: String) {
        let empty = t.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        notes.removeAll { $0.id == id }
        if !empty {
            notes.insert(Note(id: id, title: Self.title(t), text: t,
                              updated: Date().timeIntervalSince1970), at: 0)
        }
    }

    func delete(_ id: String) {
        notes.removeAll { $0.id == id }
        if id == current { current = ""; setText("") }
        if fake { return }
        CLI.load({ CLI.act(["notes", "delete", id]) }) { _ in }
    }

    /// The same rule as notes.title_of: the first line with words in it.
    static func title(_ t: String) -> String {
        for line in t.split(separator: "\n", omittingEmptySubsequences: true) {
            let s = line.trimmingCharacters(in: .whitespaces)
                .trimmingCharacters(in: CharacterSet(charactersIn: "#")).trimmingCharacters(in: .whitespaces)
            if !s.isEmpty { return String(s.prefix(80)) }
        }
        return "Empty note"
    }
}

func noteDate(_ t: Double) -> String {
    let d = Date(timeIntervalSince1970: t)
    let cal = Calendar.current
    if cal.isDateInToday(d) { return d.formatted(date: .omitted, time: .shortened) }
    if cal.isDateInYesterday(d) { return "Yesterday" }
    return d.formatted(.dateTime.day().month(.abbreviated))
}

// ---------------------------------------------------------------------------
// The window.

struct ScratchpadView: View {
    @ObservedObject var store = NotesStore.shared

    var body: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: Theme.s3) {
                HStack(spacing: Theme.s2) {
                    BrandMark(size: 20)
                    Text("Scratchpad").font(.display(15, .bold))
                        .foregroundColor(Theme.text)
                    Spacer()
                    Button { store.open(nil) } label: { Image(systemName: "square.and.pencil") }
                        .buttonStyle(IconButton())
                        .help("New note")
                }
                SearchField(prompt: "Search notes", text: $store.query)
                ScrollView {
                    VStack(spacing: 2) {
                        ForEach(store.shown) { n in NoteListRow(note: n) }
                        if store.loaded && store.shown.isEmpty {
                            Text(store.query.isEmpty ? "No notes yet." : "No matches.")
                                .font(.caption12).foregroundColor(Theme.tertiary)
                                .padding(.top, Theme.s3)
                        }
                    }
                }
                Spacer(minLength: 0)
                Label("Saved on this Mac only", systemImage: "lock.fill")
                    .font(.system(size: 11, weight: .medium)).foregroundColor(Theme.live)
            }
            .padding(.horizontal, Theme.s3)
            .padding(.top, 44)
            .padding(.bottom, Theme.s3)
            .frame(width: 240)
            .frame(maxHeight: .infinity)
            .background(Theme.sidebar)
            Rectangle().fill(Theme.border).frame(width: 1)
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text(headline).font(.system(size: 12)).foregroundColor(Theme.tertiary)
                    Spacer()
                    Button {
                        copyToPasteboard(store.text)
                    } label: { Image(systemName: "doc.on.doc") }
                        .buttonStyle(IconButton()).help("Copy the note")
                        .disabled(store.text.isEmpty)
                }
                .padding(.horizontal, Theme.s5)
                .padding(.top, 36)
                NoteEditor(text: $store.text, focus: store.focus,
                           placeholder: "Start typing, or hold your key and talk.")
                    .padding(.horizontal, Theme.s4)
                    .padding(.bottom, Theme.s4)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.card)
        }
        .frame(minWidth: 640, minHeight: 420)
        .ignoresSafeArea()
        .onAppear { store.load() }
    }

    private var headline: String {
        let words = store.text.split(whereSeparator: { $0.isWhitespace || $0.isNewline }).count
        return words == 0 ? "New note" : "\(words) word\(words == 1 ? "" : "s"), saved on this Mac"
    }
}

struct NoteListRow: View {
    @ObservedObject var store = NotesStore.shared
    var note: Note
    @StateObject private var hover = Hover()

    var body: some View {
        let on = store.current == note.id
        Button { store.open(note.id) } label: {
            VStack(alignment: .leading, spacing: 2) {
                Text(note.title).font(.system(size: 13, weight: on ? .semibold : .medium))
                    .foregroundColor(Theme.text).lineLimit(1)
                HStack(spacing: 6) {
                    Text(noteDate(note.updated)).foregroundColor(Theme.tertiary)
                    Text(preview).foregroundColor(Theme.secondary).lineLimit(1)
                }
                .font(.system(size: 11))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(on ? Theme.card : (hover.on ? Theme.border.opacity(0.5) : .clear)))
            .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous)
                .strokeBorder(on ? Theme.border : .clear, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover.on = $0 && !snapshotRun }
    }

    private var preview: String {
        let lines = note.text.split(separator: "\n").dropFirst()
        return lines.first.map { String($0) } ?? ""
    }
}

/// A plain NSTextView, because the cursor has to be put in it when the window
/// opens (so dictation lands there) and SwiftUI's TextEditor offers no way to
/// do that on the macOS this builds for without @FocusState, a macro.
struct NoteEditor: NSViewRepresentable {
    @Binding var text: String
    var focus: Int
    var placeholder: String

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: NoteEditor
        var focused = -1
        init(_ p: NoteEditor) { parent = p }
        func textDidChange(_ n: Notification) {
            guard let tv = n.object as? NSTextView else { return }
            parent.text = tv.string
            (tv as? PlaceholderTextView)?.needsDisplay = true
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false
        scroll.borderType = .noBorder
        let tv = PlaceholderTextView()
        tv.placeholder = placeholder
        tv.delegate = context.coordinator
        tv.isRichText = false
        tv.allowsUndo = true
        tv.font = .systemFont(ofSize: 15)
        tv.textColor = Palette.text
        // The icon's teal cursor, where the next words will land.
        tv.insertionPointColor = Palette.live
        tv.drawsBackground = false
        tv.textContainerInset = NSSize(width: 6, height: 12)
        tv.isVerticallyResizable = true
        tv.autoresizingMask = [.width]
        tv.textContainer?.widthTracksTextView = true
        tv.isAutomaticQuoteSubstitutionEnabled = false
        tv.string = text
        scroll.documentView = tv
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        context.coordinator.parent = self
        guard let tv = scroll.documentView as? NSTextView else { return }
        if tv.string != text {
            tv.string = text
            tv.setSelectedRange(NSRange(location: (text as NSString).length, length: 0))
        }
        if context.coordinator.focused != focus {
            context.coordinator.focused = focus
            DispatchQueue.main.async {
                tv.window?.makeFirstResponder(tv)
                tv.setSelectedRange(NSRange(location: (tv.string as NSString).length, length: 0))
            }
        }
    }
}

final class PlaceholderTextView: NSTextView {
    var placeholder = ""
    override func draw(_ r: NSRect) {
        super.draw(r)
        guard string.isEmpty, !placeholder.isEmpty else { return }
        NSAttributedString(string: placeholder, attributes: [
            .font: NSFont.systemFont(ofSize: 15),
            .foregroundColor: Palette.tertiary])
            .draw(at: NSPoint(x: textContainerInset.width + 5, y: textContainerInset.height))
    }
}

// ---------------------------------------------------------------------------
// The Hub page.

struct ScratchpadPage: View {
    @ObservedObject var store = NotesStore.shared

    var body: some View {
        PageScroll {
            PageHeader("Scratchpad", "Notes you keep on this Mac. Open the window with "
                       + "⌥S or from the pill, and dictate straight into it.") {
                SearchField(prompt: "Search notes", text: $store.query).frame(width: 220)
            }
            HStack {
                Button("New note") { (NSApp.delegate as? UI)?.showScratchpad(nil) }
                    .buttonStyle(PrimaryButton())
                Spacer()
            }
            if !store.loaded {
                Loading()
            } else if store.notes.isEmpty {
                EmptyState(art: .lines(0), title: "No notes yet",
                           line: "Press ⌥S, or the pencil on the pill, and talk. "
                               + "What you say lands in the note.")
                    .card()
            } else if store.shown.isEmpty {
                EmptyState(art: .search, title: "No matches",
                           line: "No note contains “\(store.query)”.").card()
            } else {
                RowsCard(store.shown) { n in NotePageRow(note: n) }
            }
        }
        .onAppear { store.load() }
    }
}

struct NotePageRow: View {
    var note: Note
    @StateObject private var st = RowState()

    var body: some View {
        HStack(alignment: .top, spacing: Theme.s4) {
            Text(noteDate(note.updated))
                .font(.system(size: 12).monospacedDigit())
                .foregroundColor(Theme.tertiary)
                .frame(width: 64, alignment: .leading)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 4) {
                Text(note.title).font(.system(size: 14, weight: .medium))
                    .foregroundColor(Theme.text).lineLimit(1)
                Text(body2).font(.system(size: 13)).foregroundColor(Theme.secondary)
                    .lineLimit(2)
            }
            Spacer(minLength: Theme.s2)
            HStack(spacing: 2) {
                Button { (NSApp.delegate as? UI)?.showScratchpad(note.id) } label: {
                    Image(systemName: "arrow.up.forward.square")
                }
                .buttonStyle(IconButton()).help("Open")
                Button {
                    copyToPasteboard(note.text)
                    st.copied = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) { st.copied = false }
                } label: {
                    Image(systemName: st.copied ? "checkmark" : "doc.on.doc")
                        .foregroundColor(st.copied ? Theme.good : Theme.secondary)
                }
                .buttonStyle(IconButton()).help("Copy")
                Button { NotesStore.shared.delete(note.id) } label: { Image(systemName: "trash") }
                    .buttonStyle(IconButton()).help("Delete")
            }
            .opacity(st.hover || st.copied ? 1 : 0.35)
        }
        .padding(.horizontal, Theme.s4)
        .padding(.vertical, Theme.s3)
        .contentShape(Rectangle())
        .onHover { st.hover = $0 && !snapshotRun }
        .onTapGesture(count: 2) { (NSApp.delegate as? UI)?.showScratchpad(note.id) }
    }

    private var body2: String {
        note.text.split(separator: "\n").dropFirst().joined(separator: " ")
    }
}
