# Ticket PDF assets

Place logo images here to show on generated tickets:

- **ticket_header_logo.png** – shown at the top left of the ticket (max height 36 pt). Use your FlySunbird logo (e.g. wing + “flySunBird” + tagline).
- **ticket_footer_logo.png** – optional; shown above the footer text (max height 24 pt).

If these files are missing, tickets still generate without logos. You can also set paths in `.env`:

- `TICKET_HEADER_LOGO_PATH` – absolute or project-relative path to header logo
- `TICKET_FOOTER_LOGO_PATH` – absolute or project-relative path to footer logo

Supported image formats: PNG, JPEG (ReportLab ImageReader).
