// Draw Dictator's app icon and pack it into an .icns.
//
//   swift tools/make_icon.swift native/app/AppIcon.icns
//
// The icon is drawn here rather than kept as a picture somebody exported
// once, so it can be changed in code review and rebuilt by anyone with the
// Command Line Tools. A rounded square in the app's accent colour (Theme.swift)
// with a white waveform: holding a key and talking, which is the whole app.
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

// The accent, the same numbers as Theme.accent.
let top = NSColor(srgbRed: 0.13, green: 0.60, blue: 0.53, alpha: 1)
let bottom = NSColor(srgbRed: 0.04, green: 0.42, blue: 0.37, alpha: 1)

func draw(_ px: Int) -> Data {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px,
                               bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                               isPlanar: false, colorSpaceName: .deviceRGB,
                               bytesPerRow: 0, bitsPerPixel: 0)!
    let ctx = NSGraphicsContext(bitmapImageRep: rep)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = ctx
    let s = CGFloat(px)

    // Apple's grid: the body is 824 of 1024, centred, with room for a shadow.
    let inset = s * 100 / 1024
    let body = NSRect(x: inset, y: inset, width: s - 2 * inset, height: s - 2 * inset)
    let radius = body.width * 0.225
    let shape = NSBezierPath(roundedRect: body, xRadius: radius, yRadius: radius)

    if px >= 64 {
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.28)
        shadow.shadowBlurRadius = s * 0.025
        shadow.shadowOffset = NSSize(width: 0, height: -s * 0.012)
        NSGraphicsContext.saveGraphicsState()
        shadow.set()
        bottom.setFill()
        shape.fill()
        NSGraphicsContext.restoreGraphicsState()
    }
    NSGradient(starting: top, ending: bottom)!.draw(in: shape, angle: -90)

    // A soft highlight across the top half, the way system icons catch light.
    NSGraphicsContext.saveGraphicsState()
    shape.addClip()
    NSGradient(colors: [NSColor.white.withAlphaComponent(0.16),
                        NSColor.white.withAlphaComponent(0.0)])!
        .draw(in: NSRect(x: body.minX, y: body.midY, width: body.width, height: body.height / 2),
              angle: -90)
    NSGraphicsContext.restoreGraphicsState()

    // The waveform: seven rounded bars, louder in the middle, uneven like a voice.
    let heights: [CGFloat] = [0.22, 0.46, 0.74, 0.52, 0.92, 0.62, 0.30]
    let n = CGFloat(heights.count)
    let span = body.width * 0.58
    let bar = span / (n * 1.5)
    let gap = (span - bar * n) / (n - 1)
    var x = body.midX - span / 2
    let maxH = body.height * 0.56
    for (i, h) in heights.enumerated() {
        let hh = max(bar, maxH * h)
        let r = NSRect(x: x, y: body.midY - hh / 2, width: bar, height: hh)
        let alpha: CGFloat = (i == 0 || i == heights.count - 1) ? 0.78 : 1.0
        NSColor.white.withAlphaComponent(alpha).setFill()
        NSBezierPath(roundedRect: r, xRadius: bar / 2, yRadius: bar / 2).fill()
        x += bar + gap
    }

    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])!
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
