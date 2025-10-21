**Features:**
- Imports vocabulary cards from your JPDB decks using your API key
- Saves your API key and preferences for future use
- Lists all your JPDB decks for selection
- Creates cards with spelling, reading, and meanings
- Works with any Anki note type (defaults to Basic)

**Installation:**
1. Open Anki and go to Tools → Add-ons → View Files
2. Create a new folder (e.g., "jpdb_importer")
3. Save the code as `__init__.py` in that folder
4. Restart Anki

**Usage:**
1. Go to Tools → "Import from JPDB"
2. Enter your JPDB API key (get it from jpdb.io settings)
3. Click "Refresh Decks" to load your JPDB decks
4. Select which deck to import from
5. Enter the Anki deck name to import into
6. Choose your note type
7. Click "Import Cards"

**Notes:**
- Your API key is stored locally and securely
- The addon imports spelling, reading (if different), and meanings
- Duplicate checking relies on Anki's built-in duplicate detection
- Cards are formatted as: "spelling (reading)" on front, "meanings" on back for Basic note type
