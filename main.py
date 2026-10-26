import os
import json
import logging
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from tinfoil import AsyncTinfoilAI

app = FastAPI(title="Tinfoil Attestation Proxy")
logger = logging.getLogger("tinfoil-proxy")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

TINFOIL_API_KEY = os.environ.get("TINFOIL_API_KEY", "")
client = AsyncTinfoilAI(api_key=TINFOIL_API_KEY, timeout=300)

KNOWN_CHAT = {"model", "messages", "temperature", "max_tokens", "top_p",
              "frequency_penalty", "presence_penalty", "stop", "stream",
              "response_format", "seed", "n", "logprobs", "top_logprobs",
              "user", "tools", "tool_choice", "logit_bias",
              "reasoning_effort"}
KNOWN_EMBED = {"model", "input", "encoding_format", "dimensions", "user"}

STATIC_MODELS = {
    "object": "list",
    "data": [
        {"id": "gpt-oss-120b", "object": "model", "owned_by": "tinfoil"},
        {"id": "gpt-oss-safeguard-120b", "object": "model", "owned_by": "tinfoil"},
        {"id": "gemma4-31b", "object": "model", "owned_by": "tinfoil"},
        {"id": "deepseek-v4-flash", "object": "model", "owned_by": "tinfoil"},
        {"id": "nomic-embed-text", "object": "model", "owned_by": "tinfoil"},
        {"id": "voxtral-small-24b", "object": "model", "owned_by": "tinfoil"},
        {"id": "whisper-large-v3-turbo", "object": "model", "owned_by": "tinfoil"},
        {"id": "qwen3-vl-30b", "object": "model", "owned_by": "tinfoil"},
    ],
}

TINFOIL_MODELS = os.environ.get("TINFOIL_MODELS", "").strip()
if TINFOIL_MODELS:
    STATIC_MODELS = {
        "object": "list",
        "data": [
            {"id": model_id.strip(), "object": "model", "owned_by": "tinfoil"}
            for model_id in TINFOIL_MODELS.split(",")
            if model_id.strip()
        ],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"service": "tinfoil-attestation-proxy", "attestation": True}


@app.get("/v1/models")
async def list_models():
    return Response(content=json.dumps(STATIC_MODELS), media_type="application/json")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    kwargs = {k: v for k, v in body.items() if k in KNOWN_CHAT}
    try:
        if kwargs.get("stream"):
            stream = await client.chat.completions.create(**kwargs)
            async def generate():
                async for chunk in stream:
                    yield f"data: {chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(generate(), media_type="text/event-stream")
        response = await client.chat.completions.create(**kwargs)
        return Response(content=response.model_dump_json(), media_type="application/json")
    except Exception as e:
        logger.error(f"Chat error: {e}")
        status_code = getattr(e, 'status_code', None) or 502
        return Response(content=json.dumps({"error": {"message": str(e), "type": "proxy_error"}}),
                       status_code=status_code, media_type="application/json")


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    kwargs = {k: v for k, v in body.items() if k in KNOWN_EMBED}

    input_data = kwargs.get("input")

    if not isinstance(input_data, (str, list)):
        return Response(
            content=json.dumps({"error": {"message": "'input' must be a string or a list of strings", "type": "invalid_request_error"}}),
            status_code=400,
            media_type="application/json",
        )

    BATCH_SIZE = 32

    if isinstance(input_data, str) or (isinstance(input_data, list) and len(input_data) <= BATCH_SIZE):
        try:
            response = await client.embeddings.create(**kwargs)
            return Response(content=response.model_dump_json(), media_type="application/json")
        except Exception as e:
            logger.error(f"Embeddings error: {e}")
            status_code = getattr(e, 'status_code', None) or 502
            return Response(content=json.dumps({"error": {"message": str(e), "type": "proxy_error"}}),
                           status_code=status_code, media_type="application/json")

    batches = [input_data[i:i + BATCH_SIZE] for i in range(0, len(input_data), BATCH_SIZE)]
    all_data = []
    total_prompt_tokens = 0
    total_total_tokens = 0
    model = kwargs.get("model", "")

    for batch_idx, batch in enumerate(batches):
        batch_kwargs = {**kwargs, "input": batch}
        try:
            response = await client.embeddings.create(**batch_kwargs)
            resp_json = response.model_dump()
            for item in resp_json["data"]:
                item["index"] = batch_idx * BATCH_SIZE + item["index"]
            all_data.extend(resp_json["data"])
            total_prompt_tokens += resp_json.get("usage", {}).get("prompt_tokens", 0)
            total_total_tokens += resp_json.get("usage", {}).get("total_tokens", 0)
        except Exception as e:
            logger.error(f"Embeddings batch {batch_idx} error: {e}")
            status_code = getattr(e, 'status_code', None) or 502
            return Response(content=json.dumps({"error": {"message": str(e), "type": "proxy_error"}}),
                           status_code=status_code, media_type="application/json")

    merged = {
        "object": "list",
        "data": all_data,
        "model": model,
        "usage": {"prompt_tokens": total_prompt_tokens, "total_tokens": total_total_tokens},
    }

    return Response(content=json.dumps(merged), media_type="application/json")
