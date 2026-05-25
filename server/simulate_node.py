import time
import requests
import random
import sys

# Default URL of the local Flask server
SERVER_URL = "http://localhost:5000/api/node/telemetry"

def run_simulator(token, house_name):
    print("=" * 60)
    print(f" URRJA Solar Node Simulator - {house_name}")
    print(f" Target Endpoint: {SERVER_URL}")
    print(f" Device Token   : {token}")
    print("=" * 60)
    
    # State variables
    soc = 85.0          # Initial State of Charge (%)
    is_transferring = False
    transfer_start_time = 0
    transfer_duration = 0
    
    try:
        while True:
            # Generate simulated metrics
            if is_transferring:
                # Discharging/transferring current
                current = -8.5 - random.uniform(-0.5, 0.5) # Discharging
                voltage = 11.8 + random.uniform(-0.1, 0.1) # Voltage sag
                power = voltage * current                  # Negative power draw
                
                # Slower discharge representation
                soc = max(0.0, soc - 0.2)
                surplus = 0.0
                
                print(f"[ACTIVE TRANSFER] Discharging -> Volt: {voltage:.2f}V | Curr: {current:.2f}A | Power: {power:.1f}W | SoC: {soc:.1f}%")
            else:
                # Normal solar generation/charge simulation
                # Simulate a solar curve (sinusoidal offset based on time)
                time_factor = (time.time() / 60) % 24
                is_daylight = 6.0 <= time_factor <= 18.0
                
                if is_daylight:
                    # Positive charging current
                    current = 4.5 * (1.0 - abs(time_factor - 12.0) / 6.0) + random.uniform(-0.2, 0.2)
                    voltage = 13.6 + random.uniform(-0.1, 0.1)
                else:
                    # Idle nighttime draw
                    current = -0.5 + random.uniform(-0.1, 0.1)
                    voltage = 12.2 + random.uniform(-0.1, 0.1)
                    
                power = voltage * current
                
                # Charge model
                soc = min(100.0, soc + (current * 0.01))
                
                # Calculate surplus energy (if SoC > 70%, surplus is available)
                if soc > 70.0:
                    # 1200 Wh battery capacity assumed
                    surplus = (soc - 70.0) * 12.0
                else:
                    surplus = 0.0
                    
                print(f"[IDLE / CHARGING] Volt: {voltage:.2f}V | Curr: {current:.2f}A | Power: {power:.1f}W | SoC: {soc:.1f}% | Surplus: {surplus:.1f}Wh")

            # Prepare telemetry payload
            payload = {
                "device_token": token,
                "voltage": round(voltage, 2),
                "current": round(current, 2),
                "power": round(power, 1),
                "soc": round(soc, 1),
                "surplus": round(surplus, 1)
            }
            
            # Send telemetry to server
            try:
                response = requests.post(SERVER_URL, json=payload, timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    cmd = data.get("command")
                    tx_id = data.get("transaction_id")
                    
                    if cmd == 'transfer_start':
                        if not is_transferring:
                            is_transferring = True
                            transfer_duration = data.get("duration", 30)
                            print(f"\n>>> [RELAY CLOSED ON] Commencing energy transfer. Tx ID: #{tx_id}. Duration: {transfer_duration}s. <<<\n")
                    elif cmd == 'transfer_stop':
                        if is_transferring:
                            is_transferring = False
                            print(f"\n>>> [RELAY OPEN OFF] Energy transfer completed. Stopping discharge. <<<\n")
                    elif cmd == 'idle' and is_transferring:
                        # Server resolved or transaction ended
                        is_transferring = False
                        print(f"\n>>> [RELAY OPEN OFF] Server reset. Energy transfer stopped. <<<\n")
                        
                elif response.status_code == 401:
                    print("Error: Invalid device token. Registration token required.")
                    break
                else:
                    print(f"Server Error: HTTP {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Connection Error: Unable to reach server at {SERVER_URL}. Retrying...")
                
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\nSimulator stopped by user.")

if __name__ == "__main__":
    # Allow passing token as commandline parameter
    token = "token_node_101"
    name = "Smart Villa 101 (Pre-seeded)"
    
    if len(sys.argv) > 1:
        token = sys.argv[1]
        name = f"Custom Node ({token})"
        
    run_simulator(token, name)
