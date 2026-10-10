// The look, in one place. Every colour, size and the few shared pieces of
// chrome (cards, buttons, page headers, the brand mark) the windows are built
// from.
//
// The identity comes from the app icon (tools/make_icon.swift): a white
// microphone whose grille is lines of text, on an indigo to violet to teal
// gradient, with a glowing teal cursor. Voice becomes text. So:
//
//   - Indigo ink and violet are the brand. Violet is the one accent for
//     controls, selection and links.
//   - Teal means live: the cursor, the status dot, "listening", time saved.
//     It is used sparingly, the way the icon uses it once.
//   - The full gradient is kept for brand moments only: the mark, the Home
//     hero, the onboarding welcome. Never as a wash behind ordinary content.
//   - Large headings are SF Pro Rounded. Every stroke in the icon has a round
//     cap, and the rounded face carries that into the type; it also keeps the
//     app well away from the serif display other dictation apps use. Body
//     text stays SF Pro, which is what a Mac reads best at 13 and 14 points.
//
// Every colour has a light and a dark value, resolved by the appearance of
// the view drawing it (NSColor(name:dynamicProvider:)), so Settings >
// Appearance switches the whole app at once with NSApp.appearance. The dark
// palette is designed, not inverted: a deep indigo ink background, surfaces
// that get lighter as they rise, borders as low-alpha white, and a lighter
// violet so the accent keeps its contrast. Body text is at least 4.5:1 on
// its background in both.
//
// THE WINDOWS ARE GLASS. The surfaces below are translucent and the blur
// comes from an NSVisualEffectView behind the whole window (MenuBar.show).
// `Glass` holds the two numbers that decide how it looks, and both were
// arrived at the hard way; the reasoning is in docs/ui/glass.html.

import AppKit
import SwiftUI

/// The glass, in two numbers.
enum Glass {
    /// Off puts the solid surfaces back, for anyone who finds a translucent
    /// window unreadable over their own desktop. It is one switch because a
    /// half-translucent app looks like a bug rather than a setting.
    static var on: Bool {
        if let e = env["DICTATOR_GLASS"] { return e != "0" }
        return (Prefs.store.object(forKey: "glass") as? Bool) ?? true
    }

    /// How much white sits over the blur. Six percent.
    ///
    /// Everything inside the window is drawn with hairlines rather than
    /// fills, because three sheets of ten percent is thirty percent and the
    /// window stops being see-through. If a surface needs a fill it gets
    /// this one, not a second one on top of it.
    static let tint: CGFloat = 0.06

    /// How far the scene behind the panels is softened. Fourteen points.
    ///
    /// Small on purpose, and this is the thing that took longest to learn: a
    /// heavy blur dissolves the scene into a smooth wash, a smooth wash reads
    /// as paint, and so every instinct to raise the blur and look more
    /// frosted makes the window look more solid. At fourteen the ridge behind
    /// a panel is still recognisable, which is the only thing that proves
    /// glass is glass.
    static let blur: CGFloat = 14

    /// The window carries its own sky (Backdrop.swift) rather than blurring
    /// the user's desktop.
    ///
    /// Blurring the desktop is how a Mac app normally does this, and it was
    /// the first version. It is wrong here: half the look is the soft ridge
    /// showing through the panels, and behind somebody with a white wallpaper
    /// there is no ridge. The design would then fall apart differently for
    /// every person, which is not something that can be designed for or
    /// tested. Ours looks the same on every Mac.
    static let ownBackdrop = true

    /// White at this alpha, or `clear` when glass is off and the solid
    /// surface underneath should show instead.
    static func white(_ a: CGFloat) -> NSColor {
        on ? NSColor.white.withAlphaComponent(a) : .clear
    }
}

/// A colour with a light and a dark value.
func dynamic(_ light: NSColor, _ dark: NSColor) -> NSColor {
    NSColor(name: nil) { a in
        a.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua ? dark : light
    }
}

/// sRGB from 0xRRGGBB.
func hex(_ v: UInt32, _ alpha: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255,
            blue: CGFloat(v & 0xFF) / 255, alpha: alpha)
}

enum Palette {
    // Surfaces, from the bottom up.
    //
    // With glass on these are translucent and the desktop shows through all
    // of them. The window itself carries the only fill; a panel inside it is
    // drawn with `border`, not with `card`, so the layers do not stack up
    // into something opaque. With glass off they fall back to the solid
    // values this app shipped with.
    static let background: NSColor =
        Glass.on ? .clear : dynamic(hex(0xF5F4FA), hex(0x121124))
    static let card: NSColor =
        Glass.on ? Glass.white(0.07) : dynamic(hex(0xFFFFFF), hex(0x1B1A31))
    static let raised: NSColor =
        Glass.on ? Glass.white(0.12) : dynamic(hex(0xF0EFF7), hex(0x25233F))
    static let sunken: NSColor =
        Glass.on ? NSColor.black.withAlphaComponent(0.10) : dynamic(hex(0xEEEDF5), hex(0x0E0D1D))
    static let border: NSColor =
        Glass.on ? Glass.white(0.13) : dynamic(hex(0xE2E0EE), NSColor.white.withAlphaComponent(0.10))
    static let hairline: NSColor =
        Glass.on ? Glass.white(0.09) : dynamic(hex(0xECEBF4), NSColor.white.withAlphaComponent(0.06))

    // The rail. Solid ink in the old look; with glass it is the same sheet
    // as the window, told apart by one hairline down its right edge, which
    // is all a sidebar on glass should be.
    static let rail: NSColor =
        Glass.on ? .clear : dynamic(hex(0x1C1A45), hex(0x0B0A18))
    static let railText = dynamic(hex(0xECEAFB), hex(0xE6E4F4))
    static let railSecondary = dynamic(hex(0xA9A5D4), hex(0x9591B4))
    static let railHover = NSColor.white.withAlphaComponent(0.09)
    static let railSelected = NSColor.white.withAlphaComponent(0.17)

    // Text. Contrast on `background`: text 15:1 / 15:1, secondary 6.4:1 /
    // 7.6:1, tertiary 4.6:1 / 4.7:1.
    //
    // On glass there is no known background to measure against, so these go
    // up rather than down: pure white for body, and the two quiet tints
    // lifted enough to survive a pale desktop behind them. Type that is
    // itself transparent is the fastest way to a window nobody can read at
    // noon, so none of these is given an alpha.
    static let text: NSColor =
        Glass.on ? .white : dynamic(hex(0x1A1838), hex(0xECEAF6))
    static let secondary: NSColor =
        Glass.on ? hex(0xD8D4E4) : dynamic(hex(0x57536F), hex(0xACA8C6))
    static let tertiary: NSColor =
        Glass.on ? hex(0xADA9BE) : dynamic(hex(0x726E8C), hex(0x8682A3))

    // Violet: controls, selection, links. The lighter dark value keeps 7:1
    // on the ink background; the fill behind white button text is its own
    // colour, because a fill wants to be darker than a text colour.
    static let accent = dynamic(hex(0x5631C9), hex(0xB3A2FF))
    static let accentFill = dynamic(hex(0x5631C9), hex(0x6E4FF0))
    static let accentSoft = dynamic(hex(0x5631C9, 0.09), hex(0xB3A2FF, 0.14))

    // Teal: live.
    static let live = dynamic(hex(0x0A8580), hex(0x3FE0CF))
    static let liveSoft = dynamic(hex(0x0A8580, 0.10), hex(0x3FE0CF, 0.14))

    static let good = dynamic(hex(0x1E8A4C), hex(0x5AD48A))
    static let warn = dynamic(hex(0xB8650A), hex(0xF2A649))
    static let bad = dynamic(hex(0xC23A30), hex(0xFF7A6E))

    // The icon's gradient stops.
    static let gradTeal = hex(0x18AFAB)
    static let gradViolet = hex(0x5C33C7)
    static let gradDeep = hex(0x1D1852)
    static let cursorGlow = hex(0x8CFFEB)
}

enum Theme {
    static let background = Color(nsColor: Palette.background)
    static let card = Color(nsColor: Palette.card)
    static let raised = Color(nsColor: Palette.raised)
    static let sunken = Color(nsColor: Palette.sunken)
    static let border = Color(nsColor: Palette.border)
    static let hairline = Color(nsColor: Palette.hairline)

    static let rail = Color(nsColor: Palette.rail)
    static let railText = Color(nsColor: Palette.railText)
    static let railSecondary = Color(nsColor: Palette.railSecondary)
    static let railHover = Color(nsColor: Palette.railHover)
    static let railSelected = Color(nsColor: Palette.railSelected)
    /// Kept for the Scratchpad window's notes list, which is a light panel.
    static let sidebar = Color(nsColor: Palette.raised)

    static let text = Color(nsColor: Palette.text)
    static let secondary = Color(nsColor: Palette.secondary)
    static let tertiary = Color(nsColor: Palette.tertiary)

    static let accent = Color(nsColor: Palette.accent)
    static let accentFill = Color(nsColor: Palette.accentFill)
    static let accentSoft = Color(nsColor: Palette.accentSoft)
    static let nsAccent = Palette.accent

    static let live = Color(nsColor: Palette.live)
    static let liveSoft = Color(nsColor: Palette.liveSoft)
    static let cursorGlow = Color(nsColor: Palette.cursorGlow)

    static let good = Color(nsColor: Palette.good)
    static let warn = Color(nsColor: Palette.warn)
    static let bad = Color(nsColor: Palette.bad)

    /// The icon's gradient, for brand moments only.
    static let brand = LinearGradient(
        colors: [Color(nsColor: Palette.gradTeal), Color(nsColor: Palette.gradViolet),
                 Color(nsColor: Palette.gradDeep)],
        startPoint: .topLeading, endPoint: .bottomTrailing)
    /// The grille's lines: violet into teal.
    static let ink = LinearGradient(
        colors: [Color(nsColor: Palette.gradViolet), Color(nsColor: Palette.gradTeal)],
        startPoint: .leading, endPoint: .trailing)

    // Spacing on a 4 point grid.
    static let s1: CGFloat = 4
    static let s2: CGFloat = 8
    static let s3: CGFloat = 12
    static let s4: CGFloat = 16
    static let s5: CGFloat = 24
    static let s6: CGFloat = 32
    static let s7: CGFloat = 40

    /// Large containers are rounder than the controls inside them.
    static let heroRadius: CGFloat = 20
    static let radius: CGFloat = 14
    static let smallRadius: CGFloat = 8

    static let hubSize = NSSize(width: 980, height: 660)
    static let onboardingSize = NSSize(width: 660, height: 500)
}

extension Font {
    /// SF Pro Rounded for display sizes; see the top of this file.
    static func display(_ size: CGFloat, _ weight: Font.Weight = .bold) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }
    static let pageTitle = Font.display(28)
    static let sectionTitle = Font.display(17, .semibold)
    static let cardTitle = Font.system(size: 13, weight: .semibold)
    static let body14 = Font.system(size: 14)
    static let caption12 = Font.system(size: 12)
    static let statNumber = Font.display(26, .semibold)
}

// ---------------------------------------------------------------------------
// Appearance.

enum Appearance: String, CaseIterable {
    case system, light, dark

    var title: String { rawValue.capitalized }

    var ns: NSAppearance? {
        switch self {
        case .system: return nil
        case .light: return NSAppearance(named: .aqua)
        case .dark: return NSAppearance(named: .darkAqua)
        }
    }

    /// The choice in Settings. DICTATOR_APPEARANCE overrides it in fake mode,
    /// so the snapshot runs can draw both without touching any preference.
    static var current: Appearance {
        if fake, let e = env["DICTATOR_APPEARANCE"], let a = Appearance(rawValue: e) { return a }
        return Appearance(rawValue: Prefs.store.string(forKey: "appearance") ?? "") ?? .system
    }

    /// Store and apply to every window at once. Windows set no appearance
    /// of their own, so they all follow NSApp's.
    static func set(_ a: Appearance) {
        Prefs.store.set(a.rawValue, forKey: "appearance")
        apply()
    }

    static func apply() { NSApp.appearance = current.ns }
}

// ---------------------------------------------------------------------------
// The brand mark, drawn rather than loaded, so it is crisp at every size and
// a bare build without the icon file still has it.

/// The icon in miniature: gradient tile, white grille of text lines, teal
/// cursor.
struct BrandMark: View {
    var size: CGFloat = 28

    var body: some View {
        let r = size * 0.27
        ZStack {
            RoundedRectangle(cornerRadius: r, style: .continuous).fill(Theme.brand)
            RoundedRectangle(cornerRadius: r, style: .continuous)
                .strokeBorder(Color.white.opacity(0.18), lineWidth: max(0.5, size / 64))
            HStack(alignment: .center, spacing: size * 0.08) {
                // The grille: a white capsule with four lines in it.
                ZStack {
                    Capsule().fill(Color.white)
                    VStack(alignment: .leading, spacing: size * 0.05) {
                        ForEach([0.62, 0.86, 0.5, 0.74], id: \.self) { w in
                            Capsule().fill(Theme.ink)
                                .frame(width: size * 0.26 * w, height: max(1, size * 0.045))
                        }
                    }
                }
                .frame(width: size * 0.36, height: size * 0.5)
                Capsule().fill(Theme.cursorGlow)
                    .frame(width: max(1.5, size * 0.055), height: size * 0.32)
                    .shadow(color: Color(nsColor: Palette.gradTeal).opacity(0.9),
                            radius: size * 0.06)
            }
            .offset(x: size * 0.02)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// What an empty list shows instead of a stock symbol: the grille's lines of
/// text, with the teal cursor where the next words will go. `lines` is how
/// many lines are already "written"; zero is a blank page with the cursor.
struct LinesArt: View {
    var lines: Int = 2
    var mic = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Theme.accentSoft)
                .frame(width: 112, height: 76)
            HStack(alignment: .center, spacing: 10) {
                if mic {
                    Image(systemName: "mic.fill")
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                }
                if lines == 0 {
                    // A blank page: only the cursor, waiting.
                    cursor
                } else {
                    VStack(alignment: .leading, spacing: 7) {
                        ForEach(0..<lines, id: \.self) { i in
                            HStack(spacing: 4) {
                                Capsule().fill(Theme.ink).opacity(0.85)
                                    .frame(width: [52, 38, 46, 30][i % 4] * (mic ? 0.75 : 1), height: 5)
                                if i == lines - 1 { cursor }
                            }
                            .frame(height: 5)
                        }
                    }
                }
            }
        }
        .frame(height: 80)
        .accessibilityHidden(true)
    }

    private var cursor: some View {
        Capsule().fill(Theme.live).frame(width: 3, height: 18)
            .shadow(color: Theme.live.opacity(0.6), radius: 3)
    }
}

/// A progress bar in the brand colours, the same in front or behind.
struct BrandProgress: View {
    var value: Double
    var body: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.raised)
                Capsule().strokeBorder(Theme.border, lineWidth: 1)
                Capsule().fill(Theme.ink)
                    .frame(width: max(6, g.size.width * min(max(value, 0), 1)))
            }
        }
        .frame(height: 6)
    }
}

// ---------------------------------------------------------------------------
// Shared pieces.

/// A card: a surface with a hairline border. Lifted by a shadow in light,
/// by being lighter than the page in dark.
struct Card: ViewModifier {
    var padding: CGFloat = Theme.s4
    var radius: CGFloat = Theme.radius
    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(RoundedRectangle(cornerRadius: radius, style: .continuous)
                .fill(Theme.card)
                .shadow(color: Color(nsColor: dynamic(hex(0x1A1838, 0.05), .clear)),
                        radius: 8, x: 0, y: 2))
            .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous)
                .strokeBorder(Theme.border, lineWidth: 1))
    }
}

extension View {
    func card(padding: CGFloat = Theme.s4, radius: CGFloat = Theme.radius) -> some View {
        modifier(Card(padding: padding, radius: radius))
    }
}

/// The one filled button per screen.
struct PrimaryButton: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(.white)
            .padding(.horizontal, Theme.s4)
            .frame(height: 32)
            .background(Capsule(style: .continuous)
                .fill(enabled ? Theme.accentFill : Theme.tertiary.opacity(0.5)))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .contentShape(Capsule())
    }
}

/// Everything else: a surface, bordered, quiet.
struct QuietButton: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(enabled ? Theme.text : Theme.tertiary)
            .padding(.horizontal, Theme.s3)
            .frame(height: 30)
            .background(Capsule(style: .continuous)
                .fill(configuration.isPressed ? Theme.raised : Theme.card))
            .overlay(Capsule(style: .continuous).strokeBorder(Theme.border, lineWidth: 1))
            .contentShape(Capsule())
    }
}

/// A borderless icon button, for copy and remove on list rows.
struct IconButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(Theme.secondary)
            .frame(width: 26, height: 26)
            .background(RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(configuration.isPressed ? Theme.raised : Color.clear))
            .contentShape(Rectangle())
    }
}

/// Title and one sentence at the top of every Hub page.
struct PageHeader<Trailing: View>: View {
    var title: String
    var blurb: String
    var trailing: Trailing

    init(_ title: String, _ blurb: String, @ViewBuilder trailing: () -> Trailing) {
        self.title = title
        self.blurb = blurb
        self.trailing = trailing()
    }

    var body: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.pageTitle).foregroundColor(Theme.text)
                Text(blurb).font(.body14).foregroundColor(Theme.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: Theme.s4)
            trailing
        }
    }
}

extension PageHeader where Trailing == EmptyView {
    init(_ title: String, _ blurb: String) {
        self.init(title, blurb) { EmptyView() }
    }
}

/// A small heading over a group on a page, in sentence case.
struct SectionLabel: View {
    var text: String
    init(_ t: String) { text = t }
    var body: some View {
        Text(text).font(.system(size: 13, weight: .semibold))
            .foregroundColor(Theme.secondary)
            .padding(.leading, Theme.s1)
    }
}

/// A search field that looks like the rest: rounded, a glass icon.
struct SearchField: View {
    var prompt: String
    @Binding var text: String

    var body: some View {
        HStack(spacing: Theme.s2) {
            Image(systemName: "magnifyingglass").foregroundColor(Theme.tertiary)
                .font(.system(size: 12, weight: .medium))
            TextField(prompt, text: $text)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(Theme.text)
            if !text.isEmpty {
                Button { text = "" } label: {
                    Image(systemName: "xmark.circle.fill").foregroundColor(Theme.tertiary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, Theme.s3)
        .frame(height: 32)
        .background(Capsule(style: .continuous).fill(Theme.card))
        .overlay(Capsule(style: .continuous).strokeBorder(Theme.border, lineWidth: 1))
    }
}

/// A plain text field in the same style as the search field.
struct InputField: View {
    var prompt: String
    @Binding var text: String
    var onSubmit: () -> Void = {}

    var body: some View {
        TextField(prompt, text: $text)
            .textFieldStyle(.plain)
            .font(.system(size: 13))
            .foregroundColor(Theme.text)
            .onSubmit(onSubmit)
            .padding(.horizontal, Theme.s3)
            .frame(height: 32)
            .background(RoundedRectangle(cornerRadius: Theme.smallRadius, style: .continuous)
                .fill(Theme.card))
            .overlay(RoundedRectangle(cornerRadius: Theme.smallRadius, style: .continuous)
                .strokeBorder(Theme.border, lineWidth: 1))
    }
}

/// An empty list: a drawing from the icon's motif, and one sentence that
/// says what to do.
struct EmptyState: View {
    enum Art { case lines(Int), mic, search }
    var art: Art
    var title: String
    var line: String

    var body: some View {
        VStack(spacing: Theme.s3) {
            switch art {
            case .lines(let n): LinesArt(lines: n)
            case .mic: LinesArt(lines: 0, mic: true)
            case .search:
                ZStack {
                    LinesArt(lines: 3).opacity(0.45)
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 26, weight: .semibold))
                        .foregroundColor(Theme.accent)
                        .offset(x: 34, y: 14)
                }
            }
            Text(title).font(.display(16, .semibold)).foregroundColor(Theme.text)
                .padding(.top, Theme.s1)
            Text(line).font(.system(size: 13)).foregroundColor(Theme.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 380)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Theme.s6)
    }
}

/// A small rounded label, e.g. "noticed once" or "Hinglish".
struct Pill: View {
    var text: String
    var symbol: String? = nil
    var tint: Color = Theme.accent

    var body: some View {
        HStack(spacing: 4) {
            if let s = symbol { Image(systemName: s).font(.system(size: 9, weight: .bold)) }
            Text(text).font(.system(size: 11, weight: .semibold))
        }
        .foregroundColor(tint)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(Capsule().fill(tint.opacity(0.12)))
    }
}

/// A key cap, for "Hold fn to dictate".
struct KeyCap: View {
    var label: String
    var body: some View {
        Text(label)
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundColor(Theme.text)
            .padding(.horizontal, 7)
            .frame(minWidth: 24, minHeight: 22)
            .background(RoundedRectangle(cornerRadius: 6, style: .continuous).fill(Theme.card))
            .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous)
                .strokeBorder(Theme.border, lineWidth: 1))
            .shadow(color: .black.opacity(0.08), radius: 0, x: 0, y: 1)
    }
}

/// The privacy promise, as a thing on the page rather than a footnote. Shown
/// on Home and at the top of Settings > Privacy.
struct PrivacyPromise: View {
    var compact = false

    var body: some View {
        HStack(alignment: .center, spacing: Theme.s4) {
            ZStack {
                Circle().fill(Theme.liveSoft).frame(width: 44, height: 44)
                Image(systemName: "lock.shield.fill")
                    .font(.system(size: 19, weight: .semibold))
                    .foregroundColor(Theme.live)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text("Everything stays on this Mac").font(.display(15, .semibold))
                    .foregroundColor(Theme.text)
                Text("Your voice is turned into text here, by models on this Mac. No account, "
                     + "no upload, and your history never leaves "
                     + stateDir.path.replacingOccurrences(of: home.path, with: "~") + ".")
                    .font(.system(size: 12.5)).foregroundColor(Theme.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
            if !compact {
                VStack(alignment: .trailing, spacing: 5) {
                    fact("waveform", "Speech to text, offline")
                    fact("icloud.slash", "Nothing uploaded")
                }
            }
        }
        .padding(.horizontal, Theme.s4)
        .padding(.vertical, Theme.s3)
        .background(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
            .fill(Theme.card))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
            .strokeBorder(Theme.live.opacity(0.35), style: StrokeStyle(lineWidth: 1, dash: [4, 3])))
    }

    private func fact(_ symbol: String, _ s: String) -> some View {
        HStack(spacing: 5) {
            Text(s).font(.system(size: 11.5, weight: .medium)).foregroundColor(Theme.secondary)
            Image(systemName: symbol).font(.system(size: 10, weight: .semibold))
                .foregroundColor(Theme.live).frame(width: 14)
        }
    }
}

/// Hover state for one row, held with @StateObject (no @State here; see
/// the top of Hub.swift).
final class Hover: ObservableObject {
    @Published var on = false
}

func copyToPasteboard(_ s: String) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(s, forType: .string)
}

/// macOS acts on a quick tap of fn (Globe) itself: the emoji picker, the
/// input source, or Apple's dictation. Dictator's double tap is two such
/// taps, and the key listener only listens, so it cannot stop macOS from
/// acting on them. The fix is one setting, and this says which.
struct GlobeKeyNote: View {
    var compact = false

    static let line = "A quick tap of fn (🌐) also makes macOS open the emoji picker or switch "
        + "input. Set System Settings, Keyboard, “Press 🌐 key to” to “Do Nothing”."

    var body: some View {
        HStack(alignment: .center, spacing: Theme.s3) {
            Image(systemName: "globe").font(.system(size: compact ? 13 : 15, weight: .medium))
                .foregroundColor(Theme.warn)
            Text(Self.line)
                .font(.system(size: compact ? 12 : 13))
                .foregroundColor(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: Theme.s2)
            Button("Open Keyboard Settings") { openKeyboardSettings() }
                .buttonStyle(QuietButton())
        }
        .padding(.horizontal, Theme.s3)
        .padding(.vertical, compact ? Theme.s2 : Theme.s3)
        .background(RoundedRectangle(cornerRadius: Theme.smallRadius + 2, style: .continuous)
            .fill(Theme.warn.opacity(0.09)))
        .overlay(RoundedRectangle(cornerRadius: Theme.smallRadius + 2, style: .continuous)
            .strokeBorder(Theme.warn.opacity(0.35), lineWidth: 1))
    }
}

func openKeyboardSettings() {
    if fake { NSLog("dictator (fake): would open Keyboard settings"); return }
    NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.Keyboard-Settings.extension")!)
}

extension View {
    /// Snapshot runs never make their window key (they must not take the
    /// keyboard), and SwiftUI draws the controls of a window that is not key
    /// greyed out. Told it is key, the PNG shows what a person would see.
    @ViewBuilder func snapshotActive(_ on: Bool) -> some View {
        if on { self.environment(\.controlActiveState, .key) } else { self }
    }
}

/// The app's switch: a violet track with a white knob when on. Drawn here
/// rather than AppKit's, so it carries the brand colour in both appearances
/// and looks the same whether or not its window is in front.
struct BrandSwitch: ToggleStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        let on = configuration.isOn
        return HStack(spacing: Theme.s2) {
            configuration.label
            ZStack(alignment: on ? .trailing : .leading) {
                Capsule().fill(on ? Theme.accentFill : Theme.raised)
                Capsule().strokeBorder(on ? Color.clear : Theme.border, lineWidth: 1)
                Circle().fill(Color.white)
                    .shadow(color: .black.opacity(0.22), radius: 1.5, y: 1)
                    .padding(2)
            }
            .frame(width: 36, height: 21)
            .opacity(enabled ? 1 : 0.45)
            .animation(.easeOut(duration: 0.15), value: on)
            .onTapGesture { configuration.isOn.toggle() }
            .accessibilityElement()
            .accessibilityAddTraits(.isButton)
            .accessibilityValue(on ? "On" : "Off")
        }
    }
}
