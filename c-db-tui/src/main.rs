//! c-db Agent TUI — Chat interface for AI agent.
//!
//! A beautiful terminal UI for chatting with the c-db AI agent.
//! Connects to the Python FastAPI backend over HTTP.

use anyhow::Result;
use crossterm::event::{self, Event as CEvent, KeyCode, KeyEvent, KeyEventKind, KeyModifiers};
use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem, Paragraph};
use ratatui::Terminal;
use std::io::{self, Stdout};
use std::time::{Duration, Instant};

mod api;
mod state;

use api::ApiClient;
use state::{App, InputMode, Tab};

const TICK_RATE: Duration = Duration::from_millis(200);

// ── Catppuccin-ish color palette ───────────────────────────────────────
const C_TEXT: Color = Color::Rgb(205, 214, 244);
const C_DIM: Color = Color::Rgb(108, 118, 148);
const C_MUTED: Color = Color::Rgb(70, 78, 105);
const C_CYAN: Color = Color::Rgb(137, 220, 235);
const C_BLUE: Color = Color::Rgb(137, 180, 250);
const C_AMBER: Color = Color::Rgb(249, 186, 96);
const C_RED: Color = Color::Rgb(243, 139, 168);
const C_PURPLE: Color = Color::Rgb(203, 166, 247);
const C_GREEN: Color = Color::Rgb(166, 227, 161);
const C_BG_SEL: Color = Color::Rgb(49, 50, 68);
const C_BORDER: Color = Color::Rgb(69, 71, 90);
const C_TITLE: Color = Color::Rgb(180, 190, 220);
const C_BLACK: Color = Color::Rgb(30, 30, 46);

fn main() -> Result<()> {
    let mut terminal = setup_terminal()?;
    let mut app = App::new();
    let api = ApiClient::new("http://127.0.0.1:8000");
    
    // Try to connect
    match api.connect() {
        Ok(_) => {
            app.connected = true;
            app.set_status("Connected to c-db Agent!");
            
            // Fetch tools in background
            if let Ok(tools) = api.get_tools() {
                app.tools = tools.into_iter().map(|t| state::Tool {
                    name: t.name,
                    description: t.description,
                }).collect();
            }
        }
        Err(e) => {
            app.set_status(&format!("Backend offline: {}", e));
        }
    }
    
    let result = run(&mut terminal, &mut app, &api);
    restore_terminal(&mut terminal)?;
    result
}

fn setup_terminal() -> Result<Terminal<CrosstermBackend<Stdout>>> {
    crossterm::terminal::enable_raw_mode()?;
    let mut stdout = io::stdout();
    crossterm::execute!(
        stdout,
        crossterm::terminal::EnterAlternateScreen,
        crossterm::event::EnableMouseCapture
    )?;
    let backend = CrosstermBackend::new(stdout);
    Ok(Terminal::new(backend)?)
}

fn restore_terminal(terminal: &mut Terminal<CrosstermBackend<Stdout>>) -> Result<()> {
    crossterm::terminal::disable_raw_mode()?;
    crossterm::execute!(
        terminal.backend_mut(),
        crossterm::event::DisableMouseCapture,
        crossterm::terminal::LeaveAlternateScreen
    )?;
    terminal.show_cursor()?;
    Ok(())
}

use ratatui::backend::CrosstermBackend;

fn run(
    terminal: &mut Terminal<CrosstermBackend<Stdout>>,
    app: &mut App,
    api: &ApiClient,
) -> Result<()> {
    let mut last_tick = Instant::now();
    
    loop {
        terminal.draw(|f| ui(f, app))?;
        
        let timeout = TICK_RATE
            .checked_sub(last_tick.elapsed())
            .unwrap_or(Duration::from_secs(0));
        
        if crossterm::event::poll(timeout)? {
            if let CEvent::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press {
                    if handle_key(key, app, api) {
                        return Ok(());
                    }
                }
            }
        }
        
        if last_tick.elapsed() >= TICK_RATE {
            last_tick = Instant::now();
            app.tick();
        }
    }
}

fn handle_key(key: KeyEvent, app: &mut App, api: &ApiClient) -> bool {
    // Global quit
    if key.code == KeyCode::Char('q') && app.input_mode == InputMode::Normal {
        return true;
    }
    if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
        return true;
    }
    
    // Tab switching (only in normal mode)
    if app.input_mode == InputMode::Normal {
        match key.code {
            KeyCode::F(1) | KeyCode::Char('1') => app.tab = Tab::Chat,
            KeyCode::F(2) | KeyCode::Char('2') => app.tab = Tab::Tools,
            KeyCode::F(3) | KeyCode::Char('3') => app.tab = Tab::History,
            KeyCode::F(4) | KeyCode::Char('4') => app.tab = Tab::Config,
            KeyCode::Tab => app.next_tab(),
            KeyCode::BackTab => app.prev_tab(),
            _ => {}
        }
    }
    
    match app.input_mode {
        InputMode::Normal => match key.code {
            KeyCode::Char('i') if app.tab == Tab::Chat => {
                app.input_mode = InputMode::Editing;
                app.input.clear();
            }
            // Scroll in history tab
            KeyCode::Up if app.tab == Tab::History => {
                if app.scroll < app.messages.len().saturating_sub(1) {
                    app.scroll += 1;
                }
            }
            KeyCode::Down if app.tab == Tab::History => {
                app.scroll = app.scroll.saturating_sub(1);
            }
            _ => {}
        },
        InputMode::Editing => match key.code {
            KeyCode::Enter => {
                let input = app.input.trim().to_string();
                if !input.is_empty() && !app.waiting_response {
                    app.add_message("user", &input);
                    app.waiting_response = true;
                    app.set_status("Agent is thinking...");
                    
                    if app.connected {
                        match api.send_message(&input) {
                            Ok(response) => {
                                app.add_message("agent", &response);
                                app.set_status("Ready");
                            }
                            Err(e) => {
                                app.set_status(&format!("Error: {}", e));
                            }
                        }
                    } else {
                        app.add_message("agent", "Backend is offline. Start it with: python api.py");
                        app.set_status("Backend offline");
                    }
                    
                    app.waiting_response = false;
                    app.input.clear();
                }
                app.input_mode = InputMode::Normal;
            }
            KeyCode::Esc => {
                app.input.clear();
                app.input_mode = InputMode::Normal;
            }
            KeyCode::Char(c) => app.input.push(c),
            KeyCode::Backspace => {
                app.input.pop();
            }
            _ => {}
        },
    }
    
    false
}

// ── UI Rendering ──────────────────────────────────────────────────────

fn border() -> Style { Style::default().fg(C_BORDER) }
fn title_style() -> Style { Style::default().fg(C_TITLE) }

fn panel(title: &str) -> Block<'static> {
    Block::default()
        .borders(Borders::ALL)
        .border_style(border())
        .title(Span::styled(format!(" {title} "), title_style()))
}

fn panel_accent(title: &str, accent: Color) -> Block<'static> {
    Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(accent))
        .title(Span::styled(
            format!(" {title} "),
            Style::default().fg(accent).add_modifier(Modifier::BOLD),
        ))
}

fn ui(f: &mut ratatui::Frame, app: &App) {
    let size = f.area();
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // header
            Constraint::Min(0),    // body
            Constraint::Length(3), // footer
        ])
        .split(size);

    render_header(f, app, chunks[0]);

    match app.tab {
        Tab::Chat => render_chat(f, app, chunks[1]),
        Tab::Tools => render_tools(f, app, chunks[1]),
        Tab::History => render_history(f, app, chunks[1]),
        Tab::Config => render_config(f, app, chunks[1]),
    }

    render_footer(f, app, chunks[2]);
}

fn render_header(f: &mut ratatui::Frame, app: &App, area: Rect) {
    let spin = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"][app.typing_spinner as usize];
    
    let status = if !app.connected {
        Span::styled(
            " ⚠ DISCONNECTED ",
            Style::default().fg(Color::Black).bg(C_RED).add_modifier(Modifier::BOLD),
        )
    } else if app.waiting_response {
        Span::styled(
            format!(" {} THINKING ", spin),
            Style::default().fg(Color::Black).bg(C_AMBER).add_modifier(Modifier::BOLD),
        )
    } else {
        Span::styled(
            " ● IDLE ",
            Style::default().fg(Color::Black).bg(C_GREEN).add_modifier(Modifier::BOLD),
        )
    };

    let title = Span::styled(
        " c-db Agent ",
        Style::default()
            .fg(Color::Black)
            .bg(C_CYAN)
            .add_modifier(Modifier::BOLD),
    );

    let info = if app.connected {
        Span::styled(
            format!("  {} tools loaded ", app.tools.len()),
            Style::default().fg(C_DIM),
        )
    } else {
        Span::styled(
            "  backend: python api.py ",
            Style::default().fg(C_AMBER),
        )
    };

    let toast = if !app.status_msg.is_empty() {
        Span::styled(
            format!(" · {} ", app.status_msg),
            Style::default().fg(C_AMBER),
        )
    } else {
        Span::raw("")
    };

    let line = Line::from(vec![title, status, info, toast]);
    f.render_widget(Paragraph::new(line).block(Block::default().borders(Borders::ALL).border_style(border())), area);
}

fn render_chat(f: &mut ratatui::Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(0),    // messages
            Constraint::Length(3), // input
        ])
        .split(area);

    // Messages area
    let h = chunks[0].height.saturating_sub(2) as usize;
    let start = app.messages.len().saturating_sub(h + app.scroll);

    let messages: Vec<Line> = if app.messages.is_empty() {
        vec![
            Line::from(""),
            Line::from(Span::styled("  Welcome to c-db Agent! 👋", Style::default().fg(C_CYAN).add_modifier(Modifier::BOLD))),
            Line::from(""),
            Line::from(Span::styled("  I'm your AI assistant with access to tools:", Style::default().fg(C_DIM))),
            Line::from(Span::styled("    🔢  Calculate math expressions", Style::default().fg(C_DIM))),
            Line::from(Span::styled("    🗄️  Query databases", Style::default().fg(C_DIM))),
            Line::from(Span::styled("    ✉️  Draft & send job applications", Style::default().fg(C_DIM))),
            Line::from(Span::styled("    🌤️  Check weather", Style::default().fg(C_DIM))),
            Line::from(""),
            Line::from(Span::styled("  Press 'i' to start typing, Enter to send.", Style::default().fg(C_BLUE))),
            Line::from(Span::styled("  Press 'q' to quit.", Style::default().fg(C_DIM))),
        ]
    } else {
        app.messages
            .iter()
            .skip(start)
            .take(h)
            .map(|m| {
                let (prefix, color) = if m.role == "user" {
                    ("▸ You:  ", C_CYAN)
                } else {
                    ("◂ Agent:", C_GREEN)
                };
                Line::from(vec![
                    Span::styled(prefix, Style::default().fg(color).add_modifier(Modifier::BOLD)),
                    Span::styled(&m.content, Style::default().fg(C_TEXT)),
                ])
            })
            .collect()
    };

    f.render_widget(
        Paragraph::new(messages).block(panel_accent("💬 Chat", C_CYAN)),
        chunks[0],
    );

    // Input area
    let input_display = match app.input_mode {
        InputMode::Editing => {
            if app.waiting_response {
                " Waiting for response...".to_string()
            } else {
                format!(" {}▎", app.input)
            }
        }
        InputMode::Normal => " Press 'i' to type...".to_string(),
    };

    let input_style = match app.input_mode {
        InputMode::Editing if !app.waiting_response => Style::default().fg(C_TEXT).bg(C_BG_SEL),
        _ => Style::default().fg(C_DIM),
    };

    f.render_widget(
        Paragraph::new(input_display)
            .style(input_style)
            .block(panel(" Input ")),
        chunks[1],
    );
}

fn render_tools(f: &mut ratatui::Frame, app: &App, area: Rect) {
    let items: Vec<ListItem> = if app.tools.is_empty() {
        vec![ListItem::new(Line::from(Span::styled(
            "  No tools loaded. Is the backend running?",
            Style::default().fg(C_DIM),
        )))]
    } else {
        app.tools.iter().map(|t| {
            ListItem::new(vec![
                Line::from(vec![
                    Span::styled("  ◆ ", Style::default().fg(C_CYAN)),
                    Span::styled(
                        &t.name,
                        Style::default().fg(C_TEXT).add_modifier(Modifier::BOLD),
                    ),
                ]),
                Line::from(vec![
                    Span::styled("    ", Style::default().fg(C_DIM)),
                    Span::styled(
                        truncate(&t.description, 60),
                        Style::default().fg(C_DIM),
                    ),
                ]),
            ])
        }).collect()
    };

    f.render_widget(
        List::new(items).block(panel_accent("🔧 Available Tools", C_PURPLE)),
        area,
    );
}

fn render_history(f: &mut ratatui::Frame, app: &App, area: Rect) {
    let h = area.height.saturating_sub(2) as usize;
    let start = app.messages.len().saturating_sub(h + app.scroll);

    let lines: Vec<Line> = if app.messages.is_empty() {
        vec![
            Line::from(Span::styled("  No conversation history yet.", Style::default().fg(C_DIM))),
            Line::from(Span::styled("  Start chatting in the Chat tab (F1).", Style::default().fg(C_MUTED))),
        ]
    } else {
        app.messages
            .iter()
            .enumerate()
            .skip(start)
            .take(h)
            .map(|(i, m)| {
                let (tag, color) = if m.role == "user" { ("YOU", C_CYAN) } else { ("AI ", C_GREEN) };
                Line::from(vec![
                    Span::styled(format!("#{:03} ", i + 1), Style::default().fg(C_DIM)),
                    Span::styled(format!("[{}]", tag), Style::default().fg(color).add_modifier(Modifier::BOLD)),
                    Span::styled(" ", Style::default().fg(C_DIM)),
                    Span::styled(truncate(&m.content, 60), Style::default().fg(C_TEXT)),
                ])
            })
            .collect()
    };

    let scroll_hint = if app.scroll > 0 { " · scrolled" } else { "" };
    f.render_widget(
        Paragraph::new(lines).block(panel_accent(&format!("📜 History{scroll_hint}"), C_BLUE)),
        area,
    );
}

fn render_config(f: &mut ratatui::Frame, _app: &App, area: Rect) {
    let lines = vec![
        Line::from(""),
        Line::from(vec![
            Span::styled("  Backend: ", Style::default().fg(C_DIM)),
            Span::styled("http://127.0.0.1:8000", Style::default().fg(C_TEXT)),
        ]),
        Line::from(vec![
            Span::styled("  Model:   ", Style::default().fg(C_DIM)),
            Span::styled("deepseek/deepseek-v4-flash", Style::default().fg(C_CYAN)),
        ]),
        Line::from(""),
        Line::from(Span::styled("  ─── Quick Start ───", Style::default().fg(C_MUTED))),
        Line::from(Span::styled("  Start backend:    python api.py", Style::default().fg(C_DIM))),
        Line::from(Span::styled("  Start TUI:        cargo run", Style::default().fg(C_DIM))),
        Line::from(Span::styled("  Add new tool:     Create tools/my_tool.py", Style::default().fg(C_DIM))),
        Line::from(""),
        Line::from(Span::styled("  ─── Keybindings ───", Style::default().fg(C_MUTED))),
        Line::from(Span::styled("  F1-F4 / 1-4:     Switch tabs", Style::default().fg(C_DIM))),
        Line::from(Span::styled("  i               Input mode", Style::default().fg(C_DIM))),
        Line::from(Span::styled("  Enter           Send message", Style::default().fg(C_DIM))),
        Line::from(Span::styled("  Esc             Cancel input", Style::default().fg(C_DIM))),
        Line::from(Span::styled("  q / Ctrl+C      Quit", Style::default().fg(C_DIM))),
    ];

    f.render_widget(
        Paragraph::new(lines).block(panel_accent("⚙️ Config", C_AMBER)),
        area,
    );
}

fn render_footer(f: &mut ratatui::Frame, _app: &App, area: Rect) {
    let help = match _app.input_mode {
        InputMode::Normal => "  i: type  │  q: quit  │  Tab: switch tab  │  ↑↓: scroll",
        InputMode::Editing => "  Enter: send  │  Esc: cancel",
    };

    let line = Line::from(vec![
        Span::styled(help, Style::default().fg(C_DIM)),
    ]);
    
    f.render_widget(
        Paragraph::new(line).block(Block::default().borders(Borders::ALL).border_style(border())),
        area,
    );
}

fn truncate(s: &str, max: usize) -> String {
    if s.len() <= max {
        s.to_string()
    } else {
        format!("{}…", &s[..max.saturating_sub(1)])
    }
}
