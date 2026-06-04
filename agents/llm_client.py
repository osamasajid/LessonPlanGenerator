import os
import httpx
from dataclasses import dataclass
from anthropic import AsyncAnthropic
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

class LLMClientError(Exception):
    pass

@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int

class LLMClient:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
        
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
        
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    async def generate(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LLMResponse:
        """
        Generates completions asynchronously using the selected provider.
        Returns an LLMResponse containing the text and token counts.
        """
        if self.provider == "ollama":
            return await self._generate_ollama(system_prompt, user_prompt, max_tokens)
        elif self.provider == "anthropic":
            return await self._generate_anthropic(system_prompt, user_prompt, max_tokens)
        elif self.provider == "gemini":
            return await self._generate_gemini(system_prompt, user_prompt, max_tokens)
        else:
            raise LLMClientError(f"Unsupported LLM provider: {self.provider}")

    async def _generate_ollama(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LLMResponse:
        payload = {
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "num_predict": max_tokens
            }
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json=payload,
                    timeout=600.0  # Ollama can take a while on slower local hardware
                )
                response.raise_for_status()
                data = response.json()
                
                text = data["message"]["content"]
                input_tokens = data.get("prompt_eval_count", 0)
                output_tokens = data.get("eval_count", 0)
                
                return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)
            except Exception as e:
                raise LLMClientError(f"Ollama generation failed: {str(e)}")

    async def _generate_anthropic(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LLMResponse:
        if not self.anthropic_key:
            raise LLMClientError("Anthropic API key is not configured in .env")
        
        try:
            client = AsyncAnthropic(api_key=self.anthropic_key)
            response = await client.messages.create(
                model=self.anthropic_model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            
            text = response.content[0].text
            input_tokens = response.usage.input_tokens if hasattr(response, "usage") else 0
            output_tokens = response.usage.output_tokens if hasattr(response, "usage") else 0
            
            return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)
        except Exception as e:
            raise LLMClientError(f"Anthropic Claude generation failed: {str(e)}")

    async def _generate_gemini(self, system_prompt: str, user_prompt: str, max_tokens: int) -> LLMResponse:
        if not self.gemini_key:
            raise LLMClientError("Gemini API key is not configured in .env")
        
        # Use direct async HTTP POST to Gemini API to ensure a clean async workflow without SDK thread pools
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_key}"
        payload = {
            "contents": [
                {
                    "parts": [{"text": user_prompt}]
                }
            ],
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "generationConfig": {
                "maxOutputTokens": max_tokens
            }
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                usage = data.get("usageMetadata", {})
                input_tokens = usage.get("promptTokenCount", 0)
                output_tokens = usage.get("candidatesTokenCount", 0)
                
                return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)
            except Exception as e:
                raise LLMClientError(f"Gemini generation failed: {str(e)}")

def get_llm_client() -> LLMClient:
    return LLMClient()
