// dictator-readback: what is in the text field the user is editing.
//
// This exists so dictation can find out what happened to the words it pasted.
// If you said "whisper floor" and then fixed it to "Whisper Flow" by hand,
// that correction is the single most useful signal there is, and it is
// invisible unless somebody looks.
//
// One thing here is not obvious and cost an afternoon to find. The documented
// route, asking the SYSTEM-WIDE element for kAXFocusedUIElement, returns
// kAXErrorCannotComplete (-25204) even in a process that AXIsProcessTrusted()
// reports as trusted. Asking the FRONTMOST APPLICATION for the same attribute
// works and returns a real element. So that is the route taken, and the
// system-wide one is not a fallback worth keeping.
//
// Output is one JSON object on stdout. Failures are reported in it rather than
// by exiting quietly, because a reader that silently returns nothing looks
// exactly like a field the user did not touch.
import Cocoa
import ApplicationServices

func attr(_ e: AXUIElement, _ a: String) -> AnyObject? {
    var v: AnyObject?
    return AXUIElementCopyAttributeValue(e, a as CFString, &v) == .success ? v : nil
}

func json(_ d: [String: Any]) -> String {
    guard let data = try? JSONSerialization.data(withJSONObject: d),
          let s = String(data: data, encoding: .utf8) else { return "{}" }
    return s
}

guard AXIsProcessTrusted() else {
    print(json(["ok": false, "why": "no accessibility permission"]))
    exit(1)
}
guard let front = NSWorkspace.shared.frontmostApplication else {
    print(json(["ok": false, "why": "no frontmost application"]))
    exit(1)
}
let app = AXUIElementCreateApplication(front.processIdentifier)
guard let focused = attr(app, kAXFocusedUIElementAttribute) else {
    print(json(["ok": false, "why": "nothing focused",
                "app": front.localizedName ?? ""]))
    exit(1)
}
let el = focused as! AXUIElement

var out: [String: Any] = [
    "ok": true,
    "app": front.localizedName ?? "",
    "role": (attr(el, kAXRoleAttribute) as? String) ?? "",
]
if let v = attr(el, kAXValueAttribute) as? String {
    out["value"] = v
} else {
    // Plenty of controls have no text at all, which is a fact about the field
    // and not an error, so say which it is.
    out["value"] = NSNull()
}
out["selected"] = (attr(el, kAXSelectedTextAttribute) as? String) ?? ""
print(json(out))
