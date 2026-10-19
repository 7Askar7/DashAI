import createDOMPurify from 'dompurify';
import { Marked } from 'marked';

const escapeHtml = (value: string) => value.replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]!));

function safeHref(href: string): string {
  // Relative paths and fragments stay text until document-local targets exist; do not alter app history.
  try {
    const url = new URL(href);
    return ['http:', 'https:', 'mailto:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}

// Own instances keep Mermaid's parser settings and sanitizer hooks out of document rendering.
const purifier = createDOMPurify(window);
const parser = new Marked({
  gfm: true,
  breaks: false,
  renderer: {
    html({ text }) { return escapeHtml(text); },
    image({ tokens }) { return tokens.length ? this.parser.parseInline(tokens) : 'Изображение'; },
    checkbox({ checked }) { return checked ? '[x] ' : '[ ] '; },
    heading({ depth, tokens }) {
      const level = Math.min(6, depth + 2);
      return `<h${level}>${this.parser.parseInline(tokens)}</h${level}>\n`;
    },
    link({ href, title, tokens }) {
      const label = this.parser.parseInline(tokens);
      const safe = safeHref(href);
      if (!safe) return label;
      return `<a href="${escapeHtml(safe)}"${title ? ` title="${escapeHtml(title)}"` : ''}${/^https?:/.test(safe) ? ' target="_blank" rel="noopener noreferrer"' : ''}>${label}</a>`;
    },
  },
});

// Raw HTML stays visible text; images never become fetching elements. Sanitize before either HTML sink.
export function renderMarkdown(text: string): string {
  return purifier.sanitize(parser.parse(text, { async: false }), {
    ALLOWED_TAGS: ['h3', 'h4', 'h5', 'h6', 'p', 'br', 'hr', 'blockquote', 'ul', 'ol', 'li', 'pre', 'code',
      'strong', 'em', 'del', 'a', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
    ALLOWED_ATTR: ['href', 'title', 'target', 'rel', 'start', 'align', 'class'],
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
  });
}
