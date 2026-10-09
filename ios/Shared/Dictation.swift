// Speech into text on iOS, with no model of our own.
//
// The Mac build carries whisper.cpp and parakeet and about 2GB of weights. A
// keyboard extension cannot: iOS gives an extension a memory ceiling in the
// tens of megabytes and kills it for crossing one. That was recorded as the
// reason mobile was not possible (issue #9).
//
// It is not the reason any more. `SpeechTranscriber` arrived in iOS 26 and does
// its work in a system process, so the extension ships no weights and holds no
// model. It costs accuracy and the cost is measured, on this project's own
// references, in docs/ios.md: 18.0% WER against 3.6% for the Mac pipeline, and
// 31.6% against 8.9% on the holds that contain Hindi words.
//
// What is still unknown, and is the whole reason this target exists, is whether
// an extension is allowed to open the microphone at all. `Probe` answers that
// on a real phone and reports each step separately, because "it did not work"
// without a step name is not a finding.

import AVFoundation
import Foundation
import Speech

/// Which locale to transcribe in. `en_IN` and not `hi_IN` on purpose: Apple has
/// no Hindi in `SpeechTranscriber`, and routing Hinglish through the Hindi
/// `DictationTranscriber` instead scored 69.2% WER because it writes English
/// technical words phonetically in Devanagari ("Slack summary" came back as
/// "slik smit"). Indian English keeps the English half intact and romanises the
/// Hindi half by itself, which is the shape this product wants.
public let preferredLocale = Locale(identifier: "en_IN")

/// One step of the probe, named so a failure says which step failed.
public struct Step: Sendable, Identifiable {
    public let id = UUID()
    public let name: String
    public let ok: Bool
    public let detail: String
}

public enum DictationError: Error, CustomStringConvertible {
    case localeUnsupported(String)
    case assetsMissing(String)
    case noAudioFormat
    case converterRefused

    public var description: String {
        switch self {
        case .localeUnsupported(let l): return "\(l) is not a locale SpeechTranscriber supports"
        case .assetsMissing(let l): return "the model for \(l) is not installed and could not be fetched"
        case .noAudioFormat: return "no audio format the transcriber and the microphone both accept"
        case .converterRefused: return "the microphone format could not be converted to the analyser's"
        }
    }
}

/// Live microphone to text. One instance per session; call `stop()` to finish.
///
/// Deliberately not an actor: `AVAudioEngine`'s tap calls back on a realtime
/// audio thread, and the only thing that thread does here is convert a buffer
/// and yield it to a stream, both of which are safe to do there. Anything that
/// awaits would not be.
public final class Dictation: @unchecked Sendable {
    private let transcriber: SpeechTranscriber
    private let analyzer: SpeechAnalyzer
    private let engine = AVAudioEngine()
    private var continuation: AsyncStream<AnalyzerInput>.Continuation?
    private var converter: AVAudioConverter?
    private var analyzerFormat: AVAudioFormat?
    private var collector: Task<Void, Never>?

    /// Everything the recogniser has committed to. Main actor isolated
    /// because the only thing that reads it draws it.
    @MainActor public private(set) var text: String = ""

    /// The sentence so far including the part still being revised. For showing,
    /// never for typing: a volatile result is a guess that gets replaced, and
    /// anything built on it has to be unbuilt.
    @MainActor public var onPartial: ((String) -> Void)?

    /// Settled text, only ever growing. This is the one safe to type.
    @MainActor public var onFinal: ((String) -> Void)?

    public init(locale: Locale = preferredLocale) {
        // `progressiveTranscription` so partial results arrive while the key is
        // still held. The Mac build shows nothing until the hold ends and that
        // is the single most complained about thing about it.
        transcriber = SpeechTranscriber(locale: locale, preset: .progressiveTranscription)
        analyzer = SpeechAnalyzer(modules: [transcriber])
    }

    /// Make sure the locale's model is on the device, downloading it if iOS
    /// offers to. Returns what it had to do, for the probe to report.
    public static func ensureModel(locale: Locale = preferredLocale) async throws -> String {
        let supported = await SpeechTranscriber.supportedLocales.map(\.identifier)
        guard supported.contains(locale.identifier) else {
            throw DictationError.localeUnsupported(locale.identifier)
        }
        let installed = await SpeechTranscriber.installedLocales.map(\.identifier)
        if installed.contains(locale.identifier) { return "already installed" }

        let module = SpeechTranscriber(locale: locale, preset: .progressiveTranscription)
        guard let request = try await AssetInventory.assetInstallationRequest(supporting: [module]) else {
            // No request offered and not installed is a dead end rather than a
            // slow path, so say so instead of waiting for something to happen.
            throw DictationError.assetsMissing(locale.identifier)
        }
        try await request.downloadAndInstall()
        return "downloaded"
    }

    /// Open the microphone and start transcribing. Throws if any part refuses,
    /// which inside a keyboard extension is the thing worth knowing.
    public func start() async throws {
        let session = AVAudioSession.sharedInstance()
        // `.record` and not `.playAndRecord`: a keyboard that takes over audio
        // playback would stop the user's music for no reason. `.duckOthers`
        // lowers it instead, and `.allowBluetooth` is there because a headset
        // mic is the common case for anyone dictating in public.
        try session.setCategory(.record, mode: .measurement,
                                options: [.duckOthers, .allowBluetoothHFP])
        try session.setActive(true, options: .notifyOthersOnDeactivation)

        guard let analyzerFormat = await SpeechAnalyzer.bestAvailableAudioFormat(
            compatibleWith: [transcriber]) else {
            throw DictationError.noAudioFormat
        }
        self.analyzerFormat = analyzerFormat

        let (stream, continuation) = AsyncStream<AnalyzerInput>.makeStream()
        self.continuation = continuation

        collector = Task { [transcriber] in
            // A volatile result is replaced by the next one; a final result is
            // appended. Treating both the same is what makes naive versions of
            // this repeat words as you speak.
            var settled = ""
            do {
                for try await result in transcriber.results {
                    let piece = String(result.text.characters)
                    if result.isFinal {
                        settled += piece
                        await self.settle(settled)
                    } else {
                        await self.show(settled + piece)
                    }
                }
            } catch {
                // A cancelled stream is how `stop()` ends, not a failure, and
                // whatever was settled before it is still the answer.
            }
        }

        let input = engine.inputNode
        let micFormat = input.outputFormat(forBus: 0)
        guard let converter = AVAudioConverter(from: micFormat, to: analyzerFormat) else {
            throw DictationError.converterRefused
        }
        self.converter = converter

        input.installTap(onBus: 0, bufferSize: 4096, format: micFormat) { [weak self] buffer, _ in
            guard let self, let converted = self.convert(buffer) else { return }
            self.continuation?.yield(AnalyzerInput(buffer: converted))
        }

        engine.prepare()
        try engine.start()
        try await analyzer.start(inputSequence: stream)
    }

    /// Stop recording and return everything that was said.
    @discardableResult
    public func stop() async -> String {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        continuation?.finish()
        try? await analyzer.finalizeAndFinishThroughEndOfInput()
        // Wait for the collector rather than cancelling it. `finalizeAnd...`
        // returns when the analyser is done, not when the last result has been
        // read off the stream, and cancelling here drops the final word.
        await collector?.value
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        return await MainActor.run { text }
    }

    @MainActor
    private func settle(_ s: String) {
        text = s
        onFinal?(s)
        onPartial?(s)
    }

    @MainActor
    private func show(_ s: String) {
        onPartial?(s)
    }

    /// Resample a microphone buffer into the format the analyser asked for.
    /// Returns nil rather than throwing because this runs on the audio thread,
    /// where the only safe response to a bad buffer is to drop it.
    private func convert(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        guard let converter, let format = analyzerFormat else { return nil }
        let ratio = format.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio + 1024)
        guard let out = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: capacity) else {
            return nil
        }
        // `once` and the buffer are handed to a block the compiler types as
        // @Sendable, although `convert` calls it synchronously before it
        // returns. The box says that out loud rather than silencing it with
        // @preconcurrency on the whole import.
        let feed = OneShot(buffer)
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            guard let next = feed.take() else {
                status.pointee = .noDataNow
                return nil
            }
            status.pointee = .haveData
            return next
        }
        return error == nil && out.frameLength > 0 ? out : nil
    }
}


/// One buffer, handed over exactly once.
///
/// `AVAudioConverter` asks its input block for more data until the block says
/// there is none. Resampling one buffer means answering once and refusing after
/// that; answering twice makes the converter loop on the same audio.
private final class OneShot: @unchecked Sendable {
    private var buffer: AVAudioPCMBuffer?
    init(_ b: AVAudioPCMBuffer) { buffer = b }
    func take() -> AVAudioPCMBuffer? {
        defer { buffer = nil }
        return buffer
    }
}
