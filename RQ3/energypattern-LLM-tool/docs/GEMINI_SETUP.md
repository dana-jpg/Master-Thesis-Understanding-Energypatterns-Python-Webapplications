# Google Gemini Setup Guide

## Getting Your API Key

1. Visit [Google AI Studio](https://ai.google.dev/)
2. Click "Get API key" 
3. Sign in with your Google account
4. Create a new API key or use an existing one
5. Copy the API key

## Setting Up the Environment Variable

### Option 1: Export in Terminal (Temporary)
```bash
export GOOGLE_API_KEY="your-api-key-here"
```

### Option 2: Add to Shell Profile (Permanent)

For **zsh** (default on macOS):
```bash
echo 'export GOOGLE_API_KEY="your-api-key-here"' >> ~/.zshrc
source ~/.zshrc
```

For **bash**:
```bash
echo 'export GOOGLE_API_KEY="your-api-key-here"' >> ~/.bash_profile
source ~/.bash_profile
```

### Option 3: Use .env File (Recommended for Development)

1. Create a `.env` file in your project root:
```bash
echo "GOOGLE_API_KEY=your-api-key-here" > .env
```

2. Add `.env` to your `.gitignore`:
```bash
echo ".env" >> .gitignore
```

3. Install python-dotenv:
```bash
/Users/rib/langchain-venv/bin/pip install python-dotenv
```

4. Load it in your `server.py` (add at the top):
```python
from dotenv import load_dotenv
load_dotenv()
```

## Usage

The code is now configured to use **Gemini by default** with the `gemini-2.0-flash-exp` model.

### Using with Default Settings
```python
from app.llm import get_llm

# Uses Gemini by default
llm = get_llm()
```

### Switching Between Providers
```python
# Use Gemini (default)
llm = get_llm(provider="gemini", model="gemini-2.0-flash-exp")

# Use a different Gemini model
llm = get_llm(provider="gemini", model="gemini-1.5-flash")

# Switch back to Ollama if needed
llm = get_llm(provider="ollama", model="qwen2.5:3b-instruct")
```
