import Foundation
import Speech
import AVFoundation

func note(_ s: String) {
    FileHandle.standardError.write((s + "\n").data(using: .utf8)!)
}

@main
struct Tx {
    static func main() async {
        let args = CommandLine.arguments
        note("args: \(args)")
        guard args.count >= 3 else { note("usage: tx <locale> <wav>..."); exit(2) }
        let locale = Locale(identifier: args[1])
        let installed = await SpeechTranscriber.installedLocales.map(\.identifier)
        note("installed: \(installed)")
        guard installed.contains(args[1]) else { note("locale not installed"); exit(3) }
        for path in args.dropFirst(2) {
            let started = Date()
            do {
                let text = try await one(path: path, locale: locale)
                let ms = Int(Date().timeIntervalSince(started) * 1000)
                print("\(path)\t\(ms)\t\(text.trimmingCharacters(in: .whitespacesAndNewlines))")
            } catch {
                print("\(path)\t-1\tERROR \(error)")
            }
            fflush(stdout)
        }
        exit(0)
    }

    static func one(path: String, locale: Locale) async throws -> String {
        let transcriber = SpeechTranscriber(locale: locale, preset: .transcription)
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        let file = try AVAudioFile(forReading: URL(fileURLWithPath: path))
        let collector = Task { () -> String in
            var out = ""
            for try await r in transcriber.results { out += String(r.text.characters) }
            return out
        }
        _ = try await analyzer.analyzeSequence(from: file)
        try await analyzer.finalizeAndFinishThroughEndOfInput()
        return try await collector.value
    }
}
