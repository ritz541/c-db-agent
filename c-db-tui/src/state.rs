//! Application state for c-db Agent TUI.
//!
//! This holds the conversation history, tool list, and UI state.

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Tool {
    pub name: String,
    pub description: String,
}

#[derive(Clone, Debug)]
pub struct Message {
    pub role: String,
    pub content: String,
}

#[derive(Debug)]
pub struct App {
    pub messages: Vec<Message>,
    pub tools: Vec<Tool>,
    pub input: String,
    pub status_msg: String,
    pub status_timer: u8,
    pub tab: Tab,
    pub input_mode: InputMode,
    pub scroll: usize,
    pub typing_spinner: u8,
    pub waiting_response: bool,
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
}

impl App {
    pub fn new() -> Self {
        Self {
            messages: Vec::new(),
            tools: Vec::new(),
            input: String::new(),
            status_msg: String::new(),
            status_timer: 0,
            tab: Tab::Chat,
            input_mode: InputMode::Normal,
            scroll: 0,
            typing_spinner: 0,
            waiting_response: false,
            connected: false,
        }
    }

    pub fn add_message(&mut self, role: &str, content: &str) {
        self.messages.push(Message {
            role: role.to_string(),
            content: content.to_string(),
        });
        self.scroll = 0;
    }

    pub fn set_status(&mut self, msg: &str) {
        self.status_msg = msg.to_string();
        self.status_timer = 20; // Show for ~4 seconds (20 ticks at 200ms)
    }

    pub fn tick(&mut self) {
        self.typing_spinner = (self.typing_spinner + 1) % 10;
        if self.status_timer > 0 {
            self.status_timer -= 1;
            if self.status_timer == 0 {
                self.status_msg.clear();
            }
        }
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
}
