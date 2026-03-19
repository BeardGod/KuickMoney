# 💰 KuickMoney Retail Bot

A powerful Windows desktop application for automated retail purchasing. Monitor products, detect queues, and checkout faster than manual browsing.

![KuickMoney](https://img.shields.io/badge/Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white)

## Features

- 🌐 **Multi-Retailer Support** - Pokemon Center, Target, Walmart
- 🔍 **Product Monitoring** - Real-time availability tracking
- 🚀 **Fast ATC** - Automated add-to-cart with anti-detection
- 💳 **Payment Storage** - Encrypted card storage for instant checkout
- 📱 **Telegram Alerts** - Get notified when queues form or checkout completes
- 🌐 **Proxy Support** - Residential proxy integration for bypassing blocks
- 🖥️ **Nice GUI** - Modern dark theme interface

## Download

**Latest Release:** [KuickMoney v0.1.0 (Windows .exe)](https://github.com/YOUR_USERNAME/kuickmoney/releases/latest)

Simply download the ZIP, extract, and run `KuickMoney.exe`

## Quick Start

1. Extract the ZIP file
2. Run `KuickMoney.exe`
3. Configure your proxy (Settings → Proxy)
4. Add your Telegram bot token (Settings → Telegram)
5. Add payment info (Settings → Payment)
6. Add products to monitor
7. Wait for alerts and checkout!

## Configuration

### Proxy Setup

For best results, use residential proxies (datacenter IPs will be blocked):

```
Host: gate.decodo.com
Port: 10001
Username: your-decodo-username
Password: your-decodo-password
```

### Telegram Alerts

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Get your Chat ID from [@userinfobot](https://t.me/userinfobot)
3. Enter both in Settings

### Payment Info

Your card data is encrypted with AES-256 and stored locally only.

## Development

### Requirements

- Rust 1.75+
- Node.js 20+
- Windows 10/11

### Build from Source

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/kuickmoney.git
cd kuickmoney

# Install Tauri CLI
cargo install tauri-cli --version "^2"

# Build
cargo tauri build --bundles nsis,zip
```

The executable will be in `src-tauri/target/release/bundle/`

### Project Structure

```
kuickmoney/
├── src-tauri/           # Rust backend
│   ├── src/
│   │   ├── lib.rs      # Main bot logic
│   │   └── main.rs     # Entry point
│   ├── Cargo.toml      # Rust dependencies
│   └── tauri.conf.json # Tauri config
├── frontend/
│   └── index.html       # GUI (HTML/CSS/JS)
├── .github/
│   └── workflows/
│       └── build.yml    # Windows build CI
└── README.md
```

## How It Works

1. **Monitor** - Headless browser checks products every 30 seconds
2. **Detect** - Identifies queue/waiting room patterns
3. **Alert** - Sends Telegram notification when queue appears
4. **ATC** - Automatically adds item to cart
5. **Checkout** - Fills payment info and completes purchase

## Supported Retailers

| Retailer | Anti-Bot | Proxy Required |
|----------|----------|---------------|
| Pokemon Center | Incapsula | ✅ Yes |
| Target | PerimeterX | ✅ Yes |
| Walmart | Custom | ✅ Yes |

## Disclaimer

This tool is for educational purposes. Users are responsible for:
- Complying with retailer Terms of Service
- Applicable laws in their jurisdiction
- Any charges incurred

The authors are not responsible for any misuse.

## License

MIT License - See LICENSE file

---

**Made with 💰 by KuickMoney**
