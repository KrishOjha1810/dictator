// Recording a meeting: the other people, and you, as two separate tracks.
//
// Dictation records the microphone, which is only ever your own voice. A
// meeting is mostly the other people, and their audio arrives at the speakers,
// not at the microphone. So this needs system audio, which macOS treats as a
// more invasive thing than the microphone and puts behind its own permission.
//
// Two APIs on this machine can do it:
//
//   ScreenCaptureKit      macOS 13+, needs the Screen Recording permission,
//                         which is an ordinary TCC grant any self-signed app
//                         can ask for. Since macOS 15 the same stream can also
//                         capture the microphone, as a SEPARATE output, which
//                         is what gives us two tracks with one permission
//                         prompt, one clock and no mixing.
//   Core Audio taps       AudioHardwareCreateProcessTap, macOS 14.2+. Also
//                         works, also free, but it hands you one mixed stream
//                         per aggregate device and you build the device
//                         yourself. See docs/findings.md.
//
// Neither needs a paid Apple Developer account, which was the constraint that
// could have killed the whole feature.
//
// Two tracks, not one mixed track, on purpose. Which file a sentence came out
// of is the only speaker labelling that is both free and honest: the
// microphone is you, the system is them. Anything finer is diarization, which
// is a research problem.
//
// Written as 16000Hz mono 16-bit WAV, which is exactly what whisper wants, so
// nothing downstream has to resample. The conversion from whatever the system
// hands us (48kHz stereo float, usually) happens here, once, while recording.
//
//   dictator-meeting <session-dir> [max-seconds]
//
// Records until SIGTERM or SIGINT, or until max-seconds. It never starts on
// its own and it never hides: macOS shows its own screen recording indicator
// in the menu bar for as long as this is capturing, and that is deliberate.
import AVFoundation
import AppKit
import CoreMedia
import Foundation
import ScreenCaptureKit

let args = CommandLine.arguments

guard args.count >= 2 else {
    FileHandle.standardError.write(
        ("usage: dictator-meeting <session-dir> [max-seconds]\n"
         + "       dictator-meeting --check <dir>\n").data(using: .utf8)!)
    exit(1)
}

// --check answers "would recording work right now" without recording anything
// and without raising a dialog, which is what the permissions walkthrough
// polls while the user is in System Settings. It has to be a separate process
// each time: TCC answers a process once and caches it, so a long lived checker
// would keep reporting the answer it got before the switch was flipped.
if args[1] == "--check" {
    guard args.count >= 3 else { exit(1) }
    let out = URL(fileURLWithPath: args[2], isDirectory: true)
    try? FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
    let mic = AVCaptureDevice.authorizationStatus(for: .audio)
    let payload: [String: Any] = [
        "screen": CGPreflightScreenCaptureAccess(),
        "mic": mic == .authorized,
        "mic_asked": mic != .notDetermined,
    ]
    if let d = try? JSONSerialization.data(withJSONObject: payload) {
        try? d.write(to: out.appendingPathComponent("check.json"), options: .atomic)
    }
    exit(0)
}

// --selftest writes a known tone through exactly the conversion the capture
// feeds, and needs no permission at all. That matters more here than it
// usually would: system audio is behind a grant macOS only gives by hand, so
// without this the resampling, the downmix and the WAV writing would ship
// having never run once.
let selftest = args[1] == "--selftest"
let dir = URL(fileURLWithPath: args[selftest ? 2 : 1], isDirectory: true)
let maxSecs = args.count > (selftest ? 3 : 2)
    ? (Double(args[selftest ? 3 : 2]) ?? 14400.0) : 14400.0
try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

// Everything this says goes to a file beside the recording as well as to
// stderr. The recorder is usually started through LaunchServices so that macOS
// holds IT responsible for the permission rather than whatever terminal
// happened to be the parent, and LaunchServices throws stderr away. A meeting
// that recorded nothing with the reason discarded is the failure that turns a
// one line answer into an afternoon, which the dictation recorder already
// learned once.
let errFile = dir.appendingPathComponent("recorder.err")

func say(_ m: String) {
    let line = m + "\n"
    FileHandle.standardError.write(line.data(using: .utf8)!)
    if let h = try? FileHandle(forWritingTo: errFile) {
        h.seekToEndOfFile()
        h.write(line.data(using: .utf8)!)
        try? h.close()
    } else {
        try? line.write(to: errFile, atomically: true, encoding: .utf8)
    }
}

func fail(_ m: String, _ code: Int32 = 1) -> Never {
    say(m)
    exit(code)
}

// Exit codes the Python side reads, so it can tell "you have not granted this
// yet" from "this broke", and say something different for each.
let EXIT_NO_SCREEN = 3
let EXIT_NO_MIC = 4

// ---- one track, from whatever format it arrives in to what whisper wants ----

/// A WAV being written, plus the converter that gets samples into its shape.
///
/// The input format is read from the sample buffer rather than assumed.
/// ScreenCaptureKit hands system audio over as 48kHz stereo float and the
/// microphone in whatever the device's native format is, and those are not the
/// same, so each track owns its own converter.
final class Track {
    let name: String
    // Optional so it can be RELEASED before the process exits, which is the
    // only thing that writes the WAV's header. The dictation recorder learned
    // the same lesson from the other end: a file that is never closed properly
    // is a file whose header says it holds no audio, whatever is in it.
    private var file: AVAudioFile?
    private var conv: AVAudioConverter?
    private(set) var frames: Int64 = 0
    private(set) var level: Float = 0
    private let lock = NSLock()

    init(_ name: String, at url: URL) throws {
        self.name = name
        file = try AVAudioFile(forWriting: url, settings: [
            AVFormatIDKey: Int(kAudioFormatLinearPCM),
            AVSampleRateKey: 16000.0,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false,
        ])
    }

    var seconds: Double { Double(frames) / 16000.0 }

    /// Finish the file. After this the track ignores anything else it is given,
    /// because a sample buffer still in flight on the capture queue must not be
    /// able to reopen what has just been closed.
    func close() {
        lock.lock()
        defer { lock.unlock() }
        file = nil
        conv = nil
    }

    func append(_ sb: CMSampleBuffer) {
        guard let input = Track.pcm(from: sb) else { return }
        append(input)
    }

    /// The half that can be tested without a permission, and is: see --selftest
    /// and tests/test_meeting.py. Capturing system audio needs a grant macOS
    /// only gives by hand, so the conversion underneath it would otherwise
    /// have been shipped having never converted anything.
    func append(_ input: AVAudioPCMBuffer) {
        guard input.frameLength > 0 else { return }
        lock.lock()
        defer { lock.unlock() }
        guard let file else { return }
        let want = file.processingFormat
        if conv == nil || conv!.inputFormat != input.format {
            conv = AVAudioConverter(from: input.format, to: want)
        }
        guard let conv else { return }
        let ratio = want.sampleRate / input.format.sampleRate
        let cap = AVAudioFrameCount(Double(input.frameLength) * ratio) + 2048
        guard let out = AVAudioPCMBuffer(pcmFormat: want, frameCapacity: cap) else { return }
        var err: NSError?
        var handed = false
        conv.convert(to: out, error: &err) { _, status in
            if handed {
                status.pointee = .noDataNow
                return nil
            }
            handed = true
            status.pointee = .haveData
            return input
        }
        if err != nil || out.frameLength == 0 { return }
        do {
            try file.write(from: out)
            frames += Int64(out.frameLength)
            level = Track.peak(out)
        } catch {
            say("\(name): could not write: \(error.localizedDescription)")
        }
    }

    /// Wrap a CMSampleBuffer's audio in something AVAudioConverter will take.
    private static func pcm(from sb: CMSampleBuffer) -> AVAudioPCMBuffer? {
        guard let fd = CMSampleBufferGetFormatDescription(sb),
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fd),
              let fmt = AVAudioFormat(streamDescription: asbd) else { return nil }
        let n = AVAudioFrameCount(CMSampleBufferGetNumSamples(sb))
        guard n > 0, let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: n)
        else { return nil }
        buf.frameLength = n
        let st = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sb, at: 0, frameCount: Int32(n), into: buf.mutableAudioBufferList)
        return st == noErr ? buf : nil
    }

    /// 0..1 on the same square-root curve the dictation meter uses, so a quiet
    /// voice still visibly moves a meter drawn from this.
    private static func peak(_ b: AVAudioPCMBuffer) -> Float {
        guard let ch = b.floatChannelData?[0] else { return 0 }
        var m: Float = 0
        for i in 0..<Int(b.frameLength) {
            let v = abs(ch[i])
            if v > m { m = v }
        }
        return min(1.0, sqrt(m))
    }
}

// ---- proving the conversion, with no permission involved ------------------

/// Write a known tone through both tracks in the exact shape ScreenCaptureKit
/// delivers, and report what came out.
///
/// The capture itself cannot be exercised without a grant macOS only gives by
/// hand, so this exercises everything downstream of it: 48kHz stereo float in,
/// 16kHz mono 16-bit out, resampled and downmixed by the same code path the
/// real sample buffers take. A conversion that has never converted anything is
/// the kind of thing that ships broken and is blamed on the capture.
func selfTest() -> Never {
    let seconds = 2.0
    let rate = 48000.0
    guard let inFmt = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                                    sampleRate: rate, channels: 2,
                                    interleaved: false),
          let buf = AVAudioPCMBuffer(pcmFormat: inFmt,
                                     frameCapacity: AVAudioFrameCount(rate * seconds))
    else { fail("selftest: could not make a buffer") }
    buf.frameLength = buf.frameCapacity
    // 440Hz at half scale, which is well under Nyquist at 16kHz so resampling
    // must keep it. A tone above 8kHz would be lost legitimately and would
    // make this test lie in the comfortable direction.
    for ch in 0..<2 {
        guard let p = buf.floatChannelData?[ch] else { continue }
        for i in 0..<Int(buf.frameLength) {
            p[i] = 0.5 * sinf(Float(2.0 * Double.pi * 440.0 * Double(i) / rate))
        }
    }
    do {
        them = try Track("them", at: dir.appendingPathComponent("them.wav"))
        me = try Track("me", at: dir.appendingPathComponent("me.wav"))
    } catch {
        fail("selftest: could not open the files: \(error.localizedDescription)")
    }
    them.append(buf)
    me.append(buf)
    let levels = [Double(them.level), Double(me.level)]
    let secs = [them.seconds, me.seconds]
    them.close()
    me.close()
    let out: [String: Any] = ["them_seconds": secs[0], "me_seconds": secs[1],
                              "them_level": levels[0], "me_level": levels[1]]
    if let d = try? JSONSerialization.data(withJSONObject: out) {
        try? d.write(to: dir.appendingPathComponent("selftest.json"),
                     options: .atomic)
    }
    exit(0)
}

// ---- permissions, asked for by name and never assumed --------------------

// Screen Recording is the permission that carries system audio. There is no
// separate "system audio" grant to ask for: capturing what comes out of the
// speakers is, as far as macOS is concerned, the same privilege as capturing
// what is on the screen, and the dialog says so in those words. Asking is the
// honest thing to do even though this captures no pixels.
//
// This has to be a real NSApplication, and that is not decoration. Measured
// here: the identical code as a plain command line binary, correctly signed,
// inside a correctly identified bundle, launched through LaunchServices, never
// got a dialog at all. SCShareableContent answered "The user declined TCCs for
// application, window, display capture" instantly and macOS wrote no row for
// the app, so it did not even appear in the Screen Recording list for somebody
// to switch on. There was nothing the user could do, and nothing to see.
// .accessory keeps it out of the Dock while still giving it the application
// identity the dialog is presented to.
let nsapp = NSApplication.shared
nsapp.setActivationPolicy(.accessory)

/// Ask for the microphone, but only once system audio is already allowed.
///
/// ONE prompt at a time, deliberately. Asking for both at once auto-denied the
/// second one here: the screen recording request returns before the user has
/// answered it, the microphone request then arrives while a decision is
/// pending, and macOS wrote a DENIED row for the microphone without ever
/// showing a dialog. A denied row is far worse than no row, because the app
/// never asks again and the user is left with a switch to find rather than a
/// question to answer.
func askForMicrophone() {
    switch AVCaptureDevice.authorizationStatus(for: .audio) {
    case .authorized:
        return
    case .denied, .restricted:
        giveUp("microphone permission denied: System Settings, Privacy and "
             + "Security, Microphone", "no-mic", Int32(EXIT_NO_MIC))
    case .notDetermined:
        let waiting = DispatchSemaphore(value: 0)
        var granted = false
        AVCaptureDevice.requestAccess(for: .audio) { ok in
            granted = ok
            waiting.signal()
        }
        if waiting.wait(timeout: .now() + 60) == .timedOut {
            giveUp("microphone permission was never answered", "no-mic",
                   Int32(EXIT_NO_MIC))
        } else if !granted {
            giveUp("microphone permission refused", "no-mic",
                   Int32(EXIT_NO_MIC))
        }
    @unknown default:
        return
    }
}

// ---- the two tracks ------------------------------------------------------

// Opened only once both permissions are in hand, so a run that is really a
// permission prompt does not leave two empty WAVs behind that look like a
// meeting nobody said anything in.
var them: Track!
var me: Track!

func openTracks() {
    do {
        them = try Track("them", at: dir.appendingPathComponent("them.wav"))
        me = try Track("me", at: dir.appendingPathComponent("me.wav"))
    } catch {
        fail("could not open the recording files: \(error.localizedDescription)")
    }
}

// Before anything asks for a permission, because the whole point of the self
// test is that it needs none.
if selftest {
    selfTest()
}

let started = Date()
let statusFile = dir.appendingPathComponent("status.json")

// What the heartbeat republishes. It used to publish the literal word
// "recording" from half a second after launch, before SCShareableContent had
// answered and before the microphone dialog had been shown, so the Python side
// saw success and told the user the meeting was being recorded while the
// recorder was still asking permission to record it. If the user then said no,
// the recorder exited with no audio and `dictator meeting stop` answered "No
// meeting is being recorded". The one failure this file's own docstrings say
// it must never make.
var phase = "starting"

func writeStatus(_ state: String) {
    let payload: [String: Any] = [
        "state": state,
        "started": started.timeIntervalSince1970,
        "elapsed": Date().timeIntervalSince(started),
        "them_seconds": them?.seconds ?? 0,
        "me_seconds": me?.seconds ?? 0,
        "them_level": Double(them?.level ?? 0),
        "me_level": Double(me?.level ?? 0),
        "pid": ProcessInfo.processInfo.processIdentifier,
    ]
    guard let d = try? JSONSerialization.data(withJSONObject: payload) else { return }
    // Atomic, because the Python side reads this while it is being written and
    // a half-written file reads as a crashed recorder.
    try? d.write(to: statusFile, options: .atomic)
}

// Say why it is giving up in a form the Python side can match on. It used to
// grep this process's own prose out of the log, which matched the line saying
// "asking for Screen Recording" as well as the line saying it had been
// refused, so an ordinary first run looked like a refusal and the working
// directory of a live recorder was deleted underneath it. Prose is for people.
func giveUp(_ m: String, _ kind: String, _ code: Int32) -> Never {
    phase = kind
    writeStatus(kind)
    say(m)
    exit(code)
}


final class Sink: NSObject, SCStreamOutput, SCStreamDelegate {
    func stream(_ s: SCStream, didOutputSampleBuffer sb: CMSampleBuffer,
                of type: SCStreamOutputType) {
        guard CMSampleBufferDataIsReady(sb) else { return }
        switch type {
        case .audio: them?.append(sb)
        case .microphone: me?.append(sb)
        default: break          // video frames are not consumed, see below
        }
    }

    func stream(_ s: SCStream, didStopWithError error: Error) {
        say("the capture stopped: \(error.localizedDescription)")
        finish(1)
    }
}

let sink = Sink()
var stream: SCStream?
var stopping = false

func finish(_ code: Int32) -> Never {
    if !stopping {
        stopping = true
        let waiting = DispatchSemaphore(value: 0)
        stream?.stopCapture { _ in waiting.signal() }
        _ = waiting.wait(timeout: .now() + 5)
        // Close the files BEFORE exiting. Releasing the AVAudioFile is what
        // writes the WAV header, and a process that exits with them still held
        // leaves two recordings whose headers claim to hold nothing.
        them?.close()
        me?.close()
        writeStatus("stopped")
    }
    exit(code)
}

// SIG_IGN first, for the same reason the dictation recorder does it: the
// default action kills the process before the dispatch source sees the signal,
// and the WAV headers are written when the files are closed.
signal(SIGTERM, SIG_IGN)
signal(SIGINT, SIG_IGN)
let onTerm = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
let onInt = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
onTerm.setEventHandler { finish(0) }
onInt.setEventHandler { finish(0) }
onTerm.resume()
onInt.resume()

// SCShareableContent is also the permission check that cannot be faked: it
// returns an error rather than an empty list when Screen Recording is missing,
// and asking for it is what raises the dialog.
func begin() {
if !CGPreflightScreenCaptureAccess() {
    say("asking for Screen Recording, which is the permission that carries "
        + "system audio")
    // Queues the dialog and returns the CURRENT answer, so the return value is
    // not the decision, and a grant only takes effect for a NEW process. The
    // caller starts us again once the toggle flips.
    _ = CGRequestScreenCaptureAccess()
}
SCShareableContent.getExcludingDesktopWindows(false, onScreenWindowsOnly: false) {
    content, error in
    if let error {
        giveUp("cannot see the system audio: \(error.localizedDescription)",
               "no-screen", Int32(EXIT_NO_SCREEN))
    }
    guard let display = content?.displays.first else {
        say("no display to attach the audio capture to")
        exit(1)
    }
    // Only now, with system audio already allowed, is the second dialog safe
    // to raise. See askForMicrophone.
    askForMicrophone()
    openTracks()

    // A display filter, because system audio is captured per display share and
    // there is no audio-only filter. The video side is made as small and as
    // slow as it is allowed to be (2x2 pixels, one frame every two seconds)
    // and the frames are never read, so nothing is ever recorded of the
    // screen. It is not free, but it is close enough to free to measure as
    // noise, and it is the price of the one API that does this without a
    // driver or a paid account.
    let filter = SCContentFilter(display: display, excludingApplications: [],
                                 exceptingWindows: [])
    let cfg = SCStreamConfiguration()
    cfg.capturesAudio = true
    cfg.sampleRate = 48000
    cfg.channelCount = 2
    // Our own output would otherwise be recorded back into the meeting, which
    // is how a readback ends up transcribed as something somebody said.
    cfg.excludesCurrentProcessAudio = true
    cfg.captureMicrophone = true
    cfg.width = 2
    cfg.height = 2
    cfg.minimumFrameInterval = CMTime(value: 2, timescale: 1)
    cfg.queueDepth = 5

    let s = SCStream(filter: filter, configuration: cfg, delegate: sink)
    stream = s
    do {
        try s.addStreamOutput(sink, type: .audio,
                              sampleHandlerQueue: DispatchQueue(label: "them"))
        try s.addStreamOutput(sink, type: .microphone,
                              sampleHandlerQueue: DispatchQueue(label: "me"))
    } catch {
        say("could not attach the audio outputs: \(error.localizedDescription)")
        exit(1)
    }
    s.startCapture { err in
        if let err {
            say("could not start capturing: \(err.localizedDescription)")
            exit(1)
        }
        phase = "recording"
        writeStatus(phase)
        say("recording. macOS shows a screen recording indicator in the menu "
            + "bar for as long as this runs.")
    }
}
}

// Heartbeat. A meeting runs for an hour, and the only honest answer to "is it
// still recording" is a number that keeps moving, so this publishes seconds
// captured on each track rather than a flag that was true once.
let beat = Timer(timeInterval: 0.5, repeats: true) { _ in
    if Date().timeIntervalSince(started) >= maxSecs {
        say("reached the maximum length, stopping")
        finish(0)
    }
    writeStatus(phase)
}
RunLoop.main.add(beat, forMode: .common)

// The permission work runs on the application's own run loop rather than
// before it starts, because a TCC dialog is presented to a running
// application. Asking before nsapp.run() is what produced an instant refusal
// with no dialog and no entry in the Screen Recording list.
DispatchQueue.main.async { begin() }
nsapp.run()
