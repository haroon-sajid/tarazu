# backend/app/

**Purpose:** The FastAPI application package. `main.py` creates the app and wires
up module routers; `core/` holds cross-cutting infrastructure; `shared/` holds the
data contracts; `modules/` holds all business capability, one folder per bounded
module.

**Inputs/Outputs:** See [backend/README.md](../README.md). Internally, data flows
between modules ONLY as `shared/` schema objects, through each module's
`service.py` public interface.

**Does NOT belong here:** Business logic at this level — `main.py` is wiring only.
No logic outside a module; no module internals imported here beyond routers/service
interfaces.
