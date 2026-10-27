"""Optional live smoke checks for Nebius Token Factory and Tavily.

This script makes one model inference request and one Tavily search request.
It never prints API keys or full provider error messages.
"""
import os
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()
MODEL_ID = os.getenv("NEBIUS_MODEL_ID", "nvidia/Nemotron-3-Ultra-550b-a55b")
BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.us-central1.nebius.com/v1/")


def check_nebius() -> bool:
    key = os.getenv("NEBIUS_API_KEY")
    if not key:
        print("Nebius Token Factory: SKIPPED (NEBIUS_API_KEY is not configured)")
        return False
    try:
        from openai import OpenAI
        client = OpenAI(base_url=BASE_URL, api_key=key, timeout=25.0, max_retries=0)
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": "Reply with exactly: DIGITAL_SHADOW_OK"}],
            temperature=0,
            max_tokens=32,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            print(f"Nebius Token Factory: FAIL (empty response from {MODEL_ID})")
            return False
        print(f"Nebius Token Factory: PASS (model={MODEL_ID}, response_received=yes)")
        return True
    except Exception as exc:
        print(f"Nebius Token Factory: FAIL ({type(exc).__name__}; key value suppressed)")
        return False


def check_tavily() -> bool:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        print("Tavily: SKIPPED (TAVILY_API_KEY is not configured)")
        return False
    try:
        from tavily import TavilyClient
        result = TavilyClient(api_key=key).search(
            query="global shipping port congestion and freight delay news",
            max_results=3,
            topic="news",
        )
        if not isinstance(result, dict) or not isinstance(result.get("results", []), list):
            print("Tavily: FAIL (unexpected response format)")
            return False
        rows = result.get("results", [])
        valid_rows = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            parsed = urlparse(url)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                valid_rows.append(row)
        if not valid_rows:
            print("Tavily: FAIL (request completed but returned no usable HTTP(S) source URLs)")
            return False
        domains = sorted({
            urlparse(str(row.get("url") or "")).hostname
            for row in valid_rows
            if urlparse(str(row.get("url") or "")).hostname
        })
        print(f"Tavily: PASS (API request succeeded, usable_sources={len(valid_rows)}, domains={len(domains)})")
        return True
    except Exception as exc:
        print(f"Tavily: FAIL ({type(exc).__name__}; key value suppressed)")
        return False


def main() -> int:
    neb = check_nebius()
    tav = check_tavily()
    if neb and tav:
        print("Live integration smoke check: PASS")
        return 0
    print("Live integration smoke check: INCOMPLETE. Configure valid credentials and rerun before submission.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
