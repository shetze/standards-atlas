(() => {
  const source = document.getElementById('atlasTocSource');
  const target = document.getElementById('atlasToc');
  if (source && target) {
    const entries = [...source.querySelectorAll(':scope > li')].map((li) => ({
      depth: Number(li.dataset.depth || 0),
      uid: li.dataset.uid || '',
      href: li.querySelector('a')?.getAttribute('href') || '#',
      text: li.querySelector('a')?.textContent?.trim() || ''
    }));
    source.remove();

    const root = { children: [], depth: -1 };
    const stack = [root];
    entries.forEach((entry) => {
      const node = { ...entry, children: [] };
      while (stack.length > 1 && stack[stack.length - 1].depth >= entry.depth) stack.pop();
      stack[stack.length - 1].children.push(node);
      stack.push(node);
    });

    const renderNodes = (nodes, level = 0) => {
      const ul = document.createElement('ul');
      ul.className = `atlas-toc-level atlas-toc-level-${level}`;
      nodes.forEach((node) => {
        const li = document.createElement('li');
        li.className = 'atlas-toc-node';
        li.dataset.search = `${node.text} ${node.uid}`.toLowerCase();
        const row = document.createElement('div');
        row.className = 'atlas-toc-row';
        if (node.children.length) {
          const toggle = document.createElement('button');
          toggle.type = 'button';
          toggle.className = 'atlas-tree-toggle';
          toggle.setAttribute('aria-expanded', level < 1 ? 'true' : 'false');
          toggle.innerHTML = '<span aria-hidden="true">›</span><span class="visually-hidden">Toggle subsection</span>';
          row.appendChild(toggle);
        } else {
          const spacer = document.createElement('span');
          spacer.className = 'atlas-tree-spacer';
          row.appendChild(spacer);
        }
        const link = document.createElement('a');
        link.href = node.href;
        link.textContent = node.text || node.uid;
        link.title = node.uid;
        row.appendChild(link);
        li.appendChild(row);
        if (node.children.length) {
          const childList = renderNodes(node.children, level + 1);
          childList.hidden = level >= 1;
          li.appendChild(childList);
          row.querySelector('.atlas-tree-toggle').addEventListener('click', (event) => {
            const button = event.currentTarget;
            const expanded = button.getAttribute('aria-expanded') === 'true';
            button.setAttribute('aria-expanded', String(!expanded));
            childList.hidden = expanded;
          });
        }
        ul.appendChild(li);
      });
      return ul;
    };
    target.appendChild(renderNodes(root.children));

    const search = document.getElementById('atlasTocSearch');
    const noMatches = document.getElementById('atlasNoMatches');
    const filterTree = () => {
      const term = search.value.trim().toLowerCase();
      let visibleCount = 0;
      [...target.querySelectorAll('.atlas-toc-node')].reverse().forEach((node) => {
        const ownMatch = !term || node.dataset.search.includes(term);
        const childMatch = [...node.querySelectorAll(':scope > .atlas-toc-level > .atlas-toc-node')]
          .some((child) => !child.hidden);
        node.hidden = !(ownMatch || childMatch);
        if (!node.hidden) {
          visibleCount += 1;
          if (term) {
            const list = node.querySelector(':scope > .atlas-toc-level');
            const toggle = node.querySelector(':scope > .atlas-toc-row > .atlas-tree-toggle');
            if (list) list.hidden = false;
            if (toggle) toggle.setAttribute('aria-expanded', 'true');
          }
        }
      });
      noMatches.hidden = visibleCount !== 0;
    };
    search?.addEventListener('input', filterTree);

    const expandAll = document.getElementById('atlasExpandAll');
    expandAll?.addEventListener('click', () => {
      const buttons = [...target.querySelectorAll('.atlas-tree-toggle')];
      const shouldExpand = buttons.some((button) => button.getAttribute('aria-expanded') !== 'true');
      buttons.forEach((button) => button.setAttribute('aria-expanded', String(shouldExpand)));
      target.querySelectorAll('.atlas-toc-level').forEach((list) => { list.hidden = !shouldExpand; });
      expandAll.textContent = shouldExpand ? 'Collapse all' : 'Expand all';
    });

    const linksById = new Map([...target.querySelectorAll('a[href^="#"]')]
      .map((link) => [decodeURIComponent(link.hash.slice(1)), link]));
    const sections = [...linksById.keys()].map((id) => document.getElementById(id)).filter(Boolean);
    if ('IntersectionObserver' in window && sections.length) {
      const observer = new IntersectionObserver((observed) => {
        const visible = observed.filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (!visible) return;
        target.querySelectorAll('a.is-active').forEach((link) => link.classList.remove('is-active'));
        const active = linksById.get(visible.target.id);
        active?.classList.add('is-active');
      }, { rootMargin: '-12% 0px -75% 0px', threshold: [0, 1] });
      sections.forEach((section) => observer.observe(section));
    }
  }

  const sidebar = document.getElementById('atlasSidebar');
  const backdrop = document.getElementById('atlasBackdrop');
  const setSidebar = (open) => {
    sidebar?.classList.toggle('is-open', open);
    if (backdrop) backdrop.hidden = !open;
    document.body.classList.toggle('atlas-nav-open', open);
  };
  document.getElementById('atlasMenuButton')?.addEventListener('click', () => setSidebar(true));
  document.getElementById('atlasSidebarClose')?.addEventListener('click', () => setSidebar(false));
  backdrop?.addEventListener('click', () => setSidebar(false));
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') setSidebar(false); });
})();
