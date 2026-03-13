# Groq Setup Guide

## Getting Your API Key

1. Visit [Groq Cloud Console](https://console.groq.com/keys)
2. Sign in (GitHub or Google)
3. Click "Create API Key"
4. Give it a name (e.g., "code-analyzer")
5. Copy the key (it starts with `gsk_`)

## Setting Up the Environment Variable

### Option 1: Export in Terminal (Temporary)
```bash
export GROQ_API_KEY="your-api-key-here"
```

### Option 2: Add to Shell Profile (Permanent)

For **zsh** (default on macOS):
```bash
echo 'export GROQ_API_KEY="your-api-key-here"' >> ~/.zshrc
source ~/.zshrc
```

### Option 3: Use .env File

If you created a `.env` file for Gemini, simply add this line to it:

```bash
GROQ_API_KEY=your-api-key-here
```





