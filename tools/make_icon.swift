// Draw Dictator's app icon and pack it into an .icns.
//
//   swift tools/make_icon.swift native/app/AppIcon.icns
//
// The icon is drawn here rather than kept as a picture somebody exported
// once, so it can be changed in code review and rebuilt by anyone with the
// Command Line Tools. A white square with the mark on it: a cobalt blue
// lowercase "d" whose bowl holds a voice waveform, and a text cursor beside
// it. Speech becoming writing, which is the whole app. The same shape as
// BrandMark in native/app/Theme.swift; change the two together.
//
// Every size the iconset wants is drawn at its own pixel size, not scaled
// down from 1024, so the 16 and 32 pixel versions stay sharp. The result is
// committed beside Info.plist and tools/build_dmg.sh copies it into the bundle.

import AppKit

guard CommandLine.arguments.count == 2 else {
    FileHandle.standardError.write("usage: swift tools/make_icon.swift OUT.icns\n".data(using: .utf8)!)
    exit(2)
}
let out = URL(fileURLWithPath: CommandLine.arguments[1])

// The mark's blue, light at the top left to deep at the bottom right, on a
// white tile that goes faintly warm towards the bottom.
let markTop    = NSColor(srgbRed: 0x4F / 255.0, green: 0x78 / 255.0, blue: 1.0, alpha: 1)
let markBottom = NSColor(srgbRed: 0x23 / 255.0, green: 0x48 / 255.0, blue: 0xE8 / 255.0, alpha: 1)
let tileTop    = NSColor.white
let tileBottom = NSColor(srgbRed: 0xF1 / 255.0, green: 0xF1 / 255.0, blue: 0xEB / 255.0, alpha: 1)

func capsule(_ r: NSRect) -> NSBezierPath {
    let rad = min(r.width, r.height) / 2
    return NSBezierPath(roundedRect: r, xRadius: rad, yRadius: rad)
}

func draw(_ px: Int) -> Data {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px,
                               bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                               isPlanar: false, colorSpaceName: .deviceRGB,
                               bytesPerRow: 0, bitsPerPixel: 0)!
    let ctx = NSGraphicsContext(bitmapImageRep: rep)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = ctx
    ctx.imageInterpolation = .high
    let s = CGFloat(px)
    let small = px < 64

    // Apple's grid: the body is 824 of 1024, centred, with room for a shadow.
    let inset = s * 100 / 1024
    let body = NSRect(x: inset, y: inset, width: s - 2 * inset, height: s - 2 * inset)
    let radius = body.width * 0.225
    let shape = NSBezierPath(roundedRect: body, xRadius: radius, yRadius: radius)

    if !small {
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.28)
        shadow.shadowBlurRadius = s * 0.03
        shadow.shadowOffset = NSSize(width: 0, height: -s * 0.012)
        NSGraphicsContext.saveGraphicsState()
        shadow.set()
        tileTop.setFill()
        shape.fill()
        NSGraphicsContext.restoreGraphicsState()
    }

    // The tile: white, faintly warm at the foot.
    NSGraphicsContext.saveGraphicsState()
    shape.addClip()
    NSGradient(starting: tileTop, ending: tileBottom)!.draw(in: body, angle: -90)
    NSGraphicsContext.restoreGraphicsState()

    // A hairline rim so the tile holds its edge on a white desktop.
    let rim = NSBezierPath(roundedRect: body.insetBy(dx: s * 0.002, dy: s * 0.002),
                           xRadius: radius, yRadius: radius)
    rim.lineWidth = max(1, s * 0.004)
    NSColor.black.withAlphaComponent(0.08).setStroke()
    rim.stroke()

    // The glyph, in units of its height g, as BrandMark lays it out: the
    // "d" is 0.86 wide, a 0.08 gap, the cursor 0.22. Small sizes draw it
    // bigger in the tile so it still reads at 16 pixels.
    let g = body.height * (small ? 0.66 : 0.52)
    let x0 = body.midX - g * 1.16 / 2 + body.width * 0.01
    let y0 = body.midY - g / 2   // the glyph's foot; AppKit's y runs upwards

    let d = NSBezierPath(ovalIn: NSRect(x: x0, y: y0, width: g * 0.74, height: g * 0.74))
    d.append(NSBezierPath(roundedRect: NSRect(x: x0 + g * 0.56, y: y0, width: g * 0.30, height: g),
                          xRadius: g * 0.15, yRadius: g * 0.15))
    d.windingRule = .nonZero
    NSGraphicsContext.saveGraphicsState()
    d.addClip()
    NSGradient(starting: markTop, ending: markBottom)!
        .draw(in: NSRect(x: x0, y: y0, width: g * 0.86, height: g), angle: -60)
    NSGraphicsContext.restoreGraphicsState()

    // The waveform in the bowl, running into the stem. Fewer, wider bars
    // at the smallest sizes, where six would blur into one.
    let bars: [CGFloat] = small ? [0.22, 0.42, 0.26] : [0.14, 0.28, 0.42, 0.30, 0.20, 0.10]
    let bw = g * (small ? 0.09 : 0.055), gap = g * (small ? 0.08 : 0.045)
    let total = CGFloat(bars.count) * bw + CGFloat(bars.count - 1) * gap
    var bx = x0 + (g * 0.78 - total) / 2
    let cy = y0 + g * 0.37
    NSColor.white.setFill()
    for h in bars {
        capsule(NSRect(x: bx, y: cy - g * h / 2, width: bw, height: g * h)).fill()
        bx += bw + gap
    }

    // The cursor: a stem with short caps, as tall as the bowl, where the
    // words land.
    let cx = x0 + g * (0.86 + 0.08 + 0.11)
    let ch = g * 0.70, cw = g * 0.07
    let cyMid = body.midY - g * 0.15
    let cursor = NSBezierPath(rect: NSRect(x: cx - cw / 2, y: cyMid - ch / 2, width: cw, height: ch))
    cursor.append(capsule(NSRect(x: cx - g * 0.11, y: cyMid + ch / 2 - cw, width: g * 0.22, height: cw)))
    cursor.append(capsule(NSRect(x: cx - g * 0.11, y: cyMid - ch / 2, width: g * 0.22, height: cw)))
    NSGraphicsContext.saveGraphicsState()
    cursor.addClip()
    NSGradient(starting: markTop, ending: markBottom)!
        .draw(in: NSRect(x: cx - g * 0.11, y: cyMid - ch / 2, width: g * 0.22, height: ch), angle: -90)
    NSGraphicsContext.restoreGraphicsState()

    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])!
}

// `swift tools/make_icon.swift preview.png` writes the 1024 pixel image only,
// for looking at a change before rebuilding the .icns.
if CommandLine.arguments[1].hasSuffix(".png") {
    try! draw(1024).write(to: out)
    try! draw(64).write(to: URL(fileURLWithPath: out.path.replacingOccurrences(of: ".png", with: "-64.png")))
    print(out.path)
    exit(0)
}

let fm = FileManager.default
let set = fm.temporaryDirectory.appendingPathComponent("AppIcon-\(getpid()).iconset")
try? fm.removeItem(at: set)
try! fm.createDirectory(at: set, withIntermediateDirectories: true)
for base in [16, 32, 128, 256, 512] {
    try! draw(base).write(to: set.appendingPathComponent("icon_\(base)x\(base).png"))
    try! draw(base * 2).write(to: set.appendingPathComponent("icon_\(base)x\(base)@2x.png"))
}
let p = Process()
p.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
p.arguments = ["-c", "icns", set.path, "-o", out.path]
try! p.run()
p.waitUntilExit()
try? fm.removeItem(at: set)
guard p.terminationStatus == 0 else { exit(p.terminationStatus) }
print(out.path)
