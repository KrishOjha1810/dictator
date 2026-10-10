// Quiet other audio while the microphone is open, and put it back after.
//
//   dictator-media quiet             prints "paused", "muted" or "none"
//   dictator-media restore paused    resumes what `quiet` paused
//   dictator-media restore muted     unmutes what `quiet` muted
//   dictator-media probe             prints what it can see, as JSON
//
// Music playing through the speakers is picked up by the microphone and ends
// up in the transcript. Pausing the player is the better fix, because nothing
// is missed, and it goes through MediaRemote, the private framework behind the
// Now Playing widget and the keyboard's play key. Apple restricted parts of it
// for apps that are not its own in macOS 15.4, so nothing here trusts it: a
// pause is checked by asking again, and when the player is still playing, or
// MediaRemote cannot say, the output is muted instead. Muting works for every
// source and needs no permission; the song just keeps going silently.
//
// The play key is never sent blind. It toggles, so pressing it when nothing is
// playing would START music in the middle of somebody's sentence.

import CoreAudio
import Foundation

// MARK: MediaRemote

private let mr = dlopen("/System/Library/PrivateFrameworks/MediaRemote.framework/MediaRemote",
                        RTLD_NOW)

private typealias IsPlayingFn = @convention(c) (DispatchQueue, @escaping @convention(block) (Bool) -> Void) -> Void
private typealias SendFn = @convention(c) (UInt32, CFDictionary?) -> Bool

private let kPlay: UInt32 = 0
private let kPause: UInt32 = 1

/// Whether the Now Playing app is playing. nil when MediaRemote did not
/// answer in time, which is not the same as "no".
private func nowPlaying(timeout: Double = 0.4) -> Bool? {
    guard let mr = mr, let sym = dlsym(mr, "MRMediaRemoteGetNowPlayingApplicationIsPlaying")
    else { return nil }
    let fn = unsafeBitCast(sym, to: IsPlayingFn.self)
    let done = DispatchSemaphore(value: 0)
    var answer: Bool? = nil
    fn(DispatchQueue.global()) { playing in
        answer = playing
        done.signal()
    }
    return done.wait(timeout: .now() + timeout) == .success ? answer : nil
}

private func send(_ command: UInt32) -> Bool {
    guard let mr = mr, let sym = dlsym(mr, "MRMediaRemoteSendCommand") else { return false }
    return unsafeBitCast(sym, to: SendFn.self)(command, nil)
}

// MARK: Core Audio

private func defaultOutput() -> AudioDeviceID? {
    var id = AudioDeviceID(0)
    var size = UInt32(MemoryLayout<AudioDeviceID>.size)
    var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDefaultOutputDevice,
                                          mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    let ok = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr,
                                        0, nil, &size, &id)
    return ok == noErr && id != 0 ? id : nil
}

/// Something is sending audio to the output device: music, a video, a call.
private func outputRunning(_ dev: AudioDeviceID) -> Bool {
    var running = UInt32(0)
    var size = UInt32(MemoryLayout<UInt32>.size)
    var addr = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyDeviceIsRunningSomewhere,
                                          mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    return AudioObjectGetPropertyData(dev, &addr, 0, nil, &size, &running) == noErr && running != 0
}

private var muteAddr = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyMute,
                                                  mScope: kAudioDevicePropertyScopeOutput,
                                                  mElement: kAudioObjectPropertyElementMain)

/// nil when the device has no mute control (some HDMI and AirPlay outputs).
private func muted(_ dev: AudioDeviceID) -> Bool? {
    guard AudioObjectHasProperty(dev, &muteAddr) else { return nil }
    var v = UInt32(0)
    var size = UInt32(MemoryLayout<UInt32>.size)
    return AudioObjectGetPropertyData(dev, &muteAddr, 0, nil, &size, &v) == noErr ? v != 0 : nil
}

private func setMuted(_ dev: AudioDeviceID, _ on: Bool) -> Bool {
    var settable = DarwinBoolean(false)
    guard AudioObjectHasProperty(dev, &muteAddr),
          AudioObjectIsPropertySettable(dev, &muteAddr, &settable) == noErr, settable.boolValue
    else { return false }
    var v = UInt32(on ? 1 : 0)
    return AudioObjectSetPropertyData(dev, &muteAddr, 0, nil,
                                      UInt32(MemoryLayout<UInt32>.size), &v) == noErr
}

// MARK: Commands

private func quiet() -> String {
    if nowPlaying() == true && send(kPause) {
        // Asked again, because a command MediaRemote accepted is not a
        // command the player obeyed.
        for _ in 0..<6 {
            usleep(50_000)
            if nowPlaying(timeout: 0.2) == false { return "paused" }
        }
    }
    guard let dev = defaultOutput(), outputRunning(dev), muted(dev) == false else { return "none" }
    return setMuted(dev, true) ? "muted" : "none"
}

private func restore(_ what: String) {
    switch what {
    case "paused":
        // Only if it is still paused: the user may have started something
        // else, or stopped it for good, while they talked.
        if nowPlaying() == false { _ = send(kPlay) }
    case "muted":
        if let dev = defaultOutput(), muted(dev) == true { _ = setMuted(dev, false) }
    default:
        break
    }
}

let args = CommandLine.arguments.dropFirst()
switch args.first {
case "quiet":
    print(quiet())
case "restore":
    restore(args.dropFirst().first ?? "")
case "probe":
    let dev = defaultOutput()
    let playing = nowPlaying()
    print("{\"nowPlaying\": \(playing.map { "\($0)" } ?? "null"), "
          + "\"outputRunning\": \(dev.map(outputRunning) ?? false), "
          + "\"muted\": \(dev.flatMap(muted).map { "\($0)" } ?? "null")}")
default:
    FileHandle.standardError.write("usage: dictator-media quiet | restore paused|muted | probe\n"
        .data(using: .utf8)!)
    exit(2)
}
