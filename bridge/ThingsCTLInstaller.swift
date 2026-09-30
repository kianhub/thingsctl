import AppKit
import Foundation

// A signed application entrypoint lets Finder assess the whole installer rather
// than asking users to run a quarantined .command file. The existing installer
// owns installation/recovery; this window only runs its bundled, fixed payload.
final class InstallerDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var button: NSButton!
    private var status: NSTextField!
    private var progress: NSProgressIndicator!
    private var output: NSTextView!
    private var installing = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 620, height: 420),
                          styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "Install ThingsCTL"
        window.center()
        let view = window.contentView!
        let title = NSTextField(labelWithString: "Things, inside ChatGPT")
        title.font = .systemFont(ofSize: 22, weight: .semibold)
        title.frame = NSRect(x: 24, y: 366, width: 570, height: 30)
        view.addSubview(title)
        let description = NSTextField(wrappingLabelWithString:
            "Install the ThingsCTL Bridge, command-line tool, and local plugin for this Mac. Requires Things 3, Python 3.9+, and the Codex CLI.")
        description.frame = NSRect(x: 24, y: 308, width: 570, height: 48)
        view.addSubview(description)
        status = NSTextField(wrappingLabelWithString: "Ready to install in your user account.")
        status.frame = NSRect(x: 24, y: 266, width: 570, height: 34)
        view.addSubview(status)
        let scroll = NSScrollView(frame: NSRect(x: 24, y: 68, width: 572, height: 186))
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        output = NSTextView(frame: scroll.bounds)
        output.isEditable = false
        output.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        output.autoresizingMask = [.width]
        output.isVerticallyResizable = true
        output.textContainer?.widthTracksTextView = true
        scroll.documentView = output
        view.addSubview(scroll)
        progress = NSProgressIndicator(frame: NSRect(x: 24, y: 26, width: 20, height: 20))
        progress.style = .spinning
        progress.isDisplayedWhenStopped = false
        view.addSubview(progress)
        button = NSButton(title: "Install", target: self, action: #selector(install))
        button.bezelStyle = .rounded
        button.keyEquivalent = "\r"
        button.frame = NSRect(x: 484, y: 20, width: 112, height: 32)
        view.addSubview(button)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func install() {
        guard let payload = Bundle.main.resourceURL?.appendingPathComponent("payload"),
              FileManager.default.fileExists(atPath: payload.appendingPathComponent("install.sh").path) else {
            status.stringValue = "The installer payload is missing. Download the complete installer again."
            return
        }
        installing = true
        button.isEnabled = false
        window.standardWindowButton(.closeButton)?.isEnabled = false
        status.stringValue = "Installing ThingsCTL… Allow ThingsCTL Bridge to control Things if macOS asks."
        progress.startAnimation(nil)
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process()
            let pipe = Pipe()
            process.executableURL = URL(fileURLWithPath: "/bin/sh")
            process.arguments = [payload.appendingPathComponent("install.sh").path, "--skip-build"]
            process.currentDirectoryURL = payload
            var environment = ProcessInfo.processInfo.environment
            let home = FileManager.default.homeDirectoryForCurrentUser.path
            environment["PATH"] = [home + "/.local/bin", "/opt/homebrew/bin", "/usr/local/bin",
                                   environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"].joined(separator: ":")
            process.environment = environment
            process.standardOutput = pipe
            process.standardError = pipe
            var result: String
            var succeeded = false
            do {
                try process.run()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                result = String(data: data, encoding: .utf8) ?? "The installer returned unreadable output."
                succeeded = process.terminationStatus == 0
            } catch {
                result = "Could not start installation: \(error.localizedDescription)"
            }
            DispatchQueue.main.async {
                self.installing = false
                self.output.string = result
                self.status.stringValue = succeeded
                    ? "ThingsCTL is installed. Check the details below for connection status, then refresh plugins in ChatGPT or Codex."
                    : "Installation needs attention. Review the details below, fix the reported requirement, then try again."
                self.progress.stopAnimation(nil)
                self.window.standardWindowButton(.closeButton)?.isEnabled = true
                self.button.title = succeeded ? "Close" : "Try Again"
                self.button.action = succeeded ? #selector(self.close) : #selector(self.install)
                self.button.isEnabled = true
            }
        }
    }

    @objc private func close() { NSApp.terminate(nil) }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        installing ? .terminateCancel : .terminateNow
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let application = NSApplication.shared
let delegate = InstallerDelegate()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
