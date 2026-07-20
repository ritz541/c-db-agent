//! HTTP API client for communicating with the Python backend.
//!
//! Uses blocking reqwest to send/receive messages from the c-db agent API.

use anyhow::{Result, anyhow};
use serde::{Deserialize, Serialize};
use std::time::Duration;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolInfo {
    pub name: String,
    pub description: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryMessage {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ChatRequest {
    message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ChatResponse {
    role: String,
    content: String,
}

pub struct ApiClient {
    base_url: String,
    client: reqwest::blocking::Client,
}

impl ApiClient {
    pub fn new(base_url: &str) -> Self {
        Self {
            base_url: base_url.to_string(),
            client: reqwest::blocking::Client::new(),
        }
    }
    
    /// Test connection to the backend
    pub fn connect(&self) -> Result<()> {
        let response = self.client
            .get(&format!("{}/health", self.base_url))
            .timeout(Duration::from_secs(3))
            .send()?;
        
        if response.status().is_success() {
            Ok(())
        } else {
            Err(anyhow!("Health check failed: {}", response.status()))
        }
    }
    
    /// Send a message and get the response
    pub fn send_message(&self, message: &str) -> Result<String> {
        let request = ChatRequest {
            message: message.to_string(),
        };
        
        let response = self.client
            .post(&format!("{}/chat", self.base_url))
            .json(&request)
            .timeout(Duration::from_secs(30))
            .send()?;
        
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            return Err(anyhow!("API error ({}): {}", status, body));
        }
        
        let chat_response: ChatResponse = response.json()?;
        Ok(chat_response.content)
    }
    
    /// Get list of available tools
    pub fn get_tools(&self) -> Result<Vec<ToolInfo>> {
        let response = self.client
            .get(&format!("{}/tools", self.base_url))
            .timeout(Duration::from_secs(3))
            .send()?;
        
        if !response.status().is_success() {
            return Err(anyhow!("Failed to fetch tools"));
        }
        
        let tools: Vec<ToolInfo> = response.json()?;
        Ok(tools)
    }
    
    /// Get conversation history
    pub fn get_history(&self) -> Result<Vec<HistoryMessage>> {
        let response = self.client
            .get(&format!("{}/history", self.base_url))
            .timeout(Duration::from_secs(3))
            .send()?;
        
        if !response.status().is_success() {
            return Err(anyhow!("Failed to fetch history"));
        }
        
        let history: Vec<HistoryMessage> = response.json()?;
        Ok(history)
    }
}
