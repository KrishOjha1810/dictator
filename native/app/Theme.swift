// The look, in one place. Every colour, size and the few shared pieces of
// chrome (cards, buttons, page headers) the windows are built from.
//
// Light only. The app forces the aqua appearance on its windows (main.swift),
// so these are fixed colours rather than asset-catalogue pairs: there is no
// dark variant to keep in step.

import AppKit
import SwiftUI

enum Theme {
    // Warm off-white surfaces, white cards on top.
    static let background = Color(red: 0.980, green: 0.973, blue: 0.961)   // #FAF8F5
    static let sidebar = Color(red: 0.957, green: 0.945, blue: 0.925)      // #F4F1EC
    static let card = Color.white
    static let border = Color(red: 0.902, green: 0.886, blue: 0.863)       // #E6E2DC
    static let hairline = Color(red: 0.933, green: 0.922, blue: 0.902)     // #EEEBE6

    static let text = Color(red: 0.122, green: 0.114, blue: 0.102)         // #1F1D1A
    static let secondary = Color(red: 0.420, green: 0.400, blue: 0.376)    // #6B6660
    static let tertiary = Color(red: 0.635, green: 0.616, blue: 0.588)     // #A29D96

    // One accent. The icon (tools/make_icon.swift) uses the same teal.
    static let accent = Color(red: 0.063, green: 0.490, blue: 0.431)       // #107D6E
    static let accentSoft = Color(red: 0.063, green: 0.490, blue: 0.431).opacity(0.10)
    static let nsAccent = NSColor(srgbRed: 0.063, green: 0.490, blue: 0.431, alpha: 1)

    static let good = Color(red: 0.180, green: 0.620, blue: 0.330)
    static let warn = Color(red: 0.850, green: 0.500, blue: 0.110)
    static let bad = Color(red: 0.820, green: 0.250, blue: 0.220)

    // Spacing on a 4 point grid.
    static let s1: CGFloat = 4
    static let s2: CGFloat = 8
    static let s3: CGFloat = 12
    static let s4: CGFloat = 16
    static let s5: CGFloat = 24
    static let s6: CGFloat = 32
    static let s7: CGFloat = 40

    static let radius: CGFloat = 12
    static let smallRadius: CGFloat = 8

    static let hubSize = NSSize(width: 960, height: 640)
    static let onboardingSize = NSSize(width: 640, height: 480)
}

extension Font {
    static let pageTitle = Font.system(size: 26, weight: .semibold)
    static let cardTitle = Font.system(size: 13, weight: .semibold)
    static let body14 = Font.system(size: 14)
    static let caption12 = Font.system(size: 12)
    static let statNumber = Font.system(size: 26, weight: .semibold, design: .rounded)
}

// ---------------------------------------------------------------------------
// Shared pieces.

/// A white card with a hairline border and a soft shadow.
struct Card: ViewModifier {
    var padding: CGFloat = Theme.s4
    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
                .fill(Theme.card)
                .shadow(color: .black.opacity(0.04), radius: 6, x: 0, y: 2))
            .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
                .strokeBorder(Theme.border, lineWidth: 1))
    }
}

extension View {
    func card(padding: CGFloat = Theme.s4) -> some View { modifier(Card(padding: padding)) }
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
            .background(RoundedRectangle(cornerRadius: Theme.smallRadius, style: .continuous)
                .fill(enabled ? Theme.accent : Theme.tertiary.opacity(0.6)))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .contentShape(Rectangle())
    }
}

/// Everything else: white, bordered, quiet.
struct QuietButton: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(enabled ? Theme.text : Theme.tertiary)
            .padding(.horizontal, Theme.s3)
            .frame(height: 30)
            .background(RoundedRectangle(cornerRadius: Theme.smallRadius, style: .continuous)
                .fill(configuration.isPressed ? Theme.hairline : Theme.card))
            .overlay(RoundedRectangle(cornerRadius: Theme.smallRadius, style: .continuous)
                .strokeBorder(Theme.border, lineWidth: 1))
            .contentShape(Rectangle())
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
                .fill(configuration.isPressed ? Theme.hairline : Color.clear))
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
            VStack(alignment: .leading, spacing: Theme.s1) {
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

/// A search field that looks like the rest: white, rounded, a glass icon.
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
            if !text.isEmpty {
                Button { text = "" } label: {
                    Image(systemName: "xmark.circle.fill").foregroundColor(Theme.tertiary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, Theme.s3)
        .frame(height: 32)
        .background(RoundedRectangle(cornerRadius: Theme.smallRadius, style: .continuous)
            .fill(Theme.card))
        .overlay(RoundedRectangle(cornerRadius: Theme.smallRadius, style: .continuous)
            .strokeBorder(Theme.border, lineWidth: 1))
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
            .onSubmit(onSubmit)
            .padding(.horizontal, Theme.s3)
            .frame(height: 32)
            .background(RoundedRectangle(cornerRadius: Theme.smallRadius, style: .continuous)
                .fill(Theme.card))
            .overlay(RoundedRectangle(cornerRadius: Theme.smallRadius, style: .continuous)
                .strokeBorder(Theme.border, lineWidth: 1))
    }
}

/// An empty list: an icon, and one sentence that says what to do.
struct EmptyState: View {
    var symbol: String
    var title: String
    var line: String

    var body: some View {
        VStack(spacing: Theme.s3) {
            ZStack {
                Circle().fill(Theme.accentSoft).frame(width: 52, height: 52)
                Image(systemName: symbol).font(.system(size: 20, weight: .medium))
                    .foregroundColor(Theme.accent)
            }
            Text(title).font(.system(size: 15, weight: .semibold)).foregroundColor(Theme.text)
            Text(line).font(.system(size: 13)).foregroundColor(Theme.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 360)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Theme.s7)
    }
}

/// A small rounded label, e.g. "On this Mac only" or "noticed once".
struct Pill: View {
    var text: String
    var symbol: String? = nil
    var tint: Color = Theme.accent

    var body: some View {
        HStack(spacing: 4) {
            if let s = symbol { Image(systemName: s).font(.system(size: 10, weight: .semibold)) }
            Text(text).font(.system(size: 11, weight: .medium))
        }
        .foregroundColor(tint)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(Capsule().fill(tint.opacity(0.10)))
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
            .background(RoundedRectangle(cornerRadius: 5, style: .continuous).fill(Theme.card))
            .overlay(RoundedRectangle(cornerRadius: 5, style: .continuous)
                .strokeBorder(Theme.border, lineWidth: 1))
            .shadow(color: .black.opacity(0.06), radius: 0, x: 0, y: 1)
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
