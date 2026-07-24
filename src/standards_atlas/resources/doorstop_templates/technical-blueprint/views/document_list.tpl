% rebase('base.tpl', stylesheet='doorstop.css')
<div class="atlas-index-page">
  <header class="atlas-index-hero">
    <p class="atlas-eyebrow">Standards Atlas publication</p>
    <h1>Documents</h1>
    <p>Select a document hierarchy to open its published contents.</p>
  </header>
  <main class="atlas-card-grid">
    % for prefix in prefixes:
    <a class="atlas-document-card" href="{{prefix}}">
      <span class="atlas-card-mark">§</span>
      <strong>{{prefix}}</strong>
      <span>Open document</span>
    </a>
    % end
  </main>
</div>
