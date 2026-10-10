// The look, in one place. Every colour, size and the few shared pieces of
// chrome (cards, buttons, page headers, the brand mark) the windows are built
// from.
//
// The identity is the mark (BrandMark below, and tools/make_icon.swift for
// the Dock): a lowercase "d" in cobalt blue whose bowl holds a voice
// waveform, with a text cursor beside it. Voice becomes text. So:
//
//   - Cobalt blue is the brand and the one accent: controls, the selected
//     page, links.
//   - Mint means live and local: the status dot, "listening", the privacy
//     promise. Coral is the warm second colour, for time and streaks. Both
//     are used sparingly, as small icon tiles, never as a wash.
//   - The canvas is a warm off-white in light and a blue-black in dark,
//     with plain white or slate cards on it. No gradients behind content.
//   - Headings are SF Pro, bold and slightly tight, like the wordmark. Body
//     text is SF Pro at 13 and 14 points.
//
// Every colour has a light and a dark value, resolved by the appearance of
// the view drawing it (NSColor(name:dynamicProvider:)), so Settings >
// Appearance and the sun button in the top bar switch the whole app at once
// with NSApp.appearance. The dark palette is designed, not inverted: surfaces
// get lighter as they rise, borders are low-alpha white, and the blue is
// lighter so it keeps its contrast. Body text is at least 4.5:1 on its
// background in both.

import AppKit
import SwiftUI

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
    static let background = dynamic(hex(0xF7F7F2), hex(0x10141B))
    static let card = dynamic(hex(0xFFFFFF), hex(0x1B212B))
    static let raised = dynamic(hex(0xF1F1EB), hex(0x252C38))
    static let sunken = dynamic(hex(0xEEEEE8), hex(0x0B0E13))
    static let border = dynamic(hex(0xE4E4DC), NSColor.white.withAlphaComponent(0.09))
    static let hairline = dynamic(hex(0xEDEDE7), NSColor.white.withAlphaComponent(0.06))

    // The sidebar sits a step below the canvas in both appearances.
    static let rail = dynamic(hex(0xF0F0EA), hex(0x0C1016))
    static let railText = dynamic(hex(0x141820), hex(0xF4F5F0))
    static let railSecondary = dynamic(hex(0x545A66), hex(0xA3A9B5))
    static let railHover = dynamic(hex(0x141820, 0.05), NSColor.white.withAlphaComponent(0.05))

    // Text. Contrast on `background`: text 16.5:1 / 16.8:1, secondary
    // 6.5:1 / 8.4:1, tertiary 4.8:1 / 5.5:1.
    static let text = dynamic(hex(0x141820), hex(0xF4F5F0))
    static let secondary = dynamic(hex(0x545A66), hex(0xA9AFBA))
    static let tertiary = dynamic(hex(0x676D79), hex(0x868D99))

    // Cobalt: controls, selection, links. The lighter dark value keeps 6:1
    // on the dark canvas; the fill behind white text is its own colour,
    // because a fill wants to be deeper than a text colour (white on it is
    // 5.1:1 in both).
    static let accent = dynamic(hex(0x315CFF), hex(0x6F8BFF))
    static let accentFill = dynamic(hex(0x315CFF), hex(0x3D5EF5))
    static let accentSoft = dynamic(hex(0x315CFF, 0.09), hex(0x6F8BFF, 0.15))

    // Mint: live and local.
    static let live = dynamic(hex(0x087A5C), hex(0x70E1C1))
    static let liveSoft = dynamic(hex(0x70E1C1, 0.22), hex(0x70E1C1, 0.13))

    // Coral: time and streaks. Icons only in light, where it is 3.4:1.
    static let coral = dynamic(hex(0xE8603F), hex(0xFF8B78))
    static let coralSoft = dynamic(hex(0xFF775E, 0.13), hex(0xFF8B78, 0.14))

    static let good = dynamic(hex(0x1E8A4C), hex(0x5AD48A))
    static let warn = dynamic(hex(0xB8650A), hex(0xF2A649))
    static let bad = dynamic(hex(0xC23A30), hex(0xFF7A6E))

    // The mark's blue, light at the top of the bowl to deep at the stem.
    static let markTop = hex(0x4F78FF)
    static let markBottom = hex(0x2348E8)
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
    static let coral = Color(nsColor: Palette.coral)
    static let coralSoft = Color(nsColor: Palette.coralSoft)

    static let good = Color(nsColor: Palette.good)
    static let warn = Color(nsColor: Palette.warn)
    static let bad = Color(nsColor: Palette.bad)

    /// The mark's blue, for brand moments only: the mark itself and the
    /// onboarding welcome.
    static let brand = LinearGradient(
        colors: [Color(nsColor: Palette.markTop), Color(nsColor: Palette.markBottom)],
        startPoint: .topLeading, endPoint: .bottomTrailing)
    /// Lines of text in the empty-state drawings and progress bars.
    static let ink = LinearGradient(
        colors: [Color(nsColor: Palette.accentFill), Color(nsColor: Palette.accent)],
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
    static let heroRadius: CGFloat = 18
    static let radius: CGFloat = 12
    static let smallRadius: CGFloat = 8

    static let hubSize = NSSize(width: 980, height: 660)
    static let onboardingSize = NSSize(width: 660, height: 500)
}

extension Font {
    /// SF Pro for display sizes; see the top of this file.
    static func display(_ size: CGFloat, _ weight: Font.Weight = .bold) -> Font {
        .system(size: size, weight: weight)
    }
    static let pageTitle = Font.display(28)
    static let sectionTitle = Font.display(17, .semibold)
    static let cardTitle = Font.system(size: 13, weight: .semibold)
    static let body14 = Font.system(size: 14)
    static let caption12 = Font.system(size: 12)
    static let statNumber = Font.display(24, .bold)
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
// a bare build without the icon file still has it. tools/make_icon.swift
// draws the same shape for the Dock.

/// The "d": a round bowl and a thick stem on its right, with rounded ends.
/// Drawn in a box 0.86 wide for every 1 tall.
struct DShape: Shape {
    func path(in r: CGRect) -> Path {
        let u = r.height
        var p = Path()
        p.addEllipse(in: CGRect(x: r.minX, y: r.minY + u * 0.26, width: u * 0.74, height: u * 0.74))
        p.addRoundedRect(in: CGRect(x: r.minX + u * 0.56, y: r.minY, width: u * 0.30, height: u),
                         cornerSize: CGSize(width: u * 0.15, height: u * 0.15),
                         style: .continuous)
        return p
    }
}

/// The mark: the blue "d" with a waveform in its bowl, and a text cursor
/// beside it. `size` is its height; it is a little wider than tall.
/// `tile` puts it on the app icon's white rounded square.
struct BrandMark: View {
    var size: CGFloat = 28
    var tile = false

    /// Bar heights, as a share of the glyph's height, left to right.
    static let bars: [CGFloat] = [0.14, 0.28, 0.42, 0.30, 0.20, 0.10]

    var body: some View {
        if tile {
            let r = size * 0.23
            ZStack {
                RoundedRectangle(cornerRadius: r, style: .continuous).fill(Color.white)
                RoundedRectangle(cornerRadius: r, style: .continuous)
                    .strokeBorder(Color.black.opacity(0.06), lineWidth: max(0.5, size / 96))
                glyph(size * 0.52).offset(x: size * 0.02)
            }
            .frame(width: size, height: size)
            .shadow(color: .black.opacity(0.10), radius: size * 0.06, y: size * 0.02)
            .accessibilityHidden(true)
        } else {
            glyph(size).accessibilityHidden(true)
        }
    }

    private func glyph(_ g: CGFloat) -> some View {
        HStack(alignment: .center, spacing: g * 0.08) {
            ZStack(alignment: .topLeading) {
                DShape().fill(Theme.brand)
                // The waveform, centred on the bowl and running into the stem.
                HStack(alignment: .center, spacing: g * 0.045) {
                    ForEach(Array(Self.bars.enumerated()), id: \.offset) { _, b in
                        Capsule().fill(Color.white)
                            .frame(width: max(1, g * 0.055), height: g * b)
                    }
                }
                .frame(width: g * 0.78, height: g * 0.74)
                .offset(x: g * 0.0, y: g * 0.26)
            }
            .frame(width: g * 0.86, height: g)
            // The cursor: a stem with short caps, as tall as the bowl.
            ZStack {
                Rectangle().frame(width: max(1, g * 0.07), height: g * 0.70)
                VStack(spacing: 0) {
                    Capsule().frame(width: g * 0.22, height: max(1, g * 0.07))
                    Spacer(minLength: 0)
                    Capsule().frame(width: g * 0.22, height: max(1, g * 0.07))
                }
            }
            .foregroundStyle(Theme.brand)
            .frame(width: g * 0.22, height: g * 0.70)
            .offset(y: g * 0.15)
        }
        .frame(height: g)
    }
}

/// The mark and the lowercase name beside it, as in the sidebar.
struct Wordmark: View {
    var size: CGFloat = 20

    var body: some View {
        HStack(spacing: size * 0.35) {
            BrandMark(size: size * 1.3)
            Text("dictator")
                .font(.system(size: size, weight: .bold))
                .tracking(-size * 0.03)
                .foregroundColor(Theme.text)
                .offset(y: size * 0.04)
        }
        .accessibilityElement()
        .accessibilityLabel("Dictator")
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
                .shadow(color: Color(nsColor: dynamic(hex(0x141820, 0.05), .clear)),
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
