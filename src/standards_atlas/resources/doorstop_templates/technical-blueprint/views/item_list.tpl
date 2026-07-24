% rebase('base.tpl', stylesheet='doorstop.css')
<div class="atlas-index-page">
  <header class="atlas-index-hero">
    <p class="atlas-eyebrow">Document items</p>
    <h1>{{prefix}}</h1>
    <p>Browse the published items in this document.</p>
  </header>
  <main class="atlas-card-grid atlas-item-grid">
    % for item in items:
    <a class="atlas-document-card" href="items/{{item}}">
      <span class="atlas-card-mark">#</span>
      <strong>{{item}}</strong>
      <span>Open item</span>
    </a>
    % end
  </main>
</div>
