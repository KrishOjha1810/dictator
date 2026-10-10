// The window's own sky.
//
// The first version of this took the blur from the desktop behind the window
// (NSVisualEffectView, .behindWindow), which is how a Mac app normally does
// glass. It is the wrong choice here. Half the point of the look is the soft
// ridge showing through the panels, and on somebody with a white wallpaper,
// or a screenshot of a spreadsheet, there is no ridge and the whole design
// falls apart. Worse, it falls apart differently for every person, so it
// cannot be designed for or tested.
//
// So the app carries its own. Everything below is drawn, not loaded: no image
// file to ship, no decode on launch, and it is crisp on any display and at
// any window size.
//
// It is drawn soft on purpose and then blurred again by `Glass.blur`. The
// reason the blur is small is the one thing that took longest to learn: a
// heavy blur dissolves the scene into a smooth wash, and a smooth wash reads
// as paint rather than as something seen through glass. Fine detail under the
// panels is what makes them look transparent, which is also why the grain is
// here.

import SwiftUI

/// A ridge of hills, as fractions of the canvas.
///
/// Each pair is (x, y) from 0 to 1, left to right. They are written as
/// fractions so the same ridge draws correctly in a 980 point window and in a
/// full-screen one.
private struct Ridge {
    let points: [(CGFloat, CGFloat)]
    let grey: Double
    let alpha: Double
    /// A band of fog sitting on the ridge's shoulders, which is what gives
    /// the depth. Without it the hills read as flat cut paper.
    let fog: CGFloat?
}

private let ridges: [Ridge] = [
    Ridge(points: [(0, 0.655), (0.119, 0.588), (0.206, 0.636), (0.325, 0.562),
                   (0.438, 0.644), (0.550, 0.584), (0.663, 0.656), (0.781, 0.592),
                   (0.888, 0.648), (1, 0.606)],
          grey: 0.52, alpha: 0.17, fog: 0.644),
    Ridge(points: [(0, 0.722), (0.106, 0.666), (0.200, 0.714), (0.313, 0.640),
                   (0.431, 0.726), (0.544, 0.666), (0.656, 0.732), (0.775, 0.668),
                   (0.881, 0.726), (1, 0.684)],
          grey: 0.42, alpha: 0.22, fog: 0.714),
    Ridge(points: [(0, 0.790), (0.113, 0.736), (0.206, 0.782), (0.319, 0.704),
                   (0.438, 0.792), (0.550, 0.730), (0.663, 0.798), (0.781, 0.734),
                   (0.888, 0.790), (1, 0.748)],
          grey: 0.32, alpha: 0.30, fog: 0.782),
    Ridge(points: [(0, 0.858), (0.100, 0.812), (0.213, 0.862), (0.325, 0.800),
                   (0.438, 0.868), (0.550, 0.814), (0.669, 0.874), (0.788, 0.818),
                   (0.900, 0.872), (1, 0.834)],
          grey: 0.22, alpha: 0.40, fog: 0.852),
    Ridge(points: [(0, 0.918), (0.150, 0.886), (0.294, 0.924), (0.438, 0.880),
                   (0.588, 0.928), (0.738, 0.884), (0.875, 0.926), (1, 0.892)],
          grey: 0.13, alpha: 0.55, fog: nil),
    Ridge(points: [(0, 0.964), (0.188, 0.946), (0.388, 0.968), (0.588, 0.944),
                   (0.800, 0.970), (1, 0.948)],
          grey: 0.07, alpha: 0.72, fog: nil),
]

struct Backdrop: View {
    /// Drawn once per size and reused. The scene has no state and no
    /// animation, so redrawing it on every frame of a window resize is the
    /// only way it could cost anything.
    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            ZStack {
                sky
                haze(w, h)
                hills(w, h)
                treeline(w, h)
                vignette
                Grain()
            }
            // Drawn a little larger than the window and clipped, so the blur
            // below does not pull transparent pixels in from outside the
            // edges and leave a pale rim.
            .frame(width: w, height: h)
            .blur(radius: Glass.blur, opaque: true)
            .clipped()
            .overlay(Color.white.opacity(Glass.tint))
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }

    /// Air: dark at the top, pale at the horizon, which is what makes the
    /// hills in front of it read as distance rather than as shapes.
    private var sky: some View {
        LinearGradient(stops: [
            .init(color: grey(0.055), location: 0.00),
            .init(color: grey(0.105), location: 0.42),
            .init(color: grey(0.195), location: 0.70),
            .init(color: grey(0.300), location: 0.88),
            .init(color: grey(0.380), location: 1.00),
        ], startPoint: .top, endPoint: .bottom)
    }

    /// The low sun, as a glow rather than a disc with an edge. An edge would
    /// survive the blur and read as a bright blob behind the cards.
    private func haze(_ w: CGFloat, _ h: CGFloat) -> some View {
        RadialGradient(colors: [Color(white: 0.94).opacity(0.17),
                                Color(white: 0.94).opacity(0)],
                       center: .init(x: 0.70, y: 0.60),
                       startRadius: 0, endRadius: max(w, h) * 0.46)
    }

    private func hills(_ w: CGFloat, _ h: CGFloat) -> some View {
        ZStack {
            ForEach(ridges.indices, id: \.self) { i in
                let r = ridges[i]
                ZStack {
                    shape(r, w, h).fill(grey(r.grey).opacity(r.alpha))
                    if let y = r.fog {
                        LinearGradient(colors: [Color(white: 0.82).opacity(0),
                                                Color(white: 0.82).opacity(0.14),
                                                Color(white: 0.82).opacity(0)],
                                       startPoint: .top, endPoint: .bottom)
                            .frame(height: h * 0.08)
                            .offset(y: h * (y - 0.5))
                    }
                }
            }
        }
    }

    private func shape(_ r: Ridge, _ w: CGFloat, _ h: CGFloat) -> Path {
        Path { p in
            guard let first = r.points.first else { return }
            p.move(to: CGPoint(x: first.0 * w, y: first.1 * h))
            for pt in r.points.dropFirst() {
                p.addLine(to: CGPoint(x: pt.0 * w, y: pt.1 * h))
            }
            p.addLine(to: CGPoint(x: w, y: h))
            p.addLine(to: CGPoint(x: 0, y: h))
            p.closeSubpath()
        }
    }

    /// The nearest thing in the picture and the sharpest, which is the part
    /// you watch pass behind a panel.
    private func treeline(_ w: CGFloat, _ h: CGFloat) -> some View {
        Canvas { ctx, size in
            let base = size.height * 0.962
            var x: CGFloat = size.width * 0.02
            var i = 0
            while x < size.width {
                // Varied without being random: a repeating pattern of five
                // heights reads as trees, where equal ones read as a comb.
                let tall = [0.014, 0.020, 0.012, 0.023, 0.016][i % 5]
                let top = base - size.height * tall
                let half = size.width * 0.0032
                var tree = Path()
                tree.move(to: CGPoint(x: x - half, y: base + size.height * 0.012))
                tree.addLine(to: CGPoint(x: x, y: top))
                tree.addLine(to: CGPoint(x: x + half, y: base + size.height * 0.012))
                tree.closeSubpath()
                ctx.fill(tree, with: .color(Color(white: 0.035).opacity(0.8)))
                x += size.width * 0.026
                i += 1
            }
        }
    }

    private var vignette: some View {
        RadialGradient(stops: [.init(color: .black.opacity(0), location: 0.58),
                               .init(color: .black.opacity(0.42), location: 1.0)],
                       center: .init(x: 0.5, y: 0.46),
                       startRadius: 0, endRadius: 900)
    }

    private func grey(_ v: Double) -> Color { Color(white: v) }
}

/// Fine speckle over the scene.
///
/// Not decoration. A blur is only visible when there is detail under it, so a
/// perfectly smooth gradient blurred at any radius looks exactly like the
/// same gradient unblurred. The grain is what gives the panels something to
/// soften, and it is the difference between a window that looks transparent
/// and one that looks grey.
private struct Grain: View {
    var body: some View {
        Canvas { ctx, size in
            // A fixed sequence rather than Double.random: the scene must not
            // shimmer when the window is resized or redrawn, and a snapshot
            // run has to produce the same pixels twice.
            var seed: UInt64 = 0x9E3779B97F4A7C15
            func next() -> CGFloat {
                seed ^= seed << 13
                seed ^= seed >> 7
                seed ^= seed << 17
                return CGFloat(Double(seed % 10_000) / 10_000)
            }
            let count = Int(size.width * size.height / 420)
            for _ in 0..<count {
                let x = next() * size.width
                let y = next() * size.height
                let a = 0.03 + Double(next()) * 0.05
                ctx.fill(Path(CGRect(x: x, y: y, width: 1.2, height: 1.2)),
                         with: .color(.white.opacity(a)))
            }
        }
        .blendMode(.plusLighter)
        .opacity(0.75)
    }
}
