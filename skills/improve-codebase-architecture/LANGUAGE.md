# Language

Shared vocabulary for this skill. Use these terms consistently so architecture discussion stays precise.

## Terms

**Module**
Anything with an interface and an implementation. This can be a function, class, package, subsystem, or vertical slice.

**Interface**
Everything a caller must know to use the module correctly. This includes the type signature plus invariants, ordering constraints, error modes, required configuration, and performance characteristics.

**Implementation**
The code inside a module.

**Depth**
The amount of useful behavior a caller can reach through a module's interface. A deep module puts a lot of behavior behind a clear interface. A shallow module exposes an interface almost as complex as its implementation.

**Seam**
A place where behavior can change without editing in that place. The seam is where a module's interface lives.

**Adapter**
A concrete thing that satisfies an interface at a seam.

**Leverage**
What callers get from depth: more capability per fact they need to learn.

**Locality**
What maintainers get from depth: change, bugs, knowledge, and verification concentrate in one place rather than spreading across callers.

## Principles

- Depth is a property of the interface, not the implementation.
- A deep module can have internal seams used by its own implementation and tests without exposing them to callers.
- The deletion test: if deleting a module makes complexity vanish, the module was probably pass-through; if complexity reappears across callers, the module was earning its keep.
- The interface is the test surface. If tests need to reach past the interface, the module shape may be wrong.
- One adapter means a hypothetical seam. Two adapters means a real seam. Do not add a seam unless something actually varies across it.

## Relationships

- A module has an interface and an implementation.
- Depth is measured against the interface.
- A seam is where the interface lives.
- An adapter sits at a seam and satisfies the interface.
- Depth creates leverage for callers and locality for maintainers.
