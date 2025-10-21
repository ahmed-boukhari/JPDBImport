import json
import os
from typing import List, Dict, Optional
import urllib.request
import urllib.error
from urllib.parse import urlencode

from aqt import mw, gui_hooks
from aqt.qt import QAction, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QMessageBox, QProgressDialog
from aqt.utils import showInfo, showWarning
from anki.notes import Note

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

class JPDBConfig:
    def __init__(self):
        self.api_key = ""
        self.deck_name = "JPDB Import"
        self.note_type = "Basic"
        self.load()
    
    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.api_key = data['api_key'] if 'api_key' in data else ''
                    self.deck_name = data['deck_name'] if 'deck_name' in data else 'JPDB Import'
                    self.note_type = data['note_type'] if 'note_type' in data else 'Basic'
            except:
                pass
    
    def save(self):
        data = {
            'api_key': self.api_key,
            'deck_name': self.deck_name,
            'note_type': self.note_type
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

class JPDBClient:
    BASE_URL = "https://jpdb.io/api/v1"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def _make_request(self, endpoint: str, data: Optional[Dict] = None) -> Dict:
        url = f"{self.BASE_URL}/{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Always send data as JSON, even if empty dict
        if data is None:
            data = {}
        req_data = json.dumps(data).encode('utf-8')
        request = urllib.request.Request(url, data=req_data, headers=headers, method='POST')
        
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_msg = e.read().decode('utf-8')
            raise Exception(f"HTTP {e.code}: {error_msg}")
        except urllib.error.URLError as e:
            raise Exception(f"Connection error: {str(e)}")
    
    def get_deck_list(self) -> List[Dict]:
        data = {
            'fields': ['id', 'name']
        }
        result = self._make_request('list-user-decks', data)
        return result['decks']
    
    def list_deck_vocabulary(self, deck_id: int) -> List[List[int]]:
        data = {
            'id': deck_id,
            'fetch_occurences': False
        }
        result = self._make_request('deck/list-vocabulary', data)
        return result['vocabulary']
    
    def lookup_vocabulary(self, vocab_list: List[List[int]]) -> List[Dict]:
        # Batch lookup - can send multiple vocab items at once
        data = {
            'list': vocab_list,
            'fields': ['spelling', 'reading', 'meanings']
        }
        result = self._make_request('lookup-vocabulary', data)
        # Returns vocabulary_info array
        return result['vocabulary_info'] if 'vocabulary_info' in result else []
    
    def get_deck_cards(self, deck_id: int, limit: int = 1000, batch_size: int = 100) -> List[Dict]:
        # First, get all vocabulary IDs from the deck
        vocab_list = self.list_deck_vocabulary(deck_id)
        
        # Limit if needed
        vocab_list = vocab_list[:limit]
        
        # Batch lookup vocabulary details
        cards = []
        for i in range(0, len(vocab_list), batch_size):
            batch = vocab_list[i:i + batch_size]
            
            # Filter out invalid entries
            valid_batch = []
            for vocab_ids in batch:
                if vocab_ids and len(vocab_ids) >= 1:
                    # Ensure we have [vid, sid] format
                    if len(vocab_ids) == 1:
                        valid_batch.append([vocab_ids[0], vocab_ids[0]])
                    else:
                        valid_batch.append([vocab_ids[0], vocab_ids[1]])
            
            if valid_batch:
                vocab_info_list = self.lookup_vocabulary(valid_batch)
                cards.extend(vocab_info_list)
        
        return cards

class JPDBImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = JPDBConfig()
        self.jpdb_client = None
        self.setWindowTitle("Import from JPDB")
        self.setMinimumWidth(500)
        self.setup_ui()
        self.load_settings()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # API Key
        api_layout = QHBoxLayout()
        api_layout.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter your JPDB API key")
        api_layout.addWidget(self.api_key_input)
        layout.addLayout(api_layout)
        
        # Deck selection
        deck_layout = QHBoxLayout()
        deck_layout.addWidget(QLabel("JPDB Deck:"))
        self.jpdb_deck_combo = QComboBox()
        deck_layout.addWidget(self.jpdb_deck_combo)
        self.refresh_btn = QPushButton("Refresh Decks")
        self.refresh_btn.clicked.connect(self.load_jpdb_decks)
        deck_layout.addWidget(self.refresh_btn)
        layout.addLayout(deck_layout)
        
        # Anki deck name
        anki_deck_layout = QHBoxLayout()
        anki_deck_layout.addWidget(QLabel("Anki Deck:"))
        self.anki_deck_input = QLineEdit()
        self.anki_deck_input.setPlaceholderText("Name of Anki deck to import into")
        anki_deck_layout.addWidget(self.anki_deck_input)
        layout.addLayout(anki_deck_layout)
        
        # Note type selection
        note_layout = QHBoxLayout()
        note_layout.addWidget(QLabel("Note Type:"))
        self.note_type_combo = QComboBox()
        self.load_note_types()
        note_layout.addWidget(self.note_type_combo)
        layout.addLayout(note_layout)
        
        # Status area
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(100)
        layout.addWidget(QLabel("Status:"))
        layout.addWidget(self.status_text)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.import_btn = QPushButton("Import Cards")
        self.import_btn.clicked.connect(self.import_cards)
        btn_layout.addWidget(self.import_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def load_settings(self):
        self.api_key_input.setText(self.config.api_key)
        self.anki_deck_input.setText(self.config.deck_name)
        idx = self.note_type_combo.findText(self.config.note_type)
        if idx >= 0:
            self.note_type_combo.setCurrentIndex(idx)
    
    def save_settings(self):
        self.config.api_key = self.api_key_input.text().strip()
        self.config.deck_name = self.anki_deck_input.text().strip()
        self.config.note_type = self.note_type_combo.currentText()
        self.config.save()
    
    def load_note_types(self):
        self.note_type_combo.clear()
        for notetype in mw.col.models.all_names_and_ids():
            self.note_type_combo.addItem(notetype.name)
    
    def load_jpdb_decks(self):
        api_key = self.api_key_input.text().strip()
        if not api_key:
            showWarning("Please enter your JPDB API key first.")
            return
        
        self.status_text.append("Loading decks from JPDB...")
        self.jpdb_deck_combo.clear()
        
        try:
            self.jpdb_client = JPDBClient(api_key)
            decks = self.jpdb_client.get_deck_list()
            
            for deck in decks:
                # deck is an array: [id, name]
                if not deck or len(deck) < 2:
                    continue
                deck_id = deck[0]
                deck_name = deck[1]
                self.jpdb_deck_combo.addItem(deck_name, deck_id)
            
            self.status_text.append(f"Loaded {len(decks)} decks.")
        except Exception as e:
            self.status_text.append(f"Error: {str(e)}")
            showWarning(f"Failed to load decks: {str(e)}")
    
    def import_cards(self):
        if self.jpdb_deck_combo.count() == 0:
            showWarning("Please load JPDB decks first.")
            return
        
        deck_name = self.anki_deck_input.text().strip()
        if not deck_name:
            showWarning("Please enter an Anki deck name.")
            return
        
        self.save_settings()
        
        deck_id = self.jpdb_deck_combo.currentData()
        note_type_name = self.note_type_combo.currentText()
        
        self.status_text.append(f"\nStarting import...")
        
        try:
            # Get cards from JPDB
            self.status_text.append("Fetching cards from JPDB...")
            cards = self.jpdb_client.get_deck_cards(deck_id)
            self.status_text.append(f"Retrieved {len(cards)} cards.")
            
            # Get or create deck
            deck_id_anki = mw.col.decks.id(deck_name)
            
            # Get note type
            note_type = mw.col.models.by_name(note_type_name)
            if not note_type:
                showWarning(f"Note type '{note_type_name}' not found.")
                return
            
            # Import cards
            imported = 0
            skipped = 0
            

            for card_data in cards:
                # card_data is now from lookup-vocabulary response
                # It should contain: spelling, reading, meanings as arrays
                if not card_data:
                    skipped += 1
                    continue
                
                # Get spelling and reading (arrays)
                spelling_arr = card_data[0] 
                reading_arr = card_data[1]
                meanings_arr = card_data[2]
                print(spelling_arr, reading_arr, meanings_arr)
                
                if not spelling_arr:
                    skipped += 1
                    continue
                
                spelling = spelling_arr[0] if spelling_arr else ''
                reading = reading_arr[0] if reading_arr else ''
                
                # Join meanings into a single string
                meaning_text = ', '.join([str(m) for m in meanings_arr]) if meanings_arr else ''
                
                # Create note
                note = Note(mw.col, note_type)
                note.model()['did'] = deck_id_anki
                
                # Fill fields based on note type
                fields = note.fields
                if len(fields) >= 2:
                    # For Basic and similar note types
                    front = f"{spelling}"
                    if reading and reading != spelling:
                        front += f" ({reading})"
                    note.fields[0] = front
                    note.fields[1] = meaning_text
                else:
                    note.fields[0] = spelling
                
                # Add note
                mw.col.addNote(note)
                imported += 1
            
            mw.col.reset()
            mw.reset()
            
            self.status_text.append(f"\nImport complete!")
            self.status_text.append(f"Imported: {imported} cards")
            self.status_text.append(f"Skipped: {skipped} cards")
            
            showInfo(f"Successfully imported {imported} cards to '{deck_name}'!")
            
        except Exception as e:
            self.status_text.append(f"\nError during import: {str(e)}")
            showWarning(f"Import failed: {str(e)}")

def show_import_dialog():
    dialog = JPDBImportDialog(mw)
    dialog.exec()

# Add menu item
action = QAction("Import from JPDB", mw)
action.triggered.connect(show_import_dialog)
mw.form.menuTools.addAction(action)
