<?php
// Library file for AI System plugin

/**
 * Pure page-type matching logic, split out of before_footer() so it's
 * testable without a real $PAGE object. NOTE: this is substring
 * matching (strpos), not exact match -- e.g. "my-index-dashboard"
 * would also match "my-index". Keep that in mind if a future core
 * pagetype accidentally contains one of these substrings.
 */
function local_ai_system_is_page_allowed_pagetype(string $pagetype): bool {
    $allowed = ['site-index', 'my-index', 'course-index'];
    foreach ($allowed as $pattern) {
        if (strpos($pagetype, $pattern) !== false) {
            return true;
        }
    }
    return false;
}

function local_ai_system_before_footer() {
    global $PAGE;

    if (!local_ai_system_is_page_allowed_pagetype($PAGE->pagetype)) {
        return '';
    }

    $chaturl = new moodle_url('/local/ai_system/index.php', ['embed' => 1]);

    $html = '
    <style>
      #ai-fab {
        position: fixed;
        bottom: 80px;
        right: 32px;
        z-index: 9999;
        width: 56px;
        height: 56px;
        border-radius: 50%;
        background: #005a8e;
        color: #fff;
        border: none;
        cursor: pointer;
        box-shadow: 0 4px 16px rgba(0,0,0,0.22);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 22px;
        transition: background 0.2s, transform 0.2s;
      }
      #ai-fab:hover {
        background: #003f66;
        transform: scale(1.08);
      }

      /* Затемнение фона */
      #ai-fab-backdrop {
        display: none;
        position: fixed;
        inset: 0;
        z-index: 10000;
        background: rgba(0,0,0,0.35);
        transition: opacity 0.25s;
      }
      #ai-fab-backdrop.open {
        display: block;
      }

      /* Панель справа */
      #ai-fab-panel {
        position: fixed;
        top: 0;
        right: 0;
        height: 100vh;
        width: 75vw;
        max-width: 100vw;
        z-index: 10001;
        background: #fff;
        box-shadow: -4px 0 32px rgba(0,0,0,0.18);
        transform: translateX(100%);
        transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
        display: flex;
        flex-direction: column;
      }
      #ai-fab-panel.open {
        transform: translateX(0);
      }

      #ai-fab-panel iframe {
        width: 100%;
        height: 100%;
        border: none;
        flex: 1;
      }

      @media (max-width: 520px) {
        #ai-fab-panel {
          width: 100vw;
        }
      }
    </style>

    <button id="ai-fab" title="AI Assistant" aria-label="Open AI Chatbot">
      <i class="fa fa-comment"></i>
    </button>

    <div id="ai-fab-backdrop"></div>

    <div id="ai-fab-panel">
      <iframe id="ai-fab-iframe" src="" allowfullscreen></iframe>
    </div>

    <script>
      (function() {
        const btn      = document.getElementById("ai-fab");
        const backdrop = document.getElementById("ai-fab-backdrop");
        const panel    = document.getElementById("ai-fab-panel");
        const iframe   = document.getElementById("ai-fab-iframe");
        const chatUrl  = ' . json_encode($chaturl->out(false)) . ';

        let loaded = false;

        function open() {
          if (!loaded) {
            iframe.src = chatUrl;
            loaded = true;
          }
          panel.classList.add("open");
          backdrop.classList.add("open");
          btn.innerHTML = \'<i class="fa fa-times"></i>\';
        }

        function close() {
          panel.classList.remove("open");
          backdrop.classList.remove("open");
          btn.innerHTML = \'<i class="fa fa-comment"></i>\';
        }

        btn.addEventListener("click", function() {
          panel.classList.contains("open") ? close() : open();
        });

        backdrop.addEventListener("click", close);

        document.addEventListener("keydown", function(e) {
          if (e.key === "Escape") close();
        });
      })();
    </script>
    ';

    return $html;
}
