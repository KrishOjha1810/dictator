// The pieces Home is built from.
//
// Three rules hold across all of them, and they are the whole look:
//
//   Nothing is filled that can be outlined. A panel is a hairline, not a
//   box of colour. Three sheets of translucency stack into something
//   opaque, and then the window stops being glass.
//
//   Colour appears in three cards and in the initials beside a taught word,
//   and nowhere else. Even there it is tinted glass rather than paint, so
//   the sky behind the window carries through it.
//
//   The one saturated colour is the teal that means the microphone is live.

import AppKit
import SwiftUI

/// The three card tints, and the two the chips borrow.
///
/// Muted on purpose and no purple: a saturated gradient is the first thing
/// that makes an interface look generated, and it is also the first thing
/// that fights a photograph behind it.
enum Tone {
    case sand, moss, sky, amber

    var rgb: Color {
        switch self {
        case .sand:  return Color(red: 0.882, green: 0.729, blue: 0.471)
        case .moss:  return Color(red: 0.588, green: 0.769, blue: 0.667)
        case .sky:   return Color(red: 0.588, green: 0.722, blue: 0.831)
        case .amber: return Color(red: 1.000, green: 0.788, blue: 0.471)
        }
    }
}

/// A small outlined pill. Carries a fact, never a label for its own sake.
struct Chip: View {
    var text: String
    var symbol: String? = nil
    var tone: Tone? = nil

    var body: some View {
        HStack(spacing: 5) {
            if let s = symbol {
                Image(systemName: s).font(.system(size: 8.5, weight: .semibold))
            }
            Text(text).font(.system(size: 10.5, weight: .medium))
        }
        .foregroundColor(tone?.rgb ?? Theme.tertiary)
        .padding(.horizontal, 8).frame(height: 21)
        .overlay(Capsule().strokeBorder(
            (tone?.rgb ?? Color.white).opacity(tone == nil ? 0.13 : 0.38), lineWidth: 1))
    }
}

/// One of the three numbers on Home.
///
/// Tinted glass at 26%, not a painted card: the ridge behind the window is
/// still visible through it, which is what keeps the whole surface reading
/// as one sheet rather than as stickers on a sheet.
struct StatCard: View {
    var label: String
    var symbol: String
    var tone: Tone
    var value: String
    var caption: String
    /// Seven bars, 0 to 1, or nil for no chart.
    var spark: [Double]?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(label).font(.system(size: 10.5, weight: .semibold))
                    .tracking(0.9).foregroundColor(.white.opacity(0.72))
                    .lineLimit(1).fixedSize()
                Spacer()
                Image(systemName: symbol).font(.system(size: 12, weight: .medium))
                    .foregroundColor(.white.opacity(0.6))
            }
            Spacer(minLength: 14)
            Text(value).font(.display(33, .bold))
                .foregroundColor(.white)
                .lineLimit(1).minimumScaleFactor(0.45)
            Text(caption).font(.system(size: 11.5))
                .foregroundColor(.white.opacity(0.74))
                .lineLimit(2).minimumScaleFactor(0.85)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 5)
            if let s = spark { bars(s).padding(.top, 10) }
        }
        .padding(.horizontal, 16).padding(.vertical, 15)
        .frame(minWidth: 0, minHeight: 128, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 18, style: .continuous)
            .fill(tone.rgb.opacity(0.26)))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous)
            .strokeBorder(tone.rgb.opacity(0.42), lineWidth: 1))
    }

    private func bars(_ s: [Double]) -> some View {
        GeometryReader { geo in
            HStack(alignment: .bottom, spacing: 4) {
                ForEach(s.indices, id: \.self) { i in
                    RoundedRectangle(cornerRadius: 2)
                        .fill(.white.opacity(i == s.count - 1 ? 0.85 : 0.35))
                        .frame(height: max(3, geo.size.height * s[i]))
                }
            }
        }
        .frame(height: 26)
    }
}

/// What landed in the last hour or so, down the right of Home.
///
/// Rows rather than cards, divided by hairlines, because five filled boxes
/// in a narrow column is five more sheets of translucency.
struct RecentColumn: View {
    var said: [Said]
    var listening: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Recent").font(.display(14, .semibold)).foregroundColor(Theme.text)
                Spacer()
                if listening { LevelMeter() }
            }
            if said.isEmpty {
                Text("Nothing yet today.")
                    .font(.system(size: 12.5)).foregroundColor(Theme.tertiary)
            }
            VStack(spacing: 0) {
                ForEach(said) { r in
                    row(r)
                        .overlay(alignment: .top) {
                            if r.id != said.first?.id {
                                Rectangle().fill(Theme.hairline).frame(height: 1)
                            }
                        }
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16).padding(.top, 20).padding(.bottom, 22)
        .frame(width: 274)
        .frame(maxHeight: .infinity, alignment: .topLeading)
    }

    private func row(_ r: Said) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Initial(name: r.app.isEmpty ? "?" : r.app)
                Text(r.app.isEmpty ? "somewhere" : r.app)
                    .font(.system(size: 11.5, weight: .medium)).foregroundColor(Theme.secondary)
                Spacer(minLength: 0)
                Text(ago(r.at.timeIntervalSince1970))
                    .font(.system(size: 11, design: .monospaced)).foregroundColor(Theme.tertiary)
            }
            Text(r.text)
                .font(.system(size: 12.5)).foregroundColor(Theme.text.opacity(0.88))
                .lineLimit(3).lineSpacing(2)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 12).padding(.vertical, 11)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// A rounded square with one letter, tinted by the name so the same app is
/// the same colour every time without a table of apps to maintain.
struct Initial: View {
    var name: String

    var body: some View {
        let tones: [Tone] = [.moss, .sand, .sky, .amber]
        let tone = tones[abs(name.hashValue) % tones.count]
        return Text(String(name.prefix(1)).uppercased())
            .font(.system(size: 9.5, weight: .bold))
            .foregroundColor(.white)
            .frame(width: 19, height: 19)
            .background(RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(tone.rgb.opacity(0.40)))
            .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous)
                .strokeBorder(.white.opacity(0.28), lineWidth: 1))
    }
}

/// Four bars that move while the microphone is open, and only then.
///
/// The one animation in the app. Text saying "listening" proves nothing,
/// and a colour behind glass takes on whatever is under it; movement does
/// not, so movement is what carries the promise.
struct LevelMeter: View {
    @State private var up = false

    var body: some View {
        HStack(spacing: 6) {
            HStack(alignment: .center, spacing: 2) {
                ForEach(0..<4, id: \.self) { i in
                    Capsule().fill(Theme.live)
                        .frame(width: 2.5, height: 13)
                        .scaleEffect(y: up ? [1.0, 0.45, 0.8, 0.3][i] : [0.3, 1.0, 0.4, 0.9][i])
                        .animation(.easeInOut(duration: 0.42 + Double(i) * 0.09)
                            .repeatForever(autoreverses: true), value: up)
                }
            }
            .frame(height: 13)
            Text("listening").font(.system(size: 11)).foregroundColor(Theme.live)
        }
        .onAppear { up = true }
    }
}

/// "now", "4m", "18m", "2h", "yesterday".
func ago(_ epoch: Double) -> String {
    let s = Date().timeIntervalSince1970 - epoch
    if s < 45 { return "now" }
    if s < 3600 { return "\(Int(s / 60))m" }
    if s < 86_400 { return "\(Int(s / 3600))h" }
    if s < 172_800 { return "yesterday" }
    return "\(Int(s / 86_400))d"
}
