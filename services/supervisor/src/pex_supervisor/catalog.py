"""Pluggable PEX supervisor model catalog.

This is a menu, not a default brain. IDs change; UIs should also list live
vendor /models endpoints. No API keys live here.
"""

from __future__ import annotations

CATALOG: list[dict[str, str]] = [
    # OpenAI
    {"provider": "openai", "model_id": "gpt-5.6-sol", "label": "GPT 5.6 Sol"},
    {"provider": "openai", "model_id": "gpt-5.6-terra", "label": "GPT 5.6 Terra"},
    {"provider": "openai", "model_id": "gpt-5.6-luna", "label": "GPT 5.6 Luna"},
    {"provider": "openai", "model_id": "gpt-5.5", "label": "GPT 5.5"},
    {"provider": "openai", "model_id": "gpt-5.5-pro", "label": "GPT 5.5 Pro"},
    {"provider": "openai", "model_id": "gpt-5.4", "label": "GPT 5.4"},
    {"provider": "openai", "model_id": "gpt-5.4-mini", "label": "GPT 5.4 Mini"},
    {"provider": "openai", "model_id": "gpt-5.4-nano", "label": "GPT 5.4 Nano"},
    {"provider": "openai", "model_id": "gpt-5.3-codex", "label": "GPT 5.3 Codex"},
    {"provider": "openai", "model_id": "gpt-5.2", "label": "GPT 5.2"},
    {"provider": "openai", "model_id": "gpt-5.1", "label": "GPT 5.1"},
    {"provider": "openai", "model_id": "gpt-5", "label": "GPT 5"},
    # Anthropic
    {"provider": "anthropic", "model_id": "claude-fable-5", "label": "Claude Fable 5"},
    {"provider": "anthropic", "model_id": "claude-opus-5", "label": "Claude Opus 5"},
    {"provider": "anthropic", "model_id": "claude-sonnet-5", "label": "Claude Sonnet 5"},
    {"provider": "anthropic", "model_id": "claude-opus-4-8", "label": "Claude Opus 4.8"},
    {"provider": "anthropic", "model_id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
    {"provider": "anthropic", "model_id": "claude-haiku-4-5", "label": "Claude Haiku 4.5"},
    # Google
    {"provider": "google", "model_id": "gemini-3.1-pro", "label": "Gemini 3.1 Pro"},
    {"provider": "google", "model_id": "gemini-3.7-flash", "label": "Gemini 3.7 Flash"},
    {"provider": "google", "model_id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash"},
    {"provider": "google", "model_id": "gemini-3-flash", "label": "Gemini 3 Flash"},
    # xAI
    {"provider": "grok", "model_id": "grok-4.6", "label": "Grok 4.6"},
    {"provider": "grok", "model_id": "grok-4.5", "label": "Grok 4.5"},
    {"provider": "grok", "model_id": "grok-build-0.1", "label": "Grok Build 0.1"},
    # OpenCode Zen / Go
    {"provider": "zen", "model_id": "laguna-s-2.1-free", "label": "Laguna S 2.1 Free (Zen)"},
    {"provider": "zen", "model_id": "big-pickle", "label": "Big Pickle (Zen)"},
    {"provider": "zen", "model_id": "muse-spark-1.2", "label": "Muse Spark 1.2"},
    {"provider": "zen", "model_id": "muse-spark-1.2-contributor-free", "label": "Muse Spark Contributor Free"},
    {"provider": "zen", "model_id": "big-pickle", "label": "Big Pickle"},
    {"provider": "opencode_go", "model_id": "ox-alpha-free", "label": "Ox Alpha Free (Go)"},
    # Open weights / other hosted
    {"provider": "deepseek", "model_id": "deepseek-chat", "label": "DeepSeek V4 Chat"},
    {"provider": "moonshot", "model_id": "kimi-k2.7-code", "label": "Kimi K2.7 Code"},
    {"provider": "mistral", "model_id": "mistral-large-latest", "label": "Mistral Large"},
    {"provider": "groq", "model_id": "llama-4-scout", "label": "Llama 4 Scout (Groq)"},
    {"provider": "together", "model_id": "Qwen/Qwen3-Coder-480B-A35B-Instruct", "label": "Qwen3 Coder (Together)"},
    {"provider": "fireworks", "model_id": "accounts/fireworks/models/kimi-k2p5", "label": "Kimi (Fireworks)"},
    {"provider": "nvidia", "model_id": "nvidia/llama-3.1-nemotron-70b-instruct", "label": "Nemotron (NIM)"},
    # Gateways (OpenRouter slugs — one key, many models)
    {"provider": "openrouter", "model_id": "anthropic/claude-sonnet-4.6", "label": "Claude Sonnet 4.6 via OpenRouter"},
    {"provider": "openrouter", "model_id": "openai/gpt-5.2", "label": "GPT 5.2 via OpenRouter"},
    {"provider": "openrouter", "model_id": "x-ai/grok-4.6", "label": "Grok 4.6 via OpenRouter"},
    {"provider": "openrouter", "model_id": "google/gemini-3-flash", "label": "Gemini 3 Flash via OpenRouter"},
    {"provider": "openrouter", "model_id": "deepseek/deepseek-v3.2", "label": "DeepSeek via OpenRouter"},
    {"provider": "openrouter", "model_id": "qwen/qwen3-coder", "label": "Qwen3 Coder via OpenRouter"},
    {"provider": "openrouter", "model_id": "meta-llama/llama-4-maverick", "label": "Llama 4 Maverick via OpenRouter"},
    {"provider": "openrouter", "model_id": "z-ai/glm-4.6", "label": "GLM via OpenRouter"},
    {"provider": "openrouter", "model_id": "minimax/minimax-m2", "label": "MiniMax via OpenRouter"},
    # Local placeholders — user replaces with whatever they pulled
    {"provider": "ollama", "model_id": "llama3.3", "label": "Ollama Llama"},
    {"provider": "lmstudio", "model_id": "local-model", "label": "LM Studio local"},
    {"provider": "llamacpp", "model_id": "local", "label": "llama.cpp server"},
    {"provider": "vllm", "model_id": "local", "label": "vLLM / SGLang"},
    {"provider": "custom", "model_id": "user-supplied", "label": "Custom endpoint"},
    {"provider": "github_models", "model_id": "openai/gpt-4.1", "label": "GPT 4.1 via GitHub Models"},
    {"provider": "writer", "model_id": "palmyra-x5", "label": "Writer Palmyra"},
    {"provider": "llama_api", "model_id": "Llama-4-Maverick-17B-128E-Instruct-FP8", "label": "Llama API"},
]


def catalog() -> list[dict[str, str]]:
    return list(CATALOG)
