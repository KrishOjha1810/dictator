// The microphone, without Homebrew.
//
// This replaces sox's `rec` on the dictation path. sox is GPL-2.0-or-later, so
// it can never be shipped inside a product this small wants to be, and
// installing it pulls in nine libraries (flac, lame, libogg, libpng,
// libsndfile, libvorbis, mad, opus, opusfile) to record one mono stream that
// macOS already knows how to record. AVFoundation is on every Mac.
//
// It writes exactly what whisper.cpp wants and nothing else: 16000Hz, mono,
// 16-bit little-endian PCM in a WAV. Whisper resamples nothing, so a file in
// any other shape is either refused or quietly transcribed as noise.
//
// Boundaries belong to the caller. There is no silence detection here on
// purpose: this is push-to-talk, so the person holding the key is the
// boundary. Trimming leading quiet eats the first word (you start speaking as
// you press) and stopping on a pause cuts you off every time you stop to
// think while still holding the key.
//
//   dictator-rec <out.wav> [max-seconds]
//
// Records until SIGTERM or SIGINT, or until max-seconds, whichever is first.
import AVFoundation
import Foundation

let args = CommandLine.arguments

func say(_ m: String) {
    FileHandle.standardError.write((m + "\n").data(using: .utf8)!)
}

// Errors go to stderr and are kept by the caller, because an empty recording
// with no reason attached turns a one-line answer into an afternoon.
func fail(_ m: String) -> Never {
    say(m)
    exit(1)
}

guard args.count >= 2 else {
    fail("usage: dictator-rec <out.wav> [max-seconds]")
}
let out = URL(fileURLWithPath: args[1])
let maxSecs = args.count > 2 ? (Double(args[2]) ?? 120.0) : 120.0

// The level meter's own file, beside the recording. The indicator used to read
// the tail of the wav and do its own RMS, which only works while the file is
// being flushed; AVFoundation hands us the real input level for free, and a
// meter that is one flush behind is a meter that lies about whether the mic is
// open. Deleted on the way out so nothing can read a stale level.
let levelFile = URL(fileURLWithPath: args[1] + ".lvl")

// Ask before recording, rather than recording silence and blaming the mic.
// Already granted is the normal case: this process inherits the grant of
// whichever app is responsible for it (Dictator.app, when launched from the
// login item), so the prompt is a first-run path and not the usual one.
switch AVCaptureDevice.authorizationStatus(for: .audio) {
case .authorized:
    break
case .denied, .restricted:
    fail("microphone permission denied: System Settings, Privacy and Security, Microphone")
case .notDetermined:
    let waiting = DispatchSemaphore(value: 0)
    var granted = false
    AVCaptureDevice.requestAccess(for: .audio) { ok in
        granted = ok
        waiting.signal()
    }
    // Do not wait forever on a dialog nobody is looking at. Recording anyway
    // is what sox did, and an empty file with a line in stderr beats a hold
    // that never returns.
    if waiting.wait(timeout: .now() + 20) == .timedOut {
        say("microphone permission was never answered; recording anyway")
    } else if !granted {
        fail("microphone permission refused")
    }
@unknown default:
    break
}

let settings: [String: Any] = [
    AVFormatIDKey: Int(kAudioFormatLinearPCM),
    AVSampleRateKey: 16000.0,
    AVNumberOfChannelsKey: 1,
    AVLinearPCMBitDepthKey: 16,
    AVLinearPCMIsFloatKey: false,
    AVLinearPCMIsBigEndianKey: false,
    AVLinearPCMIsNonInterleaved: false,
]

let recorder: AVAudioRecorder
do {
    recorder = try AVAudioRecorder(url: out, settings: settings)
} catch {
    fail("could not open the microphone: \(error.localizedDescription)")
}
recorder.isMeteringEnabled = true
guard recorder.prepareToRecord() else {
    fail("could not prepare the recording at \(out.path)")
}
guard recorder.record(forDuration: maxSecs) else {
    fail("could not start recording")
}

// Stopping is what finalises the WAV header: the RIFF and data chunk sizes are
// written at stop, so a recorder that is SIGKILLed leaves a file whose header
// claims zero samples. That is why the signals below are handled rather than
// left to the default action, and why the caller should terminate and not kill.
var stopping = false
func finish(_ code: Int32) -> Never {
    if !stopping {
        stopping = true
        recorder.stop()
        try? FileManager.default.removeItem(at: levelFile)
    }
    exit(code)
}

// SIG_IGN first: the default action for SIGTERM kills us before the dispatch
// source ever sees it, and the file would be left with an empty header.
signal(SIGTERM, SIG_IGN)
signal(SIGINT, SIG_IGN)
let onTerm = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
let onInt = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
onTerm.setEventHandler { finish(0) }
onInt.setEventHandler { finish(0) }
onTerm.resume()
onInt.resume()

// 0..1, on the same curve the indicator already expects. averagePower is dB
// full scale (-160 to 0), so it becomes an amplitude first; the square root
// then keeps a quiet voice visibly moving the meter, because loudness is
// perceived nowhere near linearly and a linear meter barely twitches at the
// volume people actually dictate at.
func level() -> Double {
    recorder.updateMeters()
    let db = Double(recorder.averagePower(forChannel: 0))
    if db <= -80 { return 0 }
    let amplitude = pow(10.0, db / 20.0)
    return min(1.0, (amplitude / 0.183).squareRoot())
}

let meter = Timer(timeInterval: 0.05, repeats: true) { _ in
    if !recorder.isRecording {
        finish(0)                       // max-seconds reached, file is closed
    }
    try? String(format: "%.4f", level())
        .write(to: levelFile, atomically: true, encoding: .utf8)
}
RunLoop.main.add(meter, forMode: .common)
RunLoop.main.run()
