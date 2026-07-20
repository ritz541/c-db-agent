//! c-db Agent TUI — Chat interface for AI agent.
//!
//! Connects to Python backend over HTTP and renders a beautiful chat UI.

use anyhow::Result;
use crossterm::event::{self, Event as CEvent, KeyCode, KeyEvent, KeyEventKind, KeyModifiers};
use ratatui::backend::CrosstermBackend;
use ratatui::layout::{Alignment, Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Clear, Gauge, List, ListItem, Paragraph};
use ratatui::Terminal;
use std::io::{self, Stdout};
use std::sync::mpsc::{channel, Receiver};
use std::time::{Duration, Instant};

mod state;
mod api;

use state::{App, InputMode, Tab};
use api::ApiClient;

const TICK_RATE: Duration = Duration::from_millis(200);

// ── Color palette ───────────────────────────────────────────────────────
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

fn main() -> Result<()> {
    let (tx, rx) = channel::<String>();
    let mut client = ApiClient::new("http://127.0.0.1:8000");
    
    let mut terminal = setup_terminal()?;
    let mut app = App::new();
    
    // Try to connect to backend
    match client.connect() {
        Ok(_) => {
            app.connected = true;
            app.set_status("Connected to c-db Agent");
        }
        Err(e) => {
            app.set_status(&format!("Backend offline: {}", e));
        }
    }
    
    let app_result = run_app(&mut terminal, &mut app, &mut client, &rx);
    restore_terminal(&mut terminal)?;
    app_result
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

fn run_app(
    terminal: &mut Terminal<CrosstermBackend<Stdout>>,
    app: &mut App,
    client: &mut ApiClient,
    rx: &Receiver<String>,
) -> Result<()> {
    let mut last_tick = Instant::now();
    loop {
        while let Ok(msg) = rx.try_recv() {
            app.add_message("assistant", &msg);
        }
        
        terminal.draw(|f| ui(f, app))?;
        
        let timeout = TICK_RATE
            .checked_sub(last_tick.elapsed())
            .unwrap_or(Duration::from_secs(0));
        
        if crossterm::event::poll(timeout)? {
            if let CEvent::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press && handle_key(key, app, client) {
                    return Ok(());
                }
            }
        }
        
        if last_tick.elapsed() >= TICK_RATE {
            last_tick = Instant::now();
        }
    }
}

fn handle_key(key: KeyEvent, app: &mut App, client: &mut ApiClient) -> bool {
    // Global quit
    if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
        return true;
    }
    
    // Tab switching
    if app.input_mode == InputMode::Normal {
        match key.code {
            KeyCode::F(1) => app.tab = Tab::Chat,
            KeyCode::F(2) => app.tab = Tab::Tools,
            KeyCode::F(3) => app.tab = Tab::History,
            KeyCode::F(4) => app.tab = Tab::Config,
            KeyCode::Char('1') if key.modifiers == KeyModifiers::NONE => app.tab = Tab::Chat,
            KeyCode::Char('2') if key.modifiers == KeyModifiers::NONE => app.tab = Tab::Tools,
            KeyCode::Char('3') if key.modifiers == KeyModifiers::NONE => app.tab = Tab::History,
            KeyCode::Char('4') if key.modifiers == KeyModifiers::NONE => app.tab = Tab::Config,
            KeyCode::Tab => app.next_tab(),
            KeyCode::BackTab => app.prev_tab(),
            KeyCode::Char('q') => return true,
            _ => {}
        }
    }
    
    match app.input_mode {
        InputMode::Normal => match key.code {
            KeyCode::Char('i') => {
                app.input_mode = InputMode::Editing;
                app.input.clear();
            }
            _ => {}
        },
        InputMode::Editing => match key.code {
            KeyCode::Enter => {
                let input = app.input.trim().to_string();
                if !input.is_empty() {
                    app.add_message("user", &input);
                    
                    // Send to backend
                    if app.connected {
                        match client.send_message(&input) {
                            Ok(response) => {
                                app.add_message("assistant", &response);
                            }
                            Err(e) => {
                                app.set_status(&format!("Error: {}", e));
                            }
                        }
                    }
                    
                    app.input_mode = InputMode::Normal;
                }
            }
            KeyCode::Esc => {
                app.input_mode = InputMode::Normal;
            }
            KeyCode::Char(c) => app.input.push(c),
            KeyCode::Backspace => {
                app.input.pop();
            }
            _ => {}
        },
        _ => {}
    }
    
    false
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
    let status = if !app.connected {
        Span::styled(
            " ⚠ DISCONNECTED ",
            Style::default().fg(Color::Black).bg(C_RED).add_modifier(Modifier::BOLD),
        )
    } else if app.agent_typing {
        Span::styled(
            " ● TYPING ",
            Style::default().fg(Color::Black).bg(C_AMBER).add_modifier(Modifier::BOLD),
        )
    } else {
        Span::styled(
            " ● IDLE ",
            Style::default().fg(C_DIM).bg(C_BG_SEL),
        )
    };
    
    let title = Span::styled(
        " c-db Agent ",
        Style::default()
            .fg(Color::Black)
            .bg(C_CYAN)
            .add_modifier(Modifier::BOLD),
    );
    
    let line = Line::from(vec![title, Span::raw("  "), status]);
    f.render_widget(
        Paragraph::new(line).block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(C_BORDER))
        ),
        area,
    );
}

fn render_chat(f: &mut ratatui::Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(0),    // messages
            Constraint::Length(3), // input
        ])
        .split(area);
    
    // Render messages
    let h = chunks[0].height.saturating_sub(2) as usize;
    let start = app.messages.len().saturating_sub(h + app.scroll);
    
    let messages: Vec<Line> = if app.messages.is_empty() {
        vec![
            Line::from(""),
            Line::from(Span::styled(
                "  No messages yet. Press 'i' to start chatting!",
                Style::default().fg(C_DIM),
            )),
        ]
    } else {
        app.messages
            .iter()
            .skip(start)
            .take(h)
            .map(|m| {
                let role_color = if m.role == "user" {
                    C_CYAN
                } else {
                    C_GREEN
                };
                Line::from(vec![
                    Span::styled(
                        format!("{}: ", m.role),
                        Style::default().fg(role_color).add_modifier(Modifier::BOLD),
                    ),
                    Span::styled(
                        &m.content,
                        Style::default().fg(C_TEXT),
                    ),
                ])
            })
            .collect()
    };
    
    f.render_widget(
        Paragraph::new(messages).block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(C_BORDER))
                .title(" Chat ")
        ),
        chunks[0],
    );
    
    // Render input
    let input_display = if app.input_mode == InputMode::Editing {
        format!("{}▎", app.input)
    } else {
        "Press 'i' to type...".to_string()
    };
    
    let input_style = if app.input_mode == InputMode::Editing {
        Style::default().fg(C_TEXT).bg(C_BG_SEL)
    } else {
        Style::default().fg(C_DIM)
    };
    
    f.render_widget(
        Paragraph::new(input_display).block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(input_style)
                .title(" Input ")
        ),
        chunks[1],
    );
}

fn render_tools(f: &mut ratatui::Frame, _app: &App, area: Rect) {
    let tools_list = vec![
        ListItem::new("🔢 calculate"),
        ListItem::new("🗄️ query_database")),
        ListItem::new("📄 store_resume")),
        ListItem::new("📄 list_resumes")),
        ListItem::new("🗄️ load_resume_from_pdf")),
        ListItem::new("✉️ draft_application")),
        ListItem::new("📧 list_applications")),
        ListItem::new("✉️ send_email")),
        ListItem::new("🌤️ get_weather")),
    ];
    
    f.render_widget(
        List::new(tools_list).block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(C_BORDER))
                .title(" Available Tools (9) ")
        ),
        area,
    );
}

fn render_history(f: &mut ratatui::Frame, app: &App, area: Rect) {
    let h = area.height.saturating_sub(2) as usize;
    let start = app.messages.len().saturating_sub(h + app.scroll);
    
    let messages: Vec<Line> = app.messages
        .iter()
        .skip(start)
        .take(h)
        .map(|m| {
            Line::from(vec![
                Span::styled(
                    format!("[{}] {}: ", m.timestamp, m.role),
                    Style::default().fg(C_DIM),
                ),
                Span::styled(
                    &m.content,
                    Style::default().fg(C_TEXT),
                ),
            ])
        })
        .collect();
    
    f.render_widget(
        Paragraph::new(messages).block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(C_BORDER))
                .title(" Conversation History ")
        ),
        area,
    );
}

fn render_config(f: &mut ratatui::Frame, _app: &App, area: Rect) {
    let config_lines = vec![
        Line::from(vec![
            Span::styled("Backend URL: ", Style::default().fg(C_DIM)),
            Span::styled("http://127.0.0.1:8000", Style::default().fg(C_TEXT)),
        ]),
        Line::from(vec![
            Span::styled("Model: ", Style::default().fg(C_DIM)),
            Span::styled("deepseek/deepseek-v4-flash", Style::default().fg(C_CYAN)),
        ]),
        Line::from(""),
        Line::from(Span::styled(
            "  TODO: Add config editing UI",
            Style::default().fg(C_AMBER),
        )),
    ];
    
    f.render_widget(
        Paragraph::new(config_lines).block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(C_BORDER))
                .title(" Config ")
        ),
        area,
    );
}

fn render_footer(f: &mut ratatui::Frame, app: &App, area: Rect) {
    let help = match app.input_mode {
        InputMode::Normal => {
            " F1-F4: Tabs | i: Type | q: Quit | Tab: Switch tab "
        }
        InputMode::Editing => {
            " Enter: Send | Esc: Cancel "
        }
        _ => "",
    };
    
    let status = if !app.status_msg.is_empty() {
        format!(" | {}", app.status_msg)
    } else {
        String::new()
    };
    
    let line = Line::from(vec![
        Span::styled(help, Style::default().fg(C_DIM)),
        Span::styled(status, Style::default().fg(C_AMBER)),
    ]);
    
    f.render_widget(
        Paragraph::new(line).block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(C_BORDER))
        ),
        area,
    );
}
