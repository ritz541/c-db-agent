//! Simple markdown rendering for chat messages.
//!
//! Converts markdown text into ratatui `Line`s with appropriate styling.
//! Supports: bold, inline code, code blocks, blockquotes.

use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};

use crate::theme::Theme;

/// Render a message as styled lines.
pub fn render_message(theme: &Theme, text: &str, is_user: bool) -> Vec<Line<'static>> {
    let base_color = if is_user {
        theme.text_primary
    } else {
        theme.text_secondary
    };

    let mut lines = Vec::new();
    let mut in_code_block = false;

    for raw_line in text.lines() {
        if raw_line.trim().starts_with("```") {
            in_code_block = !in_code_block;
            if in_code_block {
                lines.push(Line::from(Span::styled(
                    "  ┌─ code ─────────────────────┐".to_string(),
                    theme.style_muted(),
                )));
            } else {
                lines.push(Line::from(Span::styled(
                    "  └────────────────────────────┘".to_string(),
                    theme.style_muted(),
                )));
            }
            continue;
        }

        if in_code_block {
            lines.push(Line::from(Span::styled(
                format!("  │ {}", raw_line),
                Style::default().fg(theme.text_primary).bg(theme.bg_code),
            )));
            continue;
        }

        if raw_line.trim_start().starts_with('>') {
            let content = raw_line.trim_start().trim_start_matches('>').trim();
            lines.push(Line::from(vec![
                Span::styled(" ▌ ".to_string(), theme.style_muted()),
                Span::styled(content.to_string(), theme.style_secondary()),
            ]));
            continue;
        }

        let spans = parse_inline(theme, raw_line, base_color);
        lines.push(Line::from(spans));
    }

    lines
}

fn parse_inline(theme: &Theme, text: &str, base_color: Color) -> Vec<Span<'static>> {
    let mut spans: Vec<Span<'static>> = Vec::new();
    let mut remaining = text;

    while !remaining.is_empty() {
        if let Some(start) = remaining.find("**") {
            if start > 0 {
                spans.push(Span::styled(remaining[..start].to_string(), Style::default().fg(base_color)));
            }
            let after = &remaining[start + 2..];
            if let Some(end) = after.find("**") {
                spans.push(Span::styled(
                    after[..end].to_string(),
                    Style::default().fg(base_color).add_modifier(Modifier::BOLD),
                ));
                remaining = &after[end + 2..];
            } else {
                spans.push(Span::styled(remaining[start..].to_string(), Style::default().fg(base_color)));
                break;
            }
        } else if let Some(start) = remaining.find('`') {
            if start > 0 {
                spans.push(Span::styled(remaining[..start].to_string(), Style::default().fg(base_color)));
            }
            let after = &remaining[start + 1..];
            if let Some(end) = after.find('`') {
                spans.push(Span::styled(
                    after[..end].to_string(),
                    Style::default().fg(theme.accent_tool).bg(theme.bg_code),
                ));
                remaining = &after[end + 1..];
            } else {
                spans.push(Span::styled(remaining[start..].to_string(), Style::default().fg(base_color)));
                break;
            }
        } else {
            spans.push(Span::styled(remaining.to_string(), Style::default().fg(base_color)));
            break;
        }
    }

    spans
}
