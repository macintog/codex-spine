# Deepening

Use this guide when a candidate cluster looks shallow and the next question is how to test the deepened module.

## Dependency Categories

### In-Process

Pure computation, in-memory state, and no I/O.

Usually deepenable directly. Merge the behavior behind the new interface and test through that interface.

### Local-Substitutable

Dependencies with local test stand-ins, such as an in-memory filesystem or local database emulator.

Deepenable when the stand-in can run in the test suite. Keep the seam internal unless callers truly need it.

### Remote But Owned

Your own service across a network or process seam.

Define a port at the seam. Keep the core behavior in the deep module, use a production adapter for the transport, and use an in-memory adapter in tests.

### True External

Third-party systems you do not control.

Inject an interface for the external dependency. Tests provide a mock adapter or fake adapter that captures the external behavior the module relies on.

## Seam Discipline

- Do not add a port for a single production adapter unless a test adapter or second production adapter makes the seam real.
- Prefer internal seams for implementation convenience and external seams only for caller-facing variation.
- Keep implementation testing behind the module interface unless the module itself owns private internal seams worth testing.

## Testing Strategy

- Write new tests at the deepened module's interface.
- Assert observable outcomes through the interface, not private state.
- Keep old shallow tests only until replacement coverage exists.
- Once interface-level tests prove the behavior, delete tests that only pin old choreography.
