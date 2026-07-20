//! Application state for c-db Agent TUI.
//!
//! This holds the conversation history, tool list, and UI state.

use serde::{Deserialize, Serialize};
use std::time::{Duration, Instant};

#[derive(Clone, Debug)]
pub struct Message {
    pub role: String,
    pub content: String,
    pub timestamp: String,
    pub tool_calls: Vec<ToolCall>,
}

#[derive(Clone, Debug)]
pub struct ToolCall {
    pub tool_name: String,
    pub arguments: String,
    pub result: String,
}

#[derive(Clone, Debug)]
pub struct Tool {
    pub name: String,
    pub description: String,
    pub parameters: String,
}

#[derive(Debug)]
pub struct App {
    pub messages: Vec<Message>,
    pub tools: Vec<Tool>,
    pub input: String,
    pub status_msg: String,
    pub tab: Tab,
    pub input_mode: InputMode,
    pub scroll: usize,
    pub agent_typing: bool,
    pub tool_executing: Option<String>,
    pub connected: bool,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Tab {
    Chat,
    Tools,
    History,
    Config,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum InputMode {
    Normal,
    Editing,
    Palette,
}

impl App {
    pub fn new() -> Self {
        Self {
            messages: Vec::new(),
            tools: Vec::new(),
            input: String::new(),
            status_msg: String::new(),
            tab: Tab::Chat,
            input_mode: InputMode::Normal,
            scroll: 0,
            agent_typing: false,
            tool_executing: None,
            connected: false,
        }
    }

    pub fn add_message(&mut self, role: &str, content: &str) {
        self.messages.push(Message {
            role: role.to_string(),
            content: content.to_string(),
            timestamp: "now".to_string(), // TODO: actual timestamp
            tool_calls: Vec::new(),
        });
        // Auto-scroll to bottom
        self.scroll = 0;
    }

    pub fn set_status(&mut self, msg: &str) {
        self.status_msg = msg.to_string();
    }

    pub fn next_tab(&mut self) {
        self.tab = match self.tab {
            Tab::Chat => Tab::Tools,
            Tab::Tools => Tab::History,
            Tab::History => Tab::Config,
            Tab::Config => Tab::Chat,
        };
    }

    pub fn prev_tab(&mut self) {
        self.tab = match self.tab {
            Tab::Chat => Tab::Config,
            Tab::Tools => Tab::Chat,
            Tab::History => Tab::Tools,
            Tab::Config => Tab::History,
        };
    }

    pub fn scroll_up(&mut self) {
        if self.scroll > 0 {
            self.scroll -= 1;
        }
    }

    pub fn scroll_down(&mut self) {
        if self.scroll < self.messages.len().saturating_sub(1) {
            self.scroll += 1;
        }
    }

    pub fn jump_to_bottom(&mut self) {
        self.scroll = 0;
    }
}
