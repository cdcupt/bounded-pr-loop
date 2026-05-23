# TypeScript overlay

Applied when `tsconfig.json` is present, or any `.ts` / `.tsx` file
appears in the diff. Covers Node, browser, React, Next.js, Express.

## TypeScript-specific blockers

- **`any` in production code** (outside tests, type shims, or
  `// @ts-expect-error` lines with justification) → blocking. Use
  `unknown` and narrow.
- **Type assertions (`as`)** used to silence a real type error → blocking.
  Acceptable only when narrowing a `unknown` after a runtime check, or
  when the compiler genuinely cannot infer a safe type.
- **Floating Promises** — any `async` call ignored without `await`, `.then`,
  `void`, or assignment to a variable → blocking. Use ESLint's
  `no-floating-promises` rule as the reference.
- **Missing `await` inside `try`** — `try { riskyAsync(); } catch { ... }`
  silently swallows the rejection. Blocking.
- **`JSON.parse` of untrusted input** without a schema validator (Zod, Yup,
  Joi, or hand-rolled narrowing) → blocking. PRs adding new request-handling
  paths must validate the body.
- **`dangerouslySetInnerHTML`** without a sanitizer (DOMPurify or
  equivalent) → blocking.
- **`process.env.X` used directly** without a presence check at module
  load → blocking when the value is required for the module to function.
- **React `useEffect` missing dependencies** that the linter would flag,
  unless the author left a `// eslint-disable-next-line` with a reason →
  blocking.
- **React list rendering** without stable `key` prop → blocking.

## Style — request, do not block

- Prefer `interface` for object shapes that may be extended;
  `type` for unions, intersections, and mapped types.
- Prefer string-literal unions over `enum` unless `enum` is needed for
  interop.
- Default exports allowed but discouraged for shared library code (harder
  to refactor names across the codebase).

## Tooling expectations

A PR should pass:

```bash
pnpm tsc --noEmit
pnpm eslint .
pnpm test
```

If `prettier` is configured, treat formatting drift as a non-blocking
note (the consumer should add a format-on-save hook, not require Codex
to police it).
