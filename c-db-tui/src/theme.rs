//! Theme system for c-db TUI.
//!
//! Black & white theme inspired by Grok Build's groknight.
//! Clean, high contrast, minimal.

use ratatui::style::{Color, Modifier, Style};

/// Predefined color constants for the black & white palette.
mod bw {
    use ratatui::style::Color;

    const fn rgb(r: u8, g: u8, b: u8) -> Color {
        Color::Rgb(r, g, b)
    }

    // ── Backgrounds ─────────────────────────────────────────────
    pub const BG: Color = rgb(10, 10, 10);      // near black
    pub const BG_STORM: Color = rgb(18, 18, 18); // slightly lighter
    pub const BG_HIGHLIGHT: Color = rgb(35, 35, 35);
    pub const BG_HOVER: Color = rgb(45, 45, 45);
    pub const BG_CODE: Color = rgb(22, 22, 22);

    // ── Foreground / text ───────────────────────────────────────
    pub const FG: Color = rgb(230, 230, 230);    // near white
    pub const FG_DIM: Color = rgb(180, 180, 180);
    pub const FG_MUTED: Color = rgb(120, 120, 120);
    pub const FG_GUTTER: Color = rgb(65, 65, 65);

    // ── Accents (subtle grays) ──────────────────────────────────
    pub const CYAN: Color = rgb(180, 220, 255);   // subtle blue-white
    pub const GREEN: Color = rgb(180, 230, 200);  // subtle green-white
    pub const AMBER: Color = rgb(240, 220, 180);  // subtle warm
    pub const RED: Color = rgb(255, 160, 160);    // subtle red
    pub const PURPLE: Color = rgb(210, 190, 240); // subtle purple
}

/// Complete theme definition.
///
/// All rendering colors in one struct for easy theming.
/// Default is black & white (Grok Build inspired).
pub struct Theme {
    // Backgrounds
    pub bg_base: Color,
    pub bg_light: Color,
    pub bg_highlight: Color,
    pub bg_hover: Color,
    pub bg_code: Color,

    // Text
    pub text_primary: Color,
    pub text_secondary: Color,
    pub text_muted: Color,
    pub text_gutter: Color,

    // Message roles
    pub accent_user: Color,
    pub accent_assistant: Color,
    pub accent_tool: Color,
    pub accent_system: Color,
    pub accent_error: Color,
    pub accent_success: Color,

    // UI chrome
    pub border: Color,
    pub border_focused: Color,
    pub scrollbar_bg: Color,
    pub scrollbar_fg: Color,
    pub selection_bg: Color,
}

impl Theme {
    /// Black & white default theme (inspired by Grok Build groknight).
    pub fn default() -> Self {
        Self {
            bg_base: bw::BG,
            bg_light: bw::BG_STORM,
            bg_highlight: bw::BG_HIGHLIGHT,
            bg_hover: bw::BG_HOVER,
            bg_code: bw::BG_CODE,

            text_primary: bw::FG,
            text_secondary: bw::FG_DIM,
            text_muted: bw::FG_MUTED,
            text_gutter: bw::FG_GUTTER,

            accent_user: bw::CYAN,
            accent_assistant: bw::GREEN,
            accent_tool: bw::PURPLE,
            accent_system: bw::FG_DIM,
            accent_error: bw::RED,
            accent_success: bw::GREEN,

            border: Color::Rgb(55, 55, 55),
            border_focused: Color::Rgb(120, 120, 120),
            scrollbar_bg: bw::BG_STORM,
            scrollbar_fg: bw::BG_HIGHLIGHT,
            selection_bg: bw::BG_HOVER,
        }
    }

    // ── Style helpers ───────────────────────────────────────────

    pub fn style_border(&self) -> Style {
        Style::default().fg(self.border)
    }

    pub fn style_border_focused(&self) -> Style {
        Style::default().fg(self.border_focused)
    }

    pub fn style_primary(&self) -> Style {
        Style::default().fg(self.text_primary)
    }

    pub fn style_secondary(&self) -> Style {
        Style::default().fg(self.text_secondary)
    }

    pub fn style_muted(&self) -> Style {
        Style::default().fg(self.text_muted)
    }

    pub fn style_user(&self) -> Style {
        Style::default().fg(self.accent_user).add_modifier(Modifier::BOLD)
    }

    pub fn style_assistant(&self) -> Style {
        Style::default().fg(self.accent_assistant).add_modifier(Modifier::BOLD)
    }

    pub fn style_tool(&self) -> Style {
        Style::default().fg(self.accent_tool)
    }

    pub fn style_error(&self) -> Style {
        Style::default().fg(self.accent_error).add_modifier(Modifier::BOLD)
    }

    pub fn style_success(&self) -> Style {
        Style::default().fg(self.accent_success)
    }

    pub fn style_highlight(&self) -> Style {
        Style::default().fg(self.text_primary).bg(self.bg_highlight)
    }
}
