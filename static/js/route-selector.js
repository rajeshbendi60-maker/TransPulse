/**
 * TransPulse Searchable Route Selector Component
 * 
 * Replaces standard HTML select elements for routes with a modern, high-performance,
 * searchable dropdown with glassmorphism styling, caching, and score-based sorting.
 */

class TransPulseRouteSelector {
    constructor(selectElement) {
        if (!selectElement || selectElement.dataset.enhanced) return;
        this.selectElement = selectElement;
        this.selectElement.dataset.enhanced = "true";
        this.options = [];
        this.itemNodes = [];
        this.highlightedIndex = -1;
        this.isOpen = false;
        
        this.init();
    }
    
    init() {
        // Create custom UI elements
        this.container = document.createElement('div');
        this.container.className = 'tp-route-selector-container';
        
        this.trigger = document.createElement('div');
        this.trigger.className = 'tp-route-selector-trigger form-select bg-dark text-white border-secondary d-flex justify-content-between align-items-center';
        this.trigger.setAttribute('tabindex', '0');
        
        this.selectedLabel = document.createElement('span');
        this.selectedLabel.className = 'tp-route-selector-selected-label';
        this.selectedLabel.textContent = 'Select Route...';
        this.trigger.appendChild(this.selectedLabel);
        
        this.dropdown = document.createElement('div');
        this.dropdown.className = 'tp-route-selector-dropdown d-none';
        
        const searchWrapper = document.createElement('div');
        searchWrapper.className = 'px-1 py-1 mb-2';
        
        this.searchInput = document.createElement('input');
        this.searchInput.type = 'text';
        this.searchInput.className = 'form-control tp-route-selector-search bg-dark text-white border-secondary w-100';
        this.searchInput.placeholder = '🔍 Search Route...';
        this.searchInput.setAttribute('autocomplete', 'off');
        searchWrapper.appendChild(this.searchInput);
        this.dropdown.appendChild(searchWrapper);
        
        this.resultsList = document.createElement('div');
        this.resultsList.className = 'tp-route-selector-results-list';
        this.dropdown.appendChild(this.resultsList);
        
        this.container.appendChild(this.trigger);
        this.container.appendChild(this.dropdown);
        
        // Insert container right after select element, and hide select element
        this.selectElement.parentNode.insertBefore(this.container, this.selectElement.nextSibling);
        this.selectElement.style.display = 'none';
        
        // Load options
        this.rebuildOptions();
        
        // Listen to select mutation changes (for dynamic dropdown updates)
        this.observer = new MutationObserver(() => this.rebuildOptions());
        this.observer.observe(this.selectElement, { childList: true, subtree: true });
        
        // Intercept programmatic value assignments on original select
        this.hookSelectValueProperty();
        
        // Attach Event Listeners
        this.setupEvents();
    }
    
    hookSelectValueProperty() {
        const self = this;
        const descriptor = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
        if (descriptor && descriptor.set) {
            const originalSet = descriptor.set;
            const originalGet = descriptor.get;
            Object.defineProperty(this.selectElement, 'value', {
                get: function() {
                    return originalGet.call(this);
                },
                set: function(val) {
                    originalSet.call(this, val);
                    self.syncSelected();
                },
                configurable: true
            });
        }
    }
    
    rebuildOptions() {
        // Read options from selectElement, filtering out placeholder options
        const rawOpts = Array.from(this.selectElement.options);
        
        this.options = rawOpts
            .filter(opt => opt.value !== "")
            .map(opt => {
                const text = opt.text || '';
                const cleanText = text.replace(/[\u2192\u279c\u27aa\u279f]/g, '➜');
                
                let code = '';
                let origin = '';
                let destination = '';
                let name = '';
                
                // Formats: 
                // 1) "01004 — Nellore ➜ Tirupati" (standard option in bus_management after update)
                // 2) "01004 - Nellore ➜ Tirupati" (dynamic formatting in complaints)
                // 3) "01004" (code only)
                
                const splitDash = cleanText.split(/\s*[\u2014-]\s*/);
                if (splitDash.length >= 2) {
                    code = splitDash[0].trim();
                    name = splitDash.slice(1).join(' - ').trim();
                    const splitArrow = name.split(/\s*➜\s*/);
                    if (splitArrow.length === 2) {
                        origin = splitArrow[0].trim();
                        destination = splitArrow[1].trim();
                    } else {
                        origin = name;
                        destination = name;
                    }
                } else {
                    // Try to guess from text format or value
                    const match = cleanText.match(/^([A-Za-z0-9_-]+)(?:\s+)(.+)$/);
                    if (match) {
                        code = match[1].trim();
                        name = match[2].trim();
                        const splitArrow = name.split(/\s*➜\s*/);
                        if (splitArrow.length === 2) {
                            origin = splitArrow[0].trim();
                            destination = splitArrow[1].trim();
                        }
                    } else {
                        code = opt.value ? 'BUS-RT' : '';
                        name = cleanText;
                    }
                }
                
                return {
                    value: opt.value,
                    code: code || opt.value || 'BUS-RT',
                    name: name || cleanText,
                    origin: origin || name || cleanText,
                    destination: destination || name || cleanText,
                    originalText: text
                };
            });
            
        // Pre-render DOM nodes once
        this.resultsList.innerHTML = '';
        this.itemNodes = [];
        
        if (this.options.length === 0) {
            const noResults = document.createElement('div');
            noResults.className = 'tp-route-selector-no-results';
            noResults.textContent = 'No routes configured';
            this.resultsList.appendChild(noResults);
            this.syncSelected();
            return;
        }
        
        this.options.forEach((opt, index) => {
            const item = document.createElement('div');
            item.className = 'tp-route-selector-item';
            item.dataset.value = opt.value;
            item.dataset.index = index;
            
            const codeEl = document.createElement('div');
            codeEl.className = 'tp-route-selector-item-code';
            codeEl.innerHTML = `🚌 ${this.escapeHTML(opt.code)}`;
            
            const stopsEl = document.createElement('div');
            stopsEl.className = 'tp-route-selector-item-stops';
            stopsEl.textContent = `${opt.origin} ➜ ${opt.destination}`;
            
            item.appendChild(codeEl);
            item.appendChild(stopsEl);
            
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                this.selectValue(opt.value);
                this.closeDropdown();
            });
            
            this.resultsList.appendChild(item);
            this.itemNodes.push(item);
        });
        
        this.syncSelected();
        if (this.isOpen && this.searchInput.value) {
            this.filterAndSort(this.searchInput.value);
        }
    }
    
    escapeHTML(str) {
        return (str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
    
    syncSelected() {
        const val = this.selectElement.value;
        const matched = this.options.find(opt => opt.value === val);
        
        if (matched) {
            this.selectedLabel.innerHTML = `
                <div class="text-start">
                    <div class="tp-route-selector-item-code m-0">🚌 ${this.escapeHTML(matched.code)}</div>
                    <div class="tp-route-selector-item-stops text-white-50 small mt-0.5" style="font-size: 0.8rem;">${this.escapeHTML(matched.origin)} ➜ ${this.escapeHTML(matched.destination)}</div>
                </div>
            `;
        } else {
            this.selectedLabel.textContent = '— Select Route —';
        }
        
        this.itemNodes.forEach(node => {
            if (node.dataset.value === val) {
                node.classList.add('selected');
            } else {
                node.classList.remove('selected');
            }
        });
    }
    
    selectValue(val) {
        this.selectElement.value = val;
        // Dispatch change event to trigger existing update handlers
        this.selectElement.dispatchEvent(new Event('change', { bubbles: true }));
        this.syncSelected();
    }
    
    openDropdown() {
        if (this.isOpen) return;
        this.isOpen = true;
        this.dropdown.classList.remove('d-none');
        this.trigger.classList.add('active');
        this.searchInput.value = '';
        this.searchInput.focus();
        this.filterAndSort('');
        this.highlightedIndex = -1;
        this.scrollToSelected();
    }
    
    closeDropdown() {
        if (!this.isOpen) return;
        this.isOpen = false;
        this.dropdown.classList.add('d-none');
        this.trigger.classList.remove('active');
        this.trigger.focus();
    }
    
    scrollToSelected() {
        const selected = this.resultsList.querySelector('.tp-route-selector-item.selected');
        if (selected) {
            this.resultsList.scrollTop = selected.offsetTop - 40;
        } else {
            this.resultsList.scrollTop = 0;
        }
    }
    
    filterAndSort(searchQuery) {
        const q = searchQuery.toLowerCase().trim();
        
        if (!q) {
            // Show all in pre-rendered order
            this.itemNodes.forEach(node => {
                node.classList.remove('d-none');
                node.classList.remove('highlighted');
                this.resultsList.appendChild(node);
            });
            // Clear any no results message
            const noResultsMsg = this.resultsList.querySelector('.tp-route-selector-no-results-message');
            if (noResultsMsg) noResultsMsg.remove();
            return;
        }
        
        const scored = [];
        this.options.forEach((opt, index) => {
            const node = this.itemNodes[index];
            node.classList.remove('highlighted');
            
            const code = opt.code.toLowerCase();
            const origin = opt.origin.toLowerCase();
            const dest = opt.destination.toLowerCase();
            const name = opt.name.toLowerCase();
            
            let score = -1;
            
            if (code === q) {
                score = 0; // Exact code match
            } else if (code.startsWith(q)) {
                score = 1; // Code starts with query
            } else if (origin.startsWith(q)) {
                score = 2; // Source starts with query
            } else if (dest.startsWith(q)) {
                score = 3; // Destination starts with query
            } else if (code.includes(q)) {
                score = 4; // Code contains query
            } else if (origin.includes(q)) {
                score = 5; // Source contains query
            } else if (dest.includes(q)) {
                score = 6; // Destination contains query
            } else if (name.includes(q)) {
                score = 7; // Name contains query
            } else {
                const words = q.split(/\s+/);
                if (words.length > 1) {
                    const combined = `${code} ${name} ${origin} ${dest}`;
                    const allWordsMatch = words.every(word => combined.includes(word));
                    if (allWordsMatch) {
                        score = 8; // Partial multi-word match
                    }
                }
            }
            
            if (score !== -1) {
                scored.push({ node, score });
            } else {
                node.classList.add('d-none');
            }
        });
        
        // Sort matches by relevance score
        scored.sort((a, b) => a.score - b.score);
        
        // Remove old no results message if exists
        const oldMsg = this.resultsList.querySelector('.tp-route-selector-no-results-message');
        if (oldMsg) oldMsg.remove();
        
        if (scored.length === 0) {
            const noResultsMsg = document.createElement('div');
            noResultsMsg.className = 'tp-route-selector-no-results tp-route-selector-no-results-message';
            noResultsMsg.textContent = 'No matching routes found';
            this.resultsList.appendChild(noResultsMsg);
        } else {
            scored.forEach(item => {
                item.node.classList.remove('d-none');
                this.resultsList.appendChild(item.node); // dynamically reorders without re-creation
            });
        }
        
        this.highlightedIndex = -1;
    }
    
    setupEvents() {
        // Toggle trigger
        this.trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            if (this.isOpen) {
                this.closeDropdown();
            } else {
                this.openDropdown();
            }
        });
        
        // Close on trigger space/enter
        this.trigger.addEventListener('keydown', (e) => {
            if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                this.openDropdown();
            }
        });
        
        // Input filter
        this.searchInput.addEventListener('input', (e) => {
            this.filterAndSort(e.target.value);
        });
        
        // Click outside to close
        document.addEventListener('click', (e) => {
            if (!this.container.contains(e.target)) {
                this.closeDropdown();
            }
        });
        
        // Keyboard navigation
        this.container.addEventListener('keydown', (e) => {
            if (!this.isOpen) return;
            
            const visibleNodes = Array.from(this.resultsList.querySelectorAll('.tp-route-selector-item:not(.d-none)'));
            if (visibleNodes.length === 0) return;
            
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                this.highlightedIndex = (this.highlightedIndex + 1) % visibleNodes.length;
                this.updateHighlighted(visibleNodes);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                this.highlightedIndex = (this.highlightedIndex - 1 + visibleNodes.length) % visibleNodes.length;
                this.updateHighlighted(visibleNodes);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (this.highlightedIndex >= 0 && this.highlightedIndex < visibleNodes.length) {
                    const selectedNode = visibleNodes[this.highlightedIndex];
                    this.selectValue(selectedNode.dataset.value);
                    this.closeDropdown();
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                this.closeDropdown();
            }
        });
    }
    
    updateHighlighted(visibleNodes) {
        visibleNodes.forEach((node, idx) => {
            if (idx === this.highlightedIndex) {
                node.classList.add('highlighted');
                // Ensure scrolled into view
                const containerTop = this.resultsList.scrollTop;
                const containerBottom = containerTop + this.resultsList.clientHeight;
                const elemTop = node.offsetTop;
                const elemBottom = elemTop + node.clientHeight;
                
                if (elemTop < containerTop) {
                    this.resultsList.scrollTop = elemTop;
                } else if (elemBottom > containerBottom) {
                    this.resultsList.scrollTop = elemBottom - this.resultsList.clientHeight;
                }
            } else {
                node.classList.remove('highlighted');
            }
        });
    }
}

// Auto-initialize component on page load
document.addEventListener('DOMContentLoaded', () => {
    function initSelectors() {
        const selectElements = document.querySelectorAll('select[name="existing_route_id"], select#complaint-route-id');
        selectElements.forEach(select => {
            if (!select.dataset.enhanced) {
                new TransPulseRouteSelector(select);
            }
        });
    }
    
    initSelectors();
    
    // Check again after dynamic overlays or Ajax inserts
    const bodyObserver = new MutationObserver(() => initSelectors());
    bodyObserver.observe(document.body, { childList: true, subtree: true });
});
