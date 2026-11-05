# Financial MCP architecture

The advisor uses the official Python MCP SDK and real JSON-RPC over stdio:

```text
Browser -> Next.js BFF -> authenticated FastAPI advisor
                          -> private MCP client (per turn)
                          -> Python stdio child process
                          -> financial tools / wealth://snapshot
                          -> PostgreSQL with user + tenant RLS context
```

The backend passes verified identity in the child process environment. Model inputs
contain only financial filters/calculation arguments. The MCP tool schemas reject
unknown fields, including user/tenant identifiers. Nine existing executors are reused;
the advisor no longer invokes them directly. Snapshot access also crosses MCP.

## Lifecycle and failures

At most `MCP_MAX_CONCURRENT` turns run per API process. Queue acquisition is bounded
by `MCP_QUEUE_TIMEOUT_S`; protocol calls by `MCP_CALL_TIMEOUT_S`; the complete model
turn by `MCP_TURN_TIMEOUT_S`. Each child has a one-to-two-connection database pool.
The session and transport are closed on completion, failure or cancellation. stdout
is reserved for protocol messages; child logs go to stderr.

Transport/resource failures return `MCP_UNAVAILABLE` (503); capacity exhaustion returns
`SERVICE_BUSY`. Invalid tool arguments return a sanitized tool error. There is no
silent direct-execution fallback. Only successful MCP calls count as tool-grounding
evidence, although that alone cannot prove every generated number is correct.

The provider interface and chat response fields are preserved. Logs record request
context, tool names, success and duration, not tool arguments/results. Synthetic
profiles and simulated advisor responses are identified explicitly.

## Trust boundary

This is a private process transport, not a public remote OAuth MCP service. A local
operator who can run the process and access its database credentials is already
trusted. The app's authenticated route, ownership checks and database policies enforce
user access. Do not publish a generic launcher that lets clients supply arbitrary
identity environment values. Exposing remote MCP later requires its own authorization
design; it is outside this prototype.

PayPal order creation/capture are intentionally absent from the MCP tool catalog.
The user controls those operations through authenticated UI/API actions.
