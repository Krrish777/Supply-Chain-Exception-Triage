# Supply Chain Triage

AI-powered exception triage for small 3PLs in India. Built on Google ADK,
env-configurable Gemini or Groq models, Firestore, and Firebase Auth.

## Prerequisites

- Python 3.13 (see `.python-version`)
- [`uv`](https://github.com/astral-sh/uv) package manager
- Node.js 20 LTS (for Firebase emulator)
- Java 17 JRE (for Firestore emulator)
- `gcloud` CLI authenticated
- `firebase` CLI (`npm i -g firebase-tools`)
- GCP project with billing enabled
- Firebase project with Google Sign-In OAuth enabled

## Quick Start

```bash
# 1. Clone
git clone https://github.com/<you>/supply-chain-triage.git
cd supply-chain-triage

# 2. Setup (idempotent)
make setup

# 3. Copy env template and fill in secrets
cp .env.template .env
# Edit .env with your GCP / Firebase settings, LLM_PROVIDER / LLM_MODEL_ID,
# and either GEMINI_API_KEY or GROQ_API_KEY

# 4. Run tests
make test

# 5. Launch ADK web UI
make adk-web
# Visit http://localhost:8000
