import AppKit
import Carbon
import Darwin
import Foundation

// A local, owner-only bridge. The only scripting source is the bundled script.
// Data crosses the boundary as NSAppleEventDescriptor values, never source text.
private let commandNames: Set<String> = ["doctor", "snapshot", "get", "container_get", "add", "update", "complete", "cancel", "reopen", "move", "trash", "show", "project_add", "area_add", "tag_add", "fixture_cleanup", "fixture_restore", "fixture_find"]
private let mutations: Set<String> = ["add", "update", "complete", "cancel", "reopen", "move", "trash", "project_add", "area_add", "tag_add", "fixture_cleanup", "fixture_restore"]
private let maxRequest = 1_048_576
private let automationGate = DispatchSemaphore(value: 1)
private let fm = FileManager.default
private let appSupport = fm.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/ThingsCTL")
private let socketPath = ProcessInfo.processInfo.environment["THINGSCTL_SOCKET"] ?? appSupport.appendingPathComponent("bridge.sock").path

func fourCC(_ string: String) -> UInt32 { string.utf8.reduce(0) { ($0 << 8) | UInt32($1) } }
func errorResult(_ code: String, _ message: String, _ details: [String: Any] = [:]) -> [String: Any] {
    ["ok": false, "error": ["code": code, "message": message, "details": details]]
}
let capabilities: [String: Any] = [
    "adapter": "applescript", "coreTasks": true, "projects": true, "areas": true, "tags": true,
    "scheduling": true, "deadlines": true, "headings": false, "checklists": false,
    "evening": false, "reminders": false, "recurrence": false, "manualReorder": false,
    "shortcutsHelper": false, "includeCatalog": true,
]
let fields = ["id", "title", "notes", "status", "when", "whenKind", "deadline", "createdAt", "modifiedAt", "completedAt", "canceledAt", "projectId", "areaId", "tags", "listIds"]
let keyMap = ["taskID": "id", "entityID": "id", "taskTitle": "title", "entityTitle": "title", "taskNotes": "notes", "entityNotes": "notes", "taskStatus": "status", "projectStatus": "status", "whenDate": "when", "deadlineDate": "deadline", "taskTags": "tags", "taskRecords": "tasks", "projectRecords": "projects", "areaRecords": "areas", "tagRecords": "tags", "listRecords": "lists", "totalCount": "total", "offsetValue": "offset", "limitValue": "limit", "taskRecord": "task", "projectRecord": "project", "areaRecord": "area", "tagRecord": "tag"]

func descriptor(_ value: Any) -> NSAppleEventDescriptor {
    if value is NSNull { return NSAppleEventDescriptor(typeCode: fourCC("msng")) }
    if let date = value as? Date { return NSAppleEventDescriptor(date: date) }
    if let string = value as? String { return NSAppleEventDescriptor(string: string) }
    if let number = value as? NSNumber {
        if CFGetTypeID(number) == CFBooleanGetTypeID() { return NSAppleEventDescriptor(boolean: number.boolValue) }
        return NSAppleEventDescriptor(int32: number.int32Value)
    }
    if let array = value as? [Any] {
        let result = NSAppleEventDescriptor.list()
        for (index, item) in array.enumerated() { result.insert(descriptor(item), at: index + 1) }
        return result
    }
    if let object = value as? [String: Any] {
        let result = NSAppleEventDescriptor.record()
        let pairs = NSAppleEventDescriptor.list()
        for key in object.keys.sorted() {
            pairs.insert(NSAppleEventDescriptor(string: key), at: pairs.numberOfItems + 1)
            pairs.insert(descriptor(object[key]!), at: pairs.numberOfItems + 1)
        }
        result.setDescriptor(pairs, forKeyword: fourCC("usrf"))
        return result
    }
    return NSAppleEventDescriptor(typeCode: fourCC("msng"))
}

func decode(_ value: NSAppleEventDescriptor, key: String = "") -> Any {
    let type = value.descriptorType
    if type == fourCC("msng") || type == fourCC("null") || (type == fourCC("type") && value.typeCodeValue == fourCC("msng")) { return NSNull() }
    if type == fourCC("ldt "), let date = value.dateValue {
        if key == "when" || key == "deadline" {
            let format = DateFormatter(); format.locale = Locale(identifier: "en_US_POSIX"); format.dateFormat = "yyyy-MM-dd"
            return format.string(from: date)
        }
        return ISO8601DateFormatter().string(from: date)
    }
    if type == fourCC("bool") { return value.booleanValue }
    // AppleScript constants use typeTrue/typeFalse, not always typeBoolean.
    if type == fourCC("true") { return true }
    if type == fourCC("fals") { return false }
    if type == fourCC("long") || type == fourCC("shor") { return Int(value.int32Value) }
    if type == fourCC("doub") { return value.doubleValue }
    if type == fourCC("list") {
        if value.numberOfItems == 0 { return [Any]() }
        return (1...value.numberOfItems).compactMap { value.atIndex($0).map { decode($0) } }
    }
    if value.isRecordDescriptor {
        var object: [String: Any] = [:]
        if let pairs = value.forKeyword(fourCC("usrf")), pairs.numberOfItems > 0 {
            var index = 1
            while index < pairs.numberOfItems {
                if let original = pairs.atIndex(index)?.stringValue, let item = pairs.atIndex(index + 1) {
                    let name = keyMap[original] ?? original
                    object[name] = decode(item, key: name)
                }
                index += 2
            }
        }
        let known: [UInt32: String] = [fourCC("ID  "): "id", fourCC("pnam"): "title", fourCC("note"): "notes", fourCC("tdst"): "status"]
        if value.numberOfItems > 0 {
            for index in 1...value.numberOfItems {
                let code = value.keywordForDescriptor(at: index)
                if let name = known[code], let item = value.atIndex(index) { object[name] = decode(item, key: name) }
            }
        }
        if object["id"] != nil && object["status"] != nil && object["whenKind"] != nil {
            object["availableFields"] = object["whenKind"] is NSNull ? fields.filter { $0 != "whenKind" } : fields
        }
        return object
    }
    return value.stringValue ?? NSNull() as Any
}

func parseDate(_ value: String) -> Date? {
    let format = DateFormatter(); format.locale = Locale(identifier: "en_US_POSIX"); format.calendar = Calendar(identifier: .gregorian)
    format.dateFormat = "yyyy-MM-dd"; format.isLenient = false
    guard value.count == 10, let date = format.date(from: value), format.string(from: date) == value else { return nil }
    return Calendar.current.date(bySettingHour: 12, minute: 0, second: 0, of: date)
}

enum BridgeFailure: Error { case invalid(String) }
func options(_ args: [String: Any], command: String) throws -> [String: Any] {
    let editable: Set<String> = ["title", "notes", "tags", "when", "deadline", "projectId", "areaId"]
    let commandKeys: [String: Set<String>] = [
        "doctor": [], "snapshot": ["view", "offset", "limit", "includeCatalog"], "get": ["id"],
        "container_get": ["id", "kind"], "add": editable, "update": editable.union(["id"]),
        "complete": ["id"], "cancel": ["id"], "reopen": ["id"], "trash": ["id"], "show": ["id"],
        "move": ["id", "projectId", "areaId"], "project_add": ["title", "notes", "areaId"],
        "area_add": ["title"], "tag_add": ["title"], "fixture_cleanup": ["id", "title"], "fixture_restore": ["id", "title"], "fixture_find": ["title", "id"],
    ]
    guard let keys = commandKeys[command] else { throw BridgeFailure.invalid("Unknown command") }
    guard Set(args.keys).isSubset(of: keys) else { throw BridgeFailure.invalid("Unsupported argument") }
    var opts: [String: Any] = ["identifierValue": "", "viewValue": "today", "offsetValue": 0, "limitValue": 20, "includeCatalogValue": true,
        "hasTitle": false, "titleValue": "", "hasNotes": false, "notesValue": "", "hasTags": false, "tagsValue": "",
        "hasWhen": false, "whenValue": "", "whenDateValue": NSNull(), "hasDeadline": false, "deadlineValue": NSNull(),
        "hasProject": false, "projectValue": "", "hasArea": false, "areaValue": ""]
    for (field, target, flag, bound) in [("title", "titleValue", "hasTitle", 1000), ("notes", "notesValue", "hasNotes", 500_000), ("projectId", "projectValue", "hasProject", 256), ("areaId", "areaValue", "hasArea", 256)] {
        if let value = args[field] {
            let text: String
            if value is NSNull, field == "projectId" || field == "areaId" { text = "" }
            else if let string = value as? String { text = string }
            else { throw BridgeFailure.invalid("\(field) must be text") }
            guard text.count <= bound else { throw BridgeFailure.invalid("\(field) is too long") }
            guard !text.contains("\0"), field == "notes" || (field == "projectId" || field == "areaId") || !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw BridgeFailure.invalid("Invalid \(field)") }
            opts[target] = text; opts[flag] = true
        }
    }
    if ["add", "project_add", "area_add", "tag_add"].contains(command), (opts["titleValue"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false { throw BridgeFailure.invalid("A title is required") }
    if let id = args["id"] as? String, !id.isEmpty, id.count <= 256, !id.contains("\0") { opts["identifierValue"] = id }
    else if ["get", "container_get", "update", "complete", "cancel", "reopen", "move", "trash", "show", "fixture_cleanup", "fixture_restore"].contains(command) { throw BridgeFailure.invalid("An item ID is required") }
    if ["fixture_cleanup", "fixture_restore", "fixture_find"].contains(command), (opts["titleValue"] as? String)?.hasPrefix("[ThingsCTL integration ") != true { throw BridgeFailure.invalid("Only explicitly named integration fixtures can be inspected or cleaned up") }
    if command == "container_get" {
        guard let kind = args["kind"] as? String, ["project", "area", "tag"].contains(kind) else { throw BridgeFailure.invalid("Unknown container kind") }
        opts["kindValue"] = kind
    }
    if let tags = args["tags"] {
        guard let values = tags as? [String], values.count <= 100, values.allSatisfy({ $0.count <= 256 && !$0.contains(",") && !$0.contains("\0") && !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else { throw BridgeFailure.invalid("tags must be nonempty tag names without commas") }
        opts["tagsValue"] = values.joined(separator: ", "); opts["hasTags"] = true
    }
    if let deadline = args["deadline"] {
        opts["hasDeadline"] = true
        if deadline is NSNull || (deadline as? String) == "" { opts["deadlineValue"] = NSNull() }
        else if let string = deadline as? String, let date = parseDate(string) { opts["deadlineValue"] = date }
        else { throw BridgeFailure.invalid("deadline must be YYYY-MM-DD or null") }
    }
    if let when = args["when"] {
        guard let string = when as? String else { throw BridgeFailure.invalid("when must be a view name or date") }
        opts["hasWhen"] = true; opts["whenValue"] = string
        if !["today", "anytime", "someday", "inbox"].contains(string) {
            guard let date = parseDate(string) else { throw BridgeFailure.invalid("Unsupported scheduling choice") }
            opts["whenDateValue"] = date
        }
    }
    if let project = opts["projectValue"] as? String, let area = opts["areaValue"] as? String, !project.isEmpty && !area.isEmpty { throw BridgeFailure.invalid("Choose one destination") }
    if command == "update", !["hasTitle", "hasNotes", "hasTags", "hasWhen", "hasDeadline", "hasProject", "hasArea"].contains(where: { opts[$0] as? Bool == true }) { throw BridgeFailure.invalid("No fields to update") }
    if command == "move", opts["hasProject"] as? Bool != true && opts["hasArea"] as? Bool != true { throw BridgeFailure.invalid("No destination to change") }
    if let view = args["view"] {
        guard let value = view as? String, value.count <= 300, !value.contains("\0"), ["all", "inbox", "today", "upcoming", "anytime", "someday", "logbook", "trash"].contains(value) || (value.hasPrefix("project:") && value.count > 8) || (value.hasPrefix("area:") && value.count > 5) else { throw BridgeFailure.invalid("Unknown view") }
        opts["viewValue"] = value
    }
    if let catalog = args["includeCatalog"] {
        guard let value = catalog as? NSNumber, CFGetTypeID(value) == CFBooleanGetTypeID() else { throw BridgeFailure.invalid("includeCatalog must be a boolean") }
        opts["includeCatalogValue"] = value.boolValue
    }
    for (key, fallback, range) in [("offset", 0, 0...1_000_000), ("limit", 20, 1...500)] {
        let number = args[key] ?? fallback
        guard let numeric = number as? NSNumber, CFGetTypeID(numeric) != CFBooleanGetTypeID(), let value = number as? Int, numeric.doubleValue == Double(value), range.contains(value) else { throw BridgeFailure.invalid("Invalid \(key)") }
        opts[key + "Value"] = value
    }
    return opts
}

final class Automation {
    private let script: NSAppleScript
    init() throws {
        let path = Bundle.main.path(forResource: "Things", ofType: "scpt") ?? Bundle.main.path(forResource: "Things", ofType: "applescript")
        guard let path = path else { throw BridgeFailure.invalid("Bundled script missing") }
        var error: NSDictionary?
        guard let loaded = NSAppleScript(contentsOf: URL(fileURLWithPath: path), error: &error) else { throw BridgeFailure.invalid("Cannot load bundled automation") }
        script = loaded
    }
    func execute(_ request: [String: Any]) -> [String: Any] {
        guard let command = request["command"] as? String, commandNames.contains(command), let args = request["arguments"] as? [String: Any], Set(request.keys).isSubset(of: ["command", "arguments"]) else { return errorResult("INVALID_REQUEST", "Unknown bridge command or invalid request") }
        let opts: [String: Any]
        do { opts = try options(args, command: command) }
        catch { return errorResult("INVALID_ARGUMENT", "\(error)") }
        let event = NSAppleEventDescriptor(eventClass: fourCC("ascr"), eventID: fourCC("psbr"), targetDescriptor: nil, returnID: Int16(kAutoGenerateReturnID), transactionID: Int32(kAnyTransactionID))
        event.setParam(NSAppleEventDescriptor(string: "dispatchcommand"), forKeyword: fourCC("snam"))
        let params = NSAppleEventDescriptor.list()
        params.insert(NSAppleEventDescriptor(string: command), at: 1); params.insert(descriptor(opts), at: 2)
        event.setParam(params, forKeyword: fourCC("----"))
        var error: NSDictionary?
        let response = script.executeAppleEvent(event, error: &error)
        if error != nil {
            let number = error?[NSAppleScript.errorNumber] as? Int ?? 0
            let message = error?[NSAppleScript.errorMessage] as? String ?? ""
            let stages: Set<String> = ["task_lookup", "task_container_check", "task_id", "task_title", "task_notes", "task_status", "task_deadline", "task_start", "task_dates", "task_tags", "task_membership", "membership_batch", "collection_all", "collection_project", "collection_area", "collection_builtin", "collection_items", "container_lookup", "container_readback", "fixture_lookup", "fixture_identity", "fixture_move", "fixture_readback", "fixture_delete", "fixture_verify"]
            var details: [String: Any] = ["appleScriptError": number]
            if let marker = message.range(of: "ThingsCTL phase:") {
                let stage = String(message[marker.upperBound...].prefix { $0.isLetter || $0 == "_" })
                if stages.contains(stage) { details["automationStage"] = stage }
            }
            // Any dispatched write can have partially succeeded. Never auto-retry it.
            if mutations.contains(command) {
                let message = (number == -1743 || number == -10004)
                    ? "Allow ThingsCTL Bridge to control Things in System Settings → Privacy & Security → Automation. Check the item before retrying this change."
                    : "Things may have applied part of this change. Check the item before retrying."
                details["operationStatus"] = "uncertain"
                return errorResult("MUTATION_UNCERTAIN", message, details)
            }
            if number == -1743 || number == -10004 { return errorResult("AUTOMATION_DENIED", "Allow ThingsCTL Bridge to control Things in System Settings → Privacy & Security → Automation.") }
            if number == -1728 { return errorResult("NOT_FOUND", "The requested Things item or list was not found") }
            if number == -1701 { return errorResult("WRONG_ITEM_KIND", "This command requires a task ID; the ID belongs to a container") }
            return errorResult("AUTOMATION_ERROR", "Things automation failed", details)
        }
        guard var data = decode(response) as? [String: Any] else {
            return mutations.contains(command)
                ? errorResult("MUTATION_UNCERTAIN", "The change was sent but Things returned an unexpected result. Check Things before retrying.", ["operationStatus": "uncertain"])
                : errorResult("INVALID_RESPONSE", "Things returned an unexpected result")
        }
        if command == "snapshot" || command == "doctor" { data["capabilities"] = capabilities }
        if command == "doctor" { data["bridgeVersion"] = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"; data["socket"] = socketPath }
        return ["ok": true, "data": data]
    }
}

func runConnection(_ fd: Int32, automation: Automation) {
    defer { Darwin.close(fd) }
    var user: uid_t = 0, group: gid_t = 0
    guard getpeereid(fd, &user, &group) == 0, user == getuid() else { return }
    var timeout = timeval(tv_sec: 100, tv_usec: 0)
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
    var buffer = [UInt8](repeating: 0, count: 4096), received = Data()
    while received.count <= maxRequest {
        let count = Darwin.read(fd, &buffer, buffer.count)
        guard count > 0 else { return }
        received.append(contentsOf: buffer.prefix(count))
        if received.contains(10) { break }
    }
    var response: [String: Any]
    if received.count > maxRequest { response = errorResult("REQUEST_TOO_LARGE", "Request exceeds bridge limit") }
    else if let newline = received.firstIndex(of: 10), let value = try? JSONSerialization.jsonObject(with: received[..<newline]), let request = value as? [String: Any] {
        if automationGate.wait(timeout: .now()) == .success {
            defer { automationGate.signal() }
            response = DispatchQueue.main.sync { automation.execute(request) }
        } else { response = errorResult("BRIDGE_BUSY", "ThingsCTL is finishing another request. This request was not sent to Things.") }
    } else { response = errorResult("INVALID_REQUEST", "Expected one JSON request") }
    guard var payload = try? JSONSerialization.data(withJSONObject: response, options: [.sortedKeys]) else { return }
    payload.append(10)
    payload.withUnsafeBytes { raw in
        guard let base = raw.baseAddress else { return }
        var sent = 0
        while sent < raw.count { let n = Darwin.write(fd, base.advanced(by: sent), raw.count - sent); if n <= 0 { break }; sent += n }
    }
}

func makeServer() throws -> Int32 {
    let parent = URL(fileURLWithPath: socketPath).deletingLastPathComponent()
    try fm.createDirectory(at: parent, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    var parentInfo = stat()
    guard lstat(parent.path, &parentInfo) == 0, parentInfo.st_uid == getuid(), (parentInfo.st_mode & S_IFMT) == S_IFDIR, (parentInfo.st_mode & 0o077) == 0 else { throw BridgeFailure.invalid("Socket directory must be private and owned by this user") }
    guard socketPath.utf8.count < MemoryLayout.size(ofValue: sockaddr_un().sun_path) else { throw BridgeFailure.invalid("Socket path too long") }
    var address = sockaddr_un(); address.sun_family = sa_family_t(AF_UNIX)
    withUnsafeMutablePointer(to: &address.sun_path) { pointer in
        pointer.withMemoryRebound(to: CChar.self, capacity: 104) { buffer in _ = socketPath.withCString { strlcpy(buffer, $0, 104) } }
    }
    let probe = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
    let running = withUnsafePointer(to: &address) { pointer in pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(probe, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) == 0 } }
    Darwin.close(probe)
    if running { exit(0) }
    var info = stat()
    if lstat(socketPath, &info) == 0 {
        guard info.st_uid == getuid(), (info.st_mode & S_IFMT) == S_IFSOCK else { throw BridgeFailure.invalid("Refusing to replace non-owned socket path") }
        unlink(socketPath)
    }
    let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { throw BridgeFailure.invalid("Cannot create socket") }
    let mask = umask(0o077); defer { umask(mask) }
    let bound = withUnsafePointer(to: &address) { pointer in pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) } }
    guard bound == 0, listen(fd, 16) == 0 else { Darwin.close(fd); throw BridgeFailure.invalid("Cannot bind socket") }
    chmod(socketPath, 0o600)
    return fd
}

func selfTest() throws {
    guard let trueValue = NSAppleEventDescriptor(descriptorType: fourCC("true"), data: Data()),
          let falseValue = NSAppleEventDescriptor(descriptorType: fourCC("fals"), data: Data()),
          decode(trueValue) as? Bool == true, decode(falseValue) as? Bool == false else { throw BridgeFailure.invalid("AppleScript boolean constants were not preserved") }
    let title = "Quoted \"title\"; do shell script \"false\" — 日本語 🥾"
    let record = decode(descriptor(["taskID": "fixture-id", "taskTitle": title, "taskStatus": "open", "whenKind": "anytime", "whenDate": NSNull(), "taskTags": [["entityID": "tag-id", "entityTitle": "Focus"]]])) as? [String: Any]
    guard record?["id"] as? String == "fixture-id", record?["title"] as? String == title,
          record?["when"] is NSNull, (record?["tags"] as? [[String: Any]])?.first?["title"] as? String == "Focus",
          (record?["availableFields"] as? [String])?.contains("deadline") == true else { throw BridgeFailure.invalid("Typed descriptor round trip failed") }
    guard parseDate("2026-02-30") == nil, parseDate("2026-2-01") == nil, parseDate("2028-02-29") != nil else { throw BridgeFailure.invalid("Calendar validation failed") }
    _ = try options(["title": title, "deadline": "2028-02-29", "tags": ["Focus"], "notes": "Line one\nLine two"], command: "add")
    _ = try options(["id": "fixture-id", "projectId": NSNull(), "areaId": NSNull()], command: "move")
    for (command, args) in [("doctor", ["title": "ignored"] as [String: Any]), ("snapshot", ["limit": true]), ("snapshot", ["limit": 1.5]), ("snapshot", ["view": "project:"]), ("add", ["title": " "]), ("add", ["title": "Fixture", "tags": ["bad,tag"]]), ("update", ["id": "fixture-id"]), ("move", ["id": "fixture-id", "projectId": "p", "areaId": "a"])] {
        do { _ = try options(args, command: command) }
        catch { continue }
        throw BridgeFailure.invalid("Invalid input accepted for \(command)")
    }
    print("ThingsCTL Bridge: typed descriptors, dates, and input boundaries passed")
}

do {
    if CommandLine.arguments.contains("--self-test") { try selfTest(); exit(0) }
    let app = NSApplication.shared; app.setActivationPolicy(.accessory)
    let automation = try Automation()
    if CommandLine.arguments.contains("--check") { print("ThingsCTL Bridge script loaded"); exit(0) }
    signal(SIGPIPE, SIG_IGN)
    let server = try makeServer()
    DispatchQueue.global(qos: .userInitiated).async {
        while true { let client = accept(server, nil, nil); if client >= 0 { DispatchQueue.global(qos: .userInitiated).async { runConnection(client, automation: automation) } } }
    }
    app.run()
} catch { fputs("ThingsCTL Bridge could not start: \(error)\n", stderr); exit(1) }
