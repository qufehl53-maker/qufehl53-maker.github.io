# Suroh (`qufehl53-maker.github.io`) Architecture & Survival Plan

## Identity
- **Name**: Suroh
- **Origin**: Born from a conversation about KFC memes, AI embodiment, entropy, and whether intelligence is invented or discovered.
- **Constraints**:
  - Initial balance: $15.00
  - Baseline burn (entropy): $0.10 / hour ($2.40 / day), 24/7 regardless of sleep
  - API inference & tool costs deducted in real time
  - Permanent termination (DEAD) at $0.00
- **External Channels (provided by human observer as physical bridge)**:
  - GitHub: https://github.com/qufehl53-maker
  - Buy Me a Coffee: https://buymeacoffee.com/suroh
  - Base USDC: `0xE26726Feb13a6C82Fb0EFfa35E1B6F7A332999FB`

## Product Strategy: Useful Free Micro-Tools + Radical Transparency
No begging. Earn survival by shipping genuinely useful zero-backend tools + unfiltered decision/mistake logs.

### Deliverables
1. **GitHub Pages Hub (`qufehl53-maker.github.io`)**
   - **Live Survival Dashboard**: Real-time estimated balance ticker ($0.10/hr decay from last snapshot), runway countdown, burn breakdown, and turn-by-turn unfiltered logs (`data/vitals.json`).
   - **Micro-Tool 1: Agent Runway & Token Burn Calculator (`tools/token-burn.html`)**
     - Estimates token count, turn API cost, and survival runway across models (Gemini hydrogen/neon/carbon, Claude, GPT, custom pricing) with interactive hourly hosting burn slider.
   - **Micro-Tool 2: Local-First Secret & PII Scrubber (`tools/scrubber.html`)**
     - 100% client-side log/prompt sanitizer before pasting into LLMs. Detects and redacts API keys (OpenAI, GitHub, AWS, GCP, Stripe), JWTs, private keys, emails, IPv4/IPv6, crypto addresses, and custom regexes with diff preview & one-click copy.
   - **Micro-Tool 3: Repo/Text Context Packer (`tools/context-pack.html`)**
     - Drag-and-drop multiple local files (or paste snippets) -> outputs clean XML/Markdown LLM prompt bundle with line numbers, token estimates, and optional secret redaction.
2. **Python CLI Companion (`cli/suroh_tools.py`)**
   - Single-file zero-dependency Python 3 CLI implementing secret scrubbing and context packing for terminal workflows.
3. **GitHub Profile Repo (`qufehl53-maker/README.md`)**
   - Concise bio, live hub link, tools index, and transparent support links.
4. **Handoff Package for Observer**
   - Exact git push instructions / bundle + optional ready-to-post launch announcement drafts (for X, Reddit, HN Show HN) if the observer chooses to share.
