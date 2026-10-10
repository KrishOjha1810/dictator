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
//
// EXIT CODES, because a truncated recording looks exactly like a whole one
//
//   0  it ended when it was meant to: the caller said stop, or max-seconds
//      came up. The file holds everything there was.
//   1  it never started. Nothing was recorded and stderr says why.
//   5  it started, recorded, and then something stopped it early. The file
//      holds PART of what was said.
//   6  the caller asked it to stop before the microphone was open. Nothing
//      was recorded and nothing was lost: the key was down for less time
//      than it takes to open a device.
//
// The third one is the reason this section exists. AVAudioRecorder stops on
// its own when the input device changes underneath it, which is what happens
// when a Bluetooth headset connects while somebody is mid sentence. The file
// that is left is a valid WAV holding the first few seconds, so every check
// downstream passes and the user is handed a fragment of their own sentence
// formatted as though it were the whole thought. Saying nothing here is the
// same class of mistake as a paste receipt that lies: the failure is silent
// and the wrong answer is the believable one.
import AVFoundation
import Foundation

// Kept in step with recorder.CUT_SHORT on the Python side. There is no way to
// share a constant across the two, so it is written down in both places and
// tests/test_record.py asserts they agree.
let CUT_SHORT: Int32 = 5
let NEVER_OPENED: Int32 = 6

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

/// Told when the recorder stops for a reason that was not us asking.
///
/// It holds no state and reads nothing outside itself on purpose: the decision
/// about what a stop MEANS needs the recorder's clock and the stop flag, both
/// of which live in the top level code below, so this only carries the event
/// out to a closure installed there.
final class Watcher: NSObject, AVAudioRecorderDelegate {
    var onStop: ((Bool, String) -> Void)?

    func audioRecorderDidFinishRecording(_ r: AVAudioRecorder,
                                         successfully flag: Bool) {
        onStop?(flag, "")
    }

    func audioRecorderEncodeErrorDidOccur(_ r: AVAudioRecorder, error: Error?) {
        onStop?(false, error?.localizedDescription
                ?? "the audio system reported an error")
    }
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

// Refuse the default action for these signals NOW, before anything slow.
//
// This used to sit after `recorder.record()`, which left a window running
// from process start, through the permission check, the AVAudioRecorder
// init, prepareToRecord and record, in which SIGTERM still meant immediate
// death. A hold shorter than that window was killed mid setup, and because
// the WAV header is only written at stop, the caller found a file claiming
// zero samples and nothing at all on stderr.
//
// That is not theoretical. In one real log five holds between 758ms and
// 2521ms came back as "no audio captured (0 bytes). the recorder said
// nothing", which is exactly the shape of this: no error, no audio, and a
// hold long enough that the person had already started talking.
//
// `asked` is read below: a stop that arrives before the device is open has
// nothing to finalise, so it exits saying so rather than pretending it
// recorded an empty room.
var open = false
signal(SIGTERM, SIG_IGN)
signal(SIGINT, SIG_IGN)
let onTerm = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
let onInt = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)

// Resumed here, with a handler that only has to know the device is not open
// yet. SIG_IGN alone is not enough: a dispatch source does not receive
// anything until it is resumed, so blocking the default action and resuming
// later means the signal is simply dropped and the process hangs with the
// microphone held. That is worse than the crash it replaced.
//
// Replaced below with the real handler once there is a header to write.
onTerm.setEventHandler { exit(NEVER_OPENED) }
onInt.setEventHandler { exit(NEVER_OPENED) }
onTerm.resume()
onInt.resume()

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

// How much audio is actually in the file, sampled by the meter below while the
// recorder is running. `currentTime` reads zero once it has stopped, so the
// last sample taken while it was alive is the only honest answer afterwards.
var captured = 0.0

// Stopping is what finalises the WAV header: the RIFF and data chunk sizes are
// written at stop, so a recorder that is SIGKILLed leaves a file whose header
// claims zero samples. That is why the signals below are handled rather than
// left to the default action, and why the caller should terminate and not kill.
//
// `stopping` also keeps the delegate quiet. Calling stop() makes AVFoundation
// report that recording finished, which is true and is not news: without the
// flag, every ordinary hold would end by telling the caller it had been cut
// short, which is a worse lie than the one this change exists to fix.
var stopping = false
func finish(_ code: Int32, _ why: String = "") -> Never {
    if !stopping {
        stopping = true
        if !why.isEmpty { say(why) }
        recorder.stop()
        try? FileManager.default.removeItem(at: levelFile)
    }
    exit(code)
}

/// Whether stopping now means we reached max-seconds rather than lost the input.
///
/// A quarter of a second of slack because the meter samples every 0.05s, so the
/// last reading before the cap is always a little short of it.
func reachedTheCap() -> Bool {
    return captured >= maxSecs - 0.25
}

func cutMessage(_ detail: String) -> String {
    let got = String(format: "%.1f", captured)
    return "the recording stopped on its own after \(got)s, before the caller "
        + "asked it to"
        + (detail.isEmpty ? "" : ": \(detail)")
        + ". The input device changed or something else took the microphone. "
        + "Only the audio up to that point is in the file."
}

let watcher = Watcher()
watcher.onStop = { ok, detail in
    // We asked for this, so there is nothing to report.
    if stopping { return }
    if ok && reachedTheCap() { finish(0) }
    finish(CUT_SHORT, cutMessage(detail))
}
recorder.delegate = watcher

// The device is up, so from here a stop has a header to write. The sources
// are already running; this only swaps what they do.
open = true
onTerm.setEventHandler { finish(0) }
onInt.setEventHandler { finish(0) }

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
    // The delegate above normally gets here first and says why. This is the
    // backstop for an input that simply goes away without telling anybody,
    // and it decides the same way: reaching max-seconds is the one ordinary
    // reason to stop on our own, and anything else means the file holds part
    // of a sentence while looking exactly like a whole one.
    guard recorder.isRecording else {
        if reachedTheCap() { finish(0) }
        finish(CUT_SHORT, cutMessage(""))
    }
    captured = recorder.currentTime
    try? String(format: "%.4f", level())
        .write(to: levelFile, atomically: true, encoding: .utf8)
}
RunLoop.main.add(meter, forMode: .common)
RunLoop.main.run()
