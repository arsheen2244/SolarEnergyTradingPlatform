<div align="center">

# ☀️ URRJA: Peer‑to‑Peer Solar Energy Trading

**A neighbourhood marketplace for rooftop solar.**
Each home in a gated community runs an ESP32 energy node. A Flask server matches surplus sellers with buyers, switches the transfer on, and settles the trade in community tokens.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![ESP32](https://img.shields.io/badge/ESP32-WROOM--DA-E7352C?logo=espressif&logoColor=white)
![Arduino](https://img.shields.io/badge/Arduino-C++-00979D?logo=arduino&logoColor=white)
![JavaScript](https://img.shields.io/badge/Vanilla%20JS-F7DF1E?logo=javascript&logoColor=black)
![IoT](https://img.shields.io/badge/IoT-prototype-orange)

</div>

---

## ✨ Highlights

- ⚡ **Automated P2P matching engine**: cheapest listings meet the highest bids first, with partial fills, a self‑trade block and buyer balance checks
- 📡 **ESP32 smart nodes** read battery voltage, current and state of charge from an INA219 sensor, POST telemetry over HTTP, and close a relay while a trade is active
- 🔁 **Trade lifecycle** `initiated → transferring → completed`, driven by node telemetry, with token settlement on completion
- 📊 **Seven‑page web app**: dashboard with a state‑of‑charge dial, seller listings, marketplace, device monitor, ledger and admin console
- 🧪 **No hardware needed to try it**: `simulate_node.py` stands in for an ESP32, and `SIMULATION_MODE` fakes sensor readings on a real board

## 🏗️ System Architecture

```mermaid
flowchart TB
    subgraph Homes["🏘️ Gated community Wi‑Fi / hotspot"]
        direction LR
        A["🏠 Node A · Seller<br/>ESP32 + INA219 + relay"]
        B["🏠 Node B · Buyer<br/>ESP32 + INA219 + relay"]
        S["🐍 simulate_node.py<br/>(virtual node)"]
    end

    subgraph Server["🖥️ Community server (Raspberry Pi / PC)"]
        API["Flask app<br/>REST API + Jinja pages"]
        ME["⚙️ Matching engine<br/>match_listings_and_requests()"]
        DB[("SQLite · urrja.db")]
        API <--> ME
        API <--> DB
        ME <--> DB
    end

    A -- "POST /api/node/telemetry<br/>(V, I, P, SoC, surplus)" --> API
    B -- "POST /api/node/telemetry" --> API
    S -- "POST /api/node/telemetry" --> API
    API -- "response: trade state →<br/>close / open relay" --> A
    API -- "response" --> B

    R(["👩 Residents · 🛠️ Admin<br/>browser"]) <-- "HTML + JS polling" --> API
```

## 🔄 Trade Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor Seller as Seller (house 1)
    actor Buyer as Buyer (house 2)
    participant API as Flask server
    participant ME as Matching engine
    participant NodeA as Seller node
    participant NodeB as Buyer node

    Seller->>API: POST /api/listings (500 Wh @ 0.40)
    Buyer->>API: POST /api/buy_requests (500 Wh, max 0.45)
    API->>ME: run matching
    ME->>ME: price 0.40 ≤ 0.45 ✓ · balance ✓ · not self ✓
    ME-->>API: transaction INITIATED
    NodeA->>API: telemetry
    API-->>NodeA: start transfer → relay ON, green LED
    Note over API: status → TRANSFERRING
    loop each telemetry tick
        NodeA->>API: telemetry
        NodeB->>API: telemetry
    end
    API->>API: duration elapsed → settle tokens<br/>buyer −200 · seller +200
    Note over API: status → COMPLETED, houses back ONLINE
```

```mermaid
stateDiagram-v2
    [*] --> initiated: listing ⨯ request matched
    initiated --> transferring: seller node checks in
    transferring --> completed: transfer duration elapsed<br/>tokens settled
    completed --> [*]
```

### Matching rules

| # | Rule |
|:-:|------|
| 1 | Listings are sorted **cheapest first**, buy requests **highest bid first**, then oldest first (price–time priority) |
| 2 | A house can't trade with itself |
| 3 | A trade happens only when `seller price ≤ buyer max price`, and it settles at the **seller's price** |
| 4 | Quantity = `min(remaining listing, remaining request)`, so partial fills keep the leftover open |
| 5 | If the buyer can't afford the trade, the request is **cancelled** and a warning is logged |

## 🗄️ Data Model

```mermaid
erDiagram
    USERS ||--o{ HOUSES : owns
    HOUSES ||--o{ ENERGY_READINGS : reports
    HOUSES ||--o{ LISTINGS : sells
    HOUSES ||--o{ BUY_REQUESTS : bids
    LISTINGS ||--o{ TRANSACTIONS : fills
    BUY_REQUESTS ||--o{ TRANSACTIONS : fills

    USERS {
        int id PK
        text username
        text password_hash
        text role
        real balance
    }
    HOUSES {
        int id PK
        text house_name
        text device_token
        text status
        real battery_capacity
    }
    ENERGY_READINGS {
        real battery_voltage
        real battery_current
        real power
        real battery_soc
        real available_surplus
    }
    LISTINGS {
        real energy_amount_wh
        real remaining_energy_wh
        real price_per_wh
        text status
    }
    BUY_REQUESTS {
        real energy_amount_wh
        real remaining_energy_wh
        real max_price_per_wh
        text status
    }
    TRANSACTIONS {
        real energy_amount_wh
        real total_price
        text status
        datetime started_at
        datetime completed_at
    }
```

A separate `logs` table records server and node events for the admin console.

## 🧰 Tech Stack

| Layer | Technology |
|------|-----------|
| Backend | Python 3.10+, Flask, Werkzeug (password hashing), SQLite |
| Frontend | Jinja2 templates, hand‑written CSS (custom properties, transitions), vanilla JavaScript (REST + polling) |
| Firmware | Arduino C++ on ESP32 (core v2.x / v3.x), `HTTPClient`, ArduinoJson, Adafruit INA219 |
| Hardware | ESP32‑WROOM‑DA, INA219 high‑side current sensor, 5 V relay / MOSFET switch, status LEDs, 5 A fuse |
| Simulation | `simulate_node.py` (Python `requests`) |

## 🔌 Hardware

| ESP32 pin | Connects to | Purpose |
|---|---|---|
| **GND** | GND | Common ground |
| **GPIO 21 (SDA)** | INA219 SDA | I²C data |
| **GPIO 22 (SCL)** | INA219 SCL | I²C clock |
| **GPIO 25** | Relay IN | Switches the simulated transfer load |
| **GPIO 2** | Built‑in LED | Wi‑Fi (blinking = connecting, solid = online) |
| **GPIO 26** | Green LED | Trade active |
| **GPIO 27** | Red LED | Sensor or server error |

```mermaid
flowchart LR
    PV[☀️ Solar panel] --> INA[INA219<br/>Vin+ → Vin−]
    INA --> BAT[🔋 Battery + load]
    INA <-- "I²C (21/22)" --> ESP[ESP32]
    ESP -- GPIO25 --> REL[Relay / MOSFET] --> DL[Dummy DC load]
    ESP -- GPIO26 --> G((🟢))
    ESP -- GPIO27 --> Rr((🔴))
```

## 🚀 Getting Started

### 1. Run the server

```bash
git clone https://github.com/arsheen2244/SolarEnergyTradingPlatform.git
cd SolarEnergyTradingPlatform/server
pip install flask requests werkzeug
python database.py      # optional: creates and seeds urrja.db (also runs on startup)
python app.py           # serves http://0.0.0.0:5000
```

### 2. Flash an ESP32 (optional)

1. In the Arduino IDE, install **Adafruit INA219** and **ArduinoJson**.
2. Open `esp32_firmware/esp32_firmware.ino` and set `ssid`, `password` and `serverUrl` (your server's LAN IP).
3. Without sensors, keep `#define SIMULATION_MODE 1`. Then flash the board.

### 3. Try a trade without hardware

| Seeded account | Username | Password |
|--------------|----------|----------|
| Admin | `admin` | `admin123` |
| Home owner | `house1_owner` | `urrja123` |

1. Run `python simulate_node.py` (it uses the seeded `token_node_101`) or `python simulate_node.py <device_token>` for a node you registered.
2. As `house1_owner`, list **500 Wh @ 0.40 tokens/Wh**.
3. In an incognito window, as `house2_owner`, bid **500 Wh, max 0.45 tokens/Wh**.
4. The simulator prints `[ACTIVE TRANSFER]`. Open `/admin` to watch `initiated → transferring → completed` and the wallet balances settle.

> These are local demo accounts. Change them before running the server on any shared network.

## 📁 Project Structure

```
SolarEnergyTradingPlatform/
├── esp32_firmware/
│   └── esp32_firmware.ino     # sensor read · telemetry POST · relay/LED control
└── server/
    ├── app.py                 # Flask routes, REST API, matching engine, settlement
    ├── database.py            # schema + seed data
    ├── simulate_node.py       # virtual ESP32 node
    ├── static/{css,js}/       # design system + polling/forms
    └── templates/             # base, login, dashboard, seller, marketplace,
                               # devices, transactions, admin
```

## ⚠️ Safety & Limitations

- This is a **low‑voltage prototype**. It never switches mains electricity (110/220 V AC).
- The relay only drives a small DC dummy load (LED, fan, resistor) to show that a trade has started.
- A real deployment would send this signal to a battery management system or a microgrid controller on a dedicated DC bus.
- Tokens are an internal ledger, not real currency.

---

<div align="center">Built by <a href="https://github.com/arsheen2244">Arsheen Inamdar</a></div>
