// The keyboard. It is a keyboard so that it can type, and it types by being
// the input method rather than by faking a paste.
//
// On the Mac, delivering the words is 500 lines: a synthetic Cmd-V, a clipboard
// saved and put back, an Accessibility grant that macOS shows as granted when it
// is not, and a helper that posts into the void when it is not trusted. Here it
// is `textDocumentProxy.insertText`, and the host app receives it as typing.
//
// The open question this target exists to settle is above it: whether iOS lets
// an extension open the microphone at all. Full Access is required and the user
// has to turn it on by hand, so the keyboard says which of the two is missing
// instead of showing a dead button.

import AVFoundation
import Speech
import UIKit

final class KeyboardViewController: UIInputViewController {
    private let talk = UIButton(type: .system)
    private let status = UILabel()
    private let preview = UILabel()
    private let nextKeyboard = UIButton(type: .system)

    private var dictation: Dictation?
    private var inserted = ""

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor.secondarySystemBackground
        buildUI()
        Task { await check() }
    }

    // MARK: setup

    private func buildUI() {
        status.font = .systemFont(ofSize: 12)
        status.textColor = .secondaryLabel
        status.numberOfLines = 2
        status.textAlignment = .center

        preview.font = .systemFont(ofSize: 15)
        preview.numberOfLines = 2
        preview.textAlignment = .center
        preview.textColor = .label

        talk.setTitle("Hold to talk", for: .normal)
        talk.titleLabel?.font = .systemFont(ofSize: 20, weight: .semibold)
        talk.backgroundColor = .systemBlue
        talk.setTitleColor(.white, for: .normal)
        talk.layer.cornerRadius = 14
        talk.isEnabled = false
        talk.addTarget(self, action: #selector(down), for: [.touchDown])
        talk.addTarget(self, action: #selector(up),
                       for: [.touchUpInside, .touchUpOutside, .touchCancel])

        nextKeyboard.setTitle("ABC", for: .normal)
        nextKeyboard.titleLabel?.font = .systemFont(ofSize: 15)
        nextKeyboard.addTarget(self,
                               action: #selector(handleInputModeList(from:with:)),
                               for: .allTouchEvents)

        let stack = UIStackView(arrangedSubviews: [preview, talk, status, nextKeyboard])
        stack.axis = .vertical
        stack.spacing = 8
        stack.alignment = .fill
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 12),
            stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -12),
            stack.topAnchor.constraint(equalTo: view.topAnchor, constant: 10),
            stack.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -10),
            talk.heightAnchor.constraint(equalToConstant: 56),
            view.heightAnchor.constraint(equalToConstant: 230),
        ])
    }

    /// Two things can be missing and they need different words from the user,
    /// so they are checked and reported separately.
    private func check() async {
        // `hasFullAccess` is false until the user turns it on in Settings, and
        // without it the microphone is not merely denied, it is unavailable.
        guard hasFullAccess else {
            say("Turn on Full Access for this keyboard:\n"
                + "Settings, General, Keyboard, Keyboards, Dictator")
            return
        }
        switch AVAudioApplication.shared.recordPermission {
        case .denied:
            say("Microphone is off for Dictator. Settings, Privacy, Microphone")
            return
        case .undetermined:
            // An extension cannot show the system microphone prompt. The
            // container app asks once, which is why it exists.
            say("Open the Dictator app once to allow the microphone")
            return
        default:
            break
        }
        do {
            let what = try await Dictation.ensureModel()
            say("Ready, Indian English (\(what))")
            talk.isEnabled = true
        } catch {
            say("Speech model unavailable: \(error)")
        }
    }

    // MARK: the key

    @objc private func down() {
        guard dictation == nil else { return }
        inserted = ""
        let d = Dictation()
        // Shown while it is still being revised, typed only once it settles.
        d.onPartial = { [weak self] text in self?.preview.text = text }
        d.onFinal = { [weak self] text in self?.commit(text) }
        dictation = d
        Task {
            do {
                try await d.start()
                say("Listening")
            } catch {
                // The finding this whole target exists for. Whatever iOS says
                // when an extension asks for the microphone, it says it here.
                say("Microphone refused: \(error)")
                dictation = nil
            }
        }
    }

    @objc private func up() {
        guard let d = dictation else { return }
        dictation = nil
        Task {
            let final = await d.stop()
            commit(final)
            say("Ready")
        }
    }

    /// Insert only what is new.
    ///
    /// Settled results still arrive as the whole sentence so far rather than as
    /// deltas, so inserting each one whole would type the sentence once per
    /// update. This appends the part nobody has seen and nothing else: deleting
    /// and retyping would fight the host app's autocorrect.
    private func commit(_ text: String) {
        guard text.hasPrefix(inserted) else {
            // Settled text is not supposed to be revised, but if it is, leave
            // what was typed. A keyboard that silently rewrites what the user
            // watched appear is worse than one that is a word behind.
            return
        }
        let new = String(text.dropFirst(inserted.count))
        guard !new.isEmpty else { return }
        textDocumentProxy.insertText(new)
        inserted = text
    }

    private func say(_ s: String) { status.text = s }
}
