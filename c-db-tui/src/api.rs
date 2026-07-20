//! HTTP API client for communicating with the Python backend.
//!
//! Supports both blocking requests and SSE streaming.

use anyhow::{Result, anyhow};
use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader};
use std::sync::mpsc::Sender;
use std::time::Duration;

use crate::state::StreamEvent;

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

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SseToken {
    token: Option<String>,
    done: Option<bool>,
    error: Option<String>,
}

pub struct ApiClient {
    base_url: String,
}

impl ApiClient {
    pub fn new(base_url: &str) -> Self {
        Self {
            base_url: base_url.to_string(),
        }
    }
    
    /// Test connection to the backend
    pub fn connect(&self) -> Result<()> {
        let client = reqwest::blocking::Client::new();
        let response = client
            .get(&format!("{}/health", self.base_url))
            .timeout(Duration::from_secs(3))
            .send()?;
        
        if response.status().is_success() {
            Ok(())
        } else {
            Err(anyhow!("Health check failed: {}", response.status()))
        }
    }
    
    /// Send a message and get the full response (blocking)
    pub fn send_message(&self, message: &str) -> Result<String> {
        let client = reqwest::blocking::Client::new();
        let request = ChatRequest {
            message: message.to_string(),
        };
        
        let response = client
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
    
    /// Send a message and stream the response via SSE.
    /// Returns a thread handle. Tokens are sent via the Sender.
    pub fn send_message_stream(
        &self,
        message: String,
        tx: Sender<StreamEvent>,
    ) -> std::thread::JoinHandle<()> {
        let url = format!("{}/chat/stream", self.base_url);
        
        std::thread::spawn(move || {
            let client = reqwest::blocking::Client::new();
            let request = ChatRequest { message };
            
            match client
                .post(&url)
                .json(&request)
                .timeout(Duration::from_secs(60))
                .send()
            {
                Ok(response) => {
                    let reader = BufReader::new(response);
                    for line in reader.lines() {
                        match line {
                            Ok(line) => {
                                if line.starts_with("data: ") {
                                    let data = &line[6..]; // strip "data: "
                                    if let Ok(sse) = serde_json::from_str::<SseToken>(data) {
                                        if let Some(token) = sse.token {
                                            if tx.send(StreamEvent::Token(token)).is_err() {
                                                break;
                                            }
                                        }
                                        if sse.done.unwrap_or(false) {
                                            let _ = tx.send(StreamEvent::Done);
                                            break;
                                        }
                                        if let Some(err) = sse.error {
                                            let _ = tx.send(StreamEvent::Error(err));
                                            break;
                                        }
                                    }
                                }
                            }
                            Err(_) => break,
                        }
                    }
                }
                Err(e) => {
                    let _ = tx.send(StreamEvent::Error(format!("{}", e)));
                }
            }
        })
    }
    
    /// Get list of available tools
    pub fn get_tools(&self) -> Result<Vec<ToolInfo>> {
        let client = reqwest::blocking::Client::new();
        let response = client
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
        let client = reqwest::blocking::Client::new();
        let response = client
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
