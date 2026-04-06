import os
import sys
import httpx
import asyncio

# Ensure src/ is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from app.config import Config

async def verify_llm_connection():
    print("====================================")
    print("  Ollama / vLLM Internal Net Check  ")
    print("====================================")
    
    base_url = Config.LLM_BASE_URL.rstrip('/')
    model = Config.LLM_MODEL_NAME
    
    print(f"[*] Configured Base URL: {base_url}")
    print(f"[*] Configured Model: {model}")
    
    # Check Ollama base or vLLM models endpoint
    # vLLM exposes /v1/models, Ollama exposes /api/tags
    # Often LLM_BASE_URL for ollama is http://localhost:11434/v1 for OpenAI compat
    test_urls = [
        f"{base_url}/models",                     # OpenAI API compat
        base_url.replace('/v1', '') + "/api/tags" # Native Ollama
    ]
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        success = False
        for url in test_urls:
            print(f"[*] Pinging {url} ...")
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    print(f"[+] Connection successful! Status: {resp.status_code}")
                    data = resp.json()
                    
                    # Try to parse available models
                    models = []
                    if "data" in data:  # OpenAI compat
                        models = [m.get("id") for m in data.get("data", [])]
                    elif "models" in data:  # Ollama native
                        models = [m.get("name") for m in data.get("models", [])]
                        
                    print(f"[+] Available models ({len(models)}): {', '.join(models[:5])}{'...' if len(models) > 5 else ''}")
                    
                    if model in models or any(model in m for m in models):
                        print(f"[+] Target model '{model}' is available.")
                    else:
                        print(f"[-] WARNING: Target model '{model}' not found in the list.")
                        
                    success = True
                    break
                else:
                    print(f"[-] Received unexpected status code: {resp.status_code}")
            except Exception as e:
                print(f"[-] Failed to connect: {e}")
                
        if not success:
            print("[!] Could not connect to any LLM endpoints.")
            print("[!] Please check if the LLM server is running and accessible from this network.")
            sys.exit(1)
            
if __name__ == "__main__":
    asyncio.run(verify_llm_connection())
