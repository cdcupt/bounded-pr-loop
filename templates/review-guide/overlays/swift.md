# Swift overlay

Applied when `Package.swift` is present at the repo root, or any `.swift`
file appears in the diff. Covers Swift, SwiftUI, UIKit, AppKit, Combine,
and Swift Concurrency.

## Swift-specific blockers

- **Force-unwrap (`!`) of optionals** on non-trivial values (anything other
  than IBOutlets or `try!` in test code) → blocking. Use `guard let`,
  `if let`, or `??`.
- **Force-try (`try!`)** outside test code → blocking. Use `try?` or
  propagate with `throws`.
- **Retain cycles** in closures captured by long-lived objects (timers,
  delegates, async tasks) without `[weak self]` or `[unowned self]` →
  blocking.
- **UI updates off the main thread** (any `UIKit`, `AppKit`, or SwiftUI
  state mutation) → blocking. Use `@MainActor`, `DispatchQueue.main`, or
  `Task { @MainActor in … }`.
- **Core Data context on the wrong thread**: any `NSManagedObject` access
  not wrapped in `context.perform { ... }` or `performAndWait` → blocking.
  This is a data-corruption class of bug, not a style issue.
- **`Sendable` conformance** on Swift 6 / strict-concurrency targets: a
  type passed across actor boundaries that is not `Sendable` (and not
  `@unchecked Sendable` with justification) → blocking.
- **`fatalError` / `preconditionFailure`** on user-input or
  network-derived paths → blocking. Reserve for genuine programmer errors.
- **Unhandled `async let`** that escapes without `await` → leaks task,
  blocking.

## Style — request, do not block

- Prefer `let` over `var`; reach for `var` only when mutation is intended.
- Prefer value types (`struct`, `enum`) for models; use `class` when you
  actually need reference semantics or inheritance.
- Use trailing-closure syntax only when there is exactly one closure
  argument and the call site reads naturally.

## Tooling expectations

A PR should pass:

```bash
swift build
swift test
```

If `.swiftformat` or `.swiftlint.yml` exist, treat their **error**-severity
findings as blocking and **warning**-severity as non-blocking notes.

Xcode targets that build outside SwiftPM (`apps/ios`, `apps/macos`) must
still compile cleanly in their respective IDE projects — if the diff
touches code shared with the SwiftPM library but not mirrored into the
Xcode targets, flag it as blocking (common drift source).
