import feedparser
import os
import json
from datetime import datetime, timedelta

# Define file paths
FEEDS_FILE = "feeds.json"
ENTRIES_FILE = "entries.xml"
ARCHIVE_FILE = "archive.xml"

# Load Feed Config
def load_feed_config():
    if not os.path.exists(FEEDS_FILE):
        return []
    with open(FEEDS_FILE, 'r') as f:
        return json.load(f)

# The logic remains mostly the same, just handling the source better
def load_entries(file_path):
    if not os.path.exists(file_path): return {}
    entries = {}; item_data = None
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if line.startswith("<item>"): item_data = {}
            elif line.startswith("</item>") and item_data:
                if "guid" in item_data: entries[item_data["guid"]] = item_data
                item_data = None
            elif line.startswith("<guid>") and item_data is not None: item_data["guid"] = line[6:-7]
            elif line.startswith("<link>") and item_data is not None: item_data["link"] = line[6:-7]
            elif line.startswith("<title>") and item_data is not None: item_data["title"] = line[7:-8]
            elif line.startswith("<description>") and item_data is not None: item_data["description"] = line[13:-14]
            elif line.startswith("<published>") and item_data is not None: item_data["published"] = line[11:-12]
            elif line.startswith("<downloaded>") and item_data is not None: item_data["downloaded"] = line[12:-13]
            elif line.startswith("<source_name>") and item_data is not None: item_data["source_name"] = line[13:-14]
    return entries

def save_entries(file_path, entries):
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write("<rss><channel><title>Aggregated Feed</title>\n")
        for entry in entries.values():
            file.write("    <item>\n")
            file.write(f"      <guid>{entry.get('guid','')}</guid>\n")
            file.write(f"      <link>{entry.get('link','')}</link>\n")
            file.write(f"      <title>{entry.get('title','').replace('<','&lt;').replace('>','&gt;')}</title>\n")
            file.write(f"      <description>{entry.get('description','').replace('<','&lt;').replace('>','&gt;')}</description>\n")
            file.write(f"      <published>{entry.get('published','')}</published>\n")
            file.write(f"      <downloaded>{entry.get('downloaded','')}</downloaded>\n")
            file.write(f"      <source_name>{entry.get('source_name','Unknown')}</source_name>\n")
            file.write("    </item>\n")
        file.write("  </channel></rss>\n")

def process_feeds_logic():
    print("--- Fetching News ---")
    feed_config = load_feed_config()
    existing_entries = load_entries(ENTRIES_FILE)
    archive_entries = load_entries(ARCHIVE_FILE)
    new_entries = {}

    for feed_item in feed_config:
        print(f"Checking: {feed_item['name']}")
        try:
            d = feedparser.parse(feed_item['url'])
            for entry in d.entries:
                guid = entry.get('id', entry.get('link'))
                if guid not in existing_entries:
                    new_entries[guid] = {
                        "guid": guid,
                        "link": entry.get('link', ''),
                        "title": entry.get('title', 'No Title'),
                        "description": entry.get('summary', '')[:500], # Truncate massive descriptions
                        "published": entry.get('published', ''),
                        "downloaded": datetime.now().strftime("%Y-%m-%d"),
                        "source_name": feed_item['name'] # Bind to the source name
                    }
        except Exception as e:
            print(f"Error parsing {feed_item['name']}: {e}")

    # Cleanup Old
    for guid, entry in list(existing_entries.items()):
        d_date = datetime.strptime(entry["downloaded"], "%Y-%m-%d")
        if (datetime.now() - d_date) > timedelta(days=7):
            archive_entries[guid] = entry
            del existing_entries[guid]

    existing_entries.update(new_entries)
    save_entries(ENTRIES_FILE, existing_entries)
    save_entries(ARCHIVE_FILE, archive_entries)
    print(f"Done. {len(new_entries)} new articles.")

if __name__ == "__main__":
    process_feeds_logic()