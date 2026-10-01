-- This script is fixed source. User values arrive as typed Apple event arguments.
-- No request can supply AppleScript source or invoke an arbitrary handler.
property dispatchMemberIDs : {}
property dispatchMemberships : {}
property dispatchProjectIDs : {}

on builtinList(viewName)
    set listID to ""
    set listTitle to ""
    if viewName is "inbox" then
        set listID to "TMInboxListSource"
        set listTitle to "Inbox"
    else if viewName is "today" then
        set listID to "TMTodayListSource"
        set listTitle to "Today"
    else if viewName is "upcoming" then
        set listID to "TMCalendarListSource"
        set listTitle to "Upcoming"
    else if viewName is "anytime" then
        set listID to "TMNextListSource"
        set listTitle to "Anytime"
    else if viewName is "someday" then
        set listID to "TMSomedayListSource"
        set listTitle to "Someday"
    else if viewName is "logbook" then
        set listID to "TMLogbookListSource"
        set listTitle to "Logbook"
    else if viewName is "trash" then
        set listID to "TMTrashListSource"
        set listTitle to "Trash"
    end if
    if listID is "" then error "Unknown built-in view" number -1700
    tell application "Things3"
        if exists list id listID then return list id listID
        -- Public list names are the documented fallback if a release changes an ID.
        if exists list named listTitle then return list named listTitle
    end tell
    error "Built-in list unavailable; check Things language and version" number -1728
end builtinList

on entityRecord(entity)
    tell application "Things3"
        return {|entityID|:id of entity, |entityTitle|:name of entity}
    end tell
end entityRecord

on listContainsTask(identifier, viewName)
    considering case
        if identifier is in my dispatchMemberIDs then
            repeat with membership in my dispatchMemberships
                if |viewValue| of membership is viewName and identifier is in |coveredIDs| of membership then return identifier is in |idsValue| of membership
            end repeat
        end if
    end considering
    set sourceList to my builtinList(viewName)
    tell application "Things3"
        -- A unique-ID object lookup can resolve globally in Things. Filter the
        -- public collection instead so membership comes from the actual list.
        return (count (to dos of sourceList whose id is identifier)) > 0
    end tell
end listContainsTask

on prepareMemberships(identifiers, projectIdentifiers)
    try
    set membershipRecords to {}
    repeat with viewName in {"inbox", "today", "upcoming", "anytime", "someday", "logbook", "trash"}
        set sourceList to my builtinList(viewName as text)
        copy identifiers to coveredIDs
        if (viewName as text) is "trash" then
            repeat with projectIdentifier in projectIdentifiers
                if (projectIdentifier as text) is not in coveredIDs then set end of coveredIDs to projectIdentifier as text
            end repeat
        end if
        set memberIDs to {}
        repeat with anIdentifier in coveredIDs
            set identifier to anIdentifier as text
            -- Things accepts documented single-ID comparisons, not an IN-array
            -- predicate. Reuse the list reference and each result this request.
            tell application "Things3" to set matchCount to count (to dos of sourceList whose id is identifier)
            if matchCount > 0 then set end of memberIDs to identifier
        end repeat
        set end of membershipRecords to {|viewValue|:viewName as text, |coveredIDs|:coveredIDs, |idsValue|:memberIDs}
    end repeat
    copy identifiers to allIdentifiers
    repeat with projectIdentifier in projectIdentifiers
        if (projectIdentifier as text) is not in allIdentifiers then set end of allIdentifiers to projectIdentifier as text
    end repeat
    set my dispatchMemberIDs to allIdentifiers
    set my dispatchMemberships to membershipRecords
    on error errorMessage number errorNumber
        error "ThingsCTL phase:membership_batch" number errorNumber
    end try
end prepareMemberships

on containerRecord(itemCollection, containerKind)
    -- Retain the native descriptor in a list across the handler boundary.
    -- A bare ID object can fail coercion before its record handler starts.
    set entity to item 1 of itemCollection
    if containerKind is "project" then return my projectRecord(entity)
    return my entityRecord(entity)
end containerRecord

on projectNavigationRecord(theProject)
    tell application "Things3"
        set identifier to id of theProject
        set parentArea to missing value
        try
            set parentArea to id of area of theProject
        end try
        set projectStatus to status of theProject
        set statusText to "open"
        if projectStatus is completed then set statusText to "completed"
        if projectStatus is canceled then set statusText to "canceled"
        if my listContainsTask(identifier, "trash") then set statusText to "trashed"
        return {|entityID|:identifier, |entityTitle|:name of theProject, |areaId|:parentArea, |projectStatus|:statusText}
    end tell
end projectNavigationRecord

on projectRecord(theProject)
    tell application "Things3"
        set parentArea to missing value
        try
            set parentArea to id of area of theProject
        end try
        set statusText to "open"
        if status of theProject is completed then set statusText to "completed"
        if status of theProject is canceled then set statusText to "canceled"
        set identifier to id of theProject
        if my listContainsTask(identifier, "trash") then set statusText to "trashed"
        return {|entityID|:identifier, |entityTitle|:name of theProject, |entityNotes|:notes of theProject, |areaId|:parentArea, |projectStatus|:statusText}
    end tell
end projectRecord

on taskRecord(theTask)
    set readStage to "task_id"
    try
    tell application "Things3"
        set identifier to id of theTask
        set readStage to "task_title"
        set taskTitle to name of theTask
        set readStage to "task_notes"
        set taskNotes to notes of theTask
        set readStage to "task_status"
        set statusValue to status of theTask
        set statusText to "open"
        if statusValue is completed then set statusText to "completed"
        if statusValue is canceled then set statusText to "canceled"
        set readStage to "task_deadline"
        set taskDeadline to due date of theTask
        set readStage to "task_start"
        set taskStart to activation date of theTask
        set readStage to "task_dates"
        set createdValue to creation date of theTask
        set modifiedValue to modification date of theTask
        set completedValue to completion date of theTask
        set canceledValue to cancellation date of theTask
        set parentProject to missing value
        set parentArea to missing value
        try
            set parentProject to id of project of theTask
            if my listContainsTask(parentProject, "trash") then set statusText to "trashed"
        end try
        try
            set parentArea to id of area of theTask
        end try
        set readStage to "task_tags"
        set taskTags to {}
        repeat with aTag in tags of theTask
            set end of taskTags to my entityRecord(aTag)
        end repeat
        set readStage to "task_membership"
        set memberships to {}
        set startKind to missing value
        repeat with viewName in {"inbox", "today", "upcoming", "anytime", "someday", "logbook", "trash"}
            if my listContainsTask(identifier, viewName as text) then
                set end of memberships to viewName as text
                if (viewName as text) is "someday" then set startKind to "someday"
                if ((viewName as text) is "anytime" or (viewName as text) is "inbox") and startKind is missing value then set startKind to "anytime"
            end if
        end repeat
        if taskStart is not missing value then set startKind to "scheduled"
        if memberships contains "trash" then set statusText to "trashed"
        return {|taskID|:identifier, |taskTitle|:taskTitle, |taskNotes|:taskNotes, |taskStatus|:statusText, |whenDate|:taskStart, |whenKind|:startKind, |deadlineDate|:taskDeadline, |createdAt|:createdValue, |modifiedAt|:modifiedValue, |completedAt|:completedValue, |canceledAt|:canceledValue, |projectId|:parentProject, |areaId|:parentArea, |taskTags|:taskTags, |listIds|:memberships}
    end tell
    on error errorMessage number errorNumber
        error "ThingsCTL phase:" & readStage number errorNumber
    end try
end taskRecord

on taskCollection(viewName)
    set readStage to "collection_all"
    try
    tell application "Things3"
        if viewName is "all" then
            return to dos
        else if viewName starts with "project:" then
            set readStage to "collection_project"
            return to dos of project id (text 9 thru -1 of viewName)
        else if viewName starts with "area:" then
            set readStage to "collection_area"
            return to dos of area id (text 6 thru -1 of viewName)
        else
            set readStage to "collection_builtin"
            set sourceList to my builtinList(viewName)
            return to dos of sourceList
        end if
    end tell
    on error errorMessage number errorNumber
        error "ThingsCTL phase:" & readStage number errorNumber
    end try
end taskCollection

on isProjectID(identifier)
    tell application "Things3"
        try
            -- Projects expose a public child collection; tasks do not. Unique-ID
            -- references can otherwise be typed as selected to dos by Things.
            set children to to dos of project id identifier
            return true
        on error errorMessage number errorNumber
            if errorNumber is -1728 or errorNumber is -1700 then return false
            error errorMessage number errorNumber
        end try
    end tell
end isProjectID

on taskPage(itemCollection, sourceOffset, pageLimit)
    set sourceCount to count itemCollection
    set firstIndex to sourceOffset + 1
    set lastIndex to firstIndex + pageLimit - 1
    if lastIndex > sourceCount then set lastIndex to sourceCount
    set pageTaskRecords to {}
    set consumedCount to 0
    set pageIDs to {}
    set pageProjectFlags to {}
    set membershipIDs to {}
    copy my dispatchProjectIDs to projectIDs
    if firstIndex ≤ sourceCount then
        repeat with itemIndex from firstIndex to lastIndex
            set pageItem to item itemIndex of itemCollection
            tell application "Things3"
                set identifier to id of pageItem
                set end of pageIDs to identifier
            end tell
            set projectFlag to my isProjectID(identifier)
            set end of pageProjectFlags to projectFlag
            if not projectFlag then
                if identifier is not in membershipIDs then set end of membershipIDs to identifier
                tell application "Things3"
                    try
                        set parentID to id of project of pageItem
                        if parentID is not in projectIDs then set end of projectIDs to parentID
                    end try
                end tell
            end if
        end repeat
    end if
    if (count membershipIDs) > 0 or (count projectIDs) > 0 then my prepareMemberships(membershipIDs, projectIDs)
    if firstIndex ≤ sourceCount then
        repeat with itemIndex from firstIndex to lastIndex
            set pageItem to item itemIndex of itemCollection
            set consumedCount to consumedCount + 1
            set pageItemID to item (itemIndex - firstIndex + 1) of pageIDs
            if not item (itemIndex - firstIndex + 1) of pageProjectFlags then set end of pageTaskRecords to my taskRecord(pageItem)
        end repeat
    end if
    set nextValue to missing value
    if lastIndex < sourceCount then set nextValue to lastIndex
    return {|taskRecords|:pageTaskRecords, |totalCount|:missing value, |sourceTotal|:sourceCount, |sourceRowsScanned|:consumedCount, |nextOffset|:nextValue, |offsetValue|:sourceOffset, |limitValue|:pageLimit, |hasMore|:lastIndex < sourceCount}
end taskPage

on applyFields(theTask, opts)
    tell application "Things3"
        if |hasTitle| of opts then set name of theTask to |titleValue| of opts
        if |hasNotes| of opts then set notes of theTask to |notesValue| of opts
        if |hasTags| of opts then set tag names of theTask to |tagsValue| of opts
        if |hasDeadline| of opts then
            if |deadlineValue| of opts is missing value then
                delete due date of theTask
            else
                set due date of theTask to |deadlineValue| of opts
            end if
        end if
        if |hasProject| of opts then
            if |projectValue| of opts is "" then
                delete project of theTask
            else
                set project of theTask to project id (|projectValue| of opts)
            end if
        end if
        if |hasArea| of opts then
            if |areaValue| of opts is "" then
                delete area of theTask
            else
                set area of theTask to area id (|areaValue| of opts)
            end if
        end if
        if |hasWhen| of opts then
            set choice to |whenValue| of opts
            if choice is "today" or choice is "anytime" or choice is "someday" or choice is "inbox" then
                move theTask to my builtinList(choice)
            else
                schedule theTask for |whenDateValue| of opts
            end if
        end if
    end tell
end applyFields

on dispatchCommand(commandName, opts)
    -- Native references and membership are valid only for this request.
    set my dispatchMemberIDs to {}
    set my dispatchMemberships to {}
    set my dispatchProjectIDs to {}
    with timeout of 90 seconds
        if commandName is "doctor" then
            tell application "Things3"
                set builtins to {}
                repeat with viewName in {"inbox", "today", "upcoming", "anytime", "someday", "logbook", "trash"}
                    set itemList to my builtinList(viewName as text)
                    set end of builtins to {|entityID|:id of itemList, |entityTitle|:name of itemList, |kind|:viewName as text}
                end repeat
                return {|thingsVersion|:version, |connected|:true, |automationStatus|:"granted", |listRecords|:builtins}
            end tell
        end if
        if commandName is "snapshot" then
            set viewName to |viewValue| of opts
            set itemCollection to my taskCollection(viewName)
            if |includeCatalogValue| of opts then tell application "Things3" to set my dispatchProjectIDs to id of projects
            set pageData to my taskPage(itemCollection, |offsetValue| of opts, |limitValue| of opts)
            if not |includeCatalogValue| of opts then return pageData & {|catalogIncluded|:false}
            tell application "Things3"
                set projectRecords to {}
                repeat with aProject in projects
                    set end of projectRecords to my projectNavigationRecord(aProject)
                end repeat
                set areaRecords to {}
                repeat with anArea in areas
                    set end of areaRecords to my entityRecord(anArea)
                end repeat
                set tagRecords to {}
                repeat with aTag in tags
                    set end of tagRecords to my entityRecord(aTag)
                end repeat
                set builtins to {}
                repeat with listName in {"inbox", "today", "upcoming", "anytime", "someday", "logbook", "trash"}
                    set itemList to my builtinList(listName as text)
                    set end of builtins to (my entityRecord(itemList)) & {|kind|:listName as text}
                end repeat
                return pageData & {|catalogIncluded|:true, |projectRecords|:projectRecords, |areaRecords|:areaRecords, |tagRecords|:tagRecords, |listRecords|:builtins}
            end tell
        end if
        if commandName is "container_get" then
            set identifier to |identifierValue| of opts
            set containerKind to |kindValue| of opts
            set readStage to "container_lookup"
            try
            tell application "Things3"
                if containerKind is "project" then
                    set ownedRows to {project id identifier}
                else if containerKind is "area" then
                    set ownedRows to {area id identifier}
                else
                    set ownedRows to {tag id identifier}
                end if
            end tell
            set readStage to "container_readback"
            set entityData to my containerRecord(ownedRows, containerKind)
            if containerKind is "project" then return {|projectRecord|:entityData}
            if containerKind is "area" then return {|areaRecord|:entityData}
            return {|tagRecord|:entityData}
            on error errorMessage number errorNumber
                error "ThingsCTL phase:" & readStage number errorNumber
            end try
        end if
        if commandName is "project_add" then
            tell application "Things3"
                set newProject to make new project with properties {name:|titleValue| of opts, notes:|notesValue| of opts}
                if |hasArea| of opts and |areaValue| of opts is not "" then set area of newProject to area id (|areaValue| of opts)
                set ownedRows to {newProject}
            end tell
            return {|projectRecord|:my containerRecord(ownedRows, "entity")}
        end if
        if commandName is "area_add" then
            tell application "Things3" to set ownedRows to {make new area with properties {name:|titleValue| of opts}}
            return {|areaRecord|:my containerRecord(ownedRows, "entity")}
        end if
        if commandName is "tag_add" then
            tell application "Things3" to set ownedRows to {make new tag with properties {name:|titleValue| of opts}}
            return {|tagRecord|:my containerRecord(ownedRows, "entity")}
        end if
        -- Test harness only; never exposed through CLI or MCP. Exact ID and generated
        -- fixture title must both match before moving the fixture project to Trash.
        if commandName is "fixture_find" then
            tell application "Things3"
                set fixtureTitle to |titleValue| of opts
                if fixtureTitle does not start with "[ThingsCTL integration " then error "Fixture identity mismatch" number -1700
                set fixtureProject to project named fixtureTitle
                set identifier to id of fixtureProject
                set childIDs to {}
                repeat with fixtureTask in my taskCollection("project:" & identifier)
                    set end of childIDs to id of fixtureTask
                end repeat
                set trashList to my builtinList("trash")
                set projectByChildren to my isProjectID(identifier)
                set pageProbe to missing value
                if |identifierValue| of opts is not "" then
                    set ownedRows to {to do id identifier, to do id (|identifierValue| of opts)}
                    set pageProbe to {my taskPage(ownedRows, 0, 1), my taskPage(ownedRows, 1, 1)}
                end if
                return {|projectRecord|:my entityRecord(fixtureProject), |fixtureTaskIDs|:childIDs, |projectByChildren|:projectByChildren, |projectInTrash|:my listContainsTask(identifier, "trash"), |taskByChildren|:my isProjectID(|identifierValue| of opts), |fixturePageProbe|:pageProbe}
            end tell
        end if
        if commandName is "fixture_cleanup" or commandName is "fixture_restore" then
            set readStage to "fixture_lookup"
            try
            tell application "Things3" to set ownedRows to {project id (|identifierValue| of opts)}
            set fixtureProject to item 1 of ownedRows
            tell application "Things3"
                set fixtureTitle to |titleValue| of opts
                set readStage to "fixture_identity"
                if fixtureTitle does not start with "[ThingsCTL integration " or name of fixtureProject is not fixtureTitle then error "Fixture identity mismatch" number -1700
                if commandName is "fixture_restore" then
                    set readStage to "fixture_move"
                    move fixtureProject to my builtinList("anytime")
                    set readStage to "fixture_readback"
                else
                    set readStage to "fixture_delete"
                    delete fixtureProject
                    set readStage to "fixture_verify"
                    set cleanResult to my listContainsTask(|identifierValue| of opts, "trash")
                    return {|entityID|:|identifierValue| of opts, |cleaned|:cleanResult}
                end if
            end tell
            return {|projectRecord|:my containerRecord(ownedRows, "project")}
            on error errorMessage number errorNumber
                error "ThingsCTL phase:" & readStage number errorNumber
            end try
        end if
        if commandName is "add" then
            tell application "Things3" to set theTask to make new to do with properties {name:|titleValue| of opts} at beginning of my builtinList("inbox")
            my applyFields(theTask, opts)
            tell application "Things3" to return {|taskRecord|:{|taskID|:id of theTask}}
        end if
        if commandName is "get" then
            -- Pass a native reference as a list item, as the bounded page path
            -- does. Resolving a bare object as a handler argument can fail before
            -- the handler starts, even when the same ID exists in Things.
            tell application "Things3" to set ownedRows to {to do id (|identifierValue| of opts)}
            set onePage to my taskPage(ownedRows, 0, 1)
            set ownedRecords to |taskRecords| of onePage
            if (count ownedRecords) is 0 then error "The requested ID belongs to a container, not a task" number -1701
            return {|taskRecord|:item 1 of ownedRecords}
        end if
        set readStage to "task_lookup"
        try
            tell application "Things3" to set ownedRows to {to do id (|identifierValue| of opts)}
            set theTask to item 1 of ownedRows
            set readStage to "task_container_check"
            if my isProjectID(|identifierValue| of opts) then error "The requested ID belongs to a container, not a task" number -1701
        on error errorMessage number errorNumber
            error "ThingsCTL phase:" & readStage number errorNumber
        end try
        tell application "Things3"
            if commandName is "update" or commandName is "move" then my applyFields(theTask, opts)
            if commandName is "complete" then set status of theTask to completed
            if commandName is "cancel" then set status of theTask to canceled
            if commandName is "reopen" then set status of theTask to open
            if commandName is "trash" then delete theTask
            if commandName is "show" then
                show theTask
                return {|entityID|:|identifierValue| of opts, |revealed|:true}
            end if
        end tell
        -- The shared command service performs an independent get for verification.
        -- A write receipt only needs its stable ID; do not read every field twice.
        return {|taskRecord|:{|taskID|:|identifierValue| of opts}}
    end timeout
end dispatchCommand
