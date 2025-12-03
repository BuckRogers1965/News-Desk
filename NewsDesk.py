import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import json
import os
import sys
import argparse
import time
import webbrowser
import re
from datetime import datetime, timedelta
import google.generativeai as genai

# Import the fetcher logic
import GetNews

# --- CONFIG ---
FEEDS_FILE = "feeds.json"
ENTRIES_FILE = "entries.xml"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ==============================================================================
# CORE LOGIC
# ==============================================================================

def auto_update_feeds():
    should_update = False
    if not os.path.exists(ENTRIES_FILE):
        should_update = True
    else:
        mtime = os.path.getmtime(ENTRIES_FILE)
        age_seconds = time.time() - mtime
        if age_seconds > 7200: # 2 Hours
            print(f"Data is {int(age_seconds/60)} mins old. Auto-updating...")
            should_update = True
    
    if should_update:
        GetNews.process_feeds_logic()

def load_feed_map():
    feed_map = {}
    if os.path.exists(FEEDS_FILE):
        with open(FEEDS_FILE, 'r') as f:
            data = json.load(f)
            for item in data:
                feed_map[item['name']] = item.get('topics', [])
    return feed_map

def filter_entries(days, topic, search_term):
    entries = GetNews.load_entries(ENTRIES_FILE)
    feed_map = load_feed_map()
    
    cutoff_date = datetime.now() - timedelta(days=days)
    entry_list = sorted(entries.values(), key=lambda x: x.get('downloaded', ''), reverse=True)
    
    filtered_results = []
    
    for data in entry_list:
        try:
            d_str = data.get('downloaded', '')
            d_obj = datetime.strptime(d_str, "%Y-%m-%d")
            if d_obj < cutoff_date.replace(hour=0, minute=0, second=0):
                continue
        except: continue 

        if topic and topic != "All":
            source = data.get('source_name', '')
            source_topics = feed_map.get(source, [])
            if topic not in source_topics:
                continue
        
        if search_term:
            t = data.get('title', '').lower()
            d = data.get('description', '').lower()
            s = search_term.lower()
            if s not in t and s not in d:
                continue
        
        filtered_results.append(data)
        
    return filtered_results

def run_ai_analysis(articles, topic_constraint=None, search_constraint=None):
    if not GEMINI_API_KEY:
        return "Error: GEMINI_API_KEY not set."
    
    selected_text = ""
    source_links = []
    
    for item in articles:
        selected_text += f"Title: {item['title']}\nSource: {item.get('source_name')}\nContent: {item['description']}\n\n"
        clean_title = item['title'].replace('[', '(').replace(']', ')')
        link_str = f"* [{clean_title}]({item.get('link')})"
        source_links.append(link_str)

    genai.configure(api_key=GEMINI_API_KEY)
    
    context_instruction = ""
    if topic_constraint and topic_constraint != "All":
        context_instruction += f"\nSTRICT CONSTRAINT: The user is only interested in the topic: '{topic_constraint}'. DISCARD and IGNORE any information that does not directly pertain to this topic."
    
    if search_constraint:
        context_instruction += f"\nSTRICT CONSTRAINT: The user is only interested in the keyword: '{search_constraint}'. Focus EXCLUSIVELY on insights related to this term. IGNORE unrelated context."

    model = genai.GenerativeModel('gemini-flash-latest') 

    prompt = (
        "You are an executive news analyst. Create a structured briefing from these articles."
        f"{context_instruction}\n"
        "Use Markdown formatting. Use ## for Headlines, ** for bold importance, and * for bullet points. "
        "Group by theme.\n\n"
        f"{selected_text}"
    )
    
    response = model.generate_content(prompt)
    final_report = response.text + "\n\n## Sources Reviewed\n" + "\n".join(source_links)
    return final_report

# ==============================================================================
# GUI CLASSES
# ==============================================================================

class FeedManagerDialog(tk.Toplevel):
    def __init__(self, parent, callback_refresh):
        super().__init__(parent)
        self.title("Manage Feeds")
        self.geometry("500x450")
        self.callback_refresh = callback_refresh
        self.feeds = []
        
        self.listbox = tk.Listbox(self, height=10)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        frame = ttk.Frame(self)
        frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(frame, text="Name:").grid(row=0, column=0, sticky="w")
        self.entry_name = ttk.Entry(frame)
        self.entry_name.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Label(frame, text="URL:").grid(row=1, column=0, sticky="w")
        self.entry_url = ttk.Entry(frame)
        self.entry_url.grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Label(frame, text="Topics (csv):").grid(row=2, column=0, sticky="w")
        self.entry_topics = ttk.Entry(frame)
        self.entry_topics.grid(row=2, column=1, sticky="ew", padx=5)
        frame.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Add", command=self.add_feed).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Delete", command=self.delete_feed).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        self.load_feeds()

    def load_feeds(self):
        self.listbox.delete(0, tk.END)
        if os.path.exists(FEEDS_FILE):
            with open(FEEDS_FILE, 'r') as f:
                self.feeds = json.load(f)
                for feed in self.feeds:
                    self.listbox.insert(tk.END, f"{feed['name']} - {', '.join(feed['topics'])}")

    def add_feed(self):
        name = self.entry_name.get()
        url = self.entry_url.get()
        topics = [t.strip() for t in self.entry_topics.get().split(",") if t.strip()]
        if name and url:
            new_feed = {"name": name, "url": url, "topics": topics, "date_added": datetime.now().strftime("%Y-%m-%d")}
            self.feeds.append(new_feed)
            self.save_feeds()
            self.load_feeds()
            self.callback_refresh() 
            self.entry_name.delete(0, tk.END); self.entry_url.delete(0, tk.END); self.entry_topics.delete(0, tk.END)

    def delete_feed(self):
        sel = self.listbox.curselection()
        if sel:
            del self.feeds[sel[0]]
            self.save_feeds()
            self.load_feeds()
            self.callback_refresh()

    def save_feeds(self):
        with open(FEEDS_FILE, 'w') as f: json.dump(self.feeds, f, indent=4)

class NewsApp:
    def __init__(self, root, default_days=1, default_topic="All", default_search=""):
        self.root = root
        self.root.title("Python News Desk v3.2")
        self.root.geometry("1100x850")
        self.check_vars = {} 
        
        self.init_days = default_days
        self.init_topic = default_topic
        self.init_search = default_search
        
        self._setup_ui()
        self._load_config()
        
        if self.init_search: self.entry_search.insert(0, self.init_search)
        self.spin_days.set(self.init_days)
        
        # We need to wait a ms for the window to draw so we can get the width for the cards
        self.root.after(100, self.apply_filters)

    def _setup_ui(self):
        toolbar = ttk.Frame(self.root, padding=5)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="🔄 Fetch New Articles", command=self.fetch_news).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="⚙️ Manage Feeds", command=self.open_manager).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="❓ Help", command=self.show_help).pack(side=tk.LEFT, padx=5)
        
        filter_bar = ttk.LabelFrame(self.root, text="Filters & Search", padding=5)
        filter_bar.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(filter_bar, text="Age (Days):").pack(side=tk.LEFT, padx=5)
        self.spin_days = ttk.Spinbox(filter_bar, from_=1, to=30, width=5, command=self.apply_filters)
        self.spin_days.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(filter_bar, text="Topic:").pack(side=tk.LEFT, padx=5)
        self.combo_topic = ttk.Combobox(filter_bar, state="readonly", width=15)
        self.combo_topic.pack(side=tk.LEFT, padx=5)
        self.combo_topic.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())
        
        ttk.Label(filter_bar, text="Search:").pack(side=tk.LEFT, padx=(15, 5))
        self.entry_search = ttk.Entry(filter_bar, width=30)
        self.entry_search.pack(side=tk.LEFT, padx=5)
        self.entry_search.bind("<Return>", lambda e: self.apply_filters())

        # --- SCROLLABLE CONTAINER ---
        list_container = ttk.Frame(self.root)
        list_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.scrollbar = ttk.Scrollbar(list_container, orient="vertical")
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.news_list = tk.Canvas(list_container, bg="#f0f0f0", yscrollcommand=self.scrollbar.set)
        self.news_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.news_list.yview)
        
        self.news_frame = tk.Frame(self.news_list, bg="#f0f0f0")
        self.news_list.create_window((0, 0), window=self.news_frame, anchor="nw")
        
        def update_scrollregion(e):
            self.news_list.configure(scrollregion=self.news_list.bbox("all"))
        self.news_frame.bind("<Configure>", update_scrollregion)
        
        # Bind scroll to canvas
        def canvas_scroll_wheel(e):
            # SCROLL SPEED TUNING: Adjust the multiplier below (currently 30)
            if abs(e.delta) < 5:  # Linux/some systems use small deltas
                delta = -e.delta * 30
            else:  # Windows/Mac use larger deltas
                delta = int(-1*(e.delta/120)) * 10
            self.news_list.yview_scroll(delta, "units")
        def canvas_scroll_up(e):
            self.news_list.yview_scroll(-30, "units")  # SCROLL SPEED TUNING: Adjust this value
        def canvas_scroll_down(e):
            self.news_list.yview_scroll(30, "units")  # SCROLL SPEED TUNING: Adjust this value
        
        self.news_list.bind("<MouseWheel>", canvas_scroll_wheel)
        self.news_list.bind("<Button-4>", canvas_scroll_up)
        self.news_list.bind("<Button-5>", canvas_scroll_down)

        # --- ACTION BAR ---
        action_bar = ttk.Frame(self.root, padding=10)
        action_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
        ttk.Button(action_bar, text="Select All", command=lambda: self.set_all_checks(True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_bar, text="Select None", command=lambda: self.set_all_checks(False)).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_bar, text="Invert Selection", command=self.invert_checks).pack(side=tk.LEFT, padx=5)
        
        self.btn_summarize = ttk.Button(action_bar, text="🤖 Generate AI Briefing (Selected)", command=self.generate_summary_gui)
        self.btn_summarize.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=20, ipady=5)

    def _load_config(self):
        topics = set(["All"])
        feed_map = load_feed_map()
        for t_list in feed_map.values():
            for t in t_list: topics.add(t)
        
        sorted_topics = sorted(list(topics))
        self.combo_topic['values'] = sorted_topics
        
        if self.init_topic and self.init_topic in sorted_topics:
            self.combo_topic.set(self.init_topic)
        else:
            self.combo_topic.current(0)

    def open_manager(self): FeedManagerDialog(self.root, self._load_config)

    def show_toast(self, message, color="#333333"):
        toast = tk.Toplevel(self.root); toast.overrideredirect(True)
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 100
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 30
        toast.geometry(f"200x40+{x}+{y}"); toast.configure(bg=color)
        tk.Label(toast, text=message, bg=color, fg="white", font=("Arial", 10, "bold")).pack(expand=True, fill=tk.BOTH)
        self.root.after(1500, toast.destroy)

    def fetch_news(self):
        GetNews.process_feeds_logic()
        self.apply_filters()
        self.show_toast("Feeds Updated")

    def set_all_checks(self, state):
        for var in self.check_vars.values(): var.set(state)

    def invert_checks(self):
        for var in self.check_vars.values(): var.set(not var.get())

    def _bind_mousewheel_to_card(self, widget):
        def scroll_wheel(e):
            # SCROLL SPEED TUNING: Adjust the multipliers below (currently 30 and 10)
            if abs(e.delta) < 5:  # Linux/some systems use small deltas
                delta = -e.delta * 30
            else:  # Windows/Mac use larger deltas
                delta = int(-1*(e.delta/120)) * 10
            self.news_list.yview_scroll(delta, "units")
            return "break"
        def scroll_up(e):
            self.news_list.yview_scroll(-30, "units")  # SCROLL SPEED TUNING: Adjust this value
            return "break"
        def scroll_down(e):
            self.news_list.yview_scroll(30, "units")  # SCROLL SPEED TUNING: Adjust this value
            return "break"
        
        widget.bind("<MouseWheel>", scroll_wheel)
        widget.bind("<Button-4>", scroll_up)
        widget.bind("<Button-5>", scroll_down)
        for child in widget.winfo_children():
            self._bind_mousewheel_to_card(child)

    def apply_filters(self):
        for widget in self.news_frame.winfo_children():
            widget.destroy()
        self.check_vars = {}
        
        try: days = int(self.spin_days.get())
        except: days = 1
        
        filtered_data = filter_entries(days, self.combo_topic.get(), self.entry_search.get().strip())

        # Fixed card width
        card_width = 1050

        if not filtered_data:
            lbl = tk.Label(self.news_frame, text="No articles found.", font=("Arial", 12), bg="#f0f0f0", fg="#555")
            lbl.pack(pady=20)
        
        for data in filtered_data:
            self._render_article_card(data, card_width)
        
        # Force scrollregion update after adding all cards
        self.news_frame.update_idletasks()
        self.news_list.configure(scrollregion=self.news_list.bbox("all"))
        self.news_list.yview_moveto(0)

    def _render_article_card(self, data, width_px):
        guid = data.get('guid')
        
        # Card with fixed width
        card = tk.Frame(self.news_frame, bg="white", bd=1, relief="solid", width=width_px, height=100)
        card.pack(pady=5, padx=5)
        card.pack_propagate(False)
        
        # Header
        header = tk.Frame(card, bg="#e0e0e0", height=30)
        header.pack(fill=tk.X)
        
        var = tk.BooleanVar()
        self.check_vars[guid] = var
        chk = tk.Checkbutton(header, variable=var, bg="#e0e0e0", activebackground="#e0e0e0")
        chk.pack(side=tk.LEFT, padx=5)
        
        header_text = f"[{data.get('source_name', 'Unknown')}] {data.get('title', 'No Title')}"
        lbl_head = tk.Label(header, text=header_text, bg="#e0e0e0", fg="black", font=("Arial", 10, "bold"), wraplength=width_px-60, anchor="w", justify="left")
        lbl_head.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Body
        body = tk.Frame(card, bg="white")
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        lbl_desc = tk.Label(body, text=data.get('description', '')[:300]+"...", bg="white", fg="#333333", 
                           justify="left", wraplength=width_px-40, anchor="nw")
        lbl_desc.pack(anchor="nw", fill=tk.BOTH, expand=True)
        
        link = data.get('link', '')
        lbl_link = tk.Label(body, text="Read Full Article", fg="blue", bg="white", cursor="hand2", font=("Arial", 9, "underline"))
        lbl_link.pack(anchor="w", pady=(5,0))
        lbl_link.bind("<Button-1>", lambda e, url=link: webbrowser.open_new(url))

        # Bind scrollwheel to pass through to canvas
        self._bind_mousewheel_to_card(card)

    def show_help(self):
        manual = """# Python News Desk Manual\n\n## Auto-Update\nThe app automatically updates feeds if data is > 2 hours old on startup.\n\n## CLI Automation\nYou can generate reports without the GUI:\n`python FeedViewer.py --topic="Tech" --days=1 --output=report.md`"""
        SummaryWindow(self.root, manual)

    def generate_summary_gui(self):
        selected_entries = []
        all_entries = GetNews.load_entries(ENTRIES_FILE)
        
        count = 0
        for guid, var in self.check_vars.items():
            if var.get():
                item = all_entries.get(guid)
                if item: selected_entries.append(item)
                count += 1
        
        if count == 0:
            self.show_toast("No articles selected", "red")
            return

        try:
            self.root.config(cursor="watch"); self.root.update()
            report = run_ai_analysis(selected_entries, self.combo_topic.get(), self.entry_search.get().strip())
            self.root.config(cursor="")
            SummaryWindow(self.root, report)
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("AI Error", str(e))

class SummaryWindow(tk.Toplevel):
    def __init__(self, parent, markdown_text, title="AI Briefing"):
        super().__init__(parent); self.title(title); self.geometry("800x700")
        self.markdown_text = markdown_text
        
        toolbar = ttk.Frame(self); toolbar.pack(fill=tk.X, pady=5)
        ttk.Button(toolbar, text="Copy", command=self.copy_text).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Save", command=self.save_text).pack(side=tk.LEFT, padx=5)
        
        self.text_area = scrolledtext.ScrolledText(self, font=("Segoe UI", 11), wrap=tk.WORD, padx=20, pady=20)
        self.text_area.pack(fill=tk.BOTH, expand=True)
        self._config_tags()
        self.render_markdown(markdown_text)
        self.text_area.config(state=tk.DISABLED)

    def _config_tags(self):
        self.text_area.tag_config("h1", font=("Segoe UI", 18, "bold"), foreground="#2c3e50", spacing3=10)
        self.text_area.tag_config("h2", font=("Segoe UI", 14, "bold"), foreground="#2980b9", spacing3=5)
        self.text_area.tag_config("bold", font=("Segoe UI", 11, "bold"))
        self.text_area.tag_config("bullet", lmargin1=20, lmargin2=30)

    def render_markdown(self, text):
        lines = text.split('\n')
        for line in lines:
            tag = None; clean = line
            if line.startswith('## '): tag="h2"; clean=line[3:]
            elif line.startswith('# '): tag="h1"; clean=line[2:]
            elif line.startswith('* ') or line.startswith('- '): tag="bullet"
            idx = self.text_area.index(tk.INSERT)
            self.text_area.insert(tk.END, clean + "\n")
            if tag: self.text_area.tag_add(tag, idx, f"{idx} lineend")
            for m in re.finditer(r'\*\*(.*?)\*\*', clean):
                s = self.text_area.search(m.group(1), idx, stopindex=f"{idx} lineend")
                if s: self.text_area.tag_add("bold", s, f"{s}+{len(m.group(1))}c")

    def copy_text(self):
        self.clipboard_clear(); self.clipboard_append(self.markdown_text)

    def save_text(self):
        f = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if f: 
            with open(f, 'w', encoding='utf-8') as file: file.write(self.markdown_text)

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    if not os.path.exists(FEEDS_FILE):
        with open(FEEDS_FILE, 'w') as f: json.dump([], f)

    parser = argparse.ArgumentParser(description="Python News Desk")
    parser.add_argument("--topic", help="Filter by topic")
    parser.add_argument("--days", type=int, default=1, help="Age in days")
    parser.add_argument("--search", default="", help="Grep search term")
    parser.add_argument("--output", help="Save AI report to file (Headless Mode)")
    args = parser.parse_args()

    auto_update_feeds()

    if args.output:
        print(f"--- Headless Mode Started ---")
        articles = filter_entries(args.days, args.topic, args.search)
        print(f"Found {len(articles)} matching articles.")
        if len(articles) > 0:
            print("Sending to Gemini...")
            report = run_ai_analysis(articles, args.topic, args.search)
            with open(args.output, 'w', encoding='utf-8') as f: f.write(report)
            print(f"Report saved to: {args.output}")
        else:
            print("No articles found.")
    else:
        root = tk.Tk()
        try: style = ttk.Style(); style.theme_use('clam') 
        except: pass
        # PASS ARGS TO GUI
        app = NewsApp(root, default_days=args.days, default_topic=args.topic, default_search=args.search)
        root.mainloop()
