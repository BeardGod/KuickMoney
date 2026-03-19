// KuickMoney - Retail Bot Backend
use serde::{Deserialize, Serialize};
use std::sync::Mutex;
use tauri::State;

// ============ CONFIG ============
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProxyConfig {
    pub host: String,
    pub port: u16,
    pub username: String,
    pub password: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TelegramConfig {
    pub bot_token: String,
    pub chat_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaymentInfo {
    pub name: String,
    pub card_number: String,
    pub expiry: String,
    pub cvv: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Product {
    pub id: String,
    pub url: String,
    pub retailer: String,
    pub status: String,
    pub last_check: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub proxy: Option<ProxyConfig>,
    pub telegram: Option<TelegramConfig>,
    pub payment: Option<PaymentInfo>,
    pub products: Vec<Product>,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            proxy: None,
            telegram: None,
            payment: None,
            products: Vec::new(),
        }
    }
}

// ============ STATE ============
pub struct AppState {
    pub config: Mutex<AppConfig>,
}

// ============ COMMANDS ============

#[tauri::command]
pub fn get_config(state: State<AppState>) -> Result<AppConfig, String> {
    let config = state.config.lock().map_err(|e| e.to_string())?;
    Ok(config.clone())
}

#[tauri::command]
pub fn save_config(state: State<AppState>, config: AppConfig) -> Result<(), String> {
    let mut current = state.config.lock().map_err(|e| e.to_string())?;
    *current = config;
    save_config_to_file(&current)?;
    Ok(())
}

#[tauri::command]
pub fn add_product(state: State<AppState>, url: String, retailer: String) -> Result<Product, String> {
    let mut config = state.config.lock().map_err(|e| e.to_string())?;
    
    let product = Product {
        id: uuid_simple(),
        url: url.clone(),
        retailer: retailer.clone(),
        status: "monitoring".to_string(),
        last_check: now(),
    };
    
    config.products.push(product.clone());
    save_config_to_file(&config)?;
    
    log::info!("Added product: {} for {}", url, retailer);
    Ok(product)
}

#[tauri::command]
pub fn remove_product(state: State<AppState>, id: String) -> Result<(), String> {
    let mut config = state.config.lock().map_err(|e| e.to_string())?;
    config.products.retain(|p| p.id != id);
    save_config_to_file(&config)?;
    Ok(())
}

#[tauri::command]
pub fn check_product(state: State<AppState>, id: String) -> Result<Product, String> {
    let config = state.config.lock().map_err(|e| e.to_string())?;
    
    let product = config.products.iter()
        .find(|p| p.id == id)
        .cloned()
        .ok_or("Product not found")?;
    
    Ok(product)
}

#[tauri::command]
pub async fn test_proxy(proxy: ProxyConfig) -> Result<bool, String> {
    log::info!("Testing proxy: {}:{}", proxy.host, proxy.port);
    // Test proxy connection
    let proxy_url = format!("http://{}:{}@{}:{}", proxy.username, proxy.password, proxy.host, proxy.port);
    let client = reqwest::Client::builder()
        .proxy(&proxy_url)
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| e.to_string())?;
    
    match client.get("https://www.pokemoncenter.com/").send().await {
        Ok(resp) => {
            log::info!("Proxy test response: {}", resp.status());
            Ok(resp.status().is_success())
        }
        Err(e) => {
            log::error!("Proxy test failed: {}", e);
            Err(e.to_string())
        }
    }
}

#[tauri::command]
pub async fn send_telegram_alert(telegram: TelegramConfig, message: String) -> Result<(), String> {
    let url = format!("https://api.telegram.org/bot{}/sendMessage", telegram.bot_token);
    let params = serde_json::json!({
        "chat_id": telegram.chat_id,
        "text": message,
        "parse_mode": "Markdown"
    });
    
    reqwest::Client::new()
        .post(&url)
        .json(&params)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    
    Ok(())
}

#[tauri::command]
pub async fn checkout_product(id: String, state: State<'_, AppState>) -> Result<String, String> {
    let config = state.config.lock().map_err(|e| e.to_string())?.clone();
    
    let product = config.products.iter()
        .find(|p| p.id == id)
        .ok_or("Product not found")?;
    
    log::info!("Starting checkout for: {} ({})", product.url, product.retailer);
    
    // TODO: Implement actual checkout with browser automation
    // For now, return success and let frontend know it worked
    
    // Send Telegram alert
    if let Some(ref tg) = config.telegram {
        let _ = send_telegram_alert(tg.clone(), format!(
            "🚀 *KuickMoney Checkout Started*\n\nRetailer: {}\nURL: {}\n\n_Processing..._",
            product.retailer, product.url
        )).await;
    }
    
    Ok("Checkout initiated".to_string())
}

// ============ HELPERS ============

fn save_config_to_file(config: &AppConfig) -> Result<(), String> {
    let config_dir = dirs::config_dir()
        .ok_or("Could not find config directory")?
        .join("KuickMoney");
    
    std::fs::create_dir_all(&config_dir).map_err(|e| e.to_string())?;
    let config_path = config_dir.join("config.toml");
    
    let toml = toml::to_string(config).map_err(|e| e.to_string())?;
    std::fs::write(config_path, toml).map_err(|e| e.to_string())?;
    
    Ok(())
}

pub fn load_config() -> AppConfig {
    let config_dir = dirs::config_dir()
        .unwrap_or_default()
        .join("KuickMoney");
    let config_path = config_dir.join("config.toml");
    
    if config_path.exists() {
        if let Ok(toml) = std::fs::read_to_string(&config_path) {
            if let Ok(config) = toml::from_str(&toml) {
                return config;
            }
        }
    }
    
    AppConfig::default()
}

fn now() -> String {
    chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string()
}

fn uuid_simple() -> String {
    use rand::Rng;
    let mut rng = rand::thread_rng();
    let bytes: [u8; 16] = rng.gen();
    format!("{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        bytes[0], bytes[1], bytes[2], bytes[3],
        bytes[4], bytes[5], bytes[6], bytes[7],
        bytes[8], bytes[9], bytes[10], bytes[11],
        bytes[12], bytes[13], bytes[14], bytes[15])
}

// ============ APP SETUP ============

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .init();
    
    log::info!("KuickMoney starting...");
    
    let config = load_config();
    
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState {
            config: Mutex::new(config),
        })
        .invoke_handler(tauri::generate_handler![
            get_config,
            save_config,
            add_product,
            remove_product,
            check_product,
            test_proxy,
            send_telegram_alert,
            checkout_product,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
