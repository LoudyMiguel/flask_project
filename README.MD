# MarketFlow Server — Complete Setup Guide

This guide covers everything you need to set up and run the MarketFlow Go backend server on any device — whether it's your development machine, a friend's laptop, or a production server.

---

## Table of Contents

1. [Prerequisites — What to Install](#1-prerequisites--what-to-install)
2. [Database Setup (MySQL)](#2-database-setup-mysql)
3. [Environment Variables](#3-environment-variables)
4. [Running the Server](#4-running-the-server)
5. [Exposing to the Internet (Cloudflare Tunnel)](#5-exposing-to-the-internet-cloudflare-tunnel)
6. [Connecting the Flutter App](#6-connecting-the-flutter-app)
7. [File Uploads](#7-file-uploads)
8. [Troubleshooting](#8-troubleshooting)
9. [SOA Microservices Backend (Future)](#9-soa-microservices-backend-future)

---

## 1. Prerequisites — What to Install

### Required

| Software | Version | Download | Purpose |
|----------|---------|----------|---------|
| **Go** | 1.23+ | https://go.dev/dl/ | Compiles and runs the server |
| **MySQL** | 8.0+ | https://dev.mysql.com/downloads/installer/ | Database |
| **Git** | Any | https://git-scm.com/downloads | Clone the repo |

### Optional

| Software | Download | Purpose |
|----------|----------|---------|
| **Cloudflare Tunnel** (`cloudflared`) | https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/ | Expose server to the internet with a custom domain |
| **Docker Desktop** | https://www.docker.com/products/docker-desktop/ | Run MySQL in a container instead of installing natively |

### Step-by-Step Installation

#### Windows

1. **Install Go**
   - Download the `.msi` installer from https://go.dev/dl/
   - Run installer, accept defaults
   - Open a **new** terminal and verify: `go version`

2. **Install MySQL**
   - Download MySQL Installer from https://dev.mysql.com/downloads/installer/
   - Choose "Developer Default" or "Server Only"
   - During setup, set a root password (remember it!)
   - Set the port to **3307** (or keep 3306 and update the env var later)
   - Alternatively, use Docker:
     ```powershell
     docker run -d --name marketflow-mysql -p 3307:3306 -e MYSQL_ROOT_PASSWORD=rootpassword -e MYSQL_DATABASE=marketflowdatabase -e MYSQL_USER=marketflowdatabase -e MYSQL_PASSWORD="marketflowmobileapp@2026" mysql:8.0
     ```

3. **Install Git**
   - Download from https://git-scm.com/downloads
   - Run installer, accept defaults

#### macOS

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Go
brew install go

# Install MySQL
brew install mysql
brew services start mysql
mysql_secure_installation
```

#### Linux (Ubuntu/Debian)

```bash
# Install Go (download latest from https://go.dev/dl/)
sudo tar -C /usr/local -xzf go1.25.5.linux-amd64.tar.gz
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
source ~/.bashrc

# Install MySQL
sudo apt update
sudo apt install -y mysql-server
sudo systemctl start mysql
sudo mysql_secure_installation
```

---

## 2. Database Setup (MySQL)

### Create the Database and User

Connect to MySQL as root:

```bash
mysql -u root -p
```

Then run these SQL commands:

```sql
-- Create the database
CREATE DATABASE IF NOT EXISTS marketflowdatabase;

-- Create the user
CREATE USER IF NOT EXISTS 'marketflowdatabase'@'%' IDENTIFIED BY 'marketflowmobileapp@2026';

-- Grant full permissions
GRANT ALL PRIVILEGES ON marketflowdatabase.* TO 'marketflowdatabase'@'%';

FLUSH PRIVILEGES;
```

### Tables Are Created Automatically

The server has an `ensureSchema(db)` function that runs on startup. It will **automatically create all required tables** if they don't exist. You do NOT need to run any SQL migration scripts manually.

### Verify the Connection Works

```bash
mysql -u marketflowdatabase -p"marketflowmobileapp@2026" -h 127.0.0.1 -P 3307 marketflowdatabase
```

If the port is different (e.g., 3306), change `-P 3307` and update the `MARKETFLOW_DB_DSN` environment variable accordingly.

---

## 3. Environment Variables

The server reads configuration from environment variables. If not set, it uses development defaults (suitable for local dev only).

| Variable | Description | Default (Dev Only) |
|----------|-------------|--------------------|
| `MARKETFLOW_JWT_SECRET` | Secret key for signing auth tokens. **Change in production!** | `MarketFlow_Secure_Key_2026_CHANGE_IN_PRODUCTION` |
| `MARKETFLOW_DB_DSN` | MySQL connection string | `marketflowdatabase:marketflowmobileapp@2026@tcp(127.0.0.1:3307)/marketflowdatabase?parseTime=true` |
| `MARKETFLOW_SMTP_HOST` | SMTP server for OTP emails | `sandbox.smtp.mailtrap.io` |
| `MARKETFLOW_SMTP_PORT` | SMTP port | `587` |
| `MARKETFLOW_SMTP_USER` | SMTP username | `5284dc911ffe2d` |
| `MARKETFLOW_SMTP_PASS` | SMTP password | `44dada8a8fcd23` |
| `MARKETFLOW_ALLOWED_ORIGINS` | CORS origins (comma-separated) | `*` |

### Setting Variables

**Windows (PowerShell)** — run these before starting the server:

```powershell
$env:MARKETFLOW_JWT_SECRET="your-very-secure-random-long-string-here"
$env:MARKETFLOW_DB_DSN="marketflowdatabase:marketflowmobileapp@2026@tcp(127.0.0.1:3307)/marketflowdatabase?parseTime=true"
$env:MARKETFLOW_ALLOWED_ORIGINS="*"
```

**Windows (CMD)**:

```cmd
set MARKETFLOW_JWT_SECRET=your-very-secure-random-long-string-here
set MARKETFLOW_DB_DSN=marketflowdatabase:marketflowmobileapp@2026@tcp(127.0.0.1:3307)/marketflowdatabase?parseTime=true
```

**Linux / macOS**:

```bash
export MARKETFLOW_JWT_SECRET="your-very-secure-random-long-string-here"
export MARKETFLOW_DB_DSN="marketflowdatabase:marketflowmobileapp@2026@tcp(127.0.0.1:3307)/marketflowdatabase?parseTime=true"
export MARKETFLOW_ALLOWED_ORIGINS="*"
```

> **Important:** For production, always set `MARKETFLOW_JWT_SECRET` to a strong random string (64+ characters). Never use the default.

> **Tip:** If you just want to run locally for development and your MySQL is on port 3307 with the default credentials, you don't need to set any env vars — the defaults will work.

---

## 4. Running the Server

### Quick Start (3 commands)

```bash
# 1. Navigate to the server directory
cd "market_flow_app/server"

# 2. Download Go dependencies (first time only)
go mod download

# 3. Run the server
go run .
```

You should see:

```
MarketFlow API running on :8080
Interest accrual cron started (runs every 24 hours)
```

### Option A: Run Directly (Development)

Best for development — recompiles on every run:

```bash
go run .
```

### Option B: Build an Executable (Production / Another Device)

Compile to a standalone binary — the target device does **NOT** need Go installed:

**Build:**

```bash
# Windows
go build -o server.exe .

# Linux
go build -o server .

# macOS
go build -o server .
```

**Run:**

```bash
./server.exe          # Windows
./server              # Linux/macOS
```

### Cross-Compilation (Build for a Different OS)

Build for a different OS from your current machine:

```bash
# Build Linux binary from Windows (PowerShell)
$env:GOOS="linux"; $env:GOARCH="amd64"; go build -o server .

# Build Windows binary from Linux
GOOS=windows GOARCH=amd64 go build -o server.exe .

# Build macOS binary from Windows
$env:GOOS="darwin"; $env:GOARCH="amd64"; go build -o server-mac .
```

### What Files to Copy to Another Device

**If deploying the compiled binary** (Go NOT needed on target):

```
server.exe              # The compiled binary
config.yml              # Only if using Cloudflare Tunnel
```

The `uploads/` folder and database tables will be created automatically on first run.

**If deploying source code** (Go NEEDED on target):

```
server/                 # Copy the entire directory
├── main.go
├── background_jobs.go
├── community_handlers.go
├── search_handlers.go
├── go.mod
├── go.sum
├── config.yml          # Only if using Cloudflare Tunnel
└── schema_update.sql   # Reference only, not required
```

Then run `go mod download && go run .` on the target device.

---

## 5. Exposing to the Internet (Cloudflare Tunnel)

**This is optional.** Only needed if you want the Flutter app to access the server from outside your local network (e.g., from a phone on mobile data).

### Install cloudflared

```bash
# Windows (PowerShell)
winget install Cloudflare.cloudflared

# macOS
brew install cloudflared

# Linux
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/
```

### Run the Tunnel

The tunnel config is in `config.yml`. It maps `api.marketflow-api.com` -> `localhost:8080`.

```bash
cloudflared tunnel --config config.yml run
```

> **Note:** The `credentials-file` path in `config.yml` is machine-specific. On a new device, you'll need to authenticate first:
> ```bash
> cloudflared tunnel login
> ```
> Then update the `credentials-file` path in `config.yml` to match the new credentials file location.

### Without Cloudflare (Local Network Only)

If the Flutter app and server are on the **same Wi-Fi network**:

1. Find your PC's local IP address:
   - **Windows:** `ipconfig` (look for IPv4 Address, e.g., `192.168.1.100`)
   - **Linux/macOS:** `ifconfig` or `ip addr`
2. In the Flutter app, set the API base URL to: `http://192.168.x.x:8080`
3. Make sure your firewall allows incoming connections on port 8080

---

## 6. Connecting the Flutter App

The Flutter app needs to know the server's address. Update the API base URL in `lib/data/constants.dart`:

```dart
// Local development (server on same machine, running in emulator)
static const String baseUrl = 'http://10.0.2.2:8080';    // Android emulator
static const String baseUrl = 'http://localhost:8080';     // iOS simulator / web

// Local network (phone + PC on same Wi-Fi)
static const String baseUrl = 'http://192.168.1.100:8080'; // Use your PC's IP

// Production (via Cloudflare Tunnel)
static const String baseUrl = 'https://api.marketflow-api.com';
```

### Verify the Connection

```bash
# From the server machine
curl http://localhost:8080/api/v1/ping
# Expected: pong

# From another device on the same network
curl http://192.168.1.100:8080/api/v1/ping
# Expected: pong
```

---

## 7. File Uploads

The server automatically creates this directory structure for uploaded images:

```
uploads/
├── avatars/                 # User profile photos
├── stores/                  # Store logos and product images
└── community/
    ├── avatar_photo/        # Community avatars
    └── cover_photo/         # Community cover images
```

- Uploaded files are served at `http://localhost:8080/uploads/...`
- Max upload size: 10 MB
- Allowed formats: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
- Ensure the server process has **write permissions** in its working directory

---

## 8. Troubleshooting

### "dial tcp 127.0.0.1:3307: connect: connection refused"

**MySQL is not running** or is on a different port.

- Start MySQL service:
  - Windows: `net start mysql` or open Services app
  - Linux: `sudo systemctl start mysql`
  - Docker: `docker start marketflow-mysql`
- If MySQL runs on port 3306 instead of 3307, update the DSN:
  ```bash
  export MARKETFLOW_DB_DSN="marketflowdatabase:marketflowmobileapp@2026@tcp(127.0.0.1:3306)/marketflowdatabase?parseTime=true"
  ```

### "Access denied for user 'marketflowdatabase'"

Wrong MySQL credentials or user doesn't exist.

- Verify the user exists: `SELECT User, Host FROM mysql.user;`
- Re-create the user (see [Database Setup](#2-database-setup-mysql))
- Check the password doesn't have special characters that need escaping in the DSN

### "go: command not found"

Go is not installed or not in your PATH.

- Reinstall Go from https://go.dev/dl/
- **Restart your terminal** after installation (important!)
- Verify: `go version`

### "bind: address already in use" (port 8080)

Another process is already using port 8080.

```bash
# Windows — find and kill the process
netstat -ano | findstr :8080
taskkill /PID <pid> /F

# Linux/macOS
lsof -i :8080
kill <pid>
```

### Flutter app can't connect to server

1. Verify server is running: `curl http://localhost:8080/api/v1/ping`
2. If using a **physical phone**, use the PC's IP address, not `localhost`
3. **Android emulator** uses `10.0.2.2` to reach the host machine's `localhost`
4. Check that your **firewall** allows port 8080:
   - Windows: Settings > Firewall > Allow an app > add port 8080
   - Linux: `sudo ufw allow 8080`
5. Make sure phone and PC are on the **same Wi-Fi network**

### OTP emails not arriving

- The default SMTP credentials are for **Mailtrap** (testing sandbox)
- Check your Mailtrap inbox at https://mailtrap.io/
- For real emails in production, set `MARKETFLOW_SMTP_*` env vars to your actual SMTP provider (Gmail, SendGrid, etc.)

### "module not found" or dependency errors

```bash
# Re-download all dependencies
go mod download

# Or clean and re-fetch
go clean -modcache
go mod download
```

---

## 9. SOA Microservices Backend (Future)

A microservices version of this server is available at `marketflow-backend/` (sibling to the Flutter project). It splits the monolith into 9 independent services with Docker orchestration:

| Service | Port | Responsibility |
|---------|------|---------------|
| API Gateway | 8080 | Routing, rate limiting, CORS |
| Auth | 8081 | Login, register, OTP, JWT |
| User | 8082 | Profile, preferences, presence |
| Product | 8083 | CRUD, search, filters |
| Order | 8084 | Orders, transactions, analytics |
| Store | 8085 | Store management, applications |
| Debtor | 8086 | Debt tracking, interest cron |
| Notification | 8087 | Push notifications, pub/sub |
| Community | 8088 | Posts, comments, likes |
| Upload | 8089 | File/image uploads |

To run it (requires Docker):

```bash
cd marketflow-backend
docker-compose up -d
```

The current monolith server (`server/main.go`) remains the **primary production server** until the microservices migration is fully tested.

---

## Quick Reference

```
Server directory .... market_flow_app/server/
Server port ......... 8080
Database port ....... 3307 (MySQL)
API base path ....... /api/v1/
Health check ........ GET /api/v1/ping  -->  "pong"
Domain .............. https://api.marketflow-api.com

Start (dev) ......... go run .
Build (prod) ........ go build -o server.exe .
Run binary .......... ./server.exe
Start tunnel ........ cloudflared tunnel --config config.yml run
```
