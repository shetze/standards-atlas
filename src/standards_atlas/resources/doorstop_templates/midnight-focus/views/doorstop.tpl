%setdefault('has_index', True)
%setdefault('has_matrix', True)
% rebase('base.tpl', stylesheet='doorstop.css')
% if is_doc:
%   tmpRef='../'
% else:
%   tmpRef=''
% end

<div class="atlas-shell">
  <aside class="atlas-sidebar" id="atlasSidebar" aria-label="Document navigation">
    <div class="atlas-brand">
      <img src="{{baseurl}}{{tmpRef}}template/logo-black-white.png" alt="Doorstop" class="atlas-logo" />
      <div class="atlas-brand-copy">
        <span class="atlas-kicker">Standards Atlas</span>
        <strong>{{doc_attributes["name"]}}</strong>
      </div>
      <button class="atlas-icon-button atlas-sidebar-close" id="atlasSidebarClose" type="button" aria-label="Close navigation">×</button>
    </div>

    <nav class="atlas-primary-nav" aria-label="Publication navigation">
      % if has_index:
      <a href="{{tmpRef}}index.html">Documents</a>
      % end
      % if has_matrix:
      <a href="{{tmpRef}}traceability.html">Traceability</a>
      % end
    </nav>

    % if toc:
    <div class="atlas-toc-heading">
      <span>Contents</span>
      <button type="button" id="atlasExpandAll" class="atlas-text-button">Expand all</button>
    </div>
    <label class="atlas-search">
      <span class="visually-hidden">Filter contents</span>
      <input id="atlasTocSearch" type="search" placeholder="Filter sections…" autocomplete="off" />
    </label>
    <div class="atlas-toc-scroll">
      <ul id="atlasTocSource" class="atlas-toc-source">
        % for item in toc:
        <li data-depth="{{item['depth']}}" data-uid="{{item['uid']}}">
          <a href="#{{item['uid']}}" title="{{item['uid']}}">{{item['text']}}</a>
        </li>
        % end
      </ul>
      <div id="atlasToc" class="atlas-toc-tree"></div>
      <p id="atlasNoMatches" class="atlas-no-matches" hidden>No matching sections.</p>
    </div>
    % end

    <footer class="atlas-sidebar-footer">
      <span>Reference</span><strong>{{doc_attributes["ref"]}}</strong>
      <span>Issue</span><strong>{{doc_attributes["major"]}}{{doc_attributes["minor"]}}</strong>
    </footer>
  </aside>

  <div class="atlas-content-column">
    <header class="atlas-topbar">
      <button class="atlas-icon-button atlas-menu-button" id="atlasMenuButton" type="button" aria-label="Open navigation">☰</button>
      <div class="atlas-topbar-title">
        <span>{{doc_attributes["name"]}}</span>
        <strong>{{!doc_attributes["title"]}}</strong>
      </div>
      <div class="atlas-meta">
        <span>By</span><strong>{{doc_attributes["by"]}}</strong>
      </div>
    </header>

    <main class="atlas-main" id="main-content">
      <article class="atlas-document">
        <div class="atlas-document-heading">
          <p class="atlas-eyebrow">Published specification</p>
          <h1>{{!doc_attributes["title"]}}</h1>
          <div class="atlas-document-facts">
            <span><b>Reference</b> {{doc_attributes["ref"]}}</span>
            <span><b>Issue</b> {{doc_attributes["major"]}}{{doc_attributes["minor"]}}</span>
            <span><b>Publisher</b> {{doc_attributes["by"]}}</span>
          </div>
        </div>
        <div class="atlas-document-body">
          {{!body}}
        </div>
      </article>
    </main>
  </div>
</div>
<div class="atlas-backdrop" id="atlasBackdrop" hidden></div>
<script src="{{baseurl}}{{tmpRef}}template/bootstrap.bundle.min.js"></script>
<script src="{{baseurl}}{{tmpRef}}template/doorstop.js"></script>
