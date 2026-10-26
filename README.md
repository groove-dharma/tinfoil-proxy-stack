# tinfoil-proxy-stack

An unofficial Layer 7 proxy that lets a network of containers share a single
attested identity when talking to [Tinfoil.sh](https://tinfoil.sh) enclaves.

**Unofficial project. Not affiliated with Tinfoil.** For the official proxy
(one user, one machine) see
[tinfoil-proxy](https://github.com/tinfoilsh/tinfoil-proxy).

## Why

The official Tinfoil proxy is local by design: it serves one user on one
machine. When you run a whole stack of containers that all need attested
access to Tinfoil, you need something that serves the network instead: one
process, one API key, one attested identity, shared by every service on the
internal Docker network.

This proxy sits in front of the official Python SDK and gives a whole
container network a single door to the enclaves.

## Features

- **Attested passthrough**: built on the official
  [tinfoil-python](https://github.com/tinfoilsh/tinfoil-python) SDK.
  Attestation is verified by the SDK on every connection and it fails
  closed: if the enclave is not running the published code, no data is sent.
- **Embedding batching**: requests with more than 32 inputs are split into
  batches, sent sequentially and merged back into a single response, with
  `index` renumbered and `usage` totals summed. Neither the SDK nor the
  official proxy do this.
- **Whitelisted parameters**: only known OpenAI-style parameters are
  forwarded (`KNOWN_CHAT` / `KNOWN_EMBED`), including `reasoning_effort`.
- **Streaming**: `/v1/chat/completions` supports `stream: true` (SSE).
- **Static model catalog**: `/v1/models` serves a static catalog so clients
  can list models without hitting the enclave. Override it with
  `TINFOIL_MODELS`.

## Quick start

```bash
docker compose up -d --build
```

The proxy listens on port 3302 inside the Docker network. Point any service at:

```
http://tinfoil-proxy:3302/v1
```

## Configuration

| Variable | Required | Default | What it does |
| --- | --- | --- | --- |
| `TINFOIL_API_KEY` | yes | none | Your Tinfoil API key |
| `TINFOIL_MODELS` | no | built-in catalog | Comma-separated model IDs served by `/v1/models` |

## Endpoints

- `GET /health` (liveness probe)
- `GET /v1/models` (static catalog)
- `POST /v1/chat/completions` (passthrough, streaming supported)
- `POST /v1/embeddings` (passthrough with batching above 32 inputs)

## License

Apache-2.0. See [LICENSE](LICENSE).
