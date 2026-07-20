//! c-db Agent TUI — Chat interface for AI agent.
//!
//! A beautiful terminal UI for chatting with the c-db AI agent.
//! Connects to the Python FastAPI backend over HTTP.

use anyhow::Result;
use crossterm::event::{self, Event as CEvent, KeyCode, KeyEvent, KeyEventKind, KeyModifiers};
use ratatui::layout::{Alignment, Constraint, Direction, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, BorderType, Borders, List, ListItem, Paragraph, Gauge};
use ratatui::Terminal;
use std::io::{self, Stdout};
use std::sync::mpsc::channel;
use std::time::{Duration, Instant};

mod api;
mod markdown;
mod state;
mod theme;

use api::ApiClient;
use state::{App, InputMode, StreamEvent, Tab, ToolStatus};
use theme::Theme;

const TICK_RATE: Duration = Duration::from_millis(200);

fn main() -> Result<()> {
    let mut terminal = setup_terminal()?;
    let mut app = App::new();
    let api = ApiClient::new("http://127.0.0.1:8000");

    // Try to connect
    match api.connect() {
        Ok(_) => {
            app.connected = true;
            app.set_status("Connected");
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
    let (stream_tx, stream_rx) = channel::<StreamEvent>();

    loop {
        // Handle streaming events
        while let Ok(event) = stream_rx.try_recv() {
            match event {
                StreamEvent::Token(token) => {
                    if app.stream_buffer.is_empty() {
                        app.tool_status = ToolStatus::Idle;
                    }
                    app.stream_buffer.push_str(&token);
                    app.waiting_response = true;
                }
                StreamEvent::Done => {
                    let content = app.stream_buffer.clone();
                    if !content.is_empty() {
                        app.add_message("agent", &content);
                    }
                    app.stream_buffer.clear();
                    app.waiting_response = false;
                    app.tool_status = ToolStatus::Idle;
                    app.set_status("Ready");
                }
                StreamEvent::Error(err) => {
                    let content = app.stream_buffer.clone();
                    if !content.is_empty() {
                        app.add_message("agent", &content);
                    }
                    app.stream_buffer.clear();
                    app.waiting_response = false;
                    app.tool_status = ToolStatus::Idle;
                    app.set_status(&format!("Error: {}", err));
                }
            }
        }

        terminal.draw(|f| ui(f, app))?;

        let timeout = TICK_RATE
            .checked_sub(last_tick.elapsed())
            .unwrap_or(Duration::from_secs(0));

        if crossterm::event::poll(timeout)? {
            if let CEvent::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press {
                    if handle_key(key, app, api, &stream_tx) {
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

fn handle_key(
    key: KeyEvent,
    app: &mut App,
    _api: &ApiClient,
    stream_tx: &std::sync::mpsc::Sender<StreamEvent>,
) -> bool {
    if key.code == KeyCode::Char('q') && app.input_mode == InputMode::Normal {
        return true;
    }
    if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
        return true;
    }

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
                    app.tool_status = ToolStatus::Idle;
                    app.set_status("Thinking...");

                    if app.connected {
                        let tx = stream_tx.clone();
                        let api = ApiClient::new("http://127.0.0.1:8000");
                        api.send_message_stream(input, tx);
                    } else {
                        app.add_message("agent", "Backend is offline. Start it with `python api.py`");
                        app.waiting_response = false;
                        app.set_status("Backend offline");
                    }
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

// ── Theme helpers ────────────────────────────────────────────────────

fn panel<'a>(theme: &'a Theme, title: &str) -> Block<'a> {
    Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(theme.style_border())
        .title(Span::styled(format!(" {} ", title), theme.style_muted()))
}

fn panel_accent<'a>(_theme: &'a Theme, title: &str, style: Style) -> Block<'a> {
    Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(style)
        .title(Span::styled(format!(" {} ", title), style.add_modifier(Modifier::BOLD)))
}

// ── UI Rendering ─────────────────────────────────────────────────────

fn ui(f: &mut ratatui::Frame, app: &App) {
    let theme = Theme::default();
    let size = f.area();

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // header
            Constraint::Min(0),    // body
            Constraint::Length(3), // footer
        ])
        .split(size);

    render_header(f, app, &theme, chunks[0]);

    match app.tab {
        Tab::Chat => render_chat(f, app, &theme, chunks[1]),
        Tab::Tools => render_tools(f, app, &theme, chunks[1]),
        Tab::History => render_history(f, app, &theme, chunks[1]),
        Tab::Config => render_config(f, app, &theme, chunks[1]),
    }

    render_footer(f, app, &theme, chunks[2]);
}

fn render_header(f: &mut ratatui::Frame, app: &App, theme: &Theme, area: Rect) {
    let spin = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"][app.typing_spinner as usize];

    let status = if !app.connected {
        Span::styled(" \u{26A0} OFFLINE ", Style::default().fg(theme.bg_base).bg(theme.accent_error))
    } else if app.waiting_response {
        Span::styled(format!(" {} ", spin), Style::default().fg(theme.bg_base).bg(theme.text_secondary))
    } else {
        Span::styled(" \u{25CF} ", Style::default().fg(theme.accent_success))
    };

    let title = Span::styled(" c-db ", Style::default().fg(theme.bg_base).bg(theme.text_primary).add_modifier(Modifier::BOLD));
    let info = Span::styled(format!(" {} tools ", app.tools.len()), theme.style_muted());
    let toast = if !app.status_msg.is_empty() {
        Span::styled(format!(" \u{00B7} {} ", app.status_msg), theme.style_secondary())
    } else {
        Span::raw("")
    };

    let line = Line::from(vec![title, status, info, toast]);
    f.render_widget(
        Paragraph::new(line).block(Block::default().borders(Borders::ALL).border_type(BorderType::Rounded).border_style(theme.style_border())),
        area,
    );
}

fn render_chat(f: &mut ratatui::Frame, app: &App, theme: &Theme, area: Rect) {
    // If no messages and welcome is showing, render welcome card
    if app.show_welcome && app.messages.is_empty() {
        render_welcome(f, app, theme, area);
        return;
    }

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(0),
            Constraint::Length(3),
        ])
        .split(area);

    // Messages
    let msg_area = chunks[0];
    let msg_h = msg_area.height.saturating_sub(2) as usize;
    let start = app.messages.len().saturating_sub(msg_h + app.scroll);

    let mut lines: Vec<Line> = Vec::new();

    if app.messages.is_empty() {
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled("  No messages yet. Press i to start typing.", theme.style_muted())));
    } else {
        for msg in app.messages.iter().skip(start).take(msg_h) {
            let prefix = if msg.role == "user" { "\u{25B8} " } else { "" };
            let msg_lines = markdown::render_message(theme, &msg.content, msg.role == "user");
            for ml in msg_lines {
                let mut spans = vec![Span::styled(prefix, theme.style_muted())];
                spans.extend(ml.spans.into_iter());
                lines.push(Line::from(spans));
            }
            lines.push(Line::from("")); // spacing between messages
        }
    }

    // If streaming, show the buffer inline
    if app.waiting_response && !app.stream_buffer.is_empty() {
        let stream_lines = markdown::render_message(theme, &app.stream_buffer, false);
        for sl in stream_lines {
            let mut spans = vec![Span::styled("\u{25B8} ", theme.style_muted())];
            spans.extend(sl.spans.into_iter());
            lines.push(Line::from(spans));
        }
    }

    // Tool call status
    match &app.tool_status {
        ToolStatus::Calling(name) => {
            let spin = ["\u{25D4}", "\u{25D1}", "\u{25D5}", "\u{25D7}"][(app.typing_spinner % 4) as usize];
            lines.push(Line::from(vec![
                Span::styled(format!(" {} ", spin), theme.style_tool()),
                Span::styled(format!("Calling {}...", name), theme.style_muted()),
            ]));
        }
        ToolStatus::Done(name) => {
            lines.push(Line::from(vec![
                Span::styled(" \u{2713} ", theme.style_success()),
                Span::styled(format!("{} completed", name), theme.style_muted()),
            ]));
        }
        ToolStatus::Idle => {}
    }

    // Thinking indicator
    if app.waiting_response && app.stream_buffer.is_empty() {
        let dots = match app.typing_spinner % 4 {
            0 => "   ",
            1 => ".  ",
            2 => ".. ",
            _ => "...",
        };
        lines.push(Line::from(Span::styled(
            format!("  Thinking{}", dots),
            theme.style_muted(),
        )));
    }

    f.render_widget(
        Paragraph::new(lines).block(panel(theme, " Chat ")),
        msg_area,
    );

    // Input bar
    let input_display = match app.input_mode {
        InputMode::Editing => {
            if app.waiting_response {
                " Waiting for response...".to_string()
            } else {
                format!(" {}|", app.input)
            }
        }
        InputMode::Normal => " Press i to type, Enter to send".to_string(),
    };

    let input_style = if app.input_mode == InputMode::Editing && !app.waiting_response {
        theme.style_highlight()
    } else {
        theme.style_muted()
    };

    f.render_widget(
        Paragraph::new(input_display).style(input_style).block(panel(theme, " Input ")),
        chunks[1],
    );
}

fn render_welcome(f: &mut ratatui::Frame, app: &App, theme: &Theme, area: Rect) {

    let lines = vec![
        Line::from(""),
        Line::from(Span::styled("  c-db Agent", Style::default().fg(theme.text_primary).add_modifier(Modifier::BOLD))),
        Line::from(""),
        Line::from(Span::styled("  \u{25C9}  AI assistant with tool access", theme.style_secondary())),
        Line::from(Span::styled("  \u{25C9}  Math, databases, email, weather", theme.style_secondary())),
        Line::from(Span::styled("  \u{25C9}  Auto-discovery of tools", theme.style_secondary())),
        Line::from(""),
        Line::from(vec![
            Span::styled("  Tools loaded: ", theme.style_muted()),
            Span::styled(format!("{}", app.tools.len()), theme.style_primary()),
        ]),
        Line::from(vec![
            Span::styled("  Status: ", theme.style_muted()),
            if app.connected {
                Span::styled("Connected", theme.style_success())
            } else {
                Span::styled("Offline", theme.style_error())
            },
        ]),
        Line::from(""),
        Line::from(Span::styled("  \u{2500}\u{2500}\u{2500} Quick Start \u{2500}\u{2500}\u{2500}", theme.style_muted())),
        Line::from(Span::styled("  i     Start typing", theme.style_muted())),
        Line::from(Span::styled("  Enter Send message", theme.style_muted())),
        Line::from(Span::styled("  F1-4  Switch tabs", theme.style_muted())),
        Line::from(Span::styled("  q     Quit", theme.style_muted())),
        Line::from(""),
        Line::from(Span::styled("  Try: calculate 15 * 37", theme.style_secondary())),
        Line::from(Span::styled("  Try: what's the weather in Tokyo?", theme.style_secondary())),
        Line::from(Span::styled("  Try: draft an application for Acme Corp", theme.style_secondary())),
    ];

    f.render_widget(
        Paragraph::new(lines).block(panel_accent(theme, " \u{2728} Welcome ", theme.style_primary())),
        area,
    );
}

fn render_tools(f: &mut ratatui::Frame, app: &App, theme: &Theme, area: Rect) {
    let items: Vec<ListItem> = if app.tools.is_empty() {
        vec![ListItem::new(Line::from(Span::styled(
            "  No tools loaded.",
            theme.style_muted(),
        )))]
    } else {
        app.tools.iter().map(|t| {
            ListItem::new(vec![
                Line::from(vec![
                    Span::styled("  \u{25C6} ", theme.style_tool()),
                    Span::styled(&t.name, theme.style_primary().add_modifier(Modifier::BOLD)),
                ]),
                Line::from(vec![
                    Span::styled("    ", theme.style_muted()),
                    Span::styled(&t.description, theme.style_secondary()),
                ]),
            ])
        }).collect()
    };

    f.render_widget(
        List::new(items).block(panel_accent(theme, " Tools ", theme.style_tool())),
        area,
    );
}

fn render_history(f: &mut ratatui::Frame, app: &App, theme: &Theme, area: Rect) {
    let h = area.height.saturating_sub(2) as usize;
    let start = app.messages.len().saturating_sub(h + app.scroll);

    let lines: Vec<Line> = if app.messages.is_empty() {
        vec![
            Line::from(Span::styled("  No conversation history yet.", theme.style_muted())),
        ]
    } else {
        app.messages
            .iter()
            .enumerate()
            .skip(start)
            .take(h)
            .map(|(i, m)| {
                let role_tag = if m.role == "user" { " you " } else { " agt " };
                let role_style = if m.role == "user" { theme.style_user() } else { theme.style_assistant() };
                Line::from(vec![
                    Span::styled(format!("#{:02}", i + 1), theme.style_muted()),
                    Span::styled(format!("[{}]", role_tag), role_style),
                    Span::styled(" ", theme.style_muted()),
                    Span::styled(
                        if m.content.len() > 60 { format!("{}...", &m.content[..57]) } else { m.content.clone() },
                        theme.style_secondary(),
                    ),
                ])
            })
            .collect()
    };

    let hint = if app.scroll > 0 { " (scrolled)" } else { "" };
    f.render_widget(
        Paragraph::new(lines).block(panel_accent(theme, &format!(" History{}", hint), theme.style_secondary())),
        area,
    );
}

fn render_config(f: &mut ratatui::Frame, _app: &App, theme: &Theme, area: Rect) {
    let lines = vec![
        Line::from(""),
        Line::from(vec![
            Span::styled("  Backend:  ", theme.style_muted()),
            Span::styled("http://127.0.0.1:8000", theme.style_primary()),
        ]),
        Line::from(vec![
            Span::styled("  Model:    ", theme.style_muted()),
            Span::styled("deepseek/deepseek-v4-flash", theme.style_secondary()),
        ]),
        Line::from(""),
        Line::from(Span::styled("  \u{2500}\u{2500}\u{2500} Quick Start \u{2500}\u{2500}\u{2500}", theme.style_muted())),
        Line::from(Span::styled("  python api.py           Start backend", theme.style_muted())),
        Line::from(Span::styled("  cargo run --release     Start TUI", theme.style_muted())),
        Line::from(Span::styled("  tools/weather.py        Add a new tool", theme.style_muted())),
        Line::from(""),
        Line::from(Span::styled("  \u{2500}\u{2500}\u{2500} Keys \u{2500}\u{2500}\u{2500}", theme.style_muted())),
        Line::from(Span::styled("  i / Enter    Type and send messages", theme.style_muted())),
        Line::from(Span::styled("  F1 Chat  F2 Tools  F3 History  F4 Config", theme.style_muted())),
        Line::from(Span::styled("  Tab          Cycle tabs", theme.style_muted())),
        Line::from(Span::styled("  q / Ctrl+C   Quit", theme.style_muted())),
    ];

    f.render_widget(
        Paragraph::new(lines).block(panel_accent(theme, " Config ", theme.style_user())),
        area,
    );
}

fn render_footer(f: &mut ratatui::Frame, app: &App, theme: &Theme, area: Rect) {
    let help = match app.input_mode {
        InputMode::Normal => " i: type  |  q: quit  |  Tab: switch tab  |  \u{2191}\u{2193}: scroll",
        InputMode::Editing => " Enter: send  |  Esc: cancel",
    };

    f.render_widget(
        Paragraph::new(Line::from(Span::styled(help, theme.style_muted()))).block(
            Block::default().borders(Borders::ALL).border_type(BorderType::Rounded).border_style(theme.style_border())
        ),
        area,
    );
}
