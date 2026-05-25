/*
 * URRJA Solar Energy Trading Node - ESP32 Firmware
 * 
 * Hardware Layout:
 * - ESP32-WROOM-DA Module
 * - INA219 Current Sensor (I2C: SDA=21, SCL=22)
 * - Simulated Load Switch Relay or MOSFET (GPIO 25)
 * - LED Indicators:
 *   - WiFi Status LED: GPIO 2 (Internal Blue LED)
 *   - Trade Active LED: GPIO 26 (Green LED)
 *   - Error Status LED: GPIO 27 (Red LED)
 * 
 * Required Arduino Libraries:
 * - Adafruit INA219 (Sensor reading)
 * - ArduinoJson (JSON parser for REST APIs)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_INA219.h>
#include <ArduinoJson.h>

// --- Compilation Configuration ---
// Set to 1 to run using math equations if sensors are not physically wired
#define SIMULATION_MODE 1 

// --- Network Settings ---
const char* ssid = "URRJA_Microgrid_AP";
const char* password = "urrja_secure_pass";
const char* serverUrl = "http://192.168.4.1:5000/api/node/telemetry"; // Adjust server IP

// --- Node Device Token ---
const char* deviceToken = "token_node_101"; // Generated from web signup

// --- GPIO Pin Configuration ---
#define RELAY_PIN 25        // Pin connected to relay gate/MOSFET driver
#define WIFI_LED_PIN 2      // Onboard status LED
#define TRADE_LED_PIN 26    // LED indicating active energy transfer
#define ERROR_LED_PIN 27    // LED indicating sensor/server error

// --- Hardware Variables ---
Adafruit_INA219 ina219;
bool isSensorAvailable = false;
bool isTransferring = false;
unsigned long lastTelemetryTime = 0;
const unsigned long telemetryInterval = 5000; // Telemetry post every 5 seconds

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== URRJA Solar Node Starting ===");

  // Configure Pins
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(WIFI_LED_PIN, OUTPUT);
  pinMode(TRADE_LED_PIN, OUTPUT);
  pinMode(ERROR_LED_PIN, OUTPUT);

  // Write default values (relays/LEDs OFF)
  digitalWrite(RELAY_PIN, LOW);
  digitalWrite(WIFI_LED_PIN, LOW);
  digitalWrite(TRADE_LED_PIN, LOW);
  digitalWrite(ERROR_LED_PIN, LOW);

  // Initialize INA219 Current Sensor
  #if SIMULATION_MODE
    Serial.println("[INFO] SIMULATION_MODE active. Bypassing physical INA219 sensor setup.");
  #else
    Serial.println("[INFO] Initializing physical INA219 Current Sensor...");
    if (ina219.begin()) {
      Serial.println("[SUCCESS] INA219 Sensor detected.");
      isSensorAvailable = true;
    } else {
      Serial.println("[ERROR] Failed to locate INA219 sensor. Check wiring! Red LED turned ON.");
      digitalWrite(ERROR_LED_PIN, HIGH);
    }
  #endif

  // Initialize Wi-Fi Connection
  connectToWiFi();
}

void loop() {
  // Check Wi-Fi connectivity and attempt reconnect if dropped
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(WIFI_LED_PIN, LOW);
    digitalWrite(RELAY_PIN, LOW); // Fail-safe: shut down relay if network goes down
    digitalWrite(TRADE_LED_PIN, LOW);
    isTransferring = false;
    connectToWiFi();
    return;
  }

  // Handle telemetry at defined intervals
  unsigned long currentMillis = millis();
  if (currentMillis - lastTelemetryTime >= telemetryInterval) {
    lastTelemetryTime = currentMillis;
    postTelemetry();
  }
}

// --- WiFi Reconnect Helper ---
void connectToWiFi() {
  Serial.print("Connecting to Wi-Fi SSID: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    // Blink blue LED during connection phase
    digitalWrite(WIFI_LED_PIN, !digitalRead(WIFI_LED_PIN));
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[SUCCESS] Wi-Fi Connected!");
    Serial.print("Local IP Address: ");
    Serial.println(WiFi.localIP());
    digitalWrite(WIFI_LED_PIN, HIGH); // Solid blue LED means connected
    digitalWrite(ERROR_LED_PIN, LOW);
  } else {
    Serial.println("\n[ERROR] Wi-Fi connection timed out. Retrying in next loop.");
    digitalWrite(WIFI_LED_PIN, LOW);
    digitalWrite(ERROR_LED_PIN, HIGH);
  }
}

// --- Telemetry Post Handler ---
void postTelemetry() {
  float voltage = 0.0;
  float current = 0.0;
  float power = 0.0;
  float soc = 0.0;
  float surplus = 0.0;

  // 1. Gather Sensor Measurements
  #if SIMULATION_MODE
    // Math model representing battery charging/discharging
    if (isTransferring) {
      current = -8.2; // 8.2 Amps discharge rate
      voltage = 11.9; // Voltage drop under load
    } else {
      // Daylight sinusoidal simulation
      float hour = (millis() / 15000.0); // 15 seconds represents solar day
      float solarIntensity = sin(hour);
      if (solarIntensity > 0) {
        current = 3.8 * solarIntensity; // Charging
        voltage = 13.5 + (0.5 * solarIntensity);
      } else {
        current = -0.2; // Night standby draw
        voltage = 12.1;
      }
    }
    power = voltage * current;
    soc = 82.5 + (current * 0.1); // Dynamic SoC movement
    soc = constrain(soc, 0.0, 100.0);
    
  #else
    if (isSensorAvailable) {
      voltage = ina219.getBusVoltage_V();
      current = ina219.getCurrent_mA() / 1000.0; // Convert mA to A
      power = voltage * current;
      
      // Calculate State of Charge (SoC) based on simple Lead-Acid cell curve
      // 11.5V = 0%, 12.8V = 100%
      soc = ((voltage - 11.5) / 1.3) * 100.0;
      soc = constrain(soc, 0.0, 100.0);
    } else {
      // Sensor not connected and simulation disabled
      digitalWrite(ERROR_LED_PIN, HIGH);
      Serial.println("[ERROR] Physical INA219 reading failed.");
      return;
    }
  #endif

  // Calculate surplus Wh (Available only above 70% battery SoC)
  if (soc > 70.0) {
    surplus = (soc - 70.0) * 12.0; // Assumed 1200Wh capacity
  } else {
    surplus = 0.0;
  }

  // Print values locally
  Serial.printf("[SENSOR] Volt: %.2fV | Curr: %.2fA | Power: %.1fW | SoC: %.1f%% | Surplus: %.1fWh\n", 
                voltage, current, power, soc, surplus);

  // 2. Transmit Telemetry JSON
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");

    // Dynamic Json construction using ArduinoJson v6/v7 syntax
    StaticJsonDocument<200> doc;
    doc["device_token"] = deviceToken;
    doc["voltage"] = voltage;
    doc["current"] = current;
    doc["power"] = power;
    doc["soc"] = soc;
    doc["surplus"] = surplus;

    String jsonString;
    serializeJson(doc, jsonString);

    int httpResponseCode = http.POST(jsonString);

    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.printf("[HTTP] Status: %d | Response: %s\n", httpResponseCode, response.c_str());

      // Parse Command Response
      StaticJsonDocument<200> respDoc;
      DeserializationError error = deserializeJson(respDoc, response);

      if (!error) {
        const char* command = respDoc["command"];
        int transactionId = respDoc["transaction_id"];
        
        if (strcmp(command, "transfer_start") == 0) {
          if (!isTransferring) {
            isTransferring = true;
            digitalWrite(RELAY_PIN, HIGH);      // Close Relay (ON)
            digitalWrite(TRADE_LED_PIN, HIGH);  // Turn green trade LED ON
            Serial.printf(">>> [GRID ENGAGED] Relay closed. Transferring power. Tx: #%d <<<\n", transactionId);
          }
        } 
        else if (strcmp(command, "transfer_stop") == 0 || strcmp(command, "idle") == 0) {
          if (isTransferring) {
            isTransferring = false;
            digitalWrite(RELAY_PIN, LOW);       // Open Relay (OFF)
            digitalWrite(TRADE_LED_PIN, LOW);   // Turn green trade LED OFF
            Serial.println(">>> [GRID IDLE] Relay opened. Power transfer stopped. <<<");
          }
        }
        
        digitalWrite(ERROR_LED_PIN, LOW); // Clear error if server is ok
      } else {
        Serial.println("[ERROR] Failed to parse server response JSON.");
      }
    } else {
      Serial.printf("[ERROR] HTTP Telemetry POST failed. Code: %d. Red LED activated.\n", httpResponseCode);
      digitalWrite(ERROR_LED_PIN, HIGH);
    }
    
    http.end();
  }
}
