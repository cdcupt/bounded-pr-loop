# Go overlay

Applied automatically when `go.mod` is present at the repo root, or any
`.go` file appears in the diff.

## Go-specific blockers

- **Error wrapping**: errors returned from collaborators should be wrapped
  with `fmt.Errorf("...: %w", err)` so callers can `errors.Is` / `errors.As`
  against them. Bare `return err` at package boundaries is a smell.
- **Naked returns** in functions longer than ~10 lines are confusing.
- **Goroutine leaks**: any `go func() { ... }()` must have a clear stop
  condition — `context.Context`, a `done` channel, or finite work.
- **`context.Context` placement**: must be the first parameter of any
  function that accepts one. Never store a `Context` in a struct field
  unless the struct is request-scoped.
- **`sync.Mutex` zero value**: do not copy structs containing a mutex.
  `go vet` catches this; if it fires, treat it as blocking.
- **Maps under concurrent access** without `sync.RWMutex` or
  `sync.Map` → data race, blocking.
- **HTTP handlers** must not call `os.Exit`, `log.Fatal`, or `panic` on
  request-driven paths.
- **Unbuffered `defer rows.Close()`** missing after `db.Query` → resource
  leak, blocking.
- **Hardcoded sleeps** in tests → flake source, blocking.

## Style — request, do not block

- Prefer the standard library over third-party deps for trivial helpers.
- `if err != nil { return err }` is idiomatic; do not request refactors
  into clever generic helpers.
- `interface{}` is `any` since Go 1.18; either is acceptable.

## Tooling expectations

A PR should pass:

```bash
gofmt -l .          # no diff
go vet ./...
go test ./...
```

If the repo uses `golangci-lint`, treat its `error`-severity findings as
blocking. Treat `warning` severity as non-blocking notes.
