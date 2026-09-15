import re
import os

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Remove all ``` code blocks completely
    content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
    
    # 2. Remove buzzwords
    content = content.replace("Smart Mobility Platform", "Mobility Platform")
    content = content.replace("Smart strategy", "Optimized strategy")
    content = re.sub(r'\bSmart\b', '', content)
    content = re.sub(r'\bAI\b', '', content)
    content = re.sub(r'\bdigital\b', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\bartificial intelligence\b', '', content, flags=re.IGNORECASE)
    
    # 3. Remove HTML comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    
    # 5. Remove emoji/icon characters (basic matching for non-ascii non-latin)
    # A safer way to remove emojis is using a known regex or just the specified ones in the prompt.
    # Prompt listed: 🛡️, 📖, 🛞, 🎒, 🛠️, 📐, 🗄️, 🧩, 🔌, 🚀, 📦, 🔧, 📑, ➜
    emojis = ["🛡️", "📖", "🛞", "🎒", "🛠️", "📐", "🗄️", "🧩", "🔌", "🚀", "📦", "🔧", "📑", "➜", "⭐", "✅", "⚠️", "⚡", "🔒", "📈", "✨"]
    for e in emojis:
        content = content.replace(e, "")
    # General emoji regex if needed, but let's just stick to the prompt's examples and any others we see. Looking at the text, there are right arrows "→" which might be considered icons? The prompt said "➜" is an icon. Let's remove "→" too just in case, or leave it if it's just an arrow. Wait, "→" is used in "Palasa → Visakhapatnam". It's a standard unicode arrow. Let's not remove unless it's an emoji, but I'll remove it if it causes issues. Actually let's use the emoji library or just a regex for emojis.
    
    # 6. Remove all ** bold markers
    content = content.replace("**", "")
    
    # 7. Remove all * italic markers (standalone * used for emphasis)
    # Be careful not to remove * in lists if they exist, but rule 4 says replace - and * lists with numbers.
    
    # Let's process line by line for the rest
    lines = content.split('\n')
    new_lines = []
    
    list_counter = 1
    indent_counters = {}
    
    for line in lines:
        # Rule 8: Remove ## section heading markers (but keep #)
        if line.startswith('## '):
            line = line[3:]
        elif line.startswith('### '):
            line = line[4:]
        elif line.startswith('#### '):
            line = line[5:]
            
        # Rule 9: Remove // comment-style markers in prose
        line = re.sub(r'//\s*', '', line)
        
        # Rule 14: Remove *Note:* style markers
        line = re.sub(r'\*?Note:\*?\s*', '', line, flags=re.IGNORECASE)
        
        # Rule 4 & 7: Convert ALL bullet/dash list items into numbered lists
        # Match - or * lists, optionally indented
        list_match = re.match(r'^(\s*)([-*])\s+(.*)', line)
        if list_match:
            indent = list_match.group(1)
            marker = list_match.group(2)
            item_text = list_match.group(3)
            
            indent_level = len(indent)
            if indent_level == 0:
                line = f"{list_counter}. {item_text}"
                list_counter += 1
                indent_counters = {} # reset sub-counters
            else:
                if indent_level not in indent_counters:
                    indent_counters[indent_level] = 1
                line = f"{indent}{indent_counters[indent_level]}. {item_text}"
                indent_counters[indent_level] += 1
        else:
            # If it's not a list item, reset the top level counter if the line is not empty and not an indented line
            if line.strip() == '' or line.startswith(' '):
                pass
            else:
                # Is it an existing numbered list?
                num_match = re.match(r'^(\s*)\d+\.\s+.*', line)
                if not num_match:
                    list_counter = 1
                    indent_counters = {}
            
            # Remove standalone * (not part of a list we just processed)
            # This handles italics like *word*
            # regex to remove * but leave what's inside
            line = re.sub(r'\*(.*?)\*', r'\1', line)
            
        new_lines.append(line)
        
    # Clean up double spaces caused by replacement
    final_content = '\n'.join(new_lines)
    # Fix double spaces where "Smart" was removed
    final_content = final_content.replace('  ', ' ')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(final_content)

process_file(r'e:\TransPulse\docs\UPGRADES.md')
process_file(r'e:\TransPulse\docs\QUICK_REFERENCE.md')
