//! HTTP API client for communicating with the Python backend.
//!
//! Uses reqwest to send/receive messages from the c-db agent API.

use anyhow::{Result, anyhow};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::time::Duration;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatRequest {
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatResponse {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tool {
    pub name: String,
    pub description: String,
}

pub struct ApiClient {
    base_url: String,
    client: reqwest::Client,
}

impl ApiClient {
    pub fn new(base_url: &str) -> Self {
        Self {
            base_url: base_url.to_string(),
            client: reqwest::Client::new(),
        }
    }
    
    pub fn connect(&self) -> Result<()> {
        // Simple health check
        let response = self.client
            .get(&format!("{}/health", self.base_url))
            .timeout(Duration::from_secs(2))
            .send();
        
        match response {
            Ok(_) => Ok(()),
            Err(e) => Err(anyhow!("Failed to connect: {}", e)),
        }
    }
    
    pub fn send_message(&self, message: &str) -> Result<String> {
        let request = ChatRequest {
            message: message.to_string(),
        };
        
        let response = self.client
            .post(&format!("{}/chat", self.base_url))
            .json(&request)
            .send();
        
        match response {
            Ok(resp) => {
                let chat_response: ChatResponse = resp.json()?;
                Ok(chat_response.content)
            }
            Err(e) => Err(anyhow!("Failed to send message: {}", e)),
        }
    }
    
    pub fn get_tools(&self) -> Result<Vec<Tool>> {
        let response = self.client
            .get(&format!("{}/tools", self.base_url))
            .send();
        
        match response {
            Ok(resp) => {
                let tools: Vec<Tool> = resp.json()?;
                Ok(tools)
            }
            Err(e) => Err(anyhow!("Failed to get tools: {}", e)),
        }
    }
    
    pub fn get_history(&self) -> Result<Vec<Message>> {
        let response = self.client
            .get(&format!("{}/history", self.base_url))
            .send();
        
        match response {
            Ok(resp) => {
                let history: Vec<Message> = resp.json()?;
                Ok(history)
            }
            Err(e) => Err(anyhow!("Failed to get history: {}", e)),
        }
    }
}
