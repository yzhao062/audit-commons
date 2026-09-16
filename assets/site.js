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
    var countEl = document.getElementById('resource-count');
    var noResultsEl = document.getElementById('no-results');

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

    function applyFilters() {
      var total = cards.length;
      var matches = 0;
      var query = searchQuery.trim().toLowerCase();
      var normalizedFilter = activeCategory.trim().toLowerCase();

      cards.forEach(function (card) {
        var cardCat = (card.getAttribute('data-category') || '').trim().toLowerCase();
        var cardSearch = (card.getAttribute('data-search') || '').toLowerCase();
        var cardText = (card.textContent || '').toLowerCase();

        var matchesCategory = (normalizedFilter === 'all' || cardCat === normalizedFilter);
        var matchesSearch = !query || (cardSearch.indexOf(query) !== -1) || (cardText.indexOf(query) !== -1);

        if (matchesCategory && matchesSearch) {
          card.hidden = false;
          card.style.display = '';
          matches++;
        } else {
          card.hidden = true;
          card.style.display = 'none';
        }
      });

      // Update filter button states and aria-pressed attributes
      filterButtons.forEach(function (btn) {
        var btnCat = (btn.getAttribute('data-filter') || 'all').trim().toLowerCase();
        var isSelected = (btnCat === normalizedFilter);
        btn.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        if (isSelected) {
          btn.classList.add('is-active');
        } else {
          btn.classList.remove('is-active');
        }
      });

      // Update live status announcement for screen readers and visual counts
      if (countEl) {
        if (!query && normalizedFilter === 'all') {
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
    }

    function resetFilters() {
      activeCategory = 'all';
      searchQuery = '';
      if (searchInput) {
        searchInput.value = '';
      }
      applyFilters();
      if (searchInput) {
        searchInput.focus();
      }
    }

    // Bind category button clicks
    filterButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var val = btn.getAttribute('data-filter') || 'all';
        activeCategory = val;
        applyFilters();
      });
    });

    // Bind search input events
    if (searchInput) {
      searchInput.addEventListener('input', function (e) {
        searchQuery = e.target.value || '';
        applyFilters();
      });

      searchInput.addEventListener('search', function (e) {
        searchQuery = e.target.value || '';
        applyFilters();
      });

      searchInput.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
          searchInput.value = '';
          searchQuery = '';
          applyFilters();
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

    // Run initial filter to synchronize DOM state
    applyFilters();
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
