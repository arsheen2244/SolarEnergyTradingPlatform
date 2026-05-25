// URRJA Peer-to-Peer Solar Energy Trading Platform Javascript Logic

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initial Load & Setup
    fetchUserProfile();
    setupFlashMessageDismissals();
    
    // Determine active page context
    const pageId = document.body.dataset.page;
    if (pageId) {
        initPageContext(pageId);
    }
});

// Cache variables for user profile details
let currentUserProfile = null;
let currentHouseProfile = null;

// --- API Helper Functions ---
async function apiCall(url, method = 'GET', body = null) {
    try {
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json'
            }
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        const response = await fetch(url, options);
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.error || `HTTP error! Status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`API Call failed: ${url}`, error);
        showToast(error.message || 'Network request failed', 'error');
        return null;
    }
}

// Fetch user profile and update navigation UI
async function fetchUserProfile() {
    const data = await apiCall('/api/user/profile');
    if (data && data.user) {
        currentUserProfile = data.user;
        currentHouseProfile = data.house;
        
        // Update user elements in layouts
        const nameEl = document.getElementById('navbar-user-name');
        if (nameEl) nameEl.textContent = data.user.username;
        
        const avatarEl = document.getElementById('navbar-user-avatar');
        if (avatarEl) avatarEl.textContent = data.user.username.substring(0, 2).toUpperCase();
        
        const balanceEl = document.getElementById('navbar-user-balance');
        if (balanceEl) balanceEl.textContent = `${data.user.balance.toFixed(2)} tokens`;
        
        const houseEl = document.getElementById('navbar-user-house');
        if (houseEl && data.house) houseEl.textContent = data.house.house_name;
    }
}

// Custom Toast Notification System
function showToast(message, type = 'info') {
    const tray = document.getElementById('toast-tray');
    if (!tray) {
        const newTray = document.createElement('div');
        newTray.id = 'toast-tray';
        newTray.className = 'flash-messages';
        document.body.appendChild(newTray);
    }
    
    const toast = document.createElement('div');
    toast.className = `flash-message ${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button class="flash-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    
    document.getElementById('toast-tray').appendChild(toast);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        toast.remove();
    }, 5000);
}

function setupFlashMessageDismissals() {
    document.querySelectorAll('.flash-close').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.target.parentElement.remove();
        });
    });
}

// --- Page Specific Routines ---
function initPageContext(pageId) {
    console.log(`Initializing page: ${pageId}`);
    
    switch (pageId) {
        case 'dashboard':
            initDashboard();
            break;
        case 'seller':
            initSeller();
            break;
        case 'marketplace':
            initMarketplace();
            break;
        case 'devices':
            initDevices();
            break;
        case 'transactions':
            initTransactions();
            break;
        case 'admin':
            initAdmin();
            break;
    }
}

// 1. Dashboard Context
function initDashboard() {
    const updateDashboardData = async () => {
        // Fetch devices (to locate current user's device measurements)
        const devData = await apiCall('/api/devices');
        if (devData && devData.devices && currentHouseProfile) {
            const myHouse = devData.devices.find(d => d.id === currentHouseProfile.id);
            if (myHouse) {
                // Update local dashboard widgets
                document.getElementById('dash-house-status').className = `status-badge ${myHouse.status}`;
                document.getElementById('dash-house-status').textContent = myHouse.status;
                
                const soc = myHouse.last_soc !== null ? myHouse.last_soc.toFixed(1) : '0.0';
                const voltage = myHouse.last_soc !== null ? myHouse.battery_voltage.toFixed(2) : '0.00';
                const current = myHouse.last_soc !== null ? myHouse.battery_current.toFixed(2) : '0.00';
                const power = myHouse.last_power !== null ? myHouse.last_power.toFixed(1) : '0.0';
                const surplus = myHouse.last_surplus !== null ? myHouse.last_surplus.toFixed(1) : '0.0';
                
                document.getElementById('dash-soc-value').textContent = `${soc}%`;
                document.getElementById('dash-voltage-value').textContent = `${voltage}V`;
                document.getElementById('dash-current-value').textContent = `${current}A`;
                document.getElementById('dash-power-value').textContent = `${power}W`;
                document.getElementById('dash-surplus-value').textContent = `${surplus}Wh`;
                
                // Draw battery ring
                drawBatteryRing(parseFloat(soc));
                
                // Render energy transfer line if transferring
                const flowEl = document.getElementById('dash-energy-flow-visual');
                if (myHouse.status === 'transferring') {
                    flowEl.style.display = 'block';
                } else {
                    flowEl.style.display = 'none';
                }
            }
        }
        
        // Fetch active matched transactions to show trade progress
        const txData = await apiCall('/api/transactions?limit=5');
        if (txData && txData.transactions) {
            const tbody = document.getElementById('dash-tx-table-body');
            if (tbody) {
                if (txData.transactions.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No active or recent trades.</td></tr>`;
                } else {
                    tbody.innerHTML = txData.transactions.map(tx => `
                        <tr>
                            <td>#${tx.id}</td>
                            <td>${tx.seller_house} <small style="color: var(--text-muted);">(${tx.seller_owner})</small></td>
                            <td>${tx.buyer_house} <small style="color: var(--text-muted);">(${tx.buyer_owner})</small></td>
                            <td><span class="color-surplus">${tx.energy_amount_wh.toFixed(1)} Wh</span></td>
                            <td><span class="status-badge ${tx.status}">${tx.status}</span></td>
                        </tr>
                    `).join('');
                }
            }
        }
    };
    
    updateDashboardData();
    setInterval(updateDashboardData, 4000);
}

// SVG Circle drawing logic
function drawBatteryRing(percentage) {
    const ring = document.getElementById('battery-ring');
    if (!ring) return;
    
    const radius = 58;
    const circumference = 2 * Math.PI * radius;
    
    ring.style.strokeDasharray = `${circumference} ${circumference}`;
    
    const offset = circumference - (percentage / 100) * circumference;
    ring.style.strokeDashoffset = offset;
    
    // Change circle color based on battery SoC
    if (percentage > 50) {
        ring.style.stroke = '#10b981'; // Green
    } else if (percentage > 20) {
        ring.style.stroke = '#f59e0b'; // Amber
    } else {
        ring.style.stroke = '#ef4444'; // Red
    }
}

// 2. Seller Context
function initSeller() {
    const form = document.getElementById('create-listing-form');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const energy = document.getElementById('listing-energy').value;
            const price = document.getElementById('listing-price').value;
            
            const res = await apiCall('/api/listings', 'POST', { energy, price });
            if (res) {
                showToast('Energy listed successfully on the local grid!', 'success');
                form.reset();
                fetchUserProfile(); // Refresh balance
                fetchActiveListings();
            }
        });
    }
    
    const fetchActiveListings = async () => {
        const data = await apiCall('/api/listings');
        const listContainer = document.getElementById('seller-active-listings');
        if (listContainer && data && data.listings) {
            // Filter to only show current user's listings
            const myId = currentHouseProfile ? currentHouseProfile.id : null;
            const myListings = data.listings.filter(l => l.seller_house_id === myId);
            
            if (myListings.length === 0) {
                listContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 2rem;">You do not have any active sale listings.</div>`;
            } else {
                listContainer.innerHTML = myListings.map(l => `
                    <div class="card" style="margin-bottom: 1rem;">
                        <div class="flex-between">
                            <div>
                                <h4 style="font-size: 1.1rem; margin-bottom: 0.25rem;">${l.energy_amount_wh.toFixed(1)} Wh Surplus</h4>
                                <small style="color: var(--text-muted);">Price per Wh: ${l.price_per_wh.toFixed(2)} tokens</small>
                            </div>
                            <span class="status-badge ${l.status}">${l.status}</span>
                        </div>
                        <div class="progress-bar-bg" style="margin-top: 1rem;">
                            <div class="progress-bar-fill surplus" style="width: ${(l.remaining_energy_wh / l.energy_amount_wh) * 100}%;"></div>
                        </div>
                        <div class="flex-between" style="margin-top: 0.5rem; font-size: 0.8rem; color: var(--text-secondary);">
                            <span>Remaining: ${l.remaining_energy_wh.toFixed(1)} Wh</span>
                            <span>Total value: ${(l.energy_amount_wh * l.price_per_wh).toFixed(1)} tokens</span>
                        </div>
                    </div>
                `).join('');
            }
        }
    };
    
    setTimeout(fetchActiveListings, 500); // Small timeout to ensure houseProfile exists
}

// 3. Marketplace Context
function initMarketplace() {
    const buyForm = document.getElementById('buy-request-form');
    if (buyForm) {
        buyForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const energy = document.getElementById('buy-energy').value;
            const maxPrice = document.getElementById('buy-max-price').value;
            
            const res = await apiCall('/api/buy_requests', 'POST', { energy, max_price: maxPrice });
            if (res) {
                showToast('Energy request placed on the marketplace!', 'success');
                buyForm.reset();
                fetchUserProfile();
                fetchMarketplaceData();
            }
        });
    }
    
    const fetchMarketplaceData = async () => {
        // Fetch Sale Listings
        const sellData = await apiCall('/api/listings');
        const listTbody = document.getElementById('market-listings-body');
        if (listTbody && sellData && sellData.listings) {
            // Exclude current user's own houses from listings they can buy
            const myHouseId = currentHouseProfile ? currentHouseProfile.id : null;
            const activeListings = sellData.listings.filter(l => l.seller_house_id !== myHouseId);
            
            if (activeListings.length === 0) {
                listTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No energy for sale currently. Check back later!</td></tr>`;
            } else {
                listTbody.innerHTML = activeListings.map(l => `
                    <tr>
                        <td><strong>${l.house_name}</strong> <small style="color: var(--text-muted);">(${l.owner})</small></td>
                        <td><span class="color-surplus">${l.remaining_energy_wh.toFixed(1)} Wh</span></td>
                        <td>${l.price_per_wh.toFixed(2)} tokens/Wh</td>
                        <td><span class="color-power">${(l.remaining_energy_wh * l.price_per_wh).toFixed(2)} tokens</span></td>
                        <td>
                            <button class="btn-primary" style="padding: 0.4rem 1rem; font-size: 0.85rem;" 
                                    onclick="purchaseListingDirect(${l.id}, ${l.remaining_energy_wh}, ${l.price_per_wh})">
                                Instant Buy
                            </button>
                        </td>
                    </tr>
                `).join('');
            }
        }
        
        // Fetch Buy Requests
        const reqData = await apiCall('/api/buy_requests');
        const reqTbody = document.getElementById('market-requests-body');
        if (reqTbody && reqData && reqData.requests) {
            if (reqData.requests.length === 0) {
                reqTbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No open buyer bids.</td></tr>`;
            } else {
                reqTbody.innerHTML = reqData.requests.map(r => `
                    <tr>
                        <td><strong>${r.house_name}</strong> <small style="color: var(--text-muted);">(${r.owner})</small></td>
                        <td><span class="color-soc">${r.remaining_energy_wh.toFixed(1)} Wh</span></td>
                        <td>${r.max_price_per_wh.toFixed(2)} tokens/Wh</td>
                        <td><span class="status-badge ${r.status}">${r.status}</span></td>
                    </tr>
                `).join('');
            }
        }
    };
    
    // Direct purchase wrapper
    window.purchaseListingDirect = async (listingId, amount, pricePerWh) => {
        if (!currentUserProfile) return;
        const totalCost = amount * pricePerWh;
        
        if (currentUserProfile.balance < totalCost) {
            showToast('Insufficient tokens to purchase this listing.', 'error');
            return;
        }
        
        // Instant Buy is implemented by placing a matching buy request:
        // By creating a request for the same amount with the listing's price, the matcher matches them instantly.
        const res = await apiCall('/api/buy_requests', 'POST', { energy: amount, max_price: pricePerWh });
        if (res) {
            showToast('Purchase successful! Trading matched.', 'success');
            fetchUserProfile();
            fetchMarketplaceData();
        }
    };
    
    fetchMarketplaceData();
    setInterval(fetchMarketplaceData, 5000);
}

// 4. Devices Context
function initDevices() {
    const updateDevicesGrid = async () => {
        const data = await apiCall('/api/devices');
        const grid = document.getElementById('devices-grid-container');
        if (grid && data && data.devices) {
            if (data.devices.length === 0) {
                grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted);">No houses registered.</div>`;
            } else {
                grid.innerHTML = data.devices.map(d => {
                    const soc = d.last_soc !== null ? d.last_soc.toFixed(0) : '0';
                    const power = d.last_power !== null ? d.last_power.toFixed(1) : '0.0';
                    const surplus = d.last_surplus !== null ? d.last_surplus.toFixed(1) : '0.0';
                    
                    return `
                    <div class="card flex-column" style="gap: 1rem;">
                        <div class="flex-between">
                            <div>
                                <h3 style="font-size: 1.2rem; font-weight: 600;">${d.house_name}</h3>
                                <small style="color: var(--text-muted);">Owner: ${d.owner}</small>
                            </div>
                            <span class="status-badge ${d.status}">${d.status}</span>
                        </div>
                        
                        <div class="flex-between" style="background: rgba(0, 0, 0, 0.15); padding: 1rem; border-radius: var(--radius-sm);">
                            <div class="flex-column" style="align-items: center; width: 45%;">
                                <small style="color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase;">Battery SoC</small>
                                <span class="color-soc" style="font-size: 1.4rem; font-weight: 700;">${soc}%</span>
                                <div class="progress-bar-bg" style="margin-top: 0.5rem;">
                                    <div class="progress-bar-fill soc" style="width: ${soc}%;"></div>
                                </div>
                            </div>
                            
                            <div style="width: 1px; background: var(--border-glass); height: 50px;"></div>
                            
                            <div class="flex-column" style="align-items: center; width: 45%;">
                                <small style="color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase;">Surplus Available</small>
                                <span class="color-surplus" style="font-size: 1.4rem; font-weight: 700;">${surplus} Wh</span>
                            </div>
                        </div>
                        
                        <div class="flex-between" style="font-size: 0.85rem; color: var(--text-secondary);">
                            <span>Power Draw: <strong class="color-power">${power} W</strong></span>
                            <span>IP: ${d.ip_address || '---'}</span>
                        </div>
                        
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-align: right;">
                            Last Active: ${d.last_seen || 'Never'}
                        </div>
                    </div>
                `}).join('');
            }
        }
    };
    
    updateDevicesGrid();
    setInterval(updateDevicesGrid, 4000);
}

// 5. Transactions Context
function initTransactions() {
    const fetchTransactionsHistory = async () => {
        const data = await apiCall('/api/transactions');
        const tbody = document.getElementById('transactions-table-body');
        if (tbody && data && data.transactions) {
            if (data.transactions.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">No transaction ledger records.</td></tr>`;
            } else {
                tbody.innerHTML = data.transactions.map(tx => `
                    <tr>
                        <td>#${tx.id}</td>
                        <td>${tx.seller_house} <small style="color: var(--text-muted);">(${tx.seller_owner})</small></td>
                        <td>${tx.buyer_house} <small style="color: var(--text-muted);">(${tx.buyer_owner})</small></td>
                        <td><strong class="color-surplus">${tx.energy_amount_wh.toFixed(1)} Wh</strong></td>
                        <td><strong class="color-power">${tx.total_price.toFixed(2)} tokens</strong></td>
                        <td><span class="status-badge ${tx.status}">${tx.status}</span></td>
                        <td><small style="color: var(--text-muted);">${tx.started_at}</small></td>
                    </tr>
                `).join('');
            }
        }
    };
    
    fetchTransactionsHistory();
    setInterval(fetchTransactionsHistory, 5000);
}

// 6. Admin Context
function initAdmin() {
    const updateAdminDashboard = async () => {
        const data = await apiCall('/api/admin/overview');
        if (data) {
            // Update Stats Values
            document.getElementById('stat-total-users').textContent = data.stats.total_users;
            document.getElementById('stat-total-houses').textContent = data.stats.total_houses;
            document.getElementById('stat-energy-traded').textContent = `${data.stats.total_energy_traded} Wh`;
            document.getElementById('stat-revenue').textContent = `${data.stats.total_revenue} tokens`;
            document.getElementById('stat-active-trades').textContent = data.stats.active_trades;
            document.getElementById('stat-completed-trades').textContent = data.stats.completed_trades;
            
            // Update Logs Console
            const logsContainer = document.getElementById('system-logs-container');
            if (logsContainer && data.logs) {
                if (data.logs.length === 0) {
                    logsContainer.innerHTML = `<div class="log-entry">Console empty.</div>`;
                } else {
                    logsContainer.innerHTML = data.logs.map(l => `
                        <div class="log-entry ${l.log_level}">
                            [${l.timestamp}] [${l.log_level}] [${l.source}]: ${l.message}
                        </div>
                    `).join('');
                }
            }
        }
    };
    
    updateAdminDashboard();
    setInterval(updateAdminDashboard, 3000);
}
