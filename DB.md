Skema referensi intent/entity untuk SQLite. Backend membuat tabel ini otomatis
saat startup melalui `SQLiteChatStore.initialize()` dan melakukan seed dari
file SQL/JSON di root repository.

```sql
CREATE TABLE intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_code TEXT NOT NULL UNIQUE,
    intent_name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE languages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lang_code TEXT NOT NULL UNIQUE,
    lang_name TEXT NOT NULL
);

CREATE TABLE keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_code TEXT NOT NULL,
    lang_code TEXT NOT NULL,
    keyword TEXT NOT NULL,
    normalized_keyword TEXT,
    formality_level TEXT,
    weight INTEGER DEFAULT 1,
    notes TEXT,
    FOREIGN KEY (intent_code) REFERENCES intents(intent_code),
    FOREIGN KEY (lang_code) REFERENCES languages(lang_code),
    UNIQUE (intent_code, lang_code, keyword)
);

CREATE TABLE entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_code TEXT NOT NULL UNIQUE,
    entity_name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE entity_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_code TEXT NOT NULL,
    lang_code TEXT NOT NULL,
    keyword TEXT NOT NULL,
    normalized_keyword TEXT,
    notes TEXT,
    FOREIGN KEY (entity_code) REFERENCES entities(entity_code),
    FOREIGN KEY (lang_code) REFERENCES languages(lang_code),
    UNIQUE (entity_code, lang_code, keyword)
);

CREATE TABLE sample_utterances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_code TEXT NOT NULL,
    lang_code TEXT NOT NULL,
    utterance TEXT NOT NULL,
    formality_level TEXT,
    expected_entities TEXT,
    notes TEXT,
    FOREIGN KEY (intent_code) REFERENCES intents(intent_code),
    FOREIGN KEY (lang_code) REFERENCES languages(lang_code),
    UNIQUE (intent_code, lang_code, utterance)
);

CREATE TABLE normalization_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lang_code TEXT NOT NULL,
    source_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (lang_code) REFERENCES languages(lang_code),
    UNIQUE (lang_code, source_text)
);

CREATE TABLE intent_mappings (
    intent_code TEXT PRIMARY KEY,
    description TEXT,
    required_slots TEXT NOT NULL DEFAULT '[]',
    optional_slots TEXT NOT NULL DEFAULT '[]',
    next_action TEXT,
    FOREIGN KEY (intent_code) REFERENCES intents(intent_code)
);
```
