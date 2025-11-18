# Calendar Skill

## Overview
This skill creates, edits, and deletes Google Calendar events using the Google Calendar API v3. It handles event management for individual users authenticated via OAuth 2.0.

## What It Does
When invoked with a command like `calendar.create_event`, the skill calls `google_calendar.events.insert()` to add an event with a specific start_time (ISO 8601 format), end_time, title, and optional location and description fields. When invoked with `calendar.delete_event(event_id)`, it removes the specified event permanently using `google_calendar.events.delete()`.

## How to Use It
```bash
# Create an event
curl -X POST http://localhost:8080/calendar/create_event \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"title": "Team Standup", "start_time": "2024-03-15T10:00:00Z", "end_time": "2024-03-15T10:30:00Z", "location": "Zoom Room 1"}'

# Delete an event
curl -X DELETE http://localhost:8080/calendar/delete_event/event_abc123 \
  -H "Authorization: Bearer $API_KEY"
```

## Capabilities
| Command | Action | Required Fields | Optional Fields |
|---------|--------|-----------------|-----------------|
| `create_event` | Inserts a new event into the user's primary calendar | title, start_time (ISO 8601), end_time (ISO 8601) | location, description, color_id, attendees[] |
| `delete_event` | Permanently removes an event by its ID | event_id | - |
| `list_events` | Returns events within a specified time range | start_time, end_time (ISO 8601) | max_results, calendar_id |
| `update_event` | Modifies an existing event's fields | event_id, one or more of: title, start_time, end_time, location | description, attendees[], color_id |

## Limitations
- Requires Google Cloud Platform project with Calendar API enabled and OAuth 2.0 credentials configured
- Rate limited to 500 requests per 100 seconds per user (Google API quota)
- Time zones are handled in UTC; client-side conversion is the caller's responsibility
- Cannot create recurring events — each occurrence must be created individually

## Notes
Always validate event time ranges before calling `create_event`: start_time must be strictly before end_time, and both must be valid ISO 8601 timestamps. The skill returns HTTP status codes per REST conventions (201 for creation, 404 for missing events, 403 for unauthorized access). Check the API response body for detailed error messages in all failure cases.
