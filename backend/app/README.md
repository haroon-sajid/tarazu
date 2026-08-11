# backend/app/

**Purpose:** The FastAPI application package. `main.py` creates the app and
wires up module routers, `core/` holds cross-cutting infrastructure, `shared/`
holds the data contracts, and `modules/` holds all business capability, one
folder per bounded module.

**Inputs and outputs:** See [backend/README.md](../README.md). Internally, data
flows between modules only as `shared/` schema objects, through each module's
`service.py` public interface.

**Does not belong here:** Business logic at this level. `main.py` is wiring
only; no logic lives outside a module, and nothing here imports module internals
beyond routers and service interfaces.
