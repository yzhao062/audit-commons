/**
 * Audit Commons — Interactive Enhancements
 * Progressive enhancement for resource filtering, search, and accessible interactions.
 * All site content remains fully readable and navigable when JavaScript is disabled.
 */
(function () {
  'use strict';

  function initResourceDirectory() {
    var controls = document.getElementById('resource-controls');
    var cards = document.querySelectorAll('.resource-card');

    // If resource controls or cards are not present on this page, exit cleanly.
    if (!controls || cards.length === 0) {
      return;
    }

    var searchInput = document.getElementById('resource-search');
    var filterButtons = document.querySelectorAll('button[data-filter]');
    var tabList = document.querySelector('[role="tablist"]');
    var formatTabs = document.querySelectorAll('[role="tab"]');
    var panel = document.getElementById('resources-panel');
    var countEl = document.getElementById('resource-count');
    var noResultsEl = document.getElementById('no-results');

    var activeFormat = 'all';
    var activeCategory = 'all';
    var searchQuery = '';

    // Progressive disclosure: Reveal controls only after script initialization
    controls.hidden = false;
    controls.removeAttribute('hidden');
    controls.style.display = '';

    // Ensure empty state is initially hidden
    if (noResultsEl) {
      noResultsEl.hidden = true;
      noResultsEl.style.display = 'none';
    }

    function getValidFormats() {
      var formats = { 'all': true };
      formatTabs.forEach(function (tab) {
        var fmt = (tab.getAttribute('data-format') || '').trim().toLowerCase();
        if (fmt) {
          formats[fmt] = true;
        }
      });
      return formats;
    }

    function getValidCategories() {
      var categories = { 'all': true };
      filterButtons.forEach(function (btn) {
        var cat = (btn.getAttribute('data-filter') || '').trim().toLowerCase();
        if (cat) {
          categories[cat] = true;
        }
      });
      return categories;
    }

    function readStateFromUrl() {
      var nextFormat = 'all';
      var nextCategory = 'all';
      var nextQuery = '';

      try {
        var params = new URLSearchParams(window.location.search);
        var hash = window.location.hash ? window.location.hash.substring(1) : '';
        var hashParams = new URLSearchParams(hash);

        var validFormats = getValidFormats();
        var validCategories = getValidCategories();

        var rawFmt = params.get('format') || hashParams.get('format');
        if (rawFmt) {
          var normFmt = rawFmt.trim().toLowerCase();
          if (validFormats[normFmt]) {
            nextFormat = normFmt;
          } else {
            nextFormat = 'all';
          }
        }

        var rawCat = params.get('category') || hashParams.get('category');
        if (rawCat) {
          var normCat = rawCat.trim().toLowerCase();
          if (validCategories[normCat]) {
            nextCategory = normCat;
          } else {
            nextCategory = 'all';
          }
        }

        var rawQ = params.get('q') || params.get('search') || hashParams.get('q');
        if (rawQ) {
          nextQuery = rawQ.trim();
        }
      } catch (err) {
        nextFormat = 'all';
        nextCategory = 'all';
        nextQuery = '';
      }

      activeFormat = nextFormat;
      activeCategory = nextCategory;
      searchQuery = nextQuery;

      if (searchInput) {
        searchInput.value = searchQuery;
      }
    }

    function updateUrlState() {
      try {
        var params = new URLSearchParams();
        if (activeFormat && activeFormat.toLowerCase() !== 'all') {
          params.set('format', activeFormat);
        }
        if (activeCategory && activeCategory.toLowerCase() !== 'all') {
          params.set('category', activeCategory);
        }
        if (searchQuery && searchQuery.trim()) {
          params.set('q', searchQuery.trim());
        }
        var qs = params.toString();
        var newUrl = window.location.pathname + (qs ? '?' + qs : '');
        if (window.location.pathname + window.location.search !== newUrl) {
          window.history.replaceState({ format: activeFormat, category: activeCategory, q: searchQuery }, '', newUrl);
        }
      } catch (err) {
        // Ignore in restricted test environments
      }
    }

    function syncTabAttributes() {
      var normFmt = (activeFormat || 'all').trim().toLowerCase();
      var activeTab = null;

      formatTabs.forEach(function (tab) {
        var tabFmt = (tab.getAttribute('data-format') || 'all').trim().toLowerCase();
        if (tabFmt === normFmt) {
          activeTab = tab;
        }
      });

      if (!activeTab) {
        activeTab = document.getElementById('tab-all') || formatTabs[0];
        activeFormat = 'all';
      }

      formatTabs.forEach(function (tab) {
        var isSelected = (tab === activeTab);
        tab.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        tab.setAttribute('tabindex', isSelected ? '0' : '-1');
        if (isSelected) {
          tab.classList.add('is-active');
        } else {
          tab.classList.remove('is-active');
        }
      });

      if (panel && activeTab) {
        panel.setAttribute('aria-labelledby', activeTab.id);
      }
    }

    function syncCategoryAttributes() {
      var normCat = (activeCategory || 'all').trim().toLowerCase();
      var activeBtn = null;

      filterButtons.forEach(function (btn) {
        var btnCat = (btn.getAttribute('data-filter') || 'all').trim().toLowerCase();
        if (btnCat === normCat) {
          activeBtn = btn;
        }
      });

      if (!activeBtn) {
        activeBtn = document.querySelector("button[data-filter='All'], button[data-filter='all']") || filterButtons[0];
        activeCategory = 'all';
      }

      filterButtons.forEach(function (btn) {
        var isSelected = (btn === activeBtn);
        btn.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        if (isSelected) {
          btn.classList.add('is-active');
        } else {
          btn.classList.remove('is-active');
        }
      });
    }

    function applyFilters(updateHistory) {
      // Update button visual/ARIA states first to guarantee normalized activeFormat and activeCategory
      syncTabAttributes();
      syncCategoryAttributes();

      var total = cards.length;
      var matches = 0;
      var query = searchQuery.trim().toLowerCase();
      var normCat = (activeCategory || 'all').trim().toLowerCase();
      var normFmt = (activeFormat || 'all').trim().toLowerCase();

      cards.forEach(function (card) {
        var cardFormats = (card.getAttribute('data-formats') || card.getAttribute('data-format') || 'collection').trim().toLowerCase().split(/\s+/);
        var cardCat = (card.getAttribute('data-category') || '').trim().toLowerCase();
        var cardSearch = (card.getAttribute('data-search') || '').toLowerCase();
        var cardText = (card.textContent || '').toLowerCase();

        var matchesFormat = (normFmt === 'all' || cardFormats.indexOf(normFmt) !== -1);
        var matchesCategory = (normCat === 'all' || cardCat === normCat);
        var matchesSearch = !query || (cardSearch.indexOf(query) !== -1) || (cardText.indexOf(query) !== -1);

        if (matchesFormat && matchesCategory && matchesSearch) {
          card.hidden = false;
          card.style.display = '';
          matches++;
        } else {
          card.hidden = true;
          card.style.display = 'none';
        }
      });

      // Update live status announcement for screen readers and visual counts
      if (countEl) {
        if (!query && normCat === 'all' && normFmt === 'all') {
          countEl.textContent = 'Showing all ' + total + ' resources';
        } else if (matches > 0) {
          countEl.textContent = 'Showing ' + matches + ' of ' + total + ' resources';
        } else {
          countEl.textContent = 'No matching resources found';
        }
      }

      // Toggle empty-state visibility
      if (noResultsEl) {
        if (matches === 0) {
          noResultsEl.hidden = false;
          noResultsEl.style.display = 'block';
        } else {
          noResultsEl.hidden = true;
          noResultsEl.style.display = 'none';
        }
      }

      if (updateHistory) {
        updateUrlState();
      }
    }

    function selectFormatTab(tabEl) {
      if (!tabEl) return;
      activeFormat = tabEl.getAttribute('data-format') || 'all';
      applyFilters(true);
    }

    function resetFilters() {
      activeFormat = 'all';
      activeCategory = 'all';
      searchQuery = '';
      if (searchInput) {
        searchInput.value = '';
      }
      applyFilters(true);
      if (searchInput) {
        searchInput.focus();
      }
    }

    // Bind format tabs click
    formatTabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        selectFormatTab(tab);
      });
    });

    // Keyboard navigation across format tabs (roving tabindex ARIA pattern)
    if (tabList) {
      var tabElements = Array.prototype.slice.call(formatTabs);
      tabList.addEventListener('keydown', function (e) {
        var currentTab = document.activeElement;
        var currentIndex = tabElements.indexOf(currentTab);
        if (currentIndex === -1) return;

        var nextIndex = -1;
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
          nextIndex = (currentIndex + 1) % tabElements.length;
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
          nextIndex = (currentIndex - 1 + tabElements.length) % tabElements.length;
        } else if (e.key === 'Home') {
          nextIndex = 0;
        } else if (e.key === 'End') {
          nextIndex = tabElements.length - 1;
        }

        if (nextIndex !== -1) {
          e.preventDefault();
          var targetTab = tabElements[nextIndex];
          targetTab.focus();
          selectFormatTab(targetTab);
        }
      });
    }

    // Bind category button clicks
    filterButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var val = btn.getAttribute('data-filter') || 'all';
        activeCategory = val;
        applyFilters(true);
      });
    });

    // Bind search input events
    if (searchInput) {
      searchInput.addEventListener('input', function (e) {
        searchQuery = e.target.value || '';
        applyFilters(true);
      });

      searchInput.addEventListener('search', function (e) {
        searchQuery = e.target.value || '';
        applyFilters(true);
      });

      searchInput.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
          searchInput.value = '';
          searchQuery = '';
          applyFilters(true);
        }
      });
    }

    // Bind reset buttons in empty state or controls
    var resetButtons = document.querySelectorAll('[data-action="reset"], #reset-filters');
    resetButtons.forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        resetFilters();
      });
    });

    // Listen to browser Back/Forward navigation
    window.addEventListener('popstate', function () {
      readStateFromUrl();
      applyFilters(false);
    });

    // Read initial deep-link state from URL and synchronize DOM
    readStateFromUrl();
    applyFilters(false);
  }

  // Enhanced code copying for practical worksheets with accessible status announcements
  function initCodeCopying() {
    var codeBlocks = document.querySelectorAll('pre');
    if (codeBlocks.length === 0) {
      return;
    }

    // Accessible live region for screen-reader clipboard announcements
    var liveRegion = document.getElementById('clipboard-live-status');
    if (!liveRegion) {
      liveRegion = document.createElement('div');
      liveRegion.id = 'clipboard-live-status';
      liveRegion.className = 'sr-only';
      liveRegion.setAttribute('aria-live', 'polite');
      liveRegion.setAttribute('aria-atomic', 'true');
      document.body.appendChild(liveRegion);
    }

    function announceStatus(msg) {
      if (liveRegion) {
        liveRegion.textContent = msg;
      }
    }

    function handleCopySuccess(button) {
      button.textContent = 'Copied!';
      button.classList.add('is-copied');
      button.setAttribute('aria-label', 'Code worksheet copied to clipboard');
      announceStatus('Worksheet copied to clipboard');
      setTimeout(function () {
        button.textContent = 'Copy';
        button.classList.remove('is-copied');
        button.setAttribute('aria-label', 'Copy code worksheet to clipboard');
      }, 2000);
    }

    function handleCopyFailure(button) {
      button.textContent = 'Copy failed';
      button.classList.remove('is-copied');
      button.setAttribute('aria-label', 'Copying failed, select text manually');
      announceStatus('Copy to clipboard failed. Please select text manually.');
      setTimeout(function () {
        button.textContent = 'Copy';
        button.setAttribute('aria-label', 'Copy code worksheet to clipboard');
      }, 2500);
    }

    function fallbackCopy(text, button) {
      var success = false;
      var textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.top = '-9999px';
      textarea.style.left = '-9999px';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      try {
        success = (document.execCommand('copy') === true);
      } catch (err) {
        success = false;
      }
      document.body.removeChild(textarea);

      if (success) {
        handleCopySuccess(button);
      } else {
        handleCopyFailure(button);
      }
    }

    codeBlocks.forEach(function (pre) {
      if (pre.querySelector('.copy-button')) {
        return;
      }
      var code = pre.querySelector('code');
      if (!code) {
        return;
      }
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'copy-button';
      button.setAttribute('aria-label', 'Copy code worksheet to clipboard');
      button.textContent = 'Copy';

      button.addEventListener('click', function () {
        var text = code.innerText || code.textContent || '';
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () {
            handleCopySuccess(button);
          }).catch(function () {
            fallbackCopy(text, button);
          });
        } else {
          fallbackCopy(text, button);
        }
      });

      pre.style.position = 'relative';
      pre.classList.add('has-copy-button');
      pre.appendChild(button);
    });
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initResourceDirectory();
      initCodeCopying();
    });
  } else {
    initResourceDirectory();
    initCodeCopying();
  }
})();
