// Draw Dictator's app icon and pack it into an .icns.
//
//   swift tools/make_icon.swift native/app/AppIcon.icns
//
// The icon is drawn here rather than kept as a picture somebody exported
// once, so it can be changed in code review and rebuilt by anyone with the
// Command Line Tools. A deep indigo-to-teal square with a white microphone
// whose grille is lines of text, and a glowing cursor beside it: speech
// becoming writing, which is the whole app.
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

// Deep indigo into violet into teal: a night sky the white microphone stands
// out against in a Dock full of white and blue icons.
// Teal into deep slate. The ramp used to run through a saturated violet,
// which is the single most recognisable mark of a generated interface and
// the first thing anyone said about this icon. Teal is the one colour the
// product means something by (the microphone is live); the rest is the
// depth that keeps a 32 point icon from dissolving in the Dock.
let deep   = NSColor(srgbRed: 0.055, green: 0.125, blue: 0.150, alpha: 1)
let violet = NSColor(srgbRed: 0.090, green: 0.330, blue: 0.390, alpha: 1)
let teal   = NSColor(srgbRed: 0.100, green: 0.720, blue: 0.690, alpha: 1)
let ink    = NSColor(srgbRed: 0.070, green: 0.235, blue: 0.280, alpha: 1)
let slateTop    = NSColor(srgbRed: 0.231, green: 0.247, blue: 0.267, alpha: 1)
let slateBottom = NSColor(srgbRed: 0.102, green: 0.114, blue: 0.129, alpha: 1)

func capsule(_ r: NSRect) -> NSBezierPath {
    NSBezierPath(roundedRect: r, xRadius: r.width / 2, yRadius: r.width / 2)
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
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.35)
        shadow.shadowBlurRadius = s * 0.03
        shadow.shadowOffset = NSSize(width: 0, height: -s * 0.014)
        NSGraphicsContext.saveGraphicsState()
        shadow.set()
        deep.setFill()
        shape.fill()
        NSGraphicsContext.restoreGraphicsState()
    }

    // Background: a dark slate tile with a little light from above, and
    // nothing else. It was a diagonal teal to violet to indigo ramp, which
    // is the look every generated app icon has; the mark is the microphone,
    // so the tile's job is to stay out of its way and to read at 32 points
    // in a Dock full of saturated squares by being the quiet one.
    NSGraphicsContext.saveGraphicsState()
    shape.addClip()
    NSGradient(colors: [slateTop, slateBottom], atLocations: [0, 1],
               colorSpace: .sRGB)!.draw(in: body, angle: -90)
    NSGradient(colors: [NSColor.white.withAlphaComponent(0.10),
                        NSColor.white.withAlphaComponent(0.0)])!
        .draw(fromCenter: NSPoint(x: body.midX, y: body.maxY), radius: 0,
              toCenter: NSPoint(x: body.midX, y: body.maxY),
              radius: body.width * 0.9, options: [])
    NSGraphicsContext.restoreGraphicsState()

    // A thin glassy rim, brighter at the top.
    if !small {
        NSGraphicsContext.saveGraphicsState()
        let rim = NSBezierPath(roundedRect: body.insetBy(dx: s * 0.004, dy: s * 0.004),
                               xRadius: radius, yRadius: radius)
        rim.lineWidth = s * 0.006
        NSColor.white.withAlphaComponent(0.22).setStroke()
        rim.stroke()
        NSGraphicsContext.restoreGraphicsState()
    }

    // The microphone: a glossy white capsule on a stand.
    let mw = body.width * 0.27, mh = body.height * 0.40
    let mic = NSRect(x: body.midX - mw / 2,
                     y: body.midY - mh / 2 + body.height * 0.10, width: mw, height: mh)
    let micShadow = NSShadow()
    micShadow.shadowColor = NSColor.black.withAlphaComponent(0.30)
    micShadow.shadowBlurRadius = s * 0.035
    micShadow.shadowOffset = NSSize(width: 0, height: -s * 0.018)
    NSGraphicsContext.saveGraphicsState()
    if !small { micShadow.set() }
    NSColor.white.setFill()
    capsule(mic).fill()
    NSGraphicsContext.restoreGraphicsState()
    // Soft shading on the capsule so it reads as round, not flat.
    NSGraphicsContext.saveGraphicsState()
    capsule(mic).addClip()
    NSGradient(colors: [NSColor.white, NSColor(srgbRed: 0.88, green: 0.88, blue: 0.96, alpha: 1)])!
        .draw(in: mic, angle: 0)
    NSGraphicsContext.restoreGraphicsState()

    // The stand: a U around the capsule, a stem and a foot.
    let stand = NSBezierPath()
    let uw = mw * 1.55
    let uTop = mic.midY - mh * 0.02
    let uRect = NSRect(x: mic.midX - uw / 2, y: mic.minY - mh * 0.20, width: uw, height: (uTop - (mic.minY - mh * 0.20)) * 2)
    stand.appendArc(withCenter: NSPoint(x: uRect.midX, y: uTop), radius: uw / 2,
                    startAngle: 180, endAngle: 360, clockwise: false)
    let stemTop = uTop - uw / 2
    let stemBottom = body.minY + body.height * 0.17
    stand.move(to: NSPoint(x: mic.midX, y: stemTop))
    stand.line(to: NSPoint(x: mic.midX, y: stemBottom))
    stand.move(to: NSPoint(x: mic.midX - mw * 0.55, y: stemBottom))
    stand.line(to: NSPoint(x: mic.midX + mw * 0.55, y: stemBottom))
    stand.lineWidth = body.width * (small ? 0.07 : 0.045)
    stand.lineCapStyle = .round
    NSGraphicsContext.saveGraphicsState()
    if !small { micShadow.set() }
    NSColor.white.setStroke()
    stand.stroke()
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
