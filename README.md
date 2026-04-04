# Samsung CE Intelligence System

Enterprise-grade news aggregation and intelligence briefing system for Samsung Consumer Electronics.

## Features

- **Multi-source fetching**: RSS feeds, web scraping, REST APIs
- **5-topic classification**: Competitors, Technologies, Manufacturing, Exhibitions, Supply Chain
- **3-layer deduplication**: URL hash, title similarity, semantic embedding
- **Historical tracking**: SQLite database prevents repeat articles
- **Automated reports**: HTML and Markdown formats
- **Email delivery**: SMTP with professional HTML templates
- **GitHub Actions**: Daily automated runs

## Quick Start

### Prerequisites
- Python 3.11+
- DeepSeek API key (for summarization)
- Gmail account with App Password (for email)

### Installation

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/samsung-ce-intelligence.git
cd samsung-ce-intelligence

# Install dependencies
pip install -r requirements.txt

# Configure secrets
export DEEPSEEK_API_KEY="your-api-key"
export SENDER_EMAIL="your-email@gmail.com"
export SENDER_PASSWORD="your-app-password"
export RECEIVER_EMAIL="recipient@example.com"

# Run manually
python src/main.py
